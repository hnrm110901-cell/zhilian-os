"""
食材成本真相引擎 API

端点：
  GET  /daily          — 日级成本真相快照
  GET  /dish-detail    — 菜品级差异明细
  GET  /attribution    — 五因归因
  GET  /trend          — 近N天成本率趋势
  GET  /prediction     — 月末成本率预测
  GET  /insight        — 一句话洞察（供推送/首页）
  GET  /dashboard      — BFF驾驶舱聚合
"""

from datetime import date, timedelta

from fastapi import APIRouter, Query
from src.services.cost_truth_engine import (
    DishSale,
    IngredientUsage,
    WasteRecord,
    _safe_pct,
    _yuan,
    build_cost_truth_report,
    classify_severity,
    generate_actionable_decision,
    generate_one_sentence_insight,
    predict_month_end_cost_rate,
)

router = APIRouter(prefix="/api/v1/cost-truth", tags=["cost-truth"])


def _demo_report(store_id: str, target_date: date):
    """
    生成演示数据的成本真相报告。
    生产环境中替换为真实DB查询。
    """
    sales = [
        DishSale("D001", "酸菜鱼", 42, 42 * 6800, 2850),
        DishSale("D002", "剁椒鱼头", 28, 28 * 8800, 3200),
        DishSale("D003", "小炒肉", 65, 65 * 3800, 1100),
        DishSale("D004", "蒸蛋", 35, 35 * 1800, 380),
        DishSale("D005", "凉拌黄瓜", 50, 50 * 1200, 200),
    ]

    usages = [
        IngredientUsage("I001", "鲈鱼", 14.7, 17.2, "kg", 1800, 1650),
        IngredientUsage("I002", "鱼头", 8.4, 9.1, "kg", 2200, 2200),
        IngredientUsage("I003", "五花肉", 9.8, 10.5, "kg", 1500, 1480),
        IngredientUsage("I004", "鸡蛋", 3.5, 3.6, "kg", 600, 600),
        IngredientUsage("I005", "黄瓜", 5.0, 5.2, "kg", 300, 280),
        IngredientUsage("I006", "酸菜", 6.3, 7.0, "kg", 400, 400),
        IngredientUsage("I007", "辣椒", 2.1, 2.3, "kg", 500, 500),
    ]

    wastes = [
        WasteRecord("I001", "鲈鱼", 1.2, "kg", 1800, "staff_error"),
        WasteRecord("I006", "酸菜", 0.5, "kg", 400, "spoilage"),
    ]

    revenue_fen = sum(s.revenue_fen for s in sales)
    day_of_month = target_date.day
    days_in_month = 30

    return build_cost_truth_report(
        store_id=store_id,
        truth_date=target_date.isoformat(),
        revenue_fen=revenue_fen,
        sales=sales,
        usages=usages,
        wastes=wastes,
        target_pct=32.0,
        mtd_revenue_fen=revenue_fen * day_of_month,
        mtd_actual_cost_fen=int(revenue_fen * 0.342 * day_of_month),
        days_elapsed=day_of_month,
        days_in_month=days_in_month,
    )


@router.get("/stores/{store_id}/daily")
async def get_daily_cost_truth(
    store_id: str,
    target_date: date = Query(default=None),
):
    """日级成本真相快照"""
    d = target_date or (date.today() - timedelta(days=1))
    report = _demo_report(store_id, d)

    return {
        "store_id": report.store_id,
        "truth_date": report.truth_date,
        "revenue_yuan": _yuan(report.revenue_fen),
        "theoretical_cost_yuan": _yuan(report.theoretical_cost_fen),
        "actual_cost_yuan": _yuan(report.actual_cost_fen),
        "variance_yuan": _yuan(report.variance_fen),
        "theoretical_pct": report.theoretical_pct,
        "actual_pct": report.actual_pct,
        "variance_pct": report.variance_pct,
        "severity": report.severity,
        "target_pct": report.target_pct,
        "mtd_actual_pct": report.mtd_actual_pct,
        "predicted_eom_pct": report.predicted_eom_pct,
        "dish_count": len(report.dish_details),
        "order_count": sum(d.sold_qty for d in report.dish_details),
    }


@router.get("/stores/{store_id}/dish-detail")
async def get_dish_detail(
    store_id: str,
    target_date: date = Query(default=None),
    top_n: int = Query(default=10, ge=1, le=50),
):
    """菜品级差异明细"""
    d = target_date or (date.today() - timedelta(days=1))
    report = _demo_report(store_id, d)

    return {
        "store_id": store_id,
        "truth_date": d.isoformat(),
        "dishes": [
            {
                "rank": i + 1,
                "dish_id": dd.dish_id,
                "dish_name": dd.dish_name,
                "sold_qty": dd.sold_qty,
                "theoretical_cost_yuan": _yuan(dd.theoretical_cost_fen),
                "actual_cost_yuan": _yuan(dd.actual_cost_fen),
                "variance_yuan": _yuan(dd.variance_fen),
                "variance_pct": dd.variance_pct,
                "top_ingredients": dd.top_ingredients,
            }
            for i, dd in enumerate(report.dish_details[:top_n])
        ],
    }


@router.get("/stores/{store_id}/attribution")
async def get_attribution(
    store_id: str,
    target_date: date = Query(default=None),
):
    """五因归因"""
    d = target_date or (date.today() - timedelta(days=1))
    report = _demo_report(store_id, d)

    return {
        "store_id": store_id,
        "truth_date": d.isoformat(),
        "total_variance_yuan": _yuan(report.variance_fen),
        "factors": [
            {
                "factor": a.factor,
                "contribution_yuan": _yuan(a.contribution_fen),
                "contribution_pct": a.contribution_pct,
                "description": a.description,
                "action": a.action,
                "detail": a.detail,
            }
            for a in report.attributions
        ],
    }


@router.get("/stores/{store_id}/prediction")
async def get_prediction(
    store_id: str,
    target_date: date = Query(default=None),
):
    """月末成本率预测"""
    d = target_date or (date.today() - timedelta(days=1))
    report = _demo_report(store_id, d)

    return {
        "store_id": store_id,
        "as_of_date": d.isoformat(),
        "mtd_actual_pct": report.mtd_actual_pct,
        "predicted_eom_pct": report.predicted_eom_pct,
        "target_pct": report.target_pct,
        "gap_to_target": round((report.predicted_eom_pct or 0) - report.target_pct, 2),
        "severity": classify_severity((report.predicted_eom_pct or 0) - report.target_pct),
    }


@router.get("/stores/{store_id}/insight")
async def get_insight(
    store_id: str,
    target_date: date = Query(default=None),
):
    """一句话洞察"""
    d = target_date or (date.today() - timedelta(days=1))
    report = _demo_report(store_id, d)
    insight = generate_one_sentence_insight(report)
    decision = generate_actionable_decision(report)

    return {
        "store_id": store_id,
        "truth_date": d.isoformat(),
        "insight": insight,
        "decision": decision,
    }


@router.get("/stores/{store_id}/dashboard")
async def get_cost_truth_dashboard(
    store_id: str,
    target_date: date = Query(default=None),
):
    """BFF 驾驶舱聚合"""
    d = target_date or (date.today() - timedelta(days=1))
    report = _demo_report(store_id, d)
    insight = generate_one_sentence_insight(report)
    decision = generate_actionable_decision(report)

    return {
        "store_id": store_id,
        "truth_date": d.isoformat(),
        # 核心指标
        "kpi": {
            "actual_pct": report.actual_pct,
            "theoretical_pct": report.theoretical_pct,
            "variance_pct": report.variance_pct,
            "severity": report.severity,
            "target_pct": report.target_pct,
            "revenue_yuan": _yuan(report.revenue_fen),
            "variance_yuan": _yuan(report.variance_fen),
        },
        # 月末预测
        "prediction": {
            "mtd_actual_pct": report.mtd_actual_pct,
            "predicted_eom_pct": report.predicted_eom_pct,
            "gap_to_target": round((report.predicted_eom_pct or 0) - report.target_pct, 2),
        },
        # Top5 差异菜品
        "top_dishes": [
            {
                "rank": i + 1,
                "dish_name": dd.dish_name,
                "variance_yuan": _yuan(dd.variance_fen),
                "variance_pct": dd.variance_pct,
                "sold_qty": dd.sold_qty,
            }
            for i, dd in enumerate(report.dish_details[:5])
        ],
        # 五因归因
        "attribution": [
            {
                "factor": a.factor,
                "contribution_yuan": _yuan(a.contribution_fen),
                "contribution_pct": a.contribution_pct,
                "description": a.description,
                "action": a.action,
            }
            for a in report.attributions
        ],
        # 一句话洞察
        "insight": insight,
        # 可执行决策
        "decision": decision,
    }
