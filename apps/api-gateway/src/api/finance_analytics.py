"""
财务分析综合API
提供真实聚合数据的财务分析端点，替代旧 finance.py 中硬编码返回 0 的接口。

端点列表：
  GET  /api/v1/finance-analytics/daily-profit       日利润（真实数据）
  GET  /api/v1/finance-analytics/monthly-pnl        月度P&L
  GET  /api/v1/finance-analytics/multi-store        跨店比较
  GET  /api/v1/finance-analytics/revenue-breakdown  营收分解
  GET  /api/v1/finance-analytics/monthly-report     月度报告
  POST /api/v1/finance-analytics/kingdee/sync       同步到金蝶
  GET  /api/v1/finance-analytics/kingdee/sync-status 同步状态
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_permission
from src.models.user import User
from src.services.finance_analytics_service import FinanceAnalyticsService
from src.services.kingdee_sync_service import KingdeeSyncService

router = APIRouter(prefix="/api/v1/finance-analytics", tags=["财务分析"])


# ─────────────────────────────────────────────────────────────────
# Pydantic 请求/响应模型
# ─────────────────────────────────────────────────────────────────


class KingdeeSyncRequest(BaseModel):
    store_id: str = Field(..., description="门店ID")
    sync_date: date = Field(..., description="需要同步的日期（YYYY-MM-DD）")


class KingdeeRetryRequest(BaseModel):
    store_id: str = Field(..., description="门店ID")
    retry_date: date = Field(..., description="需要重试的日期（YYYY-MM-DD）")


# ─────────────────────────────────────────────────────────────────
# 日利润（真实数据）
# ─────────────────────────────────────────────────────────────────


@router.get("/daily-profit", summary="日利润（真实数据）")
async def get_daily_profit(
    store_id: str = Query(..., description="门店ID"),
    target_date: Optional[date] = Query(None, description="查询日期，默认今日"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店某日的完整利润数据（从真实订单/库存/损耗表聚合）。

    返回字段：
    - revenue_yuan          : 净营收（元）
    - ingredient_cost_yuan  : 食材成本（元）
    - gross_profit_yuan     : 毛利润（元）
    - gross_margin_pct      : 毛利率（%）
    - labor_cost_yuan       : 人工成本（元）
    - waste_cost_yuan       : 损耗成本（元）
    - net_profit_yuan       : 净利润（元）
    - net_margin_pct        : 净利率（%）
    - vs_yesterday_pct      : 环比昨日变化（%）
    - vs_last_week_pct      : 环比上周同日变化（%）
    """
    svc = FinanceAnalyticsService(db)
    try:
        return await svc.get_real_daily_profit(store_id, target_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"日利润查询失败: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# 月度 P&L
# ─────────────────────────────────────────────────────────────────


@router.get("/monthly-pnl", summary="月度P&L损益表")
async def get_monthly_pnl(
    store_id: str = Query(..., description="门店ID"),
    year: int = Query(..., description="年份，如 2026"),
    month: int = Query(..., ge=1, le=12, description="月份（1-12）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店月度损益表（P&L）。

    包含：营收 / 食材成本 / 人工成本 / 损耗成本 / 毛利润 / 净利润 / 各项成本率。
    """
    svc = FinanceAnalyticsService(db)
    try:
        return await svc.get_store_pnl(store_id, year, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"月度P&L查询失败: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# 跨店比较
# ─────────────────────────────────────────────────────────────────


@router.get("/multi-store", summary="跨店比较（品牌视角）")
async def get_multi_store_comparison(
    brand_id: str = Query(..., description="品牌ID"),
    year: int = Query(..., description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份（1-12）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取品牌下所有门店的月度财务对比数据，按利润率降序排列。

    返回：[{store_id, store_name, revenue_yuan, cost_rate, profit_yuan, profit_rate, order_count}]
    """
    svc = FinanceAnalyticsService(db)
    try:
        return await svc.get_multi_store_comparison(brand_id, year, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"跨店比较查询失败: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# 营收分解
# ─────────────────────────────────────────────────────────────────


@router.get("/revenue-breakdown", summary="营收分解（渠道/时段/菜品类别）")
async def get_revenue_breakdown(
    store_id: str = Query(..., description="门店ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取营收多维度分解数据。

    返回：
    - by_channel  : 按渠道（堂食/美团/饿了么/抖音/小程序）
    - by_hour     : 按小时（0-23）
    - by_category : 按菜品大类
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    svc = FinanceAnalyticsService(db)
    try:
        return await svc.get_revenue_breakdown(store_id, start_date, end_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"营收分解查询失败: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# 月度报告生成
# ─────────────────────────────────────────────────────────────────


@router.get("/monthly-report", summary="月度财务报告生成")
async def get_monthly_report(
    store_id: str = Query(..., description="门店ID"),
    year: int = Query(..., description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份（1-12）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    生成月度财务报告（含P&L / 营收分解 / 与上月环比）。
    """
    svc = FinanceAnalyticsService(db)
    try:
        return await svc.generate_monthly_report(store_id, year, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"月度报告生成失败: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# 金蝶同步
# ─────────────────────────────────────────────────────────────────


@router.post("/kingdee/sync", summary="同步日账凭证到金蝶")
async def sync_to_kingdee(
    req: KingdeeSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("finance:write")),
):
    """
    将指定门店指定日期的 P&L 数据生成凭证并推送到金蝶云星空。

    前提条件：
    - 已在环境变量中配置 KINGDEE_APP_ID / KINGDEE_APP_SECRET / KINGDEE_ACCT_ID
    - 已配置会计科目环境变量（ACCT_MAIN_REVENUE 等）

    返回：{voucher_no, status, entries_count, message}
    """
    # 先获取P&L数据
    analytics_svc = FinanceAnalyticsService(db)
    try:
        pnl_data = await analytics_svc.get_real_daily_profit(req.store_id, req.sync_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"P&L数据获取失败: {str(exc)}")

    # 推送到金蝶
    kingdee_svc = KingdeeSyncService()
    try:
        result = await kingdee_svc.sync_daily_voucher(req.store_id, req.sync_date, pnl_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"金蝶同步失败: {str(exc)}")

    return result


@router.get("/kingdee/sync-status", summary="金蝶同步状态查询")
async def get_kingdee_sync_status(
    store_id: str = Query(..., description="门店ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询指定日期范围内金蝶凭证同步状态。

    返回：[{date, status, voucher_no, synced_at, message}]
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    kingdee_svc = KingdeeSyncService()
    try:
        return await kingdee_svc.get_sync_status(store_id, start_date, end_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"同步状态查询失败: {str(exc)}")
