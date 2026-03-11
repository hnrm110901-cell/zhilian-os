"""
API 计量计费 — Phase 4 Month 11

基于 api_usage_logs 表（z09）按月汇总 API 调用量，生成账单周期与发票。

Router prefix: /api/v1/billing
Endpoints:
  POST  /cycles/compute          — 计算某月账单（幂等，可重复执行）
  GET   /cycles                  — 列出开发者账单列表
  GET   /cycles/{cycle_id}       — 账单详情（含分级计费明细）
  POST  /cycles/{cycle_id}/finalize — 锁定账单（draft → finalized）
  POST  /cycles/{cycle_id}/invoice  — 生成发票（finalized → invoiced）
  GET   /invoices                — 发票列表（支持 developer_id / period / status 过滤）
  GET   /invoices/{invoice_id}   — 发票详情
  POST  /invoices/{invoice_id}/pay  — 标记已付款
  GET   /admin/summary           — 管理端计费汇总（各月总收入 / 开发者计费分布）

计费规则（FREE_QUOTA_MAP + PRICE_MAP）：
  free:       5,000 次免费 + 超量 0 元/千次（free 套餐不收费）
  basic:     50,000 次免费 + 超量 0.50 元/千次
  pro:      200,000 次免费 + 超量 0.30 元/千次
  enterprise: 1,000,000 次免费 + 超量 0.15 元/千次
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/billing", tags=["api_billing"])

# ── Pricing constants ─────────────────────────────────────────────────────────

# Free quota per month (calls)
FREE_QUOTA_MAP: Dict[str, int] = {
    "free":       5_000,
    "basic":     50_000,
    "pro":      200_000,
    "enterprise": 1_000_000,
}

# Price per 1000 overage calls in 分 (0 = free tier, no charge)
PRICE_PER_1K_FEN: Dict[str, int] = {
    "free":       0,
    "basic":     50,    # ¥0.50 / 千次
    "pro":       30,    # ¥0.30 / 千次
    "enterprise": 15,   # ¥0.15 / 千次
}

PERIOD_RE = re.compile(r'^\d{4}-(?:0[1-9]|1[0-2])$')

VALID_CYCLE_TRANSITIONS: Dict[str, set] = {
    "draft":      {"finalized"},
    "finalized":  {"invoiced"},
    "invoiced":   set(),
}

VALID_INVOICE_TRANSITIONS: Dict[str, set] = {
    "unpaid": {"paid", "void"},
    "paid":   set(),
    "void":   set(),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(row) -> Dict[str, Any]:
    return dict(row._mapping)


def _validate_period(period: str) -> None:
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail=f"period 格式必须为 YYYY-MM，得到: {period}")


def compute_billing(total_calls: int, tier: str) -> Dict[str, Any]:
    """
    Pure function: compute billing amounts for given calls and tier.
    Returns dict with free_quota, overage_calls, amount_fen, amount_yuan.
    """
    free_quota = FREE_QUOTA_MAP.get(tier, FREE_QUOTA_MAP["free"])
    overage = max(0, total_calls - free_quota)
    price_per_1k = PRICE_PER_1K_FEN.get(tier, 0)
    amount_fen = (overage * price_per_1k) // 1000
    return {
        "free_quota":    free_quota,
        "overage_calls": overage,
        "amount_fen":    amount_fen,
        "amount_yuan":   round(amount_fen / 100, 2),
    }


def make_invoice_no(developer_id: str, period: str) -> str:
    """Generate deterministic-ish invoice number."""
    short_id = developer_id[-6:].upper().replace("-", "")
    return f"INV-{period}-{short_id}"


def build_line_items(tier: str, total_calls: int, billing: Dict[str, Any]) -> List[Dict]:
    items = [
        {
            "description": f"API 调用（{tier} 套餐免费额度）",
            "quantity": min(total_calls, billing["free_quota"]),
            "unit_price_yuan": 0.0,
            "amount_yuan": 0.0,
        }
    ]
    if billing["overage_calls"] > 0:
        items.append({
            "description": f"超量 API 调用（{tier} 套餐 ¥{PRICE_PER_1K_FEN.get(tier,0)/100:.2f}/千次）",
            "quantity": billing["overage_calls"],
            "unit_price_yuan": round(PRICE_PER_1K_FEN.get(tier, 0) / 100 / 1000, 6),
            "amount_yuan": billing["amount_yuan"],
        })
    return items


# ── Request schemas ───────────────────────────────────────────────────────────

class ComputeCycleRequest(BaseModel):
    developer_id: str
    period:       str     # 'YYYY-MM'


class AdminSummaryRequest(BaseModel):
    months: Optional[int] = 6


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/cycles/compute", status_code=200)
async def compute_billing_cycle(
    req: ComputeCycleRequest,
    db:  AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    计算（或重新计算）某月的 API 账单。
    草稿状态可反复计算；finalized/invoiced 状态不可修改。
    """
    _validate_period(req.period)

    # Get developer + tier
    dev_row = await db.execute(
        text("SELECT id, tier FROM isv_developers WHERE id = :id AND status = 'active'"),
        {"id": req.developer_id},
    )
    dev = dev_row.fetchone()
    if not dev:
        raise HTTPException(status_code=404, detail="开发者不存在或未激活")
    tier = dev.tier or "free"

    # Check existing cycle — cannot recompute if finalized/invoiced
    existing_row = await db.execute(
        text(
            "SELECT * FROM api_billing_cycles "
            "WHERE developer_id = :did AND period = :p"
        ),
        {"did": req.developer_id, "p": req.period},
    )
    existing = existing_row.fetchone()
    if existing and _row(existing)["status"] in ("finalized", "invoiced"):
        raise HTTPException(
            status_code=409,
            detail=f"账单已{_row(existing)['status']}，不可重新计算",
        )

    # Count API calls for the period from api_usage_logs
    count_row = await db.execute(
        text(
            "SELECT COUNT(*) AS cnt FROM api_usage_logs "
            "WHERE developer_id = :did "
            "AND TO_CHAR(called_at, 'YYYY-MM') = :p"
        ),
        {"did": req.developer_id, "p": req.period},
    )
    total_calls = count_row.fetchone().cnt or 0

    billable_row = await db.execute(
        text(
            "SELECT COUNT(*) AS cnt FROM api_usage_logs "
            "WHERE developer_id = :did AND is_billable = true "
            "AND TO_CHAR(called_at, 'YYYY-MM') = :p"
        ),
        {"did": req.developer_id, "p": req.period},
    )
    billable_calls = billable_row.fetchone().cnt or 0

    billing = compute_billing(billable_calls, tier)

    cycle_id = str(uuid.uuid4()) if not existing else _row(existing)["id"]

    if existing:
        await db.execute(
            text(
                "UPDATE api_billing_cycles SET "
                "total_calls = :tc, billable_calls = :bc, free_quota = :fq, "
                "overage_calls = :oc, amount_fen = :af, amount_yuan = :ay, "
                "updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "tc": total_calls,
                "bc": billable_calls,
                "fq": billing["free_quota"],
                "oc": billing["overage_calls"],
                "af": billing["amount_fen"],
                "ay": billing["amount_yuan"],
                "id": cycle_id,
            },
        )
    else:
        await db.execute(
            text(
                "INSERT INTO api_billing_cycles "
                "(id, developer_id, period, total_calls, billable_calls, "
                "free_quota, overage_calls, amount_fen, amount_yuan) "
                "VALUES (:id, :did, :p, :tc, :bc, :fq, :oc, :af, :ay)"
            ),
            {
                "id": cycle_id,
                "did": req.developer_id,
                "p": req.period,
                "tc": total_calls,
                "bc": billable_calls,
                "fq": billing["free_quota"],
                "oc": billing["overage_calls"],
                "af": billing["amount_fen"],
                "ay": billing["amount_yuan"],
            },
        )

    await db.commit()

    return {
        "cycle_id":      cycle_id,
        "developer_id":  req.developer_id,
        "period":        req.period,
        "tier":          tier,
        "total_calls":   total_calls,
        "billable_calls": billable_calls,
        **billing,
        "status":        "draft",
        "line_items":    build_line_items(tier, billable_calls, billing),
    }


@router.get("/cycles")
async def list_billing_cycles(
    developer_id: str = Query(...),
    db:           AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """列出开发者所有账单周期。"""
    rows = await db.execute(
        text(
            "SELECT * FROM api_billing_cycles "
            "WHERE developer_id = :did ORDER BY period DESC"
        ),
        {"did": developer_id},
    )
    cycles = [_row(r) for r in rows.fetchall()]
    # Add yuan conversion for amount_yuan (already stored)
    return {"developer_id": developer_id, "cycles": cycles, "total": len(cycles)}


@router.get("/cycles/{cycle_id}")
async def get_billing_cycle(
    cycle_id:    str,
    developer_id: str = Query(...),
    db:          AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """账单详情，含分级计费明细。"""
    row = await db.execute(
        text(
            "SELECT c.*, d.tier FROM api_billing_cycles c "
            "JOIN isv_developers d ON d.id = c.developer_id "
            "WHERE c.id = :id AND c.developer_id = :did"
        ),
        {"id": cycle_id, "did": developer_id},
    )
    cycle = row.fetchone()
    if not cycle:
        raise HTTPException(status_code=404, detail="账单不存在")
    data = _row(cycle)
    tier = data.pop("tier", "free")
    billing = {
        "free_quota":    data["free_quota"],
        "overage_calls": data["overage_calls"],
        "amount_fen":    data["amount_fen"],
        "amount_yuan":   float(data["amount_yuan"]),
    }
    data["line_items"] = build_line_items(tier, data["billable_calls"], billing)
    data["tier"] = tier
    return data


@router.post("/cycles/{cycle_id}/finalize")
async def finalize_billing_cycle(
    cycle_id:    str,
    developer_id: str = Query(...),
    db:          AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """锁定账单（draft → finalized），不可再修改计费数据。"""
    row = await db.execute(
        text(
            "SELECT * FROM api_billing_cycles "
            "WHERE id = :id AND developer_id = :did"
        ),
        {"id": cycle_id, "did": developer_id},
    )
    cycle = row.fetchone()
    if not cycle:
        raise HTTPException(status_code=404, detail="账单不存在")
    current = _row(cycle)["status"]
    if "finalized" not in VALID_CYCLE_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409, detail=f"当前状态 {current} 不可 finalize"
        )

    await db.execute(
        text(
            "UPDATE api_billing_cycles "
            "SET status = 'finalized', finalized_at = NOW(), updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": cycle_id},
    )
    await db.commit()
    return {"cycle_id": cycle_id, "status": "finalized"}


@router.post("/cycles/{cycle_id}/invoice")
async def generate_invoice(
    cycle_id:    str,
    developer_id: str = Query(...),
    db:          AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    生成发票（finalized → invoiced）。
    若已存在发票则返回现有发票。
    """
    row = await db.execute(
        text(
            "SELECT c.*, d.tier FROM api_billing_cycles c "
            "JOIN isv_developers d ON d.id = c.developer_id "
            "WHERE c.id = :id AND c.developer_id = :did"
        ),
        {"id": cycle_id, "did": developer_id},
    )
    cycle = row.fetchone()
    if not cycle:
        raise HTTPException(status_code=404, detail="账单不存在")
    data = _row(cycle)
    tier = data.pop("tier", "free")

    if data["status"] != "finalized":
        raise HTTPException(
            status_code=409,
            detail=f"账单必须为 finalized 状态才能开票，当前: {data['status']}",
        )

    # Idempotent: return existing invoice if already invoiced
    existing_inv = await db.execute(
        text("SELECT * FROM api_invoices WHERE cycle_id = :cid"),
        {"cid": cycle_id},
    )
    inv = existing_inv.fetchone()
    if inv:
        return _row(inv)

    billing = {
        "free_quota":    data["free_quota"],
        "overage_calls": data["overage_calls"],
        "amount_fen":    data["amount_fen"],
        "amount_yuan":   float(data["amount_yuan"]),
    }
    line_items = build_line_items(tier, data["billable_calls"], billing)

    inv_id = str(uuid.uuid4())
    inv_no = make_invoice_no(developer_id, data["period"])

    await db.execute(
        text(
            "INSERT INTO api_invoices "
            "(id, cycle_id, developer_id, period, invoice_no, amount_yuan, line_items) "
            "VALUES (:id, :cid, :did, :p, :no, :ay, :li)"
        ),
        {
            "id": inv_id,
            "cid": cycle_id,
            "did": developer_id,
            "p": data["period"],
            "no": inv_no,
            "ay": data["amount_yuan"],
            "li": json.dumps(line_items, ensure_ascii=False),
        },
    )
    # Mark cycle as invoiced
    await db.execute(
        text(
            "UPDATE api_billing_cycles "
            "SET status = 'invoiced', updated_at = NOW() WHERE id = :id"
        ),
        {"id": cycle_id},
    )
    await db.commit()

    return {
        "invoice_id":  inv_id,
        "cycle_id":    cycle_id,
        "developer_id": developer_id,
        "period":      data["period"],
        "invoice_no":  inv_no,
        "amount_yuan": float(data["amount_yuan"]),
        "line_items":  line_items,
        "status":      "unpaid",
    }


@router.get("/invoices")
async def list_invoices(
    developer_id: Optional[str] = Query(None),
    period:       Optional[str] = Query(None),
    status:       Optional[str] = Query(None),
    db:           AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """发票列表（支持多维过滤）。"""
    conditions = ["1=1"]
    params: Dict[str, Any] = {}
    if developer_id:
        conditions.append("developer_id = :did")
        params["did"] = developer_id
    if period:
        _validate_period(period)
        conditions.append("period = :p")
        params["p"] = period
    if status:
        conditions.append("status = :st")
        params["st"] = status

    rows = await db.execute(
        text(
            f"SELECT * FROM api_invoices WHERE {' AND '.join(conditions)} "
            "ORDER BY issued_at DESC"
        ),
        params,
    )
    invoices = []
    for r in rows.fetchall():
        inv = _row(r)
        if inv.get("line_items") and isinstance(inv["line_items"], str):
            try:
                inv["line_items"] = json.loads(inv["line_items"])
            except Exception as exc:
                logger.debug("billing.line_items_json_parse_failed", invoice_id=inv.get("id"), error=str(exc))
        inv["amount_yuan"] = float(inv["amount_yuan"])
        invoices.append(inv)
    return {"invoices": invoices, "total": len(invoices)}


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    db:         AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    row = await db.execute(
        text("SELECT * FROM api_invoices WHERE id = :id"),
        {"id": invoice_id},
    )
    inv = row.fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="发票不存在")
    data = _row(inv)
    if data.get("line_items") and isinstance(data["line_items"], str):
        try:
            data["line_items"] = json.loads(data["line_items"])
        except Exception as exc:
            logger.debug("billing.invoice_line_items_parse_failed", invoice_id=invoice_id, error=str(exc))
    data["amount_yuan"] = float(data["amount_yuan"])
    return data


@router.post("/invoices/{invoice_id}/pay")
async def mark_invoice_paid(
    invoice_id: str,
    db:         AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """标记发票已付款（unpaid → paid）。"""
    row = await db.execute(
        text("SELECT * FROM api_invoices WHERE id = :id"),
        {"id": invoice_id},
    )
    inv = row.fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="发票不存在")
    current = _row(inv)["status"]
    if "paid" not in VALID_INVOICE_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409, detail=f"当前状态 {current} 不可标记已付"
        )
    await db.execute(
        text(
            "UPDATE api_invoices "
            "SET status = 'paid', paid_at = NOW() WHERE id = :id"
        ),
        {"id": invoice_id},
    )
    await db.commit()
    return {"invoice_id": invoice_id, "status": "paid"}


@router.get("/admin/summary")
async def get_admin_billing_summary(
    months: int = Query(6, ge=1, le=24),
    db:     AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    管理端计费汇总：
    - 近 N 个月各月平台 API 收入
    - 各开发者账单分布（paid / unpaid / draft）
    - 欠款总额
    """
    rows = await db.execute(
        text(
            "SELECT period, SUM(amount_yuan) AS total_yuan, "
            "COUNT(*) AS dev_count, SUM(billable_calls) AS total_calls "
            "FROM api_billing_cycles "
            "WHERE status IN ('finalized', 'invoiced') "
            "GROUP BY period ORDER BY period ASC "
            "LIMIT :n"
        ),
        {"n": months},
    )
    monthly = []
    for r in rows.fetchall():
        monthly.append({
            "period":       r.period,
            "total_yuan":   float(r.total_yuan or 0),
            "dev_count":    r.dev_count,
            "total_calls":  r.total_calls or 0,
        })

    # Invoice status breakdown
    inv_rows = await db.execute(
        text(
            "SELECT status, COUNT(*) AS cnt, SUM(amount_yuan) AS total_yuan "
            "FROM api_invoices GROUP BY status"
        ),
        {},
    )
    invoice_summary: Dict[str, Any] = {}
    for r in inv_rows.fetchall():
        invoice_summary[r.status] = {
            "count":      r.cnt,
            "total_yuan": float(r.total_yuan or 0),
        }

    unpaid_yuan = invoice_summary.get("unpaid", {}).get("total_yuan", 0.0)

    return {
        "monthly_revenue": monthly,
        "invoice_summary": invoice_summary,
        "outstanding_yuan": unpaid_yuan,
        "months_shown":    months,
    }
