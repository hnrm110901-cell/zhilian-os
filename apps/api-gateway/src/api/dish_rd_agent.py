"""
菜品研发 Agent — Phase 10 核心路由
路由前缀：/api/v1/dish-rd

模块：
  菜品主档 CRUD
  配方与版本管理
  成本模拟
  试点管理
  上市管理
  反馈录入
  复盘报告
  Agent 接口（成本仿真/试点推荐/发布助手/风险扫描）
"""
import uuid
from datetime import datetime, date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.models.dish_rd import (
    Dish, DishVersion, IdeaProject, Recipe, RecipeVersion, RecipeItem,
    SOP, CostModel, SupplyAssessment, PilotTest, LaunchProject,
    DishFeedback, RetrospectiveReport, DishRdAgentLog,
    Ingredient, SemiProduct, Supplier,
    DishStatusEnum, DishTypeEnum, RecipeVersionStatusEnum,
    PilotStatusEnum, PilotDecisionEnum, LaunchStatusEnum, LaunchTypeEnum,
    FeedbackSourceEnum, FeedbackTypeEnum, DishRdAgentTypeEnum,
)
import sys
from pathlib import Path as _Path


def _load_dish_rd_agents():
    repo_root = next(
        (p for p in _Path(__file__).resolve().parents if (p / "packages").is_dir()),
        _Path(__file__).resolve().parents[2],
    )
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from packages.agents.dish_rd.src.agent import (
        CostSimAgent, PilotRecAgent, DishReviewAgent,
        LaunchAssistAgent, RiskAlertAgent,
    )
    return CostSimAgent, PilotRecAgent, DishReviewAgent, LaunchAssistAgent, RiskAlertAgent


_CostSimAgent, _PilotRecAgent, _DishReviewAgent, _LaunchAssistAgent, _RiskAlertAgent = _load_dish_rd_agents()

router = APIRouter(prefix="/api/v1/dish-rd", tags=["dish-rd"])

_cost_sim     = _CostSimAgent()
_pilot_rec    = _PilotRecAgent()
_dish_review  = _DishReviewAgent()
_launch_assist = _LaunchAssistAgent()
_risk_alert   = _RiskAlertAgent()


# ──────────── Schemas ─────────────────────────────────────────────────────────

class DishCreateReq(BaseModel):
    brand_id:           str
    dish_name:          str = Field(..., min_length=2)
    dish_type:          str = "new"
    category_id:        Optional[str] = None
    positioning_type:   Optional[str] = None
    target_price_yuan:  Optional[float] = None
    target_margin_rate: Optional[float] = None
    description:        Optional[str] = None
    highlight_tags:     list[str] = []
    flavor_tags:        list[str] = []
    region_scope:       list[str] = []


class DishUpdateReq(BaseModel):
    dish_name:          Optional[str] = None
    status:             Optional[str] = None
    lifecycle_stage:    Optional[str] = None
    positioning_type:   Optional[str] = None
    target_price_yuan:  Optional[float] = None
    target_margin_rate: Optional[float] = None
    description:        Optional[str] = None
    highlight_tags:     Optional[list[str]] = None
    flavor_tags:        Optional[list[str]] = None


class RecipeVersionCreateReq(BaseModel):
    version_type:     str = "dev"
    serving_size:     float = 1.0
    serving_unit:     str = "份"
    prep_time_min:    int = 5
    cook_time_min:    int = 10
    complexity_score: float = 3.0
    notes:            Optional[str] = None


class RecipeItemReq(BaseModel):
    item_type:           str                  # ingredient / semi_product
    item_id:             str
    item_name_snapshot:  str
    quantity:            float
    unit:                str
    loss_rate_snapshot:  float = 0.05
    unit_price_snapshot: float = 0.0
    process_stage:       str = "cooking"
    sequence_no:         int = 1
    optional_flag:       bool = False
    substitute_group_code: Optional[str] = None


class PilotTestCreateReq(BaseModel):
    target_store_ids:  list[str] = []
    start_date:        Optional[str] = None
    end_date:          Optional[str] = None
    pilot_goal:        dict = {}
    dish_version_id:   Optional[str] = None
    recipe_version_id: Optional[str] = None


class PilotDecisionReq(BaseModel):
    decision:        str   # go / revise / stop
    decision_reason: Optional[str] = None
    avg_taste_score:            Optional[float] = None
    avg_operation_score:        Optional[float] = None
    avg_sales_score:            Optional[float] = None
    avg_margin_score:           Optional[float] = None
    avg_customer_feedback_score: Optional[float] = None


class LaunchProjectCreateReq(BaseModel):
    dish_version_id:    Optional[str] = None
    launch_type:        str = "regional"
    planned_launch_date: Optional[str] = None
    launch_scope:       dict = {}


class FeedbackCreateReq(BaseModel):
    feedback_source: str = "manager"
    feedback_type:   str = "taste"
    rating_score:    Optional[float] = None
    keyword_tags:    list[str] = []
    content:         Optional[str] = None
    store_id:        Optional[str] = None
    severity_level:  str = "low"


# ──────────── 菜品主档 ────────────────────────────────────────────────────────

@router.post("/brands/{brand_id}/dishes", status_code=201)
async def create_dish(
    brand_id: str,
    body: DishCreateReq,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建菜品主档"""
    # 生成唯一编码
    count_result = await db.execute(
        select(func.count()).select_from(Dish).where(Dish.brand_id == brand_id)
    )
    count = count_result.scalar() or 0
    dish_code = f"DISH-{brand_id[:4].upper()}-{count + 1:04d}"

    dish = Dish(
        id                 = str(uuid.uuid4()),
        brand_id           = brand_id,
        dish_code          = dish_code,
        dish_name          = body.dish_name,
        dish_type          = body.dish_type,
        category_id        = body.category_id,
        positioning_type   = body.positioning_type,
        target_price_yuan  = body.target_price_yuan,
        target_margin_rate = body.target_margin_rate,
        description        = body.description,
        highlight_tags     = body.highlight_tags,
        flavor_tags        = body.flavor_tags,
        region_scope       = body.region_scope,
        owner_user_id      = str(user.id),
        status             = DishStatusEnum.DRAFT,
        created_at         = datetime.utcnow(),
        updated_at         = datetime.utcnow(),
    )
    db.add(dish)
    await db.commit()
    return {"dish_id": dish.id, "dish_code": dish.dish_code, "dish_name": dish.dish_name}


@router.get("/brands/{brand_id}/dishes")
async def list_dishes(
    brand_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    dish_type:     Optional[str] = Query(None),
    keyword:       Optional[str] = Query(None),
    page:          int = Query(1, ge=1),
    page_size:     int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查询菜品列表"""
    conditions = [Dish.brand_id == brand_id]
    if status_filter:
        conditions.append(Dish.status == status_filter)
    if dish_type:
        conditions.append(Dish.dish_type == dish_type)
    if keyword:
        conditions.append(Dish.dish_name.ilike(f"%{keyword}%"))

    total_result = await db.execute(
        select(func.count()).select_from(Dish).where(and_(*conditions))
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(Dish).where(and_(*conditions))
        .order_by(Dish.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    dishes = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "dish_id":          d.id,
                "dish_code":        d.dish_code,
                "dish_name":        d.dish_name,
                "dish_type":        d.dish_type,
                "status":           d.status,
                "lifecycle_stage":  d.lifecycle_stage,
                "positioning_type": d.positioning_type,
                "target_price_yuan": float(d.target_price_yuan) if d.target_price_yuan else None,
                "flavor_tags":      d.flavor_tags or [],
                "created_at":       d.created_at.isoformat() if d.created_at else None,
            }
            for d in dishes
        ],
    }


@router.get("/brands/{brand_id}/dishes/{dish_id}")
async def get_dish(
    brand_id: str,
    dish_id:  str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """获取菜品详情"""
    result = await db.execute(
        select(Dish).where(and_(Dish.id == dish_id, Dish.brand_id == brand_id))
    )
    dish = result.scalars().first()
    if not dish:
        raise HTTPException(status_code=404, detail="菜品不存在")

    # 获取最新成本模型
    cost_result = await db.execute(
        select(CostModel).where(CostModel.dish_id == dish_id)
        .order_by(CostModel.calculated_at.desc()).limit(1)
    )
    cost = cost_result.scalars().first()

    # 获取试点状态
    pilot_result = await db.execute(
        select(PilotTest).where(PilotTest.dish_id == dish_id)
        .order_by(PilotTest.created_at.desc()).limit(1)
    )
    pilot = pilot_result.scalars().first()

    return {
        "dish_id":           dish.id,
        "dish_code":         dish.dish_code,
        "dish_name":         dish.dish_name,
        "dish_alias":        dish.dish_alias,
        "dish_type":         dish.dish_type,
        "status":            dish.status,
        "lifecycle_stage":   dish.lifecycle_stage,
        "positioning_type":  dish.positioning_type,
        "target_price_yuan": float(dish.target_price_yuan) if dish.target_price_yuan else None,
        "target_margin_rate": dish.target_margin_rate,
        "description":       dish.description,
        "highlight_tags":    dish.highlight_tags or [],
        "flavor_tags":       dish.flavor_tags or [],
        "health_tags":       dish.health_tags or [],
        "region_scope":      dish.region_scope or [],
        "cover_image_url":   dish.cover_image_url,
        "owner_user_id":     dish.owner_user_id,
        "created_at":        dish.created_at.isoformat() if dish.created_at else None,
        "cost_summary": {
            "total_cost_yuan":      float(cost.total_cost) if cost else None,
            "suggested_price_yuan": float(cost.suggested_price_yuan) if cost else None,
            "margin_rate":          cost.margin_rate if cost else None,
            "calculated_at":        cost.calculated_at.isoformat() if cost and cost.calculated_at else None,
        } if cost else None,
        "pilot_summary": {
            "pilot_id":     pilot.id,
            "pilot_status": pilot.pilot_status,
            "decision":     pilot.decision,
        } if pilot else None,
    }


@router.patch("/brands/{brand_id}/dishes/{dish_id}")
async def update_dish(
    brand_id: str,
    dish_id:  str,
    body: DishUpdateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """更新菜品信息"""
    result = await db.execute(
        select(Dish).where(and_(Dish.id == dish_id, Dish.brand_id == brand_id))
    )
    dish = result.scalars().first()
    if not dish:
        raise HTTPException(status_code=404, detail="菜品不存在")

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(dish, field, val)
    dish.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "dish_id": dish_id, "status": dish.status}


# ──────────── 配方 & 配方版本 ─────────────────────────────────────────────────

@router.post("/brands/{brand_id}/dishes/{dish_id}/recipe-versions", status_code=201)
async def create_recipe_version(
    brand_id: str,
    dish_id:  str,
    body: RecipeVersionCreateReq,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建配方版本（自动创建配方主档）"""
    # 确保配方主档存在
    recipe_result = await db.execute(
        select(Recipe).where(Recipe.dish_id == dish_id)
    )
    recipe = recipe_result.scalars().first()
    if not recipe:
        recipe_code = f"RCP-{dish_id[:8].upper()}"
        # 获取菜品名作为配方名
        dish_result = await db.execute(select(Dish).where(Dish.id == dish_id))
        dish = dish_result.scalars().first()
        recipe = Recipe(
            id           = str(uuid.uuid4()),
            dish_id      = dish_id,
            brand_id     = brand_id,
            recipe_code  = recipe_code,
            recipe_name  = f"{dish.dish_name if dish else dish_id} 配方",
            created_at   = datetime.utcnow(),
        )
        db.add(recipe)

    # 统计版本号
    count_result = await db.execute(
        select(func.count()).select_from(RecipeVersion).where(RecipeVersion.recipe_id == recipe.id)
    )
    v_num = (count_result.scalar() or 0) + 1
    version_no = f"v{v_num}.0"

    rv = RecipeVersion(
        id               = str(uuid.uuid4()),
        recipe_id        = recipe.id,
        version_no       = version_no,
        version_type     = body.version_type,
        status           = RecipeVersionStatusEnum.DRAFT,
        serving_size     = body.serving_size,
        serving_unit     = body.serving_unit,
        prep_time_min    = body.prep_time_min,
        cook_time_min    = body.cook_time_min,
        complexity_score = body.complexity_score,
        notes            = body.notes,
        created_by       = str(user.id),
        created_at       = datetime.utcnow(),
        updated_at       = datetime.utcnow(),
    )
    db.add(rv)
    await db.commit()
    return {
        "recipe_id":         recipe.id,
        "recipe_version_id": rv.id,
        "version_no":        rv.version_no,
        "status":            rv.status,
    }


@router.post("/brands/{brand_id}/dishes/{dish_id}/recipe-versions/{version_id}/items", status_code=201)
async def add_recipe_items(
    brand_id:   str,
    dish_id:    str,
    version_id: str,
    items:      list[RecipeItemReq],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """批量添加配方明细项（BOM）"""
    if not items:
        raise HTTPException(status_code=400, detail="items 不能为空")

    created = []
    for item in items:
        ri = RecipeItem(
            id                    = str(uuid.uuid4()),
            recipe_version_id     = version_id,
            item_type             = item.item_type,
            item_id               = item.item_id,
            item_name_snapshot    = item.item_name_snapshot,
            quantity              = item.quantity,
            unit                  = item.unit,
            loss_rate_snapshot    = item.loss_rate_snapshot,
            unit_price_snapshot   = item.unit_price_snapshot,
            process_stage         = item.process_stage,
            sequence_no           = item.sequence_no,
            optional_flag         = item.optional_flag,
            substitute_group_code = item.substitute_group_code,
            created_at            = datetime.utcnow(),
        )
        db.add(ri)
        created.append(ri.id)

    await db.commit()
    return {"ok": True, "items_created": len(created), "item_ids": created}


@router.get("/brands/{brand_id}/dishes/{dish_id}/recipe-versions/{version_id}/items")
async def get_recipe_items(
    brand_id:   str,
    dish_id:    str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """获取 BOM 明细"""
    result = await db.execute(
        select(RecipeItem).where(RecipeItem.recipe_version_id == version_id)
        .order_by(RecipeItem.sequence_no)
    )
    items = result.scalars().all()
    return {
        "recipe_version_id": version_id,
        "total": len(items),
        "items": [
            {
                "id":                    i.id,
                "item_type":             i.item_type,
                "item_id":               i.item_id,
                "item_name":             i.item_name_snapshot,
                "quantity":              i.quantity,
                "unit":                  i.unit,
                "unit_price_yuan":       float(i.unit_price_snapshot or 0),
                "loss_rate":             i.loss_rate_snapshot,
                "process_stage":         i.process_stage,
                "sequence_no":           i.sequence_no,
                "optional_flag":         i.optional_flag,
                "substitute_group_code": i.substitute_group_code,
            }
            for i in items
        ],
    }


# ──────────── 试点管理 ────────────────────────────────────────────────────────

@router.post("/brands/{brand_id}/dishes/{dish_id}/pilot-tests", status_code=201)
async def create_pilot_test(
    brand_id: str,
    dish_id:  str,
    body: PilotTestCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """创建试点项目"""
    count_result = await db.execute(
        select(func.count()).select_from(PilotTest).where(PilotTest.brand_id == brand_id)
    )
    pilot_no = (count_result.scalar() or 0) + 1
    pilot_code = f"PLT-{brand_id[:4].upper()}-{pilot_no:04d}"

    pilot = PilotTest(
        id                = str(uuid.uuid4()),
        pilot_code        = pilot_code,
        dish_id           = dish_id,
        brand_id          = brand_id,
        dish_version_id   = body.dish_version_id,
        recipe_version_id = body.recipe_version_id,
        target_store_ids  = body.target_store_ids,
        start_date        = date_type.fromisoformat(body.start_date) if body.start_date else None,
        end_date          = date_type.fromisoformat(body.end_date) if body.end_date else None,
        pilot_goal        = body.pilot_goal,
        pilot_status      = PilotStatusEnum.PENDING,
        created_at        = datetime.utcnow(),
        updated_at        = datetime.utcnow(),
    )
    db.add(pilot)
    await db.commit()
    return {"pilot_id": pilot.id, "pilot_code": pilot.pilot_code, "pilot_status": pilot.pilot_status}


@router.post("/brands/{brand_id}/dishes/{dish_id}/pilot-tests/{pilot_id}/decision")
async def record_pilot_decision(
    brand_id: str,
    dish_id:  str,
    pilot_id: str,
    body: PilotDecisionReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """记录试点决策（go/revise/stop）"""
    if body.decision not in {"go", "revise", "stop"}:
        raise HTTPException(status_code=400, detail="decision 必须是 go/revise/stop")

    result = await db.execute(
        select(PilotTest).where(and_(PilotTest.id == pilot_id, PilotTest.dish_id == dish_id))
    )
    pilot = result.scalars().first()
    if not pilot:
        raise HTTPException(status_code=404, detail="试点不存在")

    pilot.decision              = body.decision
    pilot.decision_reason       = body.decision_reason
    pilot.pilot_status          = PilotStatusEnum.COMPLETED
    pilot.avg_taste_score       = body.avg_taste_score
    pilot.avg_operation_score   = body.avg_operation_score
    pilot.avg_sales_score       = body.avg_sales_score
    pilot.avg_margin_score      = body.avg_margin_score
    pilot.avg_customer_feedback_score = body.avg_customer_feedback_score
    pilot.updated_at            = datetime.utcnow()
    await db.commit()
    return {"ok": True, "pilot_id": pilot_id, "decision": body.decision}


@router.get("/brands/{brand_id}/dishes/{dish_id}/pilot-tests")
async def list_pilot_tests(
    brand_id: str,
    dish_id:  str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查询菜品的试点记录"""
    result = await db.execute(
        select(PilotTest).where(and_(PilotTest.dish_id == dish_id, PilotTest.brand_id == brand_id))
        .order_by(PilotTest.created_at.desc())
    )
    pilots = result.scalars().all()
    return {
        "dish_id": dish_id,
        "total":   len(pilots),
        "items": [
            {
                "pilot_id":      p.id,
                "pilot_code":    p.pilot_code,
                "pilot_status":  p.pilot_status,
                "decision":      p.decision,
                "start_date":    str(p.start_date) if p.start_date else None,
                "end_date":      str(p.end_date) if p.end_date else None,
                "store_count":   len(p.target_store_ids or []),
                "avg_taste_score": p.avg_taste_score,
            }
            for p in pilots
        ],
    }


# ──────────── 上市管理 ────────────────────────────────────────────────────────

@router.post("/brands/{brand_id}/dishes/{dish_id}/launch-projects", status_code=201)
async def create_launch_project(
    brand_id: str,
    dish_id:  str,
    body: LaunchProjectCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """创建上市项目"""
    count_result = await db.execute(
        select(func.count()).select_from(LaunchProject).where(LaunchProject.brand_id == brand_id)
    )
    launch_no = (count_result.scalar() or 0) + 1
    launch_code = f"LCH-{brand_id[:4].upper()}-{launch_no:04d}"

    lp = LaunchProject(
        id                  = str(uuid.uuid4()),
        launch_code         = launch_code,
        dish_id             = dish_id,
        brand_id            = brand_id,
        dish_version_id     = body.dish_version_id,
        launch_type         = body.launch_type,
        planned_launch_date = date_type.fromisoformat(body.planned_launch_date) if body.planned_launch_date else None,
        launch_scope        = body.launch_scope,
        launch_status       = LaunchStatusEnum.PENDING,
        created_at          = datetime.utcnow(),
        updated_at          = datetime.utcnow(),
    )
    db.add(lp)

    # 同步更新菜品状态
    dish_result = await db.execute(select(Dish).where(Dish.id == dish_id))
    dish = dish_result.scalars().first()
    if dish:
        dish.status = DishStatusEnum.LAUNCH_READY
        dish.updated_at = datetime.utcnow()

    await db.commit()
    return {"launch_id": lp.id, "launch_code": lp.launch_code, "launch_status": lp.launch_status}


# ──────────── 反馈录入 ────────────────────────────────────────────────────────

@router.post("/brands/{brand_id}/dishes/{dish_id}/feedbacks", status_code=201)
async def add_feedback(
    brand_id: str,
    dish_id:  str,
    body: FeedbackCreateReq,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """录入菜品反馈"""
    feedback = DishFeedback(
        id              = str(uuid.uuid4()),
        dish_id         = dish_id,
        brand_id        = brand_id,
        feedback_source = body.feedback_source,
        feedback_type   = body.feedback_type,
        rating_score    = body.rating_score,
        keyword_tags    = body.keyword_tags,
        content         = body.content,
        store_id        = body.store_id,
        severity_level  = body.severity_level,
        happened_at     = datetime.utcnow(),
        created_at      = datetime.utcnow(),
    )
    db.add(feedback)
    await db.commit()
    return {"feedback_id": feedback.id, "dish_id": dish_id}


@router.get("/brands/{brand_id}/dishes/{dish_id}/feedbacks")
async def list_feedbacks(
    brand_id:        str,
    dish_id:         str,
    feedback_type:   Optional[str] = Query(None),
    page:            int = Query(1, ge=1),
    page_size:       int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查询菜品反馈列表"""
    conditions = [DishFeedback.dish_id == dish_id, DishFeedback.brand_id == brand_id]
    if feedback_type:
        conditions.append(DishFeedback.feedback_type == feedback_type)

    total_result = await db.execute(
        select(func.count()).select_from(DishFeedback).where(and_(*conditions))
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(DishFeedback).where(and_(*conditions))
        .order_by(DishFeedback.happened_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    feedbacks = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "feedback_id":    f.id,
                "feedback_type":  f.feedback_type,
                "feedback_source": f.feedback_source,
                "rating_score":   f.rating_score,
                "keyword_tags":   f.keyword_tags or [],
                "content":        f.content,
                "store_id":       f.store_id,
                "severity_level": f.severity_level,
                "happened_at":    f.happened_at.isoformat() if f.happened_at else None,
            }
            for f in feedbacks
        ],
    }


# ──────────── 复盘报告 ────────────────────────────────────────────────────────

@router.get("/brands/{brand_id}/dishes/{dish_id}/retrospective-reports")
async def list_retrospective_reports(
    brand_id: str,
    dish_id:  str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查询菜品复盘报告列表"""
    result = await db.execute(
        select(RetrospectiveReport).where(
            and_(RetrospectiveReport.dish_id == dish_id, RetrospectiveReport.brand_id == brand_id)
        ).order_by(RetrospectiveReport.generated_at.desc())
    )
    reports = result.scalars().all()
    return {
        "dish_id": dish_id,
        "total":   len(reports),
        "items": [
            {
                "report_id":             r.id,
                "retrospective_period":  r.retrospective_period,
                "lifecycle_assessment":  r.lifecycle_assessment,
                "conclusion":            r.conclusion,
                "generated_at":          r.generated_at.isoformat() if r.generated_at else None,
            }
            for r in reports
        ],
    }


# ──────────── Agent 接口 ──────────────────────────────────────────────────────

@router.post("/brands/{brand_id}/dishes/{dish_id}/agent/cost-sim")
async def run_cost_sim(
    brand_id:          str,
    dish_id:           str,
    recipe_version_id: str = Query(..., description="配方版本ID"),
    save:              bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    成本仿真 Agent — 基于BOM计算单份成本与毛利，输出多定价方案
    """
    return await _cost_sim.simulate(
        recipe_version_id=recipe_version_id,
        dish_id=dish_id,
        brand_id=brand_id,
        db=db,
        save=save,
    )


@router.get("/brands/{brand_id}/dishes/{dish_id}/agent/pilot-recommend")
async def run_pilot_recommend(
    brand_id: str,
    dish_id:  str,
    top_n:    int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    试点推荐 Agent — 根据菜品画像推荐最适合的试点门店
    """
    return await _pilot_rec.recommend_stores(
        dish_id=dish_id,
        brand_id=brand_id,
        db=db,
        top_n=top_n,
    )


@router.post("/brands/{brand_id}/dishes/{dish_id}/agent/review")
async def run_dish_review(
    brand_id:  str,
    dish_id:   str,
    period:    str = Query("30d", description="复盘周期: 30d/60d/90d"),
    dry_run:   bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    复盘优化 Agent — 聚合反馈数据输出生命周期判断与优化建议
    """
    if period not in {"30d", "60d", "90d"}:
        raise HTTPException(status_code=400, detail="period 必须是 30d/60d/90d")
    return await _dish_review.run_review(
        dish_id=dish_id,
        brand_id=brand_id,
        db=db,
        period=period,
        dry_run=dry_run,
    )


@router.get("/brands/{brand_id}/dishes/{dish_id}/agent/launch-readiness")
async def run_launch_readiness(
    brand_id:          str,
    dish_id:           str,
    launch_project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    发布助手 Agent — 检查上市前置条件，输出就绪状态与缺项清单
    """
    return await _launch_assist.check_launch_readiness(
        dish_id=dish_id,
        brand_id=brand_id,
        launch_project_id=launch_project_id,
        db=db,
    )


@router.get("/brands/{brand_id}/agent/risk-scan")
async def run_risk_scan(
    brand_id:  str,
    days_back: int = Query(14, ge=1, le=90),
    dry_run:   bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    风险预警 Agent — 扫描品牌下所有菜品的风险信号（成本/评分/退菜/差评）
    """
    return await _risk_alert.scan_risks(
        brand_id=brand_id,
        db=db,
        days_back=days_back,
        dry_run=dry_run,
    )


# ──────────── 驾驶舱 ──────────────────────────────────────────────────────────

@router.get("/brands/{brand_id}/dashboard")
async def get_dish_rd_dashboard(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """菜品研发驾驶舱 — 全局概览"""
    # 各状态菜品数
    status_counts_result = await db.execute(
        select(Dish.status, func.count().label("cnt"))
        .where(Dish.brand_id == brand_id)
        .group_by(Dish.status)
    )
    status_counts = {row.status: row.cnt for row in status_counts_result.all()}

    # 活跃试点数
    pilot_result = await db.execute(
        select(func.count()).select_from(PilotTest).where(
            and_(PilotTest.brand_id == brand_id, PilotTest.pilot_status == PilotStatusEnum.ACTIVE)
        )
    )
    active_pilots = pilot_result.scalar() or 0

    # 平均毛利率（近30天成本模型）
    cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=30)
    margin_result = await db.execute(
        select(func.avg(CostModel.margin_rate)).where(
            and_(CostModel.brand_id == brand_id, CostModel.calculated_at >= cutoff)
        )
    )
    avg_margin = margin_result.scalar()

    # 近期高风险数量（毛利<45%）
    risk_result = await db.execute(
        select(func.count()).select_from(CostModel).where(
            and_(
                CostModel.brand_id == brand_id,
                CostModel.margin_rate < 0.45,
                CostModel.calculated_at >= cutoff,
            )
        )
    )
    high_risk_count = risk_result.scalar() or 0

    total_dishes = sum(status_counts.values())
    return {
        "brand_id":       brand_id,
        "total_dishes":   total_dishes,
        "by_status":      status_counts,
        "active_pilots":  active_pilots,
        "avg_margin_rate_30d": round(float(avg_margin), 4) if avg_margin else None,
        "high_risk_dishes": high_risk_count,
        "in_dev_count":   status_counts.get(DishStatusEnum.IN_DEV, 0),
        "launched_count": status_counts.get(DishStatusEnum.LAUNCHED, 0),
        "as_of":          datetime.utcnow().isoformat(),
    }
