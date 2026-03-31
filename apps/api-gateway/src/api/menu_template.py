"""
集团菜单模板 + 多渠道定价 API

端点列表：
  POST /api/v1/menu-templates                          # 创建模板
  GET  /api/v1/menu-templates                          # 品牌模板列表
  POST /api/v1/menu-templates/{id}/items               # 添加菜品到模板
  POST /api/v1/menu-templates/{id}/publish             # 发布到门店
  GET  /api/v1/stores/{store_id}/effective-menu        # 获取有效菜单
  PUT  /api/v1/stores/{store_id}/dish-overrides/{item_id}  # 门店覆盖设置
  POST /api/v1/channel-prices                          # 设置渠道价格
  GET  /api/v1/stores/{store_id}/channel-prices        # 查看渠道价格
  POST /api/v1/time-period-prices                      # 设置时段规则
  GET  /api/v1/price-lookup                            # 价格查询
  GET  /api/v1/menu-templates/coverage/{brand_id}      # 覆盖率统计
"""

from datetime import datetime, time
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.menu_template_service import MenuTemplateService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["menu-templates"])


# ================================================================== #
#  请求 / 响应 Pydantic 模型                                             #
# ================================================================== #


class CreateTemplateRequest(BaseModel):
    """创建菜单模板请求"""

    brand_id: str = Field(..., description="品牌ID（UUID）")
    creator_id: str = Field(..., description="创建人ID（UUID）")
    name: str = Field(..., min_length=1, max_length=200, description="模板名称")


class AddTemplateItemRequest(BaseModel):
    """向模板添加菜品请求"""

    dish_master_id: str = Field(..., description="集团菜品主档ID（UUID）")
    base_price_fen: int = Field(..., ge=0, description="基准价格（分）")
    category: str = Field("", max_length=100, description="分类名称")
    allow_adjust: bool = Field(True, description="是否允许门店调价")
    max_adjust_rate: float = Field(0.2, ge=0, le=1.0, description="最大调价幅度，如 0.2=20%")
    is_required: bool = Field(False, description="是否为总部强制菜品")


class PublishTemplateRequest(BaseModel):
    """发布模板请求"""

    publisher_id: str = Field(..., description="发布人ID（UUID）")
    target_store_ids: Optional[List[str]] = Field(
        None, description="目标门店ID列表，不传则使用当前门店"
    )


class DishOverrideRequest(BaseModel):
    """门店菜品覆盖请求"""

    custom_price_fen: Optional[int] = Field(None, ge=0, description="自定义价格（分），None=继承模板价")
    is_available: bool = Field(True, description="是否上架")
    custom_name: Optional[str] = Field(None, max_length=200, description="自定义名称")


class ChannelPriceRequest(BaseModel):
    """设置渠道价格请求"""

    store_id: str = Field(..., description="门店ID（UUID）")
    dish_id: str = Field(..., description="菜品ID（UUID）")
    channel: str = Field(..., description="渠道（dine_in/meituan/eleme/douyin/miniprogram/corporate）")
    price_fen: int = Field(..., ge=0, description="渠道价格（分）")


class TimePeriodPriceRequest(BaseModel):
    """创建时段定价规则请求"""

    store_id: str = Field(..., description="门店ID（UUID）")
    name: str = Field(..., min_length=1, max_length=100, description="规则名称")
    period_type: str = Field(
        ...,
        description="时段类型（lunch/dinner/breakfast/late_night/holiday/weekend）",
    )
    start_time: str = Field(..., description="开始时间（HH:MM 格式）")
    end_time: str = Field(..., description="结束时间（HH:MM 格式）")
    weekdays: List[int] = Field(..., description="适用星期列表（1-7，1=周一）")
    discount_rate: Optional[float] = Field(None, ge=0, le=1.0, description="折扣率，如 0.8=八折")
    fixed_prices: Optional[Dict[str, int]] = Field(
        None, description="固定价格映射 {dish_id: price_fen}"
    )


# ================================================================== #
#  路由处理函数                                                           #
# ================================================================== #


@router.post("/menu-templates", summary="创建菜单模板")
async def create_menu_template(request: CreateTemplateRequest) -> Dict[str, Any]:
    """创建草稿状态的菜单模板"""
    try:
        service = MenuTemplateService()
        result = await service.create_template(
            brand_id=request.brand_id,
            creator_id=request.creator_id,
            name=request.name,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("创建菜单模板失败", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/menu-templates", summary="品牌模板列表")
async def list_menu_templates(
    brand_id: str = Query(..., description="品牌ID（UUID）"),
) -> Dict[str, Any]:
    """获取品牌下所有菜单模板及覆盖率统计"""
    try:
        service = MenuTemplateService()
        result = await service.get_template_coverage(brand_id=brand_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("查询模板列表失败", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/menu-templates/{template_id}/items", summary="添加菜品到模板")
async def add_template_item(
    template_id: str, request: AddTemplateItemRequest
) -> Dict[str, Any]:
    """向指定模板添加菜品条目"""
    try:
        service = MenuTemplateService()
        result = await service.add_template_item(
            template_id=template_id,
            dish_master_id=request.dish_master_id,
            base_price_fen=request.base_price_fen,
            category=request.category,
            allow_adjust=request.allow_adjust,
            max_adjust_rate=request.max_adjust_rate,
            is_required=request.is_required,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("添加模板菜品失败", template_id=template_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/menu-templates/{template_id}/publish", summary="发布模板到门店")
async def publish_template(
    template_id: str, request: PublishTemplateRequest
) -> Dict[str, Any]:
    """将草稿模板发布到一个或多个门店"""
    try:
        service = MenuTemplateService()
        result = await service.publish_template(
            template_id=template_id,
            publisher_id=request.publisher_id,
            target_store_ids=request.target_store_ids,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error("发布模板失败", template_id=template_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stores/{store_id}/effective-menu", summary="获取门店有效菜单")
async def get_effective_menu(
    store_id: str,
    channel: str = Query("dine_in", description="渠道"),
    time_str: Optional[str] = Query(None, alias="time", description="时间（ISO格式，默认当前时间）"),
) -> Dict[str, Any]:
    """
    获取门店在指定渠道和时间点的有效菜单。
    价格已按四级优先级计算（时段 > 渠道 > 门店覆盖 > 模板基准）。
    """
    try:
        current_time = None
        if time_str:
            try:
                current_time = datetime.fromisoformat(time_str)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"时间格式无效，请使用 ISO 格式: {time_str}"
                )

        service = MenuTemplateService(store_id=store_id)
        menu = await service.get_store_effective_menu(
            store_id=store_id, channel=channel, current_time=current_time
        )
        return {"success": True, "store_id": store_id, "channel": channel, "data": menu}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取有效菜单失败", store_id=store_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/stores/{store_id}/dish-overrides/{template_item_id}",
    summary="门店菜品覆盖设置",
)
async def store_override_dish(
    store_id: str, template_item_id: str, request: DishOverrideRequest
) -> Dict[str, Any]:
    """门店对模板菜品进行个性化设置（价格/上下架/名称）"""
    try:
        service = MenuTemplateService(store_id=store_id)
        result = await service.store_override_dish(
            store_id=store_id,
            template_item_id=template_item_id,
            custom_price_fen=request.custom_price_fen,
            is_available=request.is_available,
            custom_name=request.custom_name,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("门店菜品覆盖失败", store_id=store_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/channel-prices", summary="设置渠道价格")
async def set_channel_price(request: ChannelPriceRequest) -> Dict[str, Any]:
    """设置或更新指定门店菜品的渠道价格（upsert）"""
    try:
        service = MenuTemplateService(store_id=request.store_id)
        result = await service.set_channel_price(
            store_id=request.store_id,
            dish_id=request.dish_id,
            channel=request.channel,
            price_fen=request.price_fen,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("设置渠道价格失败", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stores/{store_id}/channel-prices", summary="查看渠道价格列表")
async def get_channel_prices(
    store_id: str,
    dish_id: Optional[str] = Query(None, description="按菜品ID过滤"),
    channel: Optional[str] = Query(None, description="按渠道过滤"),
) -> Dict[str, Any]:
    """查询门店渠道定价配置"""
    try:
        from sqlalchemy import and_, select

        from src.core.database import get_db_session
        from src.models.channel_pricing import DishChannelPrice
        import uuid as _uuid

        store_uuid = _uuid.UUID(str(store_id))
        conditions = [DishChannelPrice.store_id == store_uuid]
        if dish_id:
            conditions.append(DishChannelPrice.dish_id == _uuid.UUID(str(dish_id)))
        if channel:
            conditions.append(DishChannelPrice.channel == channel)

        async with get_db_session() as session:
            result = await session.execute(
                select(DishChannelPrice).where(and_(*conditions))
            )
            prices = result.scalars().all()

        data = [
            {
                "id": str(p.id),
                "store_id": str(p.store_id),
                "dish_id": str(p.dish_id),
                "channel": p.channel,
                "price_fen": p.price_fen,
                "is_active": p.is_active,
            }
            for p in prices
        ]
        return {"success": True, "store_id": store_id, "data": data}
    except Exception as e:
        logger.error("查询渠道价格失败", store_id=store_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/time-period-prices", summary="设置时段定价规则")
async def set_time_period_price(request: TimePeriodPriceRequest) -> Dict[str, Any]:
    """创建时段定价规则（午市/晚市/早餐/深夜/节假日/周末）"""
    try:
        # 解析时间字符串
        try:
            start_t = time.fromisoformat(request.start_time)
            end_t = time.fromisoformat(request.end_time)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"时间格式无效（HH:MM），请检查 start_time/end_time: {e}",
            )

        service = MenuTemplateService(store_id=request.store_id)
        result = await service.set_time_period_price(
            store_id=request.store_id,
            name=request.name,
            period_type=request.period_type,
            start_time=start_t,
            end_time=end_t,
            weekdays=request.weekdays,
            discount_rate=request.discount_rate,
            fixed_prices=request.fixed_prices,
        )
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("设置时段定价规则失败", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/price-lookup", summary="单菜品实时价格查询")
async def price_lookup(
    store_id: str = Query(..., description="门店ID"),
    dish_id: str = Query(..., description="菜品ID"),
    channel: str = Query("dine_in", description="渠道"),
    time_str: Optional[str] = Query(None, alias="time", description="时间（ISO格式，默认当前时间）"),
) -> Dict[str, Any]:
    """查询指定门店菜品在指定渠道和时间点的实时有效价格"""
    try:
        timestamp = None
        if time_str:
            try:
                timestamp = datetime.fromisoformat(time_str)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"时间格式无效: {time_str}"
                )

        service = MenuTemplateService(store_id=store_id)
        price_fen = await service.get_effective_price(
            store_id=store_id,
            dish_id=dish_id,
            channel=channel,
            timestamp=timestamp,
        )
        return {
            "success": True,
            "store_id": store_id,
            "dish_id": dish_id,
            "channel": channel,
            "price_fen": price_fen,
            "price_yuan": round(price_fen / 100, 2),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("价格查询失败", store_id=store_id, dish_id=dish_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/menu-templates/coverage/{brand_id}", summary="品牌模板覆盖率统计")
async def get_template_coverage(brand_id: str) -> Dict[str, Any]:
    """查询品牌的菜单模板覆盖情况（已部署/未部署门店数）"""
    try:
        service = MenuTemplateService()
        result = await service.get_template_coverage(brand_id=brand_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("查询覆盖率失败", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
