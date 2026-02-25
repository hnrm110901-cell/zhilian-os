"""
竞争分析 API
提供竞品管理、市场份额分析、价格对比、价格敏感度分析
"""
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.dependencies import get_current_active_user, require_role
from src.models import User
from src.models.user import UserRole
from src.services.competitive_analysis_service import competitive_analysis_service

router = APIRouter(prefix="/api/v1/competitive", tags=["competitive_analysis"])


# ------------------------------------------------------------------ #
# Pydantic 模型                                                        #
# ------------------------------------------------------------------ #

class CompetitorCreateRequest(BaseModel):
    name: str = Field(..., max_length=100)
    brand: Optional[str] = None
    cuisine_type: Optional[str] = None
    address: Optional[str] = None
    distance_meters: Optional[int] = Field(None, ge=0)
    avg_price_per_person: Optional[float] = Field(None, ge=0)
    rating: Optional[float] = Field(None, ge=0, le=5)
    monthly_customers: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None


class CompetitorUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = None
    cuisine_type: Optional[str] = None
    address: Optional[str] = None
    distance_meters: Optional[int] = Field(None, ge=0)
    avg_price_per_person: Optional[float] = Field(None, ge=0)
    rating: Optional[float] = Field(None, ge=0, le=5)
    monthly_customers: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PriceRecordRequest(BaseModel):
    dish_name: str = Field(..., max_length=100)
    price: float = Field(..., ge=0)
    record_date: date
    category: Optional[str] = None
    our_dish_id: Optional[str] = None


# ------------------------------------------------------------------ #
# 竞品门店管理                                                          #
# ------------------------------------------------------------------ #

@router.get("/competitors")
async def list_competitors(
    store_id: str = Query(..., description="我方门店ID"),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定门店的竞品列表"""
    competitors = await competitive_analysis_service.list_competitors(store_id)
    return {"competitors": [c.to_dict() for c in competitors], "total": len(competitors)}


@router.post("/competitors", status_code=201)
async def create_competitor(
    store_id: str = Query(..., description="我方门店ID"),
    request: CompetitorCreateRequest = ...,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.ASSISTANT_MANAGER)),
):
    """
    添加竞品门店

    - avg_price_per_person：人均消费（元），用于市场份额估算
    - monthly_customers：月均客流量（估算），用于市场份额估算
    - distance_meters：与我方门店的距离（米）
    """
    competitor = await competitive_analysis_service.create_competitor(
        our_store_id=store_id,
        **request.model_dump(),
    )
    return competitor.to_dict()


@router.put("/competitors/{competitor_id}")
async def update_competitor(
    competitor_id: str,
    request: CompetitorUpdateRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.ASSISTANT_MANAGER)),
):
    """更新竞品门店信息"""
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    competitor = await competitive_analysis_service.update_competitor(competitor_id, **update_data)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品门店不存在")
    return competitor.to_dict()


@router.delete("/competitors/{competitor_id}")
async def delete_competitor(
    competitor_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """删除竞品门店"""
    success = await competitive_analysis_service.delete_competitor(competitor_id)
    if not success:
        raise HTTPException(status_code=404, detail="竞品门店不存在")
    return {"success": True, "message": "竞品门店已删除"}


# ------------------------------------------------------------------ #
# 竞品价格管理                                                          #
# ------------------------------------------------------------------ #

@router.get("/competitors/{competitor_id}/prices")
async def get_competitor_prices(
    competitor_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
):
    """获取竞品价格记录"""
    records = await competitive_analysis_service.get_price_records(
        competitor_id=competitor_id,
        start_date=start_date,
        end_date=end_date,
    )
    return {"prices": [r.to_dict() for r in records], "total": len(records)}


@router.post("/competitors/{competitor_id}/prices", status_code=201)
async def add_price_record(
    competitor_id: str,
    request: PriceRecordRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.ASSISTANT_MANAGER)),
):
    """
    录入竞品价格

    定期录入竞品菜品价格，用于价格对比和敏感度分析。
    """
    # 验证竞品存在
    competitor = await competitive_analysis_service.get_competitor(competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品门店不存在")

    record = await competitive_analysis_service.add_price_record(
        competitor_id=competitor_id,
        dish_name=request.dish_name,
        price=request.price,
        record_date=request.record_date,
        category=request.category,
        our_dish_id=request.our_dish_id,
    )
    return record.to_dict()


# ------------------------------------------------------------------ #
# 分析端点                                                              #
# ------------------------------------------------------------------ #

@router.get("/market-share")
async def analyze_market_share(
    store_id: str = Query(..., description="我方门店ID"),
    start_date: Optional[date] = Query(None, description="开始日期（默认近30天）"),
    end_date: Optional[date] = Query(None, description="结束日期（默认今天）"),
    current_user: User = Depends(get_current_active_user),
):
    """
    市场份额分析

    基于我方实际营收和竞品估算营收，计算市场份额占比。

    **注意**：竞品营收为估算值，需要先录入竞品的月均客流量和人均消费。
    """
    try:
        result = await competitive_analysis_service.analyze_market_share(
            our_store_id=store_id,
            start_date=start_date,
            end_date=end_date,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-comparison")
async def compare_prices(
    store_id: str = Query(..., description="我方门店ID"),
    category: Optional[str] = Query(None, description="菜品分类过滤"),
    current_user: User = Depends(get_current_active_user),
):
    """
    竞品价格对比

    对比我方菜品与竞品同类菜品的价格差异，计算与市场均价的偏差。

    **前提**：需要先录入竞品价格记录。
    """
    try:
        result = await competitive_analysis_service.compare_prices(
            our_store_id=store_id,
            category=category,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-sensitivity")
async def analyze_price_sensitivity(
    store_id: str = Query(..., description="我方门店ID"),
    days: int = Query(90, ge=7, le=365, description="分析天数"),
    current_user: User = Depends(get_current_active_user),
):
    """
    价格敏感度分析

    分析我方菜品价格分布，与市场均价对比，识别定价偏高的菜品，
    并给出调价建议。
    """
    try:
        result = await competitive_analysis_service.analyze_price_sensitivity(
            our_store_id=store_id,
            days=days,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
