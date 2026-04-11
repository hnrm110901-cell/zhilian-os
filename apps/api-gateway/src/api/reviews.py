"""
复盘管理 API — 日/周/月/季经营复盘

端点：
  GET  /api/v1/reviews/{store_id}             — 复盘记录列表
  GET  /api/v1/reviews/{store_id}/latest       — 最新复盘报告
  GET  /api/v1/reviews/{store_id}/pnl          — 最新日度P&L（店长5个数字）
  GET  /api/v1/reviews/{store_id}/pnl/trend    — P&L趋势（近N天）
  GET  /api/v1/reviews/{store_id}/breakeven    — 盈亏平衡状态
  PATCH /api/v1/reviews/{review_id}/confirm    — 店长确认复盘
  POST /api/v1/reviews/{store_id}/trigger      — 手动触发复盘
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, validate_store_brand
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class ConfirmReviewRequest(BaseModel):
    manager_notes: Optional[str] = None
    action_items: Optional[List[Dict[str, Any]]] = None


class TriggerReviewRequest(BaseModel):
    review_type: str = "daily"
    target_date: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/reviews/{store_id}", summary="复盘记录列表", tags=["reviews"])
async def list_reviews(
    store_id: str,
    review_type: str = Query(default="daily", description="daily|weekly|monthly|quarterly"),
    limit: int = Query(default=30, le=90),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取门店复盘记录列表"""
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT id, review_type, period_start, period_end,
                   ai_summary, status, confirmed_by, confirmed_at, created_at
            FROM review_sessions
            WHERE store_id = :sid AND review_type = :rtype
            ORDER BY period_end DESC
            LIMIT :lim
        """),
        {"sid": store_id, "rtype": review_type, "lim": limit},
    )

    rows = []
    for r in result.mappings():
        row = dict(r)
        row["id"] = str(row["id"])
        if row.get("confirmed_by"):
            row["confirmed_by"] = str(row["confirmed_by"])
        rows.append(row)

    return {"store_id": store_id, "review_type": review_type, "reviews": rows}


@router.get("/reviews/{store_id}/latest", summary="最新复盘报告", tags=["reviews"])
async def latest_review(
    store_id: str,
    review_type: str = Query(default="daily"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取最新一期复盘报告（含AI摘要 + 异常 + 建议）"""
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT id, review_type, period_start, period_end,
                   ai_summary, benchmark_data, manager_notes, action_items,
                   status, confirmed_by, confirmed_at, created_at
            FROM review_sessions
            WHERE store_id = :sid AND review_type = :rtype
            ORDER BY period_end DESC
            LIMIT 1
        """),
        {"sid": store_id, "rtype": review_type},
    )

    row = result.mappings().first()
    if not row:
        return {"status": "no_data", "message": "暂无复盘记录"}

    data = dict(row)
    data["id"] = str(data["id"])
    if data.get("confirmed_by"):
        data["confirmed_by"] = str(data["confirmed_by"])

    return data


@router.get("/reviews/{store_id}/pnl", summary="最新日度P&L", tags=["reviews"])
async def latest_daily_pnl(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取最新日度P&L — 店长的5个数字（阿米巴简化版）

    返回：
      - today_revenue_yuan: 当日营收（元）
      - material_cost_ratio: 食材成本率(%)
      - labor_cost_ratio: 人力成本率(%)
      - mtd_profit_yuan: 月累计利润（元）
      - mtd_target_pct: 月目标达成率(%)
    """
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT
                period_date,
                total_revenue_fen,
                material_cost_ratio,
                labor_cost_ratio,
                gross_margin,
                operating_margin,
                operating_profit_fen,
                mtd_revenue_fen,
                mtd_profit_fen,
                mtd_target_pct,
                revenue_per_seat_fen,
                revenue_per_employee_fen
            FROM store_pnl
            WHERE store_id = :sid AND period_type = 'daily'
            ORDER BY period_date DESC
            LIMIT 1
        """),
        {"sid": store_id},
    )

    row = result.mappings().first()
    if not row:
        return {"status": "no_data", "message": "暂无P&L数据，请等待日度收盘"}

    return {
        "store_id": store_id,
        "date": str(row["period_date"]),
        "five_numbers": {
            "today_revenue_yuan": (row["total_revenue_fen"] or 0) / 100,
            "material_cost_ratio": float(row["material_cost_ratio"] or 0),
            "labor_cost_ratio": float(row["labor_cost_ratio"] or 0),
            "mtd_profit_yuan": (row["mtd_profit_fen"] or 0) / 100,
            "mtd_target_pct": float(row["mtd_target_pct"] or 0),
        },
        "detail": {
            "gross_margin": float(row["gross_margin"] or 0),
            "operating_margin": float(row["operating_margin"] or 0),
            "operating_profit_yuan": (row["operating_profit_fen"] or 0) / 100,
            "mtd_revenue_yuan": (row["mtd_revenue_fen"] or 0) / 100,
            "revenue_per_seat_yuan": (row["revenue_per_seat_fen"] or 0) / 100,
            "revenue_per_employee_yuan": (row["revenue_per_employee_fen"] or 0) / 100,
        },
    }


@router.get("/reviews/{store_id}/pnl/trend", summary="P&L趋势", tags=["reviews"])
async def pnl_trend(
    store_id: str,
    days: int = Query(default=7, le=90, description="查询天数"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取近N天的P&L趋势数据，用于图表展示"""
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT
                period_date,
                total_revenue_fen,
                material_cost_ratio,
                labor_cost_ratio,
                gross_margin,
                operating_profit_fen,
                mtd_target_pct
            FROM store_pnl
            WHERE store_id = :sid
              AND period_type = 'daily'
              AND period_date >= CURRENT_DATE - :days * INTERVAL '1 day'
            ORDER BY period_date ASC
        """),
        {"sid": store_id, "days": days},
    )

    trend = []
    for r in result.mappings():
        trend.append({
            "date": str(r["period_date"]),
            "revenue_yuan": (r["total_revenue_fen"] or 0) / 100,
            "material_cost_ratio": float(r["material_cost_ratio"] or 0),
            "labor_cost_ratio": float(r["labor_cost_ratio"] or 0),
            "gross_margin": float(r["gross_margin"] or 0),
            "operating_profit_yuan": (r["operating_profit_fen"] or 0) / 100,
            "mtd_target_pct": float(r["mtd_target_pct"] or 0),
        })

    return {"store_id": store_id, "days": days, "trend": trend}


@router.get("/reviews/{store_id}/breakeven", summary="盈亏平衡状态", tags=["reviews"])
async def breakeven_status(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当月盈亏平衡线状态

    返回：
      - breakeven_revenue_yuan: 保本营收线
      - actual_revenue_yuan: 当月实际营收
      - breakeven_reached: 是否已达保本线
      - store_model_score: 单店模型健康度(0-100)
    """
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT *
            FROM breakeven_tracker
            WHERE store_id = :sid
            ORDER BY calc_month DESC
            LIMIT 1
        """),
        {"sid": store_id},
    )

    row = result.mappings().first()
    if not row:
        return {"status": "no_data", "message": "暂无盈亏平衡数据"}

    return {
        "store_id": store_id,
        "calc_month": str(row["calc_month"]),
        "breakeven_revenue_yuan": (row["breakeven_revenue_fen"] or 0) / 100,
        "actual_revenue_yuan": (row["actual_revenue_fen"] or 0) / 100,
        "breakeven_reached": row["breakeven_reached"],
        "reached_date": str(row["reached_date"]) if row["reached_date"] else None,
        "breakeven_day": row["breakeven_day"],
        "store_model_score": float(row["store_model_score"]) if row["store_model_score"] else None,
        "score_details": row["score_details"],
        "fixed_cost_yuan": (row["fixed_cost_fen"] or 0) / 100,
        "variable_cost_ratio": float(row["variable_cost_ratio"] or 0),
    }


@router.patch("/reviews/{review_id}/confirm", summary="店长确认复盘", tags=["reviews"])
async def confirm_review(
    review_id: str,
    req: ConfirmReviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    店长确认复盘报告

    确认后复盘状态变为 confirmed，店长可补充笔记和行动项。
    行动项格式: [{"task": "联系新供应商", "owner": "张三", "due_date": "2026-04-15", "status": "pending"}]
    """
    # 归属校验：确认复盘记录属于当前用户品牌
    ownership = await db.execute(
        text("SELECT brand_id, store_id FROM review_sessions WHERE id = :rid::uuid"),
        {"rid": review_id},
    )
    own_row = ownership.mappings().first()
    if not own_row:
        raise HTTPException(status_code=404, detail="复盘记录不存在")
    if own_row["store_id"]:
        await validate_store_brand(own_row["store_id"], current_user)

    action_items_json = json.dumps(req.action_items or [], ensure_ascii=False)

    result = await db.execute(
        text("""
            UPDATE review_sessions
            SET status = 'confirmed',
                manager_notes = :notes,
                action_items = :actions::jsonb,
                confirmed_by = :uid::uuid,
                confirmed_at = NOW()
            WHERE id = :rid::uuid
            RETURNING id, status
        """),
        {
            "rid": review_id,
            "notes": req.manager_notes,
            "actions": action_items_json,
            "uid": str(current_user.id),
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="复盘记录不存在")

    await db.commit()

    logger.info("review_confirmed", review_id=review_id, user_id=str(current_user.id))

    return {"id": review_id, "status": "confirmed"}


@router.post("/reviews/{store_id}/trigger", summary="手动触发复盘", tags=["reviews"])
async def trigger_review(
    store_id: str,
    req: TriggerReviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发经营复盘（调用Chief Agent）

    当自动复盘未按时生成或需要即时分析时使用。
    """
    await validate_store_brand(store_id, current_user)

    # 获取brand_id
    store_result = await db.execute(
        text("SELECT brand_id FROM stores WHERE id = :sid"),
        {"sid": store_id},
    )
    store_row = store_result.mappings().first()
    if not store_row:
        raise HTTPException(status_code=404, detail="门店不存在")

    brand_id = store_row["brand_id"]
    target = date.fromisoformat(req.target_date) if req.target_date else date.today() - timedelta(days=1)

    try:
        from ..services.chief_agent_service import ChiefAgentService

        chief = ChiefAgentService()

        if req.review_type == "daily":
            result = await chief.daily_review(db, store_id, brand_id, target)
        elif req.review_type == "weekly":
            week_end = target
            result = await chief.weekly_review(db, store_id, brand_id, week_end)
        else:
            result = await chief.daily_review(db, store_id, brand_id, target)

        return {
            "status": "completed",
            "review_type": req.review_type,
            "store_id": store_id,
            "result": result,
        }
    except Exception as e:
        logger.error("trigger_review_failed", store_id=store_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"复盘触发失败: {str(e)}")


# ── Agent Events 端点（运维/调试用）────────────────────────────────────────────


@router.get("/reviews/{store_id}/events", summary="Agent事件列表", tags=["reviews"])
async def list_agent_events(
    store_id: str,
    unprocessed_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取门店的Agent事件列表（异常事件、联动响应等）"""
    await validate_store_brand(store_id, current_user)

    conditions = ["store_id = :sid"]
    params: Dict[str, Any] = {"sid": store_id, "lim": limit}

    if unprocessed_only:
        conditions.append("processed = FALSE")

    where_clause = " AND ".join(conditions)

    result = await db.execute(
        text(f"""
            SELECT id, source_agent, event_type, severity, payload,
                   target_agents, responses, processed, processed_at, created_at
            FROM agent_events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :lim
        """),
        params,
    )

    rows = []
    for r in result.mappings():
        row = dict(r)
        row["id"] = str(row["id"])
        rows.append(row)

    return {"store_id": store_id, "events": rows}
