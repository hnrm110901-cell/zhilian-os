"""
结算风控 API — Phase 5 Month 3

Router prefix: /api/v1/settlement
Endpoints:
  POST /records                        — 录入平台结算记录
  GET  /records                        — 查询结算记录列表
  GET  /records/{id}                   — 查询单条结算详情
  POST /records/{id}/verify            — 人工核销结算记录
  POST /records/{id}/dispute           — 标记结算争议
  POST /records/{id}/items             — 添加结算明细行项
  GET  /records/{id}/items             — 查询结算明细
  POST /scan/overdue                   — 扫描逾期未结算（定时任务触发）
  GET  /risk-tasks                     — 查询风控待办任务列表
  POST /risk-tasks/{id}/resolve        — 解决风控任务
  GET  /summary/{store_id}             — 门店结算风控摘要
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.settlement_risk_service import ITEM_TYPE_LABELS, PLATFORM_LABELS, create_settlement_record, run_overdue_scan

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/settlement", tags=["settlement_risk"])

SUPPORTED_PLATFORMS = list(PLATFORM_LABELS.keys())
SUPPORTED_ITEM_TYPES = list(ITEM_TYPE_LABELS.keys())
VALID_RECORD_TRANSITIONS = {
    "pending": {"verified", "disputed"},
    "verified": {"disputed"},  # 已核销后可重新争议
    "disputed": {"pending", "verified"},
    "auto_closed": set(),
}
VALID_TASK_TRANSITIONS = {
    "open": {"in_progress", "resolved", "ignored"},
    "in_progress": {"resolved", "ignored"},
    "resolved": set(),
    "ignored": set(),
}


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


# ── Pydantic models ───────────────────────────────────────────────────────────


class SettlementRecordCreate(BaseModel):
    store_id: str
    brand_id: Optional[str] = None
    platform: str
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    settle_date: str
    cycle_start: Optional[str] = None
    cycle_end: Optional[str] = None
    settlement_no: Optional[str] = None
    gross_yuan: float = Field(..., ge=0)
    commission_yuan: float = Field(0.0, ge=0)
    refund_yuan: float = Field(0.0, ge=0)
    adjustment_yuan: float = 0.0

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        if v not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform '{v}'. Supported: {SUPPORTED_PLATFORMS}")
        return v

    @field_validator("settle_date", "cycle_start", "cycle_end")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Date must be YYYY-MM-DD, got '{v}'")
        return v


class SettlementItemCreate(BaseModel):
    item_type: str
    item_desc: Optional[str] = None
    amount_yuan: float
    ref_event_id: Optional[str] = None

    @field_validator("item_type")
    @classmethod
    def validate_item_type(cls, v: str) -> str:
        if v not in SUPPORTED_ITEM_TYPES:
            raise ValueError(f"Unsupported item_type '{v}'. Supported: {SUPPORTED_ITEM_TYPES}")
        return v


class VerifyRequest(BaseModel):
    note: Optional[str] = None


class DisputeRequest(BaseModel):
    reason: str


class ResolveTaskRequest(BaseModel):
    resolution_note: Optional[str] = None


# ── Settlement record endpoints ───────────────────────────────────────────────


@router.post("/records", status_code=201)
async def create_record(
    body: SettlementRecordCreate,
    db: AsyncSession = Depends(get_db),
):
    """录入平台结算记录（自动风险评估）"""
    result = await create_settlement_record(
        db=db,
        store_id=body.store_id,
        platform=body.platform,
        period=body.period,
        settle_date=body.settle_date,
        gross_yuan=body.gross_yuan,
        commission_yuan=body.commission_yuan,
        refund_yuan=body.refund_yuan,
        adjustment_yuan=body.adjustment_yuan,
        settlement_no=body.settlement_no,
        cycle_start=body.cycle_start,
        cycle_end=body.cycle_end,
        brand_id=body.brand_id,
    )
    return result


@router.get("/records")
async def list_records(
    store_id: str = Query(...),
    period: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """查询结算记录列表（支持多条件过滤）"""
    # Build with fixed branches (L011)
    base = "FROM settlement_records WHERE store_id = :sid"
    params: Dict[str, Any] = {"sid": store_id}

    if period:
        base += " AND period = :period"
        params["period"] = period
    if platform:
        base += " AND platform = :platform"
        params["platform"] = platform
    if risk_level:
        base += " AND risk_level = :risk"
        params["risk"] = risk_level
    if status:
        base += " AND status = :status"
        params["status"] = status

    count_q = text(f"SELECT COUNT(*) {base}")
    data_q = text(f"SELECT * {base} ORDER BY settle_date DESC, created_at DESC LIMIT :limit OFFSET :offset")
    params["limit"] = limit
    params["offset"] = offset

    total = (await db.execute(count_q, params)).scalar() or 0
    rows = (await db.execute(data_q, params)).fetchall()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": [_format_record(r) for r in rows],
    }


@router.get("/records/{record_id}")
async def get_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询单条结算详情"""
    row = (await db.execute(text("SELECT * FROM settlement_records WHERE id = :id"), {"id": record_id})).fetchone()
    if not row:
        raise HTTPException(404, f"Settlement record {record_id} not found")
    return _format_record(row)


@router.post("/records/{record_id}/verify")
async def verify_record(
    record_id: str,
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """人工核销结算记录（pending → verified）"""
    row = (await db.execute(text("SELECT id, status FROM settlement_records WHERE id = :id"), {"id": record_id})).fetchone()
    if not row:
        raise HTTPException(404, f"Record {record_id} not found")
    if "verified" not in VALID_RECORD_TRANSITIONS.get(row.status, set()):
        raise HTTPException(409, f"Cannot verify record in status '{row.status}'")

    await db.execute(
        text("""
        UPDATE settlement_records
        SET status = 'verified', verified_at = NOW(), notes = :note, updated_at = NOW()
        WHERE id = :id
    """),
        {"note": body.note, "id": record_id},
    )
    await db.commit()
    return {"record_id": record_id, "status": "verified"}


@router.post("/records/{record_id}/dispute")
async def dispute_record(
    record_id: str,
    body: DisputeRequest,
    db: AsyncSession = Depends(get_db),
):
    """标记结算争议（pending/verified → disputed）"""
    row = (await db.execute(text("SELECT id, status FROM settlement_records WHERE id = :id"), {"id": record_id})).fetchone()
    if not row:
        raise HTTPException(404, f"Record {record_id} not found")
    if "disputed" not in VALID_RECORD_TRANSITIONS.get(row.status, set()):
        raise HTTPException(409, f"Cannot dispute record in status '{row.status}'")

    await db.execute(
        text("""
        UPDATE settlement_records
        SET status = 'disputed', notes = :reason, updated_at = NOW()
        WHERE id = :id
    """),
        {"reason": body.reason, "id": record_id},
    )
    await db.commit()
    return {"record_id": record_id, "status": "disputed"}


@router.post("/records/{record_id}/items", status_code=201)
async def add_settlement_item(
    record_id: str,
    body: SettlementItemCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加结算明细行项"""
    row = (await db.execute(text("SELECT id, store_id FROM settlement_records WHERE id = :id"), {"id": record_id})).fetchone()
    if not row:
        raise HTTPException(404, f"Record {record_id} not found")

    iid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO settlement_items
          (id, settlement_id, store_id, item_type, item_desc,
           amount_yuan, ref_event_id, reconciled, created_at)
        VALUES (:id, :sid, :store, :type, :desc, :amt, :ref, false, NOW())
    """),
        {
            "id": iid,
            "sid": record_id,
            "store": row.store_id,
            "type": body.item_type,
            "desc": body.item_desc,
            "amt": body.amount_yuan,
            "ref": body.ref_event_id,
        },
    )
    await db.commit()
    return {"item_id": iid, "settlement_id": record_id}


@router.get("/records/{record_id}/items")
async def list_settlement_items(
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询结算明细行项"""
    rows = (
        await db.execute(
            text("""
        SELECT * FROM settlement_items WHERE settlement_id = :sid
        ORDER BY created_at
    """),
            {"sid": record_id},
        )
    ).fetchall()
    return {
        "settlement_id": record_id,
        "total": len(rows),
        "items": [
            {
                "id": r.id,
                "item_type": r.item_type,
                "item_type_label": ITEM_TYPE_LABELS.get(r.item_type, r.item_type),
                "item_desc": r.item_desc,
                "amount_yuan": _safe_float(r.amount_yuan),
                "reconciled": r.reconciled,
                "ref_event_id": r.ref_event_id,
            }
            for r in rows
        ],
    }


# ── Scan endpoint ─────────────────────────────────────────────────────────────


@router.post("/scan/overdue")
async def scan_overdue(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """扫描逾期未结算记录并更新风险等级"""
    result = await run_overdue_scan(db, store_id)
    return result


# ── Risk task endpoints ───────────────────────────────────────────────────────


@router.get("/risk-tasks")
async def list_risk_tasks(
    store_id: str = Query(...),
    severity: Optional[str] = Query(None),
    risk_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """查询风控待办任务"""
    if severity and risk_type and status:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM risk_tasks
            WHERE store_id = :sid AND severity = :sev AND risk_type = :rt AND status = :st
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
            LIMIT :limit
        """),
                {"sid": store_id, "sev": severity, "rt": risk_type, "st": status, "limit": limit},
            )
        ).fetchall()
    elif severity and risk_type:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM risk_tasks
            WHERE store_id = :sid AND severity = :sev AND risk_type = :rt
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
            LIMIT :limit
        """),
                {"sid": store_id, "sev": severity, "rt": risk_type, "limit": limit},
            )
        ).fetchall()
    elif severity:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM risk_tasks
            WHERE store_id = :sid AND severity = :sev
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
            LIMIT :limit
        """),
                {"sid": store_id, "sev": severity, "limit": limit},
            )
        ).fetchall()
    elif status:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM risk_tasks
            WHERE store_id = :sid AND status = :st
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
            LIMIT :limit
        """),
                {"sid": store_id, "st": status, "limit": limit},
            )
        ).fetchall()
    else:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM risk_tasks
            WHERE store_id = :sid
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                     WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
            LIMIT :limit
        """),
                {"sid": store_id, "limit": limit},
            )
        ).fetchall()

    return {
        "total": len(rows),
        "tasks": [_format_task(r) for r in rows],
    }


@router.post("/risk-tasks/{task_id}/resolve")
async def resolve_risk_task(
    task_id: str,
    body: ResolveTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """解决风控任务（open/in_progress → resolved）"""
    row = (await db.execute(text("SELECT id, status FROM risk_tasks WHERE id = :id"), {"id": task_id})).fetchone()
    if not row:
        raise HTTPException(404, f"Risk task {task_id} not found")
    if "resolved" not in VALID_TASK_TRANSITIONS.get(row.status, set()):
        raise HTTPException(409, f"Cannot resolve task in status '{row.status}'")

    await db.execute(
        text("""
        UPDATE risk_tasks
        SET status = 'resolved', resolved_at = NOW(),
            resolution_note = :note, updated_at = NOW()
        WHERE id = :id
    """),
        {"note": body.resolution_note, "id": task_id},
    )
    await db.commit()
    return {"task_id": task_id, "status": "resolved"}


# ── Summary endpoint ──────────────────────────────────────────────────────────


@router.get("/summary/{store_id}")
async def get_settlement_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """门店结算风控摘要（本月结算汇总 + 开放风险任务数）"""
    # 结算汇总
    settle_row = (
        await db.execute(
            text("""
        SELECT COUNT(*)            AS total_records,
               SUM(gross_yuan)     AS total_gross,
               SUM(net_yuan)       AS total_net,
               SUM(commission_yuan) AS total_commission,
               SUM(refund_yuan)    AS total_refund,
               COUNT(CASE WHEN risk_level IN ('high','critical') THEN 1 END) AS high_risk_count,
               COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending_count
        FROM settlement_records
        WHERE store_id = :sid AND period = :period
    """),
            {"sid": store_id, "period": period},
        )
    ).fetchone()

    # 平台明细
    platform_rows = (
        await db.execute(
            text("""
        SELECT platform, SUM(net_yuan) AS net, COUNT(*) AS cnt
        FROM settlement_records
        WHERE store_id = :sid AND period = :period
        GROUP BY platform ORDER BY net DESC
    """),
            {"sid": store_id, "period": period},
        )
    ).fetchall()

    # 开放风险任务
    risk_row = (
        await db.execute(
            text("""
        SELECT COUNT(*) AS total,
               COUNT(CASE WHEN severity IN ('high','critical') THEN 1 END) AS high_count
        FROM risk_tasks
        WHERE store_id = :sid AND status = 'open'
    """),
            {"sid": store_id},
        )
    ).fetchone()

    return {
        "store_id": store_id,
        "period": period,
        "settlement": {
            "total_records": settle_row.total_records if settle_row else 0,
            "total_gross_yuan": _safe_float(settle_row.total_gross) if settle_row else 0.0,
            "total_net_yuan": _safe_float(settle_row.total_net) if settle_row else 0.0,
            "total_commission_yuan": _safe_float(settle_row.total_commission) if settle_row else 0.0,
            "total_refund_yuan": _safe_float(settle_row.total_refund) if settle_row else 0.0,
            "high_risk_count": settle_row.high_risk_count if settle_row else 0,
            "pending_count": settle_row.pending_count if settle_row else 0,
        },
        "by_platform": [
            {
                "platform": r.platform,
                "platform_label": PLATFORM_LABELS.get(r.platform, r.platform),
                "net_yuan": _safe_float(r.net),
                "record_count": r.cnt,
            }
            for r in platform_rows
        ],
        "risk_tasks": {
            "open_total": risk_row.total if risk_row else 0,
            "high_priority": risk_row.high_count if risk_row else 0,
        },
    }


# ── Formatters ────────────────────────────────────────────────────────────────


def _format_record(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "store_id": row.store_id,
        "platform": row.platform,
        "platform_label": PLATFORM_LABELS.get(row.platform, row.platform),
        "period": row.period,
        "settlement_no": row.settlement_no,
        "settle_date": str(row.settle_date),
        "cycle_start": str(row.cycle_start) if row.cycle_start else None,
        "cycle_end": str(row.cycle_end) if row.cycle_end else None,
        "gross_yuan": _safe_float(row.gross_yuan),
        "commission_yuan": _safe_float(row.commission_yuan),
        "refund_yuan": _safe_float(row.refund_yuan),
        "adjustment_yuan": _safe_float(row.adjustment_yuan),
        "net_yuan": _safe_float(row.net_yuan),
        "expected_yuan": _safe_float(row.expected_yuan),
        "deviation_yuan": _safe_float(row.deviation_yuan),
        "deviation_pct": _safe_float(row.deviation_pct),
        "risk_level": row.risk_level,
        "status": row.status,
    }


def _format_task(row: Any) -> Dict[str, Any]:
    related = []
    if row.related_event_ids:
        try:
            related = json.loads(row.related_event_ids)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": row.id,
        "store_id": row.store_id,
        "risk_type": row.risk_type,
        "severity": row.severity,
        "title": row.title,
        "description": row.description,
        "amount_yuan": _safe_float(row.amount_yuan),
        "status": row.status,
        "due_date": str(row.due_date) if row.due_date else None,
        "related_event_ids": related,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
