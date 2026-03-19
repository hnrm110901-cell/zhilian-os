"""
DishMaster API — 集团菜品主档管理

端点：
  GET   /api/v1/dish-master/                  查询集团主档列表（支持 brand_id / is_active 过滤）
  POST  /api/v1/dish-master/                  创建新 SKU 主档
  GET   /api/v1/dish-master/{dish_master_id}  查询主档详情
  PATCH /api/v1/dish-master/{dish_master_id}  更新主档信息

  GET   /api/v1/dish-master/{dish_master_id}/brand-menus   查询品牌层价格配置
  POST  /api/v1/dish-master/{dish_master_id}/brand-menus   创建品牌层价格配置
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.dish_master import BrandMenu, DishMaster
from src.models.user import User

router = APIRouter(prefix="/api/v1/dish-master", tags=["dish-master"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class DishMasterCreate(BaseModel):
    sku_code: str = Field(..., max_length=50, description="集团唯一SKU编码")
    canonical_name: str = Field(..., max_length=200)
    category_name: str = Field(..., max_length=100)
    floor_price: int = Field(0, ge=0, description="最低售价保护（分）")
    allergens: List[str] = Field(default_factory=list)
    brand_id: Optional[str] = Field(None, max_length=50, description="品牌ID，null=全品牌通用")
    is_active: bool = True
    description: Optional[str] = None


class DishMasterPatch(BaseModel):
    canonical_name: Optional[str] = Field(None, max_length=200)
    category_name: Optional[str] = Field(None, max_length=100)
    floor_price: Optional[int] = Field(None, ge=0)
    allergens: Optional[List[str]] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class DishMasterOut(BaseModel):
    id: UUID
    sku_code: str
    canonical_name: str
    category_name: str
    floor_price: int
    allergens: List[str]
    brand_id: Optional[str]
    is_active: bool
    description: Optional[str]

    model_config = {"from_attributes": True}


class BrandMenuCreate(BaseModel):
    brand_id: str = Field(..., max_length=50)
    price_fen: Optional[int] = Field(None, ge=0, description="null=继承主档")
    is_available: bool = True
    notes: Optional[str] = None


class BrandMenuOut(BaseModel):
    id: UUID
    brand_id: str
    dish_master_id: UUID
    price_fen: Optional[int]
    is_available: bool
    notes: Optional[str]

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/", response_model=List[DishMasterOut])
async def list_dish_masters(
    brand_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """查询集团主档列表"""
    q = select(DishMaster)
    if brand_id is not None:
        q = q.where(DishMaster.brand_id == brand_id)
    if is_active is not None:
        q = q.where(DishMaster.is_active == is_active)
    q = q.offset(offset).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("/", response_model=DishMasterOut, status_code=status.HTTP_201_CREATED)
async def create_dish_master(
    body: DishMasterCreate,
    session: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """创建新 SKU 主档"""
    # 唯一性检查
    existing = await session.execute(select(DishMaster).where(DishMaster.sku_code == body.sku_code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"sku_code '{body.sku_code}' 已存在",
        )
    dm = DishMaster(**body.model_dump())
    session.add(dm)
    await session.commit()
    await session.refresh(dm)
    return dm


@router.get("/{dish_master_id}", response_model=DishMasterOut)
async def get_dish_master(
    dish_master_id: UUID,
    session: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """查询主档详情"""
    result = await session.execute(select(DishMaster).where(DishMaster.id == dish_master_id))
    dm = result.scalar_one_or_none()
    if dm is None:
        raise HTTPException(status_code=404, detail="DishMaster not found")
    return dm


@router.patch("/{dish_master_id}", response_model=DishMasterOut)
async def patch_dish_master(
    dish_master_id: UUID,
    body: DishMasterPatch,
    session: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """更新主档信息（部分更新）"""
    result = await session.execute(select(DishMaster).where(DishMaster.id == dish_master_id))
    dm = result.scalar_one_or_none()
    if dm is None:
        raise HTTPException(status_code=404, detail="DishMaster not found")
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(dm, field_name, value)
    await session.commit()
    await session.refresh(dm)
    return dm


@router.get("/{dish_master_id}/brand-menus", response_model=List[BrandMenuOut])
async def list_brand_menus(
    dish_master_id: UUID,
    session: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """查询品牌层价格配置列表"""
    result = await session.execute(select(BrandMenu).where(BrandMenu.dish_master_id == dish_master_id))
    return result.scalars().all()


@router.post(
    "/{dish_master_id}/brand-menus",
    response_model=BrandMenuOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand_menu(
    dish_master_id: UUID,
    body: BrandMenuCreate,
    session: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """创建品牌层价格配置"""
    # 确认主档存在
    dm_result = await session.execute(select(DishMaster).where(DishMaster.id == dish_master_id))
    if dm_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="DishMaster not found")

    # 重复检查
    existing = await session.execute(
        select(BrandMenu).where(
            BrandMenu.dish_master_id == dish_master_id,
            BrandMenu.brand_id == body.brand_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"brand_id '{body.brand_id}' 已有该 SKU 的品牌配置",
        )

    bm = BrandMenu(dish_master_id=dish_master_id, **body.model_dump())
    session.add(bm)
    await session.commit()
    await session.refresh(bm)
    return bm
