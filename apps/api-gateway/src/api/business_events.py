"""
经营事件中心 API — Phase 5 Month 1

标准化接收10种经营事件，驱动利润归因引擎。

Router prefix: /api/v1/events
Endpoints:
  POST /ingest                         — 批量注入经营事件（支持1-100条）
  GET  /stream                         — 事件流水查询（store + date range + type filter）
  GET  /types                          — 支持的事件类型列表
  GET  /stats                          — 事件统计摘要（store + period）
  POST /mapping-rules                  — 创建事件映射规则
  GET  /mapping-rules                  — 查询映射规则列表
  POST /{event_id}/reprocess           — 重新触发单条事件归因
  GET  /profit/attribution/{store_id}  — 利润归因查询（period 维度）
  POST /profit/compute/{store_id}      — 触发利润归因计算（幂等，今天覆盖）
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.profit_attribution_service import compute_profit_attribution

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["business_events"])

# ── 支持的事件类型 ────────────────────────────────────────────────────────────

SUPPORTED_EVENT_TYPES = [
    "sale",  # 销售收入
    "refund",  # 退款退单
    "purchase",  # 采购下单
    "receipt",  # 收货入库
    "waste",  # 库存损耗
    "invoice",  # 发票开具/接收
    "payment",  # 对外付款
    "collection",  # 平台收款/到账
    "expense",  # 费用报销
    "settlement",  # 平台结算
]

SOURCE_SYSTEMS = ["pos", "meituan", "eleme", "wechat_pay", "erp", "manual", "system"]

EVENT_TYPE_LABELS = {
    "sale": "销售收入",
    "refund": "退款退单",
    "purchase": "采购下单",
    "receipt": "收货入库",
    "waste": "库存损耗",
    "invoice": "发票",
    "payment": "对外付款",
    "collection": "平台收款",
    "expense": "费用报销",
    "settlement": "平台结算",
}

# 哪些事件类型直接影响利润归因
PROFIT_RELEVANT_TYPES = {"sale", "refund", "waste", "purchase", "receipt", "expense", "settlement"}


# ── Pydantic Models ───────────────────────────────────────────────────────────


class EventIngestItem(BaseModel):
    store_id: str
    brand_id: Optional[str] = None
    event_type: str
    event_subtype: Optional[str] = None
    source_system: str = "manual"
    source_event_id: Optional[str] = None
    amount_yuan: float = 0.0
    payload: Optional[Dict[str, Any]] = None
    event_date: str  # YYYY-MM-DD
    period: Optional[str] = None  # YYYY-MM, auto-derived if absent

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in SUPPORTED_EVENT_TYPES:
            raise ValueError(f"Unsupported event_type '{v}'. Supported: {SUPPORTED_EVENT_TYPES}")
        return v

    @field_validator("source_system")
    @classmethod
    def validate_source_system(cls, v: str) -> str:
        if v not in SOURCE_SYSTEMS:
            raise ValueError(f"Unsupported source_system '{v}'. Supported: {SOURCE_SYSTEMS}")
        return v

    @field_validator("event_date")
    @classmethod
    def validate_event_date(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"event_date must be ISO format YYYY-MM-DD, got '{v}'")
        return v


class EventIngestRequest(BaseModel):
    events: List[EventIngestItem] = Field(..., min_length=1, max_length=100)


class MappingRuleCreate(BaseModel):
    source_system: str
    source_event_type: str
    target_event_type: str
    target_subtype: Optional[str] = None
    transform_rules: Optional[Dict[str, Any]] = None
    priority: int = 100

    @field_validator("target_event_type")
    @classmethod
    def validate_target(cls, v: str) -> str:
        if v not in SUPPORTED_EVENT_TYPES:
            raise ValueError(f"target_event_type '{v}' not in supported types")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────


def _derive_period(event_date_str: str) -> str:
    """YYYY-MM-DD → YYYY-MM"""
    return event_date_str[:7]


def _yuan_to_fen(yuan: float) -> int:
    return round(yuan * 100)


def _float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _format_event(row: Any) -> Dict[str, Any]:
    payload_data = None
    if row.payload:
        try:
            payload_data = json.loads(row.payload)
        except (json.JSONDecodeError, TypeError):
            payload_data = None
    return {
        "id": row.id,
        "store_id": row.store_id,
        "brand_id": row.brand_id,
        "event_type": row.event_type,
        "event_type_label": EVENT_TYPE_LABELS.get(row.event_type, row.event_type),
        "event_subtype": row.event_subtype,
        "source_system": row.source_system,
        "source_event_id": row.source_event_id,
        "amount_yuan": _float(row.amount_yuan),
        "amount_fen": row.amount_fen,
        "payload": payload_data,
        "period": row.period,
        "event_date": str(row.event_date),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/types")
async def list_event_types():
    """支持的事件类型列表"""
    return {
        "event_types": [
            {
                "type": t,
                "label": EVENT_TYPE_LABELS[t],
                "profit_relevant": t in PROFIT_RELEVANT_TYPES,
            }
            for t in SUPPORTED_EVENT_TYPES
        ],
        "source_systems": SOURCE_SYSTEMS,
    }


@router.post("/ingest", status_code=201)
async def ingest_events(
    body: EventIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量注入经营事件（1-100条）。同一 source_event_id+source_system 幂等。"""
    inserted = []
    skipped = []

    for item in body.events:
        # 幂等检查：相同 source_system + source_event_id 只插入一次
        if item.source_event_id:
            check = await db.execute(
                text("""
                SELECT id FROM business_events
                WHERE source_system = :sys AND source_event_id = :sid
                LIMIT 1
            """),
                {"sys": item.source_system, "sid": item.source_event_id},
            )
            existing = check.fetchone()
            if existing:
                skipped.append({"source_event_id": item.source_event_id, "reason": "duplicate"})
                continue

        eid = str(uuid.uuid4())
        period = item.period or _derive_period(item.event_date)
        amount_fen = _yuan_to_fen(item.amount_yuan)

        await db.execute(
            text("""
            INSERT INTO business_events
              (id, store_id, brand_id, event_type, event_subtype, source_system,
               source_event_id, amount_fen, amount_yuan, payload, period,
               event_date, status, created_at, updated_at)
            VALUES
              (:id, :store_id, :brand_id, :event_type, :event_subtype, :source_system,
               :source_event_id, :amount_fen, :amount_yuan, :payload, :period,
               :event_date, 'raw', NOW(), NOW())
        """),
            {
                "id": eid,
                "store_id": item.store_id,
                "brand_id": item.brand_id,
                "event_type": item.event_type,
                "event_subtype": item.event_subtype,
                "source_system": item.source_system,
                "source_event_id": item.source_event_id,
                "amount_fen": amount_fen,
                "amount_yuan": item.amount_yuan,
                "payload": json.dumps(item.payload) if item.payload else None,
                "period": period,
                "event_date": item.event_date,
            },
        )
        inserted.append(eid)

    await db.commit()
    logger.info("events_ingested", inserted=len(inserted), skipped=len(skipped))
    return {
        "inserted": len(inserted),
        "skipped": len(skipped),
        "event_ids": inserted,
        "skip_details": skipped,
    }


@router.get("/stream")
async def get_event_stream(
    store_id: str = Query(...),
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """事件流水查询（store + date range + 可选type过滤）"""
    # Validate dates
    try:
        date.fromisoformat(date_from)
        date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(400, "date_from / date_to must be YYYY-MM-DD")

    if event_type and event_type not in SUPPORTED_EVENT_TYPES:
        raise HTTPException(400, f"Unknown event_type '{event_type}'")

    # Build query with fixed branches (L011: no f-string in text())
    if event_type and status:
        q_data = text("""
            SELECT * FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
              AND event_type = :etype
              AND status     = :status
            ORDER BY event_date DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        q_count = text("""
            SELECT COUNT(*) FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
              AND event_type = :etype
              AND status     = :status
        """)
    elif event_type:
        q_data = text("""
            SELECT * FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
              AND event_type = :etype
            ORDER BY event_date DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        q_count = text("""
            SELECT COUNT(*) FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
              AND event_type = :etype
        """)
    elif status:
        q_data = text("""
            SELECT * FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
              AND status = :status
            ORDER BY event_date DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        q_count = text("""
            SELECT COUNT(*) FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
              AND status = :status
        """)
    else:
        q_data = text("""
            SELECT * FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
            ORDER BY event_date DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        q_count = text("""
            SELECT COUNT(*) FROM business_events
            WHERE store_id = :store_id
              AND event_date BETWEEN :df AND :dt
        """)

    params = {
        "store_id": store_id,
        "df": date_from,
        "dt": date_to,
        "etype": event_type,
        "status": status,
        "limit": limit,
        "offset": offset,
    }
    rows = (await db.execute(q_data, params)).fetchall()
    total = (await db.execute(q_count, params)).scalar() or 0

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [_format_event(r) for r in rows],
    }


@router.get("/stats")
async def get_event_stats(
    store_id: str = Query(...),
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """事件统计摘要：各类型事件数量 + 金额汇总"""
    rows = (
        await db.execute(
            text("""
        SELECT
            event_type,
            COUNT(*)          AS event_count,
            SUM(amount_yuan)  AS total_yuan,
            MIN(event_date)   AS first_date,
            MAX(event_date)   AS last_date
        FROM business_events
        WHERE store_id = :store_id AND period = :period
        GROUP BY event_type
        ORDER BY event_type
    """),
            {"store_id": store_id, "period": period},
        )
    ).fetchall()

    by_type = {}
    for r in rows:
        by_type[r.event_type] = {
            "label": EVENT_TYPE_LABELS.get(r.event_type, r.event_type),
            "event_count": r.event_count,
            "total_yuan": _float(r.total_yuan),
            "first_date": str(r.first_date) if r.first_date else None,
            "last_date": str(r.last_date) if r.last_date else None,
        }

    total_count = sum(v["event_count"] for v in by_type.values())
    total_sale = by_type.get("sale", {}).get("total_yuan", 0.0)
    total_cost = sum(by_type.get(t, {}).get("total_yuan", 0.0) for t in ("purchase", "waste", "expense", "settlement"))

    return {
        "store_id": store_id,
        "period": period,
        "total_events": total_count,
        "by_type": by_type,
        "summary": {
            "total_sale_yuan": round(total_sale, 2),
            "total_cost_yuan": round(total_cost, 2),
            "estimated_profit_yuan": round(total_sale - total_cost, 2),
        },
    }


@router.post("/mapping-rules", status_code=201)
async def create_mapping_rule(
    body: MappingRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建或更新事件映射规则（source_system+source_event_type唯一）"""
    # 检查是否已存在
    existing = (
        await db.execute(
            text("""
        SELECT id FROM event_mapping_rules
        WHERE source_system = :sys AND source_event_type = :set
    """),
            {"sys": body.source_system, "set": body.source_event_type},
        )
    ).fetchone()

    if existing:
        await db.execute(
            text("""
            UPDATE event_mapping_rules
            SET target_event_type = :tet,
                target_subtype    = :ts,
                transform_rules   = :tr,
                priority          = :prio,
                is_active         = true
            WHERE source_system = :sys AND source_event_type = :set
        """),
            {
                "tet": body.target_event_type,
                "ts": body.target_subtype,
                "tr": json.dumps(body.transform_rules) if body.transform_rules else None,
                "prio": body.priority,
                "sys": body.source_system,
                "set": body.source_event_type,
            },
        )
        await db.commit()
        return {"action": "updated", "source_system": body.source_system, "source_event_type": body.source_event_type}

    rid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO event_mapping_rules
          (id, source_system, source_event_type, target_event_type,
           target_subtype, transform_rules, priority, is_active, created_at)
        VALUES
          (:id, :sys, :set, :tet, :ts, :tr, :prio, true, NOW())
    """),
        {
            "id": rid,
            "sys": body.source_system,
            "set": body.source_event_type,
            "tet": body.target_event_type,
            "ts": body.target_subtype,
            "tr": json.dumps(body.transform_rules) if body.transform_rules else None,
            "prio": body.priority,
        },
    )
    await db.commit()
    return {"action": "created", "id": rid, "source_system": body.source_system, "source_event_type": body.source_event_type}


@router.get("/mapping-rules")
async def list_mapping_rules(
    source_system: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """查询事件映射规则列表"""
    if source_system:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM event_mapping_rules
            WHERE source_system = :sys
            ORDER BY priority, source_event_type
        """),
                {"sys": source_system},
            )
        ).fetchall()
    else:
        rows = (
            await db.execute(
                text("""
            SELECT * FROM event_mapping_rules
            ORDER BY source_system, priority, source_event_type
        """),
                {},
            )
        ).fetchall()

    return {
        "total": len(rows),
        "rules": [
            {
                "id": r.id,
                "source_system": r.source_system,
                "source_event_type": r.source_event_type,
                "target_event_type": r.target_event_type,
                "target_subtype": r.target_subtype,
                "priority": r.priority,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@router.post("/{event_id}/reprocess")
async def reprocess_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """重新触发单条事件的利润归因（将状态重置为 raw）"""
    row = (
        await db.execute(
            text("""
        SELECT id, store_id, period, status FROM business_events WHERE id = :id
    """),
            {"id": event_id},
        )
    ).fetchone()

    if not row:
        raise HTTPException(404, f"Event {event_id} not found")

    await db.execute(
        text("""
        UPDATE business_events
        SET status = 'raw', attributed_at = NULL, updated_at = NOW()
        WHERE id = :id
    """),
        {"id": event_id},
    )
    await db.commit()

    return {"event_id": event_id, "store_id": row.store_id, "period": row.period, "queued": True}


@router.get("/profit/attribution/{store_id}")
async def get_profit_attribution(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """查询利润归因结果（先查缓存，无则实时计算）"""
    # 先查缓存
    today_str = date.today().isoformat()
    cached = (
        await db.execute(
            text("""
        SELECT * FROM profit_attribution_results
        WHERE store_id = :sid AND period = :period AND calc_date = :today
        ORDER BY created_at DESC LIMIT 1
    """),
            {"sid": store_id, "period": period, "today": today_str},
        )
    ).fetchone()

    if cached:
        return _format_attribution(cached)

    # 实时计算
    result = await compute_profit_attribution(db, store_id, period)
    return result


@router.post("/profit/compute/{store_id}")
async def compute_profit(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """触发利润归因计算（幂等，当日覆盖）"""
    result = await compute_profit_attribution(db, store_id, period, force=True)
    return {"computed": True, "store_id": store_id, "period": period, "result": result}


# ── Formatters ────────────────────────────────────────────────────────────────


def _format_attribution(row: Any) -> Dict[str, Any]:
    detail = None
    if row.attribution_detail:
        try:
            detail = json.loads(row.attribution_detail)
        except (json.JSONDecodeError, TypeError):
            detail = None
    return {
        "store_id": row.store_id,
        "period": row.period,
        "calc_date": str(row.calc_date),
        "revenue": {
            "gross_revenue_yuan": _float(row.gross_revenue_yuan),
            "refund_yuan": _float(row.refund_yuan),
            "net_revenue_yuan": _float(row.net_revenue_yuan),
        },
        "costs": {
            "food_cost_yuan": _float(row.food_cost_yuan),
            "waste_cost_yuan": _float(row.waste_cost_yuan),
            "platform_commission_yuan": _float(row.platform_commission_yuan),
            "labor_cost_yuan": _float(row.labor_cost_yuan),
            "other_expense_yuan": _float(row.other_expense_yuan),
            "total_cost_yuan": _float(row.total_cost_yuan),
        },
        "profit": {
            "gross_profit_yuan": _float(row.gross_profit_yuan),
            "profit_margin_pct": _float(row.profit_margin_pct),
        },
        "event_count": row.event_count,
        "attribution_detail": detail,
    }
