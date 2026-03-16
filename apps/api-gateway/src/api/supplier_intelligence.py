"""
供应商智能评分 API 端点
前缀: /api/v1/supplier-intel
跨系统供应商评分：B2B采购 + 食品安全溯源 + 价格趋势
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.supplier_intelligence_service import SupplierIntelligenceService

router = APIRouter(prefix="/api/v1/supplier-intel", tags=["supplier-intelligence"])

service = SupplierIntelligenceService()


# ── 请求体 ──────────────────────────────────────────────────────────


class ComputeRequest(BaseModel):
    brand_id: str
    period: str  # "2026-03"
    supplier_id: Optional[str] = None  # 为空则批量计算所有


# ── 计算评分卡 ──────────────────────────────────────────────────────


@router.post("/compute")
async def compute_scorecards(
    body: ComputeRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """计算供应商评分卡（单个或批量）"""
    try:
        if body.supplier_id:
            result = await service.compute_scorecard(
                db=db,
                brand_id=body.brand_id,
                supplier_id=body.supplier_id,
                period=body.period,
            )
        else:
            result = await service.compute_all_scorecards(
                db=db,
                brand_id=body.brand_id,
                period=body.period,
            )
        await db.commit()
        return {"success": True, "data": result}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"计算评分卡失败: {str(e)}")


# ── 评分卡列表 ──────────────────────────────────────────────────────


@router.get("/scorecards")
async def list_scorecards(
    brand_id: str = Query(...),
    period: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询供应商评分卡"""
    result = await service.get_scorecards(
        db=db,
        brand_id=brand_id,
        period=period,
        tier=tier,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}


# ── 评分卡详情 ──────────────────────────────────────────────────────


@router.get("/scorecards/{scorecard_id}")
async def get_scorecard_detail(
    scorecard_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取单张评分卡详情"""
    detail = await service.get_scorecard_detail(db=db, scorecard_id=scorecard_id)
    if not detail:
        raise HTTPException(status_code=404, detail="评分卡不存在")
    return {"success": True, "data": detail}


# ── 供应商排名 ──────────────────────────────────────────────────────


@router.get("/ranking")
async def get_ranking(
    brand_id: str = Query(...),
    period: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """供应商排名及评级分布"""
    result = await service.get_ranking(db=db, brand_id=brand_id, period=period)
    return {"success": True, "data": result}


# ── 价格趋势 ────────────────────────────────────────────────────────


@router.get("/price-trends")
async def get_price_trends(
    brand_id: str = Query(...),
    supplier_id: str = Query(...),
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """供应商食材价格趋势（最近N个月）"""
    trends = await service.get_price_trends(
        db=db,
        brand_id=brand_id,
        supplier_id=supplier_id,
        months=months,
    )
    return {"success": True, "data": trends}


# ── 风险预警 ────────────────────────────────────────────────────────


@router.get("/risk-alerts")
async def get_risk_alerts(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """识别高风险供应商"""
    alerts = await service.get_risk_alerts(db=db, brand_id=brand_id)
    return {"success": True, "data": alerts}
