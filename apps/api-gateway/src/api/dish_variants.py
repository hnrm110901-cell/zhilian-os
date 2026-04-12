"""
菜品做法变体 + 多规格 API 端点

路由：
  GET  /api/v1/dishes/{dish_id}/methods       — 获取做法列表
  POST /api/v1/dishes/{dish_id}/methods       — 创建做法
  GET  /api/v1/dishes/{dish_id}/specs         — 获取规格列表
  POST /api/v1/dishes/{dish_id}/specs         — 创建规格
  GET  /api/v1/dishes/{dish_id}/full-options  — 一次性获取做法+规格（点单用）
  GET  /api/v1/dishes/{dish_id}/methods/{method_name}/cost — 计算做法成本
  GET  /api/v1/dishes/{dish_id}/methods/{method_name}/station — KDS 工位路由
  PUT  /api/v1/dish-methods/{variant_id}      — 更新做法
  PUT  /api/v1/dish-specs/{spec_id}           — 更新规格
  PATCH /api/v1/dish-specs/{spec_id}/availability — 切换规格可用性
  POST /api/v1/dishes/{dish_id}/specs/{spec_id}/bom-deduction — 计算BOM扣减
"""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.dish_method_service import DishMethodService
from src.services.dish_specification_service import DishSpecificationService

router = APIRouter(prefix="/dishes", tags=["dish-variants"])


# ── Pydantic 请求/响应模型 ──


class MethodVariantCreate(BaseModel):
    """创建做法变体请求"""
    method_name: str = Field(..., description="做法名称", max_length=50)
    kitchen_station: str = Field(..., description="KDS工位", max_length=50)
    prep_time_minutes: int = Field(10, description="制作时间（分钟）", ge=1)
    bom_template_id: Optional[UUID] = Field(None, description="关联BOM模板ID")
    extra_cost_fen: int = Field(0, description="做法附加费（分）", ge=0)
    is_default: bool = Field(False, description="是否默认做法")
    is_available: bool = Field(True, description="是否可选")
    display_order: int = Field(0, description="排序")
    description: Optional[str] = Field(None, description="做法说明")


class MethodVariantUpdate(BaseModel):
    """更新做法变体请求"""
    method_name: Optional[str] = Field(None, max_length=50)
    kitchen_station: Optional[str] = Field(None, max_length=50)
    prep_time_minutes: Optional[int] = Field(None, ge=1)
    bom_template_id: Optional[UUID] = None
    extra_cost_fen: Optional[int] = Field(None, ge=0)
    is_default: Optional[bool] = None
    is_available: Optional[bool] = None
    display_order: Optional[int] = None
    description: Optional[str] = None


class MethodVariantResponse(BaseModel):
    """做法变体响应"""
    id: UUID
    dish_id: UUID
    method_name: str
    kitchen_station: str
    prep_time_minutes: int
    bom_template_id: Optional[UUID]
    extra_cost_fen: int
    extra_cost_yuan: float = Field(description="¥做法附加费（元）")
    is_default: bool
    is_available: bool
    display_order: int
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class SpecificationCreate(BaseModel):
    """创建规格请求"""
    spec_name: str = Field(..., description="规格名称", max_length=50)
    price_fen: int = Field(..., description="售价（分）", ge=0)
    cost_fen: Optional[int] = Field(None, description="成本（分）", ge=0)
    bom_multiplier: Decimal = Field(
        Decimal("1.00"), description="BOM系数", ge=Decimal("0.01"), le=Decimal("99.99")
    )
    unit: str = Field("份", description="单位", max_length=20)
    min_order_qty: int = Field(1, description="最小点单量", ge=1)
    is_default: bool = Field(False, description="是否默认规格")
    is_available: bool = Field(True, description="是否可选")
    display_order: int = Field(0, description="排序")


class SpecificationUpdate(BaseModel):
    """更新规格请求"""
    spec_name: Optional[str] = Field(None, max_length=50)
    price_fen: Optional[int] = Field(None, ge=0)
    cost_fen: Optional[int] = Field(None, ge=0)
    bom_multiplier: Optional[Decimal] = Field(None, ge=Decimal("0.01"), le=Decimal("99.99"))
    unit: Optional[str] = Field(None, max_length=20)
    min_order_qty: Optional[int] = Field(None, ge=1)
    is_default: Optional[bool] = None
    is_available: Optional[bool] = None
    display_order: Optional[int] = None


class SpecificationResponse(BaseModel):
    """规格响应"""
    id: UUID
    dish_id: UUID
    spec_name: str
    price_fen: int
    price_yuan: float = Field(description="¥售价（元）")
    cost_fen: Optional[int]
    cost_yuan: Optional[float] = Field(None, description="¥成本（元）")
    profit_margin: Optional[float] = Field(None, description="毛利率（%）")
    bom_multiplier: float
    unit: str
    min_order_qty: int
    is_default: bool
    is_available: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)


class CostWithMethodResponse(BaseModel):
    """做法成本响应"""
    base_cost_fen: int
    extra_cost_fen: int
    bom_cost_fen: Optional[int]
    total_cost_fen: int
    total_cost_yuan: float = Field(description="¥总成本（元）")
    method_name: str
    kitchen_station: str
    prep_time_minutes: int


class KitchenStationResponse(BaseModel):
    """KDS 工位响应"""
    kitchen_station: str
    prep_time_minutes: int
    method_name: str


class BomDeductionRequest(BaseModel):
    """BOM 扣减请求"""
    quantity: int = Field(..., description="点单数量", ge=1)


class BomDeductionItem(BaseModel):
    """BOM 扣减明细"""
    ingredient_id: str
    standard_qty: float
    deduction_qty: float
    unit: str
    unit_cost_fen: int
    item_cost_fen: int


class BomDeductionResponse(BaseModel):
    """BOM 扣减响应"""
    spec_name: str
    bom_multiplier: float
    quantity: int
    deductions: List[BomDeductionItem]
    total_cost_fen: int
    total_cost_yuan: float = Field(description="¥总成本（元）")


class FullOptionsResponse(BaseModel):
    """做法+规格完整选项（点单用）"""
    dish_id: UUID
    methods: List[MethodVariantResponse]
    specifications: List[SpecificationResponse]


class AvailabilityToggle(BaseModel):
    """可用性切换请求"""
    is_available: bool


# ── 做法相关端点 ──


@router.get("/{dish_id}/methods", response_model=List[MethodVariantResponse])
async def list_methods(
    dish_id: UUID,
    include_unavailable: bool = Query(False, description="是否包含不可用做法"),
    current_user: User = Depends(get_current_user),
):
    """获取菜品所有做法"""
    service = DishMethodService()
    if include_unavailable:
        methods = await service.get_all_methods_for_dish(dish_id)
    else:
        methods = await service.get_methods_for_dish(dish_id)
    return methods


@router.post("/{dish_id}/methods", response_model=MethodVariantResponse, status_code=201)
async def create_method(
    dish_id: UUID,
    data: MethodVariantCreate,
    current_user: User = Depends(get_current_user),
):
    """创建做法变体"""
    service = DishMethodService()
    try:
        variant = await service.create_method_variant(
            dish_id, data.model_dump(exclude_none=True)
        )
        return variant
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{dish_id}/methods/{method_name}/cost",
    response_model=CostWithMethodResponse,
)
async def get_method_cost(
    dish_id: UUID,
    method_name: str,
    current_user: User = Depends(get_current_user),
):
    """计算含做法的成本"""
    service = DishMethodService()
    try:
        cost_info = await service.calculate_cost_with_method(dish_id, method_name)
        return cost_info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{dish_id}/methods/{method_name}/station",
    response_model=KitchenStationResponse,
)
async def get_kitchen_station(
    dish_id: UUID,
    method_name: str,
    current_user: User = Depends(get_current_user),
):
    """获取做法对应 KDS 工位"""
    service = DishMethodService()
    try:
        station_info = await service.route_to_kitchen_station(dish_id, method_name)
        return station_info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 规格相关端点 ──


@router.get("/{dish_id}/specs", response_model=List[SpecificationResponse])
async def list_specs(
    dish_id: UUID,
    include_unavailable: bool = Query(False, description="是否包含不可用规格"),
    current_user: User = Depends(get_current_user),
):
    """获取菜品所有规格"""
    service = DishSpecificationService()
    if include_unavailable:
        specs = await service.get_all_specs_for_dish(dish_id)
    else:
        specs = await service.get_specs_for_dish(dish_id)
    return specs


@router.post("/{dish_id}/specs", response_model=SpecificationResponse, status_code=201)
async def create_spec(
    dish_id: UUID,
    data: SpecificationCreate,
    current_user: User = Depends(get_current_user),
):
    """创建规格"""
    service = DishSpecificationService()
    try:
        spec = await service.create_spec(dish_id, data.model_dump(exclude_none=True))
        return spec
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{dish_id}/specs/{spec_id}/bom-deduction",
    response_model=BomDeductionResponse,
)
async def calculate_bom_deduction(
    dish_id: UUID,
    spec_id: UUID,
    data: BomDeductionRequest,
    current_user: User = Depends(get_current_user),
):
    """计算 BOM 扣减量"""
    service = DishSpecificationService()
    try:
        result = await service.calculate_bom_deduction(
            dish_id, spec_id, data.quantity
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 点单聚合端点 ──


@router.get("/{dish_id}/full-options", response_model=FullOptionsResponse)
async def get_full_options(
    dish_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """一次性获取做法+规格（点单用）"""
    method_service = DishMethodService()
    spec_service = DishSpecificationService()

    methods = await method_service.get_methods_for_dish(dish_id)
    specs = await spec_service.get_specs_for_dish(dish_id)

    return FullOptionsResponse(
        dish_id=dish_id,
        methods=methods,
        specifications=specs,
    )


# ── 独立资源更新端点（不嵌套在 dishes 下，避免路由冲突） ──

update_router = APIRouter(tags=["dish-variants"])


@update_router.put(
    "/api/v1/dish-methods/{variant_id}",
    response_model=MethodVariantResponse,
)
async def update_method(
    variant_id: UUID,
    data: MethodVariantUpdate,
    current_user: User = Depends(get_current_user),
):
    """更新做法变体"""
    service = DishMethodService()
    variant = await service.update_method_variant(
        variant_id, data.model_dump(exclude_none=True)
    )
    if variant is None:
        raise HTTPException(status_code=404, detail="做法变体不存在")
    return variant


@update_router.put(
    "/api/v1/dish-specs/{spec_id}",
    response_model=SpecificationResponse,
)
async def update_spec(
    spec_id: UUID,
    data: SpecificationUpdate,
    current_user: User = Depends(get_current_user),
):
    """更新规格"""
    service = DishSpecificationService()
    spec = await service.update_spec(spec_id, data.model_dump(exclude_none=True))
    if spec is None:
        raise HTTPException(status_code=404, detail="规格不存在")
    return spec


@update_router.patch(
    "/api/v1/dish-specs/{spec_id}/availability",
    response_model=SpecificationResponse,
)
async def toggle_spec_availability(
    spec_id: UUID,
    data: AvailabilityToggle,
    current_user: User = Depends(get_current_user),
):
    """切换规格可用性"""
    service = DishSpecificationService()
    spec = await service.toggle_availability(spec_id, data.is_available)
    if spec is None:
        raise HTTPException(status_code=404, detail="规格不存在")
    return spec
