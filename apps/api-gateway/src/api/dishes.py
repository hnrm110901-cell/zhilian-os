"""
菜品管理API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID

from src.services.dish_service import DishService, DishCategoryService
from src.core.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/dishes", tags=["dishes"])


# Pydantic模型
class DishCategoryCreate(BaseModel):
    name: str = Field(..., description="分类名称")
    code: Optional[str] = Field(None, description="分类编码")
    parent_id: Optional[UUID] = Field(None, description="父分类ID")
    sort_order: int = Field(0, description="排序")
    description: Optional[str] = Field(None, description="描述")


class DishCategoryResponse(BaseModel):
    id: UUID
    name: str
    code: Optional[str]
    parent_id: Optional[UUID]
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class DishCreate(BaseModel):
    name: str = Field(..., description="菜品名称")
    code: str = Field(..., description="菜品编码")
    category_id: Optional[UUID] = Field(None, description="分类ID")
    description: Optional[str] = Field(None, description="描述")
    image_url: Optional[str] = Field(None, description="图片URL")
    price: float = Field(..., description="售价")
    original_price: Optional[float] = Field(None, description="原价")
    cost: Optional[float] = Field(None, description="成本")
    unit: str = Field("份", description="单位")
    serving_size: Optional[str] = Field(None, description="规格")
    spicy_level: int = Field(0, description="辣度等级")
    tags: Optional[List[str]] = Field(None, description="标签")
    is_available: bool = Field(True, description="是否可售")
    is_recommended: bool = Field(False, description="是否推荐")
    preparation_time: Optional[int] = Field(None, description="制作时间（分钟）")


class DishUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[UUID] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    cost: Optional[float] = None
    is_available: Optional[bool] = None
    is_recommended: Optional[bool] = None
    tags: Optional[List[str]] = None


class DishResponse(BaseModel):
    id: UUID
    name: str
    code: str
    category_id: Optional[UUID]
    price: float
    cost: Optional[float]
    profit_margin: Optional[float]
    unit: str
    is_available: bool
    is_recommended: bool
    total_sales: int
    rating: Optional[float]

    class Config:
        from_attributes = True


class DishIngredientAdd(BaseModel):
    ingredient_id: UUID = Field(..., description="食材ID")
    quantity: float = Field(..., description="用量")
    unit: str = Field(..., description="单位")
    is_required: bool = Field(True, description="是否必需")


# API端点
@router.post("/categories", response_model=DishCategoryResponse)
async def create_category(
    category_data: DishCategoryCreate,
    current_user: User = Depends(get_current_user),
):
    """创建菜品分类"""
    service = DishCategoryService()
    category = await service.create_category(category_data.dict())
    return category


@router.get("/categories", response_model=List[DishCategoryResponse])
async def list_categories(
    current_user: User = Depends(get_current_user),
):
    """获取菜品分类列表"""
    service = DishCategoryService()
    categories = await service.list_categories()
    return categories


@router.post("", response_model=DishResponse)
async def create_dish(
    dish_data: DishCreate,
    current_user: User = Depends(get_current_user),
):
    """创建菜品"""
    service = DishService()
    dish = await service.create_dish(dish_data.dict())
    return dish


@router.get("", response_model=List[DishResponse])
async def list_dishes(
    category_id: Optional[UUID] = Query(None, description="分类ID"),
    is_available: Optional[bool] = Query(None, description="是否可售"),
    is_recommended: Optional[bool] = Query(None, description="是否推荐"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """获取菜品列表"""
    service = DishService()
    dishes = await service.list_dishes(
        category_id=str(category_id) if category_id else None,
        is_available=is_available,
        is_recommended=is_recommended,
        search=search,
        limit=limit,
        offset=offset,
    )
    return dishes


@router.get("/{dish_id}", response_model=DishResponse)
async def get_dish(
    dish_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """获取菜品详情"""
    service = DishService()
    dish = await service.get_dish(str(dish_id))

    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")

    return dish


@router.put("/{dish_id}", response_model=DishResponse)
async def update_dish(
    dish_id: UUID,
    dish_data: DishUpdate,
    current_user: User = Depends(get_current_user),
):
    """更新菜品"""
    service = DishService()
    dish = await service.update_dish(
        str(dish_id),
        dish_data.dict(exclude_unset=True)
    )

    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")

    return dish


@router.delete("/{dish_id}")
async def delete_dish(
    dish_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """删除菜品"""
    service = DishService()
    success = await service.delete_dish(str(dish_id))

    if not success:
        raise HTTPException(status_code=404, detail="Dish not found")

    return {"message": "Dish deleted successfully"}


@router.post("/{dish_id}/ingredients")
async def add_ingredient(
    dish_id: UUID,
    ingredient_data: DishIngredientAdd,
    current_user: User = Depends(get_current_user),
):
    """为菜品添加食材"""
    service = DishService()

    try:
        dish_ingredient = await service.add_ingredient(
            str(dish_id),
            str(ingredient_data.ingredient_id),
            ingredient_data.quantity,
            ingredient_data.unit,
            is_required=ingredient_data.is_required,
        )
        return {"message": "Ingredient added successfully", "id": str(dish_ingredient.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{dish_id}/cost-breakdown")
async def get_cost_breakdown(
    dish_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """获取菜品成本分解"""
    service = DishService()
    breakdown = await service.get_dish_cost_breakdown(str(dish_id))

    if not breakdown:
        raise HTTPException(status_code=404, detail="Dish not found")

    return breakdown


@router.get("/popular/top")
async def get_popular_dishes(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """获取热门菜品"""
    service = DishService()
    popular_dishes = await service.get_popular_dishes(limit=limit)
    return popular_dishes
