"""CFO 工作台 API — Phase 5 Month 6

端点：
  GET  /api/v1/cfo/dashboard           — BFF 全量（品牌+期间）
  GET  /api/v1/cfo/health-overview     — 门店健康排名
  GET  /api/v1/cfo/alert-summary       — 活跃告警摘要
  GET  /api/v1/cfo/budget-summary      — 预算执行汇总
  GET  /api/v1/cfo/actions             — 品牌行动清单
  POST /api/v1/cfo/report/save         — 持久化快照
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services import cfo_dashboard_service as svc

router = APIRouter(prefix="/api/v1/cfo", tags=["cfo_dashboard"])


def _default_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ── BFF ──────────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_cfo_dashboard(
    brand_id: str = Query(..., description="品牌ID"),
    period: Optional[str] = Query(None, description="期间 YYYY-MM，默认当月"),
    db: AsyncSession = Depends(get_db),
):
    p = period or _default_period()
    return await svc.get_cfo_dashboard(db, brand_id, p)


# ── 子模块端点 ────────────────────────────────────────────────────────────────


@router.get("/health-overview")
async def get_health_overview(
    brand_id: str = Query(...),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    p = period or _default_period()
    return await svc.get_brand_health_overview(db, brand_id, p)


@router.get("/alert-summary")
async def get_alert_summary(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_brand_alert_summary(db, brand_id)


@router.get("/budget-summary")
async def get_budget_summary(
    brand_id: str = Query(...),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    p = period or _default_period()
    return await svc.get_brand_budget_summary(db, brand_id, p)


@router.get("/actions")
async def get_actions(
    brand_id: str = Query(...),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    p = period or _default_period()
    return await svc.get_brand_actions(db, brand_id, p)


# ── 快照持久化 ────────────────────────────────────────────────────────────────


@router.post("/report/save")
async def save_report(
    brand_id: str = Query(...),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """先计算再持久化 CFO 报告快照。"""
    p = period or _default_period()
    data = await svc.get_cfo_dashboard(db, brand_id, p)
    await svc.save_report_snapshot(db, brand_id, p, data)
    return {"status": "saved", "brand_id": brand_id, "period": p}


# ── Meta ──────────────────────────────────────────────────────────────────────


@router.get("/meta/grades")
async def get_grade_meta():
    return {
        "thresholds": svc.GRADE_THRESHOLDS,
        "descriptions": {
            "A": "优秀（≥80分）",
            "B": "良好（60-79分）",
            "C": "待改善（40-59分）",
            "D": "高风险（<40分）",
        },
    }
