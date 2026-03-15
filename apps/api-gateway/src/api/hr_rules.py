"""
HR业务规则配置 API — 管理考勤扣款/工龄补贴/加班倍数等可配置规则
"""
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.core.dependencies import get_current_active_user
from src.models.user import User
from src.models.hr_business_rule import HRBusinessRule, RuleCategory
from src.services.hr_rule_engine import HRRuleEngine

logger = structlog.get_logger()
router = APIRouter()


# ── 请求/响应模型 ──────────────────────────────────────

class RuleCreateRequest(BaseModel):
    brand_id: str
    store_id: Optional[str] = None
    position: Optional[str] = None
    employment_type: Optional[str] = None
    category: str = Field(..., description="规则类别，见 RuleCategory 枚举")
    rule_name: str = Field(..., max_length=100)
    rules_json: dict
    priority: int = 0
    is_active: bool = True
    description: Optional[str] = None


class RuleUpdateRequest(BaseModel):
    rule_name: Optional[str] = None
    rules_json: Optional[dict] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class RuleResponse(BaseModel):
    id: str
    brand_id: str
    store_id: Optional[str]
    position: Optional[str]
    employment_type: Optional[str]
    category: str
    rule_name: str
    rules_json: dict
    priority: int
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


class EffectiveRulesResponse(BaseModel):
    brand_id: str
    store_id: str
    position: Optional[str]
    employment_type: Optional[str]
    rules: dict  # category -> rule_json


class PayrollImpactPreview(BaseModel):
    category: str
    current_rule: dict
    proposed_rule: dict
    impact_description: str
    estimated_monthly_diff_fen: int  # 正值=成本增加，负值=成本减少


def _rule_to_response(rule: HRBusinessRule) -> dict:
    return {
        "id": str(rule.id),
        "brand_id": rule.brand_id,
        "store_id": rule.store_id,
        "position": rule.position,
        "employment_type": rule.employment_type,
        "category": rule.category,
        "rule_name": rule.rule_name,
        "rules_json": rule.rules_json,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "description": rule.description,
    }


# ── 端点 ──────────────────────────────────────────────
# 注意: 固定路径端点必须在 {rule_id} 路径参数端点之前注册，
# 否则 FastAPI 会尝试将 "effective" 等字符串解析为 UUID。

@router.get("/hr/rules/effective", summary="查询生效规则")
async def get_effective_rules(
    brand_id: str = Query(...),
    store_id: str = Query(...),
    position: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询某品牌/门店/岗位/用工类型的所有生效规则（含继承降级）"""
    engine = HRRuleEngine(brand_id, store_id)
    rules = await engine.get_all_effective_rules(db, position, employment_type)
    return EffectiveRulesResponse(
        brand_id=brand_id,
        store_id=store_id,
        position=position,
        employment_type=employment_type,
        rules=rules,
    )


@router.post("/hr/rules/seed-defaults", summary="初始化默认规则")
async def seed_defaults(
    brand_id: str = Query(...),
    store_id: str = Query("__unused__", description="仅用于构建引擎实例，种子数据为品牌级"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """为品牌初始化一组默认规则（幂等：已有规则时跳过）"""
    engine = HRRuleEngine(brand_id, store_id)
    count = await engine.seed_default_rules(db)
    await db.commit()
    return {"brand_id": brand_id, "seeded_count": count}


@router.post("/hr/rules/preview-payroll-impact", summary="预览规则变更薪酬影响")
async def preview_payroll_impact(
    brand_id: str = Query(...),
    store_id: str = Query(...),
    category: str = Query(...),
    proposed_rules_json: dict = None,
    position: Optional[str] = Query(None),
    employee_count: int = Query(50, description="受影响员工估算数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    预览规则变更对薪酬的影响

    对比当前生效规则 vs 提议的新规则，估算月度成本变化。
    """
    if proposed_rules_json is None:
        raise HTTPException(400, "请提供 proposed_rules_json")

    engine = HRRuleEngine(brand_id, store_id)
    current_rule = await engine.get_rule(db, category, position)

    # 根据类别计算估算影响
    diff_fen = 0
    description = ""

    if category == RuleCategory.ATTENDANCE_PENALTY.value:
        old_late = current_rule.get("late_per_time_fen", 5000)
        new_late = proposed_rules_json.get("late_per_time_fen", old_late)
        # 假设平均每人每月迟到 1 次
        avg_late_per_person = 1
        diff_fen = (new_late - old_late) * avg_late_per_person * employee_count
        description = (
            f"迟到扣款 {old_late / 100:.0f}元→{new_late / 100:.0f}元/次，"
            f"按{employee_count}人均1次/月估算"
        )

    elif category == RuleCategory.FULL_ATTENDANCE.value:
        old_bonus = current_rule.get("bonus_fen", 0) if current_rule.get("enabled") else 0
        new_bonus = proposed_rules_json.get("bonus_fen", 0) if proposed_rules_json.get("enabled") else 0
        # 假设 80% 员工可获得全勤奖
        eligible_ratio = 0.8
        diff_fen = int((new_bonus - old_bonus) * employee_count * eligible_ratio)
        description = (
            f"全勤奖 {old_bonus / 100:.0f}元→{new_bonus / 100:.0f}元/月，"
            f"按{employee_count}人×80%获得率估算"
        )

    elif category == RuleCategory.MEAL_SUBSIDY.value:
        old_per_day = current_rule.get("per_day_fen", 0)
        new_per_day = proposed_rules_json.get("per_day_fen", old_per_day)
        work_days = 22
        diff_fen = (new_per_day - old_per_day) * work_days * employee_count
        description = (
            f"餐补 {old_per_day / 100:.0f}元→{new_per_day / 100:.0f}元/日，"
            f"按{employee_count}人×{work_days}工作日估算"
        )

    elif category == RuleCategory.SENIORITY_SUBSIDY.value:
        # 工龄补贴影响较难精确估算，给出定性描述
        description = f"工龄补贴阶梯调整，影响视员工工龄分布而定（{employee_count}人）"
        diff_fen = 0

    else:
        description = f"{category} 规则变更影响需根据实际数据计算"
        diff_fen = 0

    return PayrollImpactPreview(
        category=category,
        current_rule=current_rule,
        proposed_rule=proposed_rules_json,
        impact_description=description,
        estimated_monthly_diff_fen=diff_fen,
    )


# ── CRUD 端点（含路径参数，必须在固定路径之后） ──────────

@router.get("/hr/rules", summary="查询规则列表")
async def list_rules(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """按品牌/门店/类别筛选规则列表"""
    conditions = [HRBusinessRule.brand_id == brand_id]
    if store_id is not None:
        conditions.append(HRBusinessRule.store_id == store_id)
    if category is not None:
        conditions.append(HRBusinessRule.category == category)
    if is_active is not None:
        conditions.append(HRBusinessRule.is_active == is_active)

    stmt = (
        select(HRBusinessRule)
        .where(and_(*conditions))
        .order_by(HRBusinessRule.category, HRBusinessRule.priority.desc())
    )
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return {"items": [_rule_to_response(r) for r in rules], "total": len(rules)}


@router.post("/hr/rules", summary="创建规则")
async def create_rule(
    req: RuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建新的业务规则"""
    valid_categories = {c.value for c in RuleCategory}
    if req.category not in valid_categories:
        raise HTTPException(400, f"无效类别: {req.category}，可选: {sorted(valid_categories)}")

    import uuid as uuid_mod
    rule = HRBusinessRule(
        id=uuid_mod.uuid4(),
        brand_id=req.brand_id,
        store_id=req.store_id,
        position=req.position,
        employment_type=req.employment_type,
        category=req.category,
        rule_name=req.rule_name,
        rules_json=req.rules_json,
        priority=req.priority,
        is_active=req.is_active,
        description=req.description,
    )
    db.add(rule)
    await db.flush()
    await db.commit()

    logger.info(
        "hr_rule_created",
        rule_id=str(rule.id),
        category=rule.category,
        brand_id=rule.brand_id,
        store_id=rule.store_id,
    )
    return _rule_to_response(rule)


@router.put("/hr/rules/{rule_id}", summary="更新规则")
async def update_rule(
    rule_id: UUID,
    req: RuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新已有规则的字段"""
    stmt = select(HRBusinessRule).where(HRBusinessRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "规则不存在")

    if req.rule_name is not None:
        rule.rule_name = req.rule_name
    if req.rules_json is not None:
        rule.rules_json = req.rules_json
    if req.priority is not None:
        rule.priority = req.priority
    if req.is_active is not None:
        rule.is_active = req.is_active
    if req.description is not None:
        rule.description = req.description

    await db.flush()
    await db.commit()

    logger.info("hr_rule_updated", rule_id=str(rule_id))
    return _rule_to_response(rule)


@router.delete("/hr/rules/{rule_id}", summary="删除规则")
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """删除指定规则"""
    stmt = select(HRBusinessRule).where(HRBusinessRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "规则不存在")

    await db.delete(rule)
    await db.commit()

    logger.info("hr_rule_deleted", rule_id=str(rule_id), category=rule.category)
    return {"deleted": True, "id": str(rule_id)}
