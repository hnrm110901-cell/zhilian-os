"""
预算管理服务 — Phase 5 Month 4

职责:
  - 创建/更新预算计划（draft → approved → active → closed FSM）
  - 预算 vs 实际偏差计算（对接 profit_attribution_results）
  - 预算计划列表与详情查询

FSM:
  draft  → approved
  approved → active | draft
  active → closed
  closed → (terminal)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_BUDGET_TRANSITIONS: Dict[str, set] = {
    "draft": {"approved"},
    "approved": {"active", "draft"},
    "active": {"closed"},
    "closed": set(),
}

BUDGET_CATEGORIES: List[str] = [
    "revenue",
    "food_cost",
    "labor_cost",
    "platform_commission",
    "waste",
    "other_expense",
    "tax",
]

# Map budget category → column in profit_attribution_results
CATEGORY_TO_ACTUAL_COL: Dict[str, str] = {
    "revenue": "net_revenue_yuan",
    "food_cost": "food_cost_yuan",
    "labor_cost": "labor_cost_yuan",
    "platform_commission": "platform_commission_yuan",
    "waste": "waste_cost_yuan",
    "other_expense": "other_expense_yuan",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute_variance(budget_yuan: float, actual_yuan: float) -> Dict[str, float]:
    """
    variance_yuan = actual − budget
    variance_pct  = variance_yuan / |budget| × 100  (0 when budget=0)
    """
    variance_yuan = round(actual_yuan - budget_yuan, 2)
    if budget_yuan != 0:
        variance_pct = round((variance_yuan / abs(budget_yuan)) * 100, 1)
    else:
        variance_pct = 0.0
    return {"variance_yuan": variance_yuan, "variance_pct": variance_pct}


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_or_update_budget_plan(
    db: AsyncSession,
    store_id: str,
    period: str,
    period_type: str,
    brand_id: Optional[str],
    total_revenue_budget: float,
    total_cost_budget: float,
    profit_budget: float,
    notes: Optional[str],
    line_items: List[Dict],
) -> Dict:
    """
    Upsert a budget plan for (store_id, period, period_type).
    Only draft plans can be updated; other statuses return an error.
    Line items are fully replaced on update.
    """
    existing = await db.execute(
        text("""
        SELECT id, status FROM budget_plans
        WHERE store_id = :sid AND period = :period AND period_type = :ptype
        LIMIT 1
    """),
        {"sid": store_id, "period": period, "ptype": period_type},
    )
    row = existing.fetchone()

    now = datetime.now(timezone.utc)

    if row:
        plan_id, current_status = row[0], row[1]
        if current_status != "draft":
            return {"error": f"Cannot edit plan in status '{current_status}'", "plan_id": plan_id}
        await db.execute(
            text("""
            UPDATE budget_plans
            SET brand_id              = :brand_id,
                total_revenue_budget  = :rev,
                total_cost_budget     = :cost,
                profit_budget         = :profit,
                notes                 = :notes,
                updated_at            = :now
            WHERE id = :pid
        """),
            {
                "brand_id": brand_id,
                "rev": total_revenue_budget,
                "cost": total_cost_budget,
                "profit": profit_budget,
                "notes": notes,
                "now": now,
                "pid": plan_id,
            },
        )
        # Full replace of line items
        await db.execute(
            text("DELETE FROM budget_line_items WHERE plan_id = :pid"),
            {"pid": plan_id},
        )
        action = "updated"
    else:
        plan_id = str(uuid.uuid4())
        await db.execute(
            text("""
            INSERT INTO budget_plans
                (id, store_id, brand_id, period, period_type, status,
                 total_revenue_budget, total_cost_budget, profit_budget,
                 notes, created_at, updated_at)
            VALUES
                (:id, :sid, :brand_id, :period, :ptype, 'draft',
                 :rev, :cost, :profit, :notes, :now, :now)
        """),
            {
                "id": plan_id,
                "sid": store_id,
                "brand_id": brand_id,
                "period": period,
                "ptype": period_type,
                "rev": total_revenue_budget,
                "cost": total_cost_budget,
                "profit": profit_budget,
                "notes": notes,
                "now": now,
            },
        )
        action = "created"

    for item in line_items:
        cat = item.get("category", "")
        if cat not in BUDGET_CATEGORIES:
            continue
        await db.execute(
            text("""
            INSERT INTO budget_line_items
                (id, plan_id, category, sub_category, budget_yuan, period, created_at)
            VALUES
                (:id, :pid, :cat, :subcat, :budget, :period, :now)
        """),
            {
                "id": str(uuid.uuid4()),
                "pid": plan_id,
                "cat": cat,
                "subcat": item.get("sub_category"),
                "budget": _safe_float(item.get("budget_yuan", 0)),
                "period": period,
                "now": now,
            },
        )

    await db.commit()
    return {"plan_id": plan_id, "status": "draft", "action": action}


async def get_budget_plans(
    db: AsyncSession,
    store_id: str,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict]:
    res = await db.execute(
        text("""
        SELECT id, store_id, period, period_type, status,
               total_revenue_budget, total_cost_budget, profit_budget,
               notes, created_at, updated_at, approved_at
        FROM budget_plans
        WHERE store_id = :sid
        ORDER BY period DESC, created_at DESC
        LIMIT :lim OFFSET :off
    """),
        {"sid": store_id, "lim": limit, "off": offset},
    )
    keys = [
        "id",
        "store_id",
        "period",
        "period_type",
        "status",
        "total_revenue_budget",
        "total_cost_budget",
        "profit_budget",
        "notes",
        "created_at",
        "updated_at",
        "approved_at",
    ]
    return [dict(zip(keys, r)) for r in res.fetchall()]


async def get_budget_plan_detail(db: AsyncSession, plan_id: str) -> Optional[Dict]:
    res = await db.execute(
        text("""
        SELECT id, store_id, period, period_type, status,
               total_revenue_budget, total_cost_budget, profit_budget,
               notes, created_at, updated_at, approved_at
        FROM budget_plans WHERE id = :pid
    """),
        {"pid": plan_id},
    )
    row = res.fetchone()
    if not row:
        return None
    keys = [
        "id",
        "store_id",
        "period",
        "period_type",
        "status",
        "total_revenue_budget",
        "total_cost_budget",
        "profit_budget",
        "notes",
        "created_at",
        "updated_at",
        "approved_at",
    ]
    plan = dict(zip(keys, row))

    li_res = await db.execute(
        text("""
        SELECT id, category, sub_category, budget_yuan
        FROM budget_line_items WHERE plan_id = :pid ORDER BY category
    """),
        {"pid": plan_id},
    )
    plan["line_items"] = [
        {"id": r[0], "category": r[1], "sub_category": r[2], "budget_yuan": _safe_float(r[3])} for r in li_res.fetchall()
    ]
    return plan


async def get_budget_variance(db: AsyncSession, plan_id: str) -> Optional[Dict]:
    """Join budget line items with actuals from profit_attribution_results."""
    plan = await get_budget_plan_detail(db, plan_id)
    if not plan:
        return None

    store_id = plan["store_id"]
    period = plan["period"]

    actuals_res = await db.execute(
        text("""
        SELECT net_revenue_yuan, food_cost_yuan, labor_cost_yuan,
               platform_commission_yuan, waste_cost_yuan, other_expense_yuan,
               total_cost_yuan, gross_profit_yuan, profit_margin_pct
        FROM profit_attribution_results
        WHERE store_id = :sid AND period = :period
        ORDER BY calc_date DESC LIMIT 1
    """),
        {"sid": store_id, "period": period},
    )
    actuals_row = actuals_res.fetchone()

    actuals: Dict[str, float] = {}
    profit_margin_pct = 0.0
    actual_profit = 0.0
    actual_revenue = 0.0
    if actuals_row:
        actuals = {
            "revenue": _safe_float(actuals_row[0]),
            "food_cost": _safe_float(actuals_row[1]),
            "labor_cost": _safe_float(actuals_row[2]),
            "platform_commission": _safe_float(actuals_row[3]),
            "waste": _safe_float(actuals_row[4]),
            "other_expense": _safe_float(actuals_row[5]),
        }
        actual_revenue = _safe_float(actuals_row[0])
        actual_profit = _safe_float(actuals_row[7])
        profit_margin_pct = _safe_float(actuals_row[8])

    variance_items = []
    for li in plan.get("line_items", []):
        cat = li["category"]
        budget_yuan = _safe_float(li["budget_yuan"])
        actual_yuan = actuals.get(cat, 0.0)
        v = compute_variance(budget_yuan, actual_yuan)
        variance_items.append(
            {
                "category": cat,
                "sub_category": li.get("sub_category"),
                "budget_yuan": budget_yuan,
                "actual_yuan": actual_yuan,
                "variance_yuan": v["variance_yuan"],
                "variance_pct": v["variance_pct"],
            }
        )

    rev_budget = _safe_float(plan["total_revenue_budget"])
    profit_budget = _safe_float(plan["profit_budget"])

    return {
        "plan_id": plan_id,
        "store_id": store_id,
        "period": period,
        "status": plan["status"],
        "summary": {
            "revenue_budget": rev_budget,
            "revenue_actual": actual_revenue,
            "revenue_variance": compute_variance(rev_budget, actual_revenue),
            "profit_budget": profit_budget,
            "profit_actual": actual_profit,
            "profit_variance": compute_variance(profit_budget, actual_profit),
            "profit_margin_pct": profit_margin_pct,
        },
        "line_items": variance_items,
    }


async def transition_budget_status(
    db: AsyncSession,
    plan_id: str,
    new_status: str,
) -> Dict:
    res = await db.execute(
        text("""
        SELECT id, status FROM budget_plans WHERE id = :pid
    """),
        {"pid": plan_id},
    )
    row = res.fetchone()
    if not row:
        return {"error": "Plan not found"}

    current = row[1]
    if new_status not in VALID_BUDGET_TRANSITIONS.get(current, set()):
        return {"error": f"Cannot transition from '{current}' to '{new_status}'"}

    now = datetime.now(timezone.utc)
    if new_status == "approved":
        await db.execute(
            text("""
            UPDATE budget_plans
            SET status = :new_status, updated_at = :now, approved_at = :now
            WHERE id = :pid
        """),
            {"new_status": new_status, "now": now, "pid": plan_id},
        )
    else:
        await db.execute(
            text("""
            UPDATE budget_plans
            SET status = :new_status, updated_at = :now
            WHERE id = :pid
        """),
            {"new_status": new_status, "now": now, "pid": plan_id},
        )

    await db.commit()
    return {"plan_id": plan_id, "old_status": current, "new_status": new_status}
