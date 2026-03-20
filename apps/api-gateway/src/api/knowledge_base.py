"""餐饮行业知识库 API — BOM配方 / 成本基准 / 定价策略 / 菜品知识库 / 行业字典。

路由前缀: /api/v1/knowledge-base
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.models.knowledge_base import (
    BOMRecipe,
    BOMRecipeItem,
    BOMRecipeProcessStep,
    CostBenchmark,
    CostBenchmarkItem,
    DishKnowledge,
    IndustryDictionary,
    PricingStrategy,
    PricingDishRule,
    PromotionRule,
    CouponTemplate,
)

router = APIRouter(prefix="/api/v1/knowledge-base", tags=["知识库"])


# ═══════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════


class DictItemOut(BaseModel):
    """行业字典项输出。"""
    id: UUID
    dict_type: str
    dict_code: str
    dict_name_zh: str
    dict_name_en: Optional[str] = None
    parent_code: Optional[str] = None
    level: int
    sort_order: int
    description: Optional[str] = None
    children: list["DictItemOut"] = []

    class Config:
        from_attributes = True


class DishKnowledgeOut(BaseModel):
    """菜品知识库简要输出。"""
    id: UUID
    dish_code: str
    dish_name_zh: str
    dish_name_en: Optional[str] = None
    cuisine_region: str
    category_l1: str
    category_l2: Optional[str] = None
    main_ingredient_group: Optional[str] = None
    cooking_method: Optional[str] = None
    taste_profile_primary: Optional[str] = None
    spicy_level: Optional[int] = None
    is_signature: Optional[bool] = False
    is_chain_friendly: Optional[bool] = True
    standardization_level: Optional[str] = None
    dine_in_fit: Optional[int] = None
    takeaway_fit: Optional[int] = None

    class Config:
        from_attributes = True


class DishKnowledgeDetailOut(DishKnowledgeOut):
    """菜品知识库详细输出。"""
    alias_names: Optional[list[str]] = None
    dish_status: str = "active"
    cuisine_country: Optional[str] = None
    category_l3: Optional[str] = None
    dish_type: Optional[str] = None
    serving_temp: Optional[str] = None
    taste_profile_secondary: Optional[list[str]] = None
    texture_profile: Optional[list[str]] = None
    color_profile: Optional[str] = None
    plating_style: Optional[str] = None
    is_classic: Optional[bool] = False
    prep_complexity: Optional[str] = None
    catering_fit: Optional[int] = None
    breakfast_fit: Optional[int] = None
    lunch_fit: Optional[int] = None
    dinner_fit: Optional[int] = None
    supper_fit: Optional[int] = None
    seasonality: Optional[str] = None
    allergen_flags: Optional[list[str]] = None
    dietary_flags: Optional[list[str]] = None
    culture_story: Optional[str] = None
    search_keywords: Optional[list[str]] = None


class BOMRecipeOut(BaseModel):
    """BOM配方简要输出。"""
    id: UUID
    recipe_code: str
    recipe_name: str
    recipe_type: str
    cuisine_type: Optional[str] = None
    status: str
    version_no: int
    standard_cost: Optional[float] = None
    channel_scope: str = "all"

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    """分页响应。"""
    items: list[Any]
    total: int
    page: int
    page_size: int


class DishKnowledgeCreateIn(BaseModel):
    """创建菜品知识库条目。"""
    dish_code: str
    dish_name_zh: str
    dish_name_en: Optional[str] = None
    alias_names: Optional[list[str]] = None
    cuisine_country: str = "中国"
    cuisine_region: str
    category_l1: str
    category_l2: Optional[str] = None
    category_l3: Optional[str] = None
    main_ingredient_group: Optional[str] = None
    dish_type: str = "a_la_carte"
    cooking_method: Optional[str] = None
    taste_profile_primary: Optional[str] = None
    spicy_level: Optional[int] = None
    is_signature: bool = False
    is_classic: bool = False
    is_chain_friendly: bool = True
    standardization_level: Optional[str] = None
    prep_complexity: Optional[str] = None


class DictBatchCreateIn(BaseModel):
    """批量创建行业字典项。"""
    items: list[dict]


# ═══════════════════════════════════════════════════
# 行业字典 API
# ═══════════════════════════════════════════════════


@router.get("/dictionaries", summary="获取行业字典(按类型)")
async def list_dictionaries(
    dict_type: str = Query(..., description="字典类型: dish_category/cuisine/cooking_method/flavor/..."),
    db: AsyncSession = Depends(get_db),
) -> list[DictItemOut]:
    """获取指定类型的行业字典树形结构。"""
    result = await db.execute(
        select(IndustryDictionary)
        .where(
            and_(
                IndustryDictionary.dict_type == dict_type,
                IndustryDictionary.is_active.is_(True),
            )
        )
        .order_by(IndustryDictionary.level, IndustryDictionary.sort_order)
    )
    items = result.scalars().all()

    # 构建树形结构
    by_code: dict[str, DictItemOut] = {}
    roots: list[DictItemOut] = []

    for item in items:
        node = DictItemOut.model_validate(item)
        by_code[item.dict_code] = node

    for item in items:
        node = by_code[item.dict_code]
        if item.parent_code and item.parent_code in by_code:
            by_code[item.parent_code].children.append(node)
        else:
            roots.append(node)

    return roots


@router.get("/dictionaries/flat", summary="获取行业字典(平铺)")
async def list_dictionaries_flat(
    dict_type: Optional[str] = Query(None, description="字典类型(不传返回全部)"),
    level: Optional[int] = Query(None, description="层级筛选"),
    db: AsyncSession = Depends(get_db),
) -> list[DictItemOut]:
    """获取行业字典平铺列表。"""
    query = select(IndustryDictionary).where(IndustryDictionary.is_active.is_(True))
    if dict_type:
        query = query.where(IndustryDictionary.dict_type == dict_type)
    if level:
        query = query.where(IndustryDictionary.level == level)
    query = query.order_by(IndustryDictionary.dict_type, IndustryDictionary.sort_order)

    result = await db.execute(query)
    return [DictItemOut.model_validate(r) for r in result.scalars().all()]


@router.get("/dictionaries/types", summary="获取所有字典类型")
async def list_dictionary_types(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """获取所有可用的字典类型及其条目数量。"""
    result = await db.execute(
        select(
            IndustryDictionary.dict_type,
            func.count(IndustryDictionary.id).label("count"),
        )
        .where(IndustryDictionary.is_active.is_(True))
        .group_by(IndustryDictionary.dict_type)
        .order_by(IndustryDictionary.dict_type)
    )
    return [{"dict_type": row[0], "count": row[1]} for row in result.all()]


# ═══════════════════════════════════════════════════
# 菜品知识库 API
# ═══════════════════════════════════════════════════


@router.get("/dishes", summary="菜品知识库列表")
async def list_dish_knowledge(
    keyword: Optional[str] = Query(None, description="关键词搜索(名称/别名)"),
    cuisine_region: Optional[str] = Query(None, description="菜系"),
    category_l1: Optional[str] = Query(None, description="一级分类"),
    category_l2: Optional[str] = Query(None, description="二级分类"),
    cooking_method: Optional[str] = Query(None, description="烹饪方法"),
    is_chain_friendly: Optional[bool] = Query(None, description="是否适合连锁"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """分页查询菜品知识库。"""
    query = select(DishKnowledge).where(DishKnowledge.dish_status == "active")

    if keyword:
        query = query.where(DishKnowledge.dish_name_zh.ilike(f"%{keyword}%"))
    if cuisine_region:
        query = query.where(DishKnowledge.cuisine_region == cuisine_region)
    if category_l1:
        query = query.where(DishKnowledge.category_l1 == category_l1)
    if category_l2:
        query = query.where(DishKnowledge.category_l2 == category_l2)
    if cooking_method:
        query = query.where(DishKnowledge.cooking_method == cooking_method)
    if is_chain_friendly is not None:
        query = query.where(DishKnowledge.is_chain_friendly == is_chain_friendly)

    # 总数
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # 分页
    result = await db.execute(
        query.order_by(DishKnowledge.cuisine_region, DishKnowledge.dish_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [DishKnowledgeOut.model_validate(r) for r in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/dishes/{dish_id}", summary="菜品知识库详情")
async def get_dish_knowledge(
    dish_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DishKnowledgeDetailOut:
    """获取菜品知识库详细信息。"""
    result = await db.execute(
        select(DishKnowledge).where(DishKnowledge.id == dish_id)
    )
    dish = result.scalar_one_or_none()
    if not dish:
        raise HTTPException(status_code=404, detail="菜品不存在")
    return DishKnowledgeDetailOut.model_validate(dish)


@router.post("/dishes", summary="创建菜品知识库条目")
async def create_dish_knowledge(
    data: DishKnowledgeCreateIn,
    db: AsyncSession = Depends(get_db),
) -> DishKnowledgeDetailOut:
    """创建新的菜品知识库条目。"""
    dish = DishKnowledge(**data.model_dump())
    db.add(dish)
    await db.commit()
    await db.refresh(dish)
    return DishKnowledgeDetailOut.model_validate(dish)


# ═══════════════════════════════════════════════════
# BOM 配方 API
# ═══════════════════════════════════════════════════


@router.get("/bom/recipes", summary="BOM配方列表")
async def list_bom_recipes(
    keyword: Optional[str] = Query(None),
    recipe_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """分页查询BOM配方。"""
    query = select(BOMRecipe).where(BOMRecipe.is_deleted.is_(False))

    if keyword:
        query = query.where(BOMRecipe.recipe_name.ilike(f"%{keyword}%"))
    if recipe_type:
        query = query.where(BOMRecipe.recipe_type == recipe_type)
    if status:
        query = query.where(BOMRecipe.status == status)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(BOMRecipe.recipe_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [BOMRecipeOut.model_validate(r) for r in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/bom/recipes/{recipe_id}", summary="BOM配方详情(含明细)")
async def get_bom_recipe(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取BOM配方详情，含物料明细和工艺步骤。"""
    result = await db.execute(
        select(BOMRecipe)
        .options(
            selectinload(BOMRecipe.items),
            selectinload(BOMRecipe.process_steps),
            selectinload(BOMRecipe.serving_standard),
            selectinload(BOMRecipe.storage_rule),
        )
        .where(BOMRecipe.id == recipe_id)
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="配方不存在")

    return {
        "id": str(recipe.id),
        "recipe_code": recipe.recipe_code,
        "recipe_name": recipe.recipe_name,
        "recipe_type": recipe.recipe_type,
        "status": recipe.status,
        "version_no": recipe.version_no,
        "channel_scope": recipe.channel_scope,
        "output_qty": float(recipe.output_qty) if recipe.output_qty else None,
        "output_unit": recipe.output_unit,
        "standard_cost": float(recipe.standard_cost) if recipe.standard_cost else None,
        "items": [
            {
                "line_no": item.line_no,
                "material_name": item.material_name,
                "material_type": item.material_type,
                "net_qty": float(item.net_qty) if item.net_qty else None,
                "base_unit": item.base_unit,
                "is_key_material": item.is_key_material,
            }
            for item in sorted(recipe.items, key=lambda x: x.sort_order)
        ],
        "process_steps": [
            {
                "line_no": step.line_no,
                "process_stage": step.process_stage,
                "step_name": step.step_name,
                "step_desc": step.step_desc,
                "is_ccp": step.is_ccp,
                "target_temp": float(step.target_temp) if step.target_temp else None,
                "target_time_sec": step.target_time_sec,
            }
            for step in sorted(recipe.process_steps, key=lambda x: x.sort_order)
        ],
        "serving_standard": {
            "portion_weight": float(recipe.serving_standard.portion_weight) if recipe.serving_standard and recipe.serving_standard.portion_weight else None,
            "serving_temp": float(recipe.serving_standard.serving_temp) if recipe.serving_standard and recipe.serving_standard.serving_temp else None,
            "plating_desc": recipe.serving_standard.plating_desc if recipe.serving_standard else None,
        } if recipe.serving_standard else None,
        "storage_rule": {
            "shelf_life_hours": recipe.storage_rule.shelf_life_hours if recipe.storage_rule else None,
            "hold_time_minutes": recipe.storage_rule.hold_time_minutes if recipe.storage_rule else None,
            "discard_rule": recipe.storage_rule.discard_rule if recipe.storage_rule else None,
        } if recipe.storage_rule else None,
    }


# ═══════════════════════════════════════════════════
# 统计概览 API
# ═══════════════════════════════════════════════════


@router.get("/stats", summary="知识库统计概览")
async def knowledge_base_stats(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回知识库各模块的统计数据。"""
    dish_count = await db.execute(
        select(func.count(DishKnowledge.id))
        .where(DishKnowledge.dish_status == "active")
    )
    recipe_count = await db.execute(
        select(func.count(BOMRecipe.id))
        .where(BOMRecipe.is_deleted.is_(False))
    )
    dict_count = await db.execute(
        select(func.count(IndustryDictionary.id))
        .where(IndustryDictionary.is_active.is_(True))
    )
    benchmark_count = await db.execute(
        select(func.count(CostBenchmark.id))
        .where(CostBenchmark.is_deleted.is_(False))
    )
    strategy_count = await db.execute(
        select(func.count(PricingStrategy.id))
        .where(PricingStrategy.is_deleted.is_(False))
    )

    return {
        "dish_knowledge_count": dish_count.scalar() or 0,
        "bom_recipe_count": recipe_count.scalar() or 0,
        "industry_dictionary_count": dict_count.scalar() or 0,
        "cost_benchmark_count": benchmark_count.scalar() or 0,
        "pricing_strategy_count": strategy_count.scalar() or 0,
    }


# ═══════════════════════════════════════════════════
# 种子数据初始化 API
# ═══════════════════════════════════════════════════


@router.post("/seed/dictionary", summary="初始化行业字典种子数据")
async def seed_dictionary(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """写入行业字典预置数据（幂等，已存在的不重复写入）。"""
    from src.models.knowledge_base.seed_data import ALL_SEED_DATA
    import uuid as _uuid

    inserted = 0
    skipped = 0

    for item in ALL_SEED_DATA:
        dict_type, dict_code, dict_name_zh, dict_name_en, parent_code, level, sort_order = item

        # 检查是否已存在
        exists = await db.execute(
            select(IndustryDictionary.id).where(
                and_(
                    IndustryDictionary.dict_type == dict_type,
                    IndustryDictionary.dict_code == dict_code,
                )
            )
        )
        if exists.scalar_one_or_none():
            skipped += 1
            continue

        entry = IndustryDictionary(
            id=_uuid.uuid4(),
            dict_type=dict_type,
            dict_code=dict_code,
            dict_name_zh=dict_name_zh,
            dict_name_en=dict_name_en,
            parent_code=parent_code,
            level=level,
            sort_order=sort_order,
            is_active=True,
            is_system=True,
        )
        db.add(entry)
        inserted += 1

    await db.commit()
    return {"inserted": inserted, "skipped": skipped, "total": len(ALL_SEED_DATA)}
