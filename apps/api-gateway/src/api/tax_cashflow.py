"""
CFO 工作台 API — Phase 5 Month 2: 税务智能引擎 + 现金流预测

Router prefix: /api/v1/finance-agent
Endpoints:
  POST /tax/compute/{store_id}          — 触发税务计算（幂等）
  GET  /tax/{store_id}                  — 查询税务计算结果（period）
  GET  /tax/{store_id}/summary          — 税务汇总（所有税种合计）
  POST /cashflow/compute/{store_id}     — 触发现金流预测（幂等）
  GET  /cashflow/{store_id}             — 查询未来30天现金流预测
  GET  /cashflow/{store_id}/gap-alert   — 现金缺口预警
  GET  /actions/{store_id}              — Agent 动作列表（pending优先）
  POST /actions/{action_id}/respond     — 回应 Agent 动作（接受/忽略）
  GET  /dashboard/{store_id}            — CFO 首屏聚合（BFF）
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.tax_engine_service import compute_tax_calculation
from ..services.cashflow_forecast_service import compute_cashflow_forecast

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/finance-agent", tags=["finance_agent"])

RISK_BADGE = {"low": "safe", "medium": "warn", "high": "alert", "critical": "critical"}


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


# ── Tax endpoints ─────────────────────────────────────────────────────────────

@router.post("/tax/compute/{store_id}", status_code=201)
async def compute_tax(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    force:    bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """触发税务计算（幂等，当日覆盖）"""
    results = await compute_tax_calculation(db, store_id, period, force=force)
    total_tax = sum(r["tax_amount_yuan"] for r in results)
    return {
        "computed":    True,
        "store_id":    store_id,
        "period":      period,
        "tax_types":   len(results),
        "total_tax_yuan": round(total_tax, 2),
        "results":     results,
    }


@router.get("/tax/{store_id}")
async def get_tax_calculations(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """查询税务计算结果"""
    rows = (await db.execute(text("""
        SELECT * FROM tax_calculations
        WHERE store_id = :sid AND period = :period
        ORDER BY calc_date DESC, tax_type
    """), {"sid": store_id, "period": period})).fetchall()

    results = []
    for r in rows:
        detail_str = None
        if r.calc_detail:
            try:
                d = json.loads(r.calc_detail)
                detail_str = d.get("formula")
            except (json.JSONDecodeError, TypeError):
                pass
        results.append({
            "tax_type":          r.tax_type,
            "tax_name":          r.tax_name,
            "tax_rate":          _safe_float(r.tax_rate),
            "taxable_base_yuan": _safe_float(r.taxable_base_yuan),
            "tax_amount_yuan":   _safe_float(r.tax_amount_yuan),
            "declared_yuan":     _safe_float(r.declared_yuan),
            "deviation_yuan":    _safe_float(r.deviation_yuan),
            "deviation_pct":     _safe_float(r.deviation_pct),
            "risk_level":        r.risk_level,
            "calc_date":         str(r.calc_date),
            "detail":            detail_str,
        })

    if not results:
        return {"store_id": store_id, "period": period,
                "message": "暂无税务计算结果，请先调用 compute", "results": []}

    total_tax = sum(r["tax_amount_yuan"] for r in results)
    total_declared = sum(r["declared_yuan"] for r in results)
    return {
        "store_id":          store_id,
        "period":            period,
        "total_tax_yuan":    round(total_tax, 2),
        "total_declared_yuan": round(total_declared, 2),
        "results":           results,
    }


@router.get("/tax/{store_id}/summary")
async def get_tax_summary(
    store_id: str,
    months:   int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    """近N月税务汇总趋势"""
    today = date.today()
    periods = []
    for i in range(months):
        d = today.replace(day=1) - timedelta(days=1) * (i * 28)
        d = d.replace(day=1)
        periods.append(d.strftime("%Y-%m"))

    rows = (await db.execute(text("""
        SELECT period, SUM(tax_amount_yuan) AS total_tax,
               MAX(risk_level) AS max_risk,
               COUNT(*) AS tax_types
        FROM tax_calculations
        WHERE store_id = :sid AND period = ANY(:periods)
        GROUP BY period
        ORDER BY period DESC
    """), {"sid": store_id, "periods": periods})).fetchall()

    return {
        "store_id": store_id,
        "periods":  periods,
        "summary":  [
            {
                "period":        r.period,
                "total_tax_yuan": _safe_float(r.total_tax),
                "max_risk":      r.max_risk,
                "tax_types":     r.tax_types,
            }
            for r in rows
        ],
    }


# ── Cash flow endpoints ───────────────────────────────────────────────────────

@router.post("/cashflow/compute/{store_id}", status_code=201)
async def compute_cashflow(
    store_id:        str,
    opening_balance: float = Query(0.0, description="期初余额（元）"),
    force:           bool  = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """触发现金流预测（幂等，当日覆盖）"""
    result = await compute_cashflow_forecast(
        db, store_id, opening_balance=opening_balance, force=force
    )
    return {"computed": True, **result}


@router.get("/cashflow/{store_id}")
async def get_cashflow_forecast(
    store_id: str,
    days:     int = Query(30, ge=7, le=60),
    db: AsyncSession = Depends(get_db),
):
    """查询最新现金流预测（最近一次生成）"""
    # 找最新 generated_on
    latest = (await db.execute(text("""
        SELECT MAX(generated_on) AS gen FROM cashflow_forecasts
        WHERE store_id = :sid
    """), {"sid": store_id})).fetchone()

    if not latest or not latest.gen:
        return {"store_id": store_id, "message": "暂无预测，请先调用 compute", "forecasts": []}

    gen_str = str(latest.gen)
    rows = (await db.execute(text("""
        SELECT forecast_date, inflow_yuan, outflow_yuan, net_yuan, balance_yuan, confidence
        FROM cashflow_forecasts
        WHERE store_id = :sid AND generated_on = :gen
        ORDER BY forecast_date
        LIMIT :days
    """), {"sid": store_id, "gen": gen_str, "days": days})).fetchall()

    forecasts = [{
        "forecast_date": str(r.forecast_date),
        "inflow_yuan":   _safe_float(r.inflow_yuan),
        "outflow_yuan":  _safe_float(r.outflow_yuan),
        "net_yuan":      _safe_float(r.net_yuan),
        "balance_yuan":  _safe_float(r.balance_yuan),
        "confidence":    _safe_float(r.confidence),
    } for r in rows]

    gap_days = [f for f in forecasts if f["balance_yuan"] < 0]
    return {
        "store_id":         store_id,
        "generated_on":     gen_str,
        "forecast_days":    len(forecasts),
        "cash_gap_days":    len(gap_days),
        "min_balance_yuan": min(f["balance_yuan"] for f in forecasts) if forecasts else 0.0,
        "max_balance_yuan": max(f["balance_yuan"] for f in forecasts) if forecasts else 0.0,
        "forecasts":        forecasts,
    }


@router.get("/cashflow/{store_id}/gap-alert")
async def get_cash_gap_alert(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询预测期内现金缺口天数及最低余额"""
    rows = (await db.execute(text("""
        SELECT forecast_date, balance_yuan, net_yuan
        FROM cashflow_forecasts
        WHERE store_id = :sid
          AND generated_on = (
              SELECT MAX(generated_on) FROM cashflow_forecasts WHERE store_id = :sid
          )
          AND balance_yuan < 0
        ORDER BY forecast_date
    """), {"sid": store_id})).fetchall()

    if not rows:
        return {"store_id": store_id, "has_gap": False, "gap_days": [], "min_balance_yuan": 0.0}

    gap_days = [{
        "date":          str(r.forecast_date),
        "balance_yuan":  _safe_float(r.balance_yuan),
        "net_yuan":      _safe_float(r.net_yuan),
    } for r in rows]

    return {
        "store_id":       store_id,
        "has_gap":        True,
        "gap_count":      len(gap_days),
        "min_balance_yuan": min(g["balance_yuan"] for g in gap_days),
        "first_gap_date": gap_days[0]["date"],
        "gap_days":       gap_days,
    }


# ── Agent action endpoints ────────────────────────────────────────────────────

class ActionResponse(BaseModel):
    action: str  # "accepted" | "dismissed"
    note:   Optional[str] = None


@router.get("/actions/{store_id}")
async def get_agent_actions(
    store_id: str,
    status:   Optional[str] = Query(None),
    level:    Optional[str] = Query(None),
    limit:    int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询 Agent 动作列表（pending 优先）"""
    if status and level:
        rows = (await db.execute(text("""
            SELECT * FROM agent_action_log
            WHERE store_id = :sid AND status = :status AND action_level = :level
            ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC
            LIMIT :limit
        """), {"sid": store_id, "status": status, "level": level, "limit": limit})).fetchall()
    elif status:
        rows = (await db.execute(text("""
            SELECT * FROM agent_action_log
            WHERE store_id = :sid AND status = :status
            ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC
            LIMIT :limit
        """), {"sid": store_id, "status": status, "limit": limit})).fetchall()
    elif level:
        rows = (await db.execute(text("""
            SELECT * FROM agent_action_log
            WHERE store_id = :sid AND action_level = :level
            ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC
            LIMIT :limit
        """), {"sid": store_id, "level": level, "limit": limit})).fetchall()
    else:
        rows = (await db.execute(text("""
            SELECT * FROM agent_action_log
            WHERE store_id = :sid
            ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC
            LIMIT :limit
        """), {"sid": store_id, "limit": limit})).fetchall()

    return {
        "total": len(rows),
        "actions": [_format_action(r) for r in rows],
    }


@router.post("/actions/{action_id}/respond")
async def respond_to_action(
    action_id: str,
    body:      ActionResponse,
    db: AsyncSession = Depends(get_db),
):
    """回应 Agent 动作（accepted / dismissed）"""
    if body.action not in ("accepted", "dismissed"):
        raise HTTPException(400, "action must be 'accepted' or 'dismissed'")

    row = (await db.execute(text("""
        SELECT id, status FROM agent_action_log WHERE id = :id
    """), {"id": action_id})).fetchone()

    if not row:
        raise HTTPException(404, f"Action {action_id} not found")
    if row.status != "pending":
        raise HTTPException(409, f"Action already in status '{row.status}'")

    await db.execute(text("""
        UPDATE agent_action_log
        SET status = :status, responded_at = NOW(), response_note = :note
        WHERE id = :id
    """), {"status": body.action, "note": body.note, "id": action_id})
    await db.commit()

    return {"action_id": action_id, "status": body.action}


# ── BFF dashboard ─────────────────────────────────────────────────────────────

@router.get("/dashboard/{store_id}")
async def get_cfo_dashboard(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    CFO 首屏聚合端点（BFF）。
    模块降级：任意子查询失败返回 null，不阻塞整屏。
    """
    today = date.today().isoformat()

    # ── 利润归因 ──────────────────────────────────────────────────────────
    profit_data = None
    try:
        attr = (await db.execute(text("""
            SELECT net_revenue_yuan, gross_profit_yuan, profit_margin_pct, total_cost_yuan
            FROM profit_attribution_results
            WHERE store_id = :sid AND period = :period
            ORDER BY calc_date DESC LIMIT 1
        """), {"sid": store_id, "period": period})).fetchone()
        if attr:
            profit_data = {
                "net_revenue_yuan":   _safe_float(attr.net_revenue_yuan),
                "gross_profit_yuan":  _safe_float(attr.gross_profit_yuan),
                "profit_margin_pct":  _safe_float(attr.profit_margin_pct),
                "total_cost_yuan":    _safe_float(attr.total_cost_yuan),
            }
    except Exception:
        logger.warning("cfo_dashboard_profit_failed", store_id=store_id)

    # ── 税务摘要 ──────────────────────────────────────────────────────────
    tax_summary = None
    try:
        tax_rows = (await db.execute(text("""
            SELECT SUM(tax_amount_yuan) AS total_tax,
                   SUM(deviation_yuan)  AS total_dev,
                   COUNT(*) AS types,
                   MAX(risk_level) AS max_risk
            FROM tax_calculations
            WHERE store_id = :sid AND period = :period
        """), {"sid": store_id, "period": period})).fetchone()
        if tax_rows and tax_rows.total_tax is not None:
            tax_summary = {
                "total_tax_yuan":       _safe_float(tax_rows.total_tax),
                "total_deviation_yuan": _safe_float(tax_rows.total_dev),
                "tax_types":            tax_rows.types,
                "max_risk":             tax_rows.max_risk or "low",
            }
    except Exception:
        logger.warning("cfo_dashboard_tax_failed", store_id=store_id)

    # ── 现金流摘要 ────────────────────────────────────────────────────────
    cashflow_summary = None
    try:
        cf_rows = (await db.execute(text("""
            SELECT SUM(net_yuan) AS total_net,
                   MIN(balance_yuan) AS min_bal,
                   MAX(balance_yuan) AS max_bal,
                   COUNT(CASE WHEN balance_yuan < 0 THEN 1 END) AS gap_days
            FROM cashflow_forecasts
            WHERE store_id = :sid
              AND generated_on = (
                  SELECT MAX(generated_on) FROM cashflow_forecasts WHERE store_id = :sid
              )
        """), {"sid": store_id})).fetchone()
        if cf_rows and cf_rows.total_net is not None:
            cashflow_summary = {
                "total_net_yuan":    _safe_float(cf_rows.total_net),
                "min_balance_yuan":  _safe_float(cf_rows.min_bal),
                "max_balance_yuan":  _safe_float(cf_rows.max_bal),
                "gap_days":          cf_rows.gap_days or 0,
            }
    except Exception:
        logger.warning("cfo_dashboard_cashflow_failed", store_id=store_id)

    # ── Pending Agent 动作 ────────────────────────────────────────────────
    pending_actions = []
    try:
        act_rows = (await db.execute(text("""
            SELECT * FROM agent_action_log
            WHERE store_id = :sid AND status = 'pending'
            ORDER BY CASE action_level WHEN 'L2' THEN 0 WHEN 'L1' THEN 1 ELSE 2 END,
                     created_at DESC
            LIMIT 5
        """), {"sid": store_id})).fetchall()
        pending_actions = [_format_action(r) for r in act_rows]
    except Exception:
        logger.warning("cfo_dashboard_actions_failed", store_id=store_id)

    # ── 风险任务 ──────────────────────────────────────────────────────────
    risk_summary = None
    try:
        rsk = (await db.execute(text("""
            SELECT COUNT(*) AS total,
                   COUNT(CASE WHEN severity IN ('high','critical') THEN 1 END) AS high_count
            FROM risk_tasks
            WHERE (store_id = :sid OR brand_id IS NULL) AND status = 'open'
        """), {"sid": store_id})).fetchone()
        if rsk:
            risk_summary = {"open_total": rsk.total, "high_priority": rsk.high_count}
    except Exception:
        logger.warning("cfo_dashboard_risk_failed", store_id=store_id)

    return {
        "store_id":        store_id,
        "period":          period,
        "as_of":           today,
        "profit":          profit_data,
        "tax":             tax_summary,
        "cashflow":        cashflow_summary,
        "pending_actions": pending_actions,
        "risk":            risk_summary,
    }


# ── Formatter ─────────────────────────────────────────────────────────────────

def _format_action(row: Any) -> Dict[str, Any]:
    return {
        "id":                   row.id,
        "action_level":         row.action_level,
        "agent_name":           row.agent_name,
        "trigger_type":         row.trigger_type,
        "title":                row.title,
        "description":          row.description,
        "recommended_action":   row.recommended_action,
        "expected_impact_yuan": _safe_float(row.expected_impact_yuan),
        "confidence":           _safe_float(row.confidence),
        "status":               row.status,
        "period":               row.period,
        "created_at":           row.created_at.isoformat() if row.created_at else None,
    }
