"""
HR业务规则引擎 — 三级继承查询 + 系统默认兜底

查询优先级（从精确到宽泛）:
1. store_id + position + employment_type
2. store_id + position
3. store_id only
4. brand_id + position + employment_type
5. brand_id + position
6. brand_id only（品牌默认）
7. 系统默认值（硬编码兜底，不依赖数据库）
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from sqlalchemy import and_, case, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.hr_business_rule import HRBusinessRule, RuleCategory

logger = structlog.get_logger()

# ── 系统默认值（第7级兜底） ──────────────────────────────

DEFAULT_ATTENDANCE_PENALTY = {
    "late_per_time_fen": 5000,  # 50元/次
    "absent_per_day_fen": 20000,  # 200元/天
    "early_leave_per_time_fen": 3000,  # 30元/次
}

DEFAULT_SENIORITY_TIERS = [
    {"min_months": 13, "max_months": 24, "amount_fen": 5000},  # 50元/月
    {"min_months": 24, "max_months": 36, "amount_fen": 10000},  # 100元/月
    {"min_months": 36, "max_months": 48, "amount_fen": 15000},  # 150元/月
    {"min_months": 48, "max_months": 99999, "amount_fen": 20000},  # 200元/月
]

DEFAULT_OVERTIME_RATE = {
    "weekday": 1.5,
    "weekend": 2.0,
    "holiday": 3.0,
}

DEFAULT_FULL_ATTENDANCE = {
    "enabled": False,
    "bonus_fen": 0,
}

DEFAULT_MEAL_SUBSIDY = {
    "per_day_fen": 0,
    "workday_only": True,
}

DEFAULT_POSITION_ALLOWANCE: dict = {}

# 类别 → 系统默认值映射
_SYSTEM_DEFAULTS: dict[str, dict] = {
    RuleCategory.ATTENDANCE_PENALTY.value: DEFAULT_ATTENDANCE_PENALTY,
    RuleCategory.SENIORITY_SUBSIDY.value: {"tiers": DEFAULT_SENIORITY_TIERS},
    RuleCategory.OVERTIME_RATE.value: DEFAULT_OVERTIME_RATE,
    RuleCategory.FULL_ATTENDANCE.value: DEFAULT_FULL_ATTENDANCE,
    RuleCategory.MEAL_SUBSIDY.value: DEFAULT_MEAL_SUBSIDY,
    RuleCategory.TRANSPORT_SUBSIDY.value: {"per_month_fen": 0},
    RuleCategory.HOUSING_SUBSIDY.value: {"per_month_fen": 0},
    RuleCategory.POSITION_ALLOWANCE.value: DEFAULT_POSITION_ALLOWANCE,
    RuleCategory.OTHER.value: {},
}

# 初始化时的品牌默认规则种子数据
_SEED_RULES = [
    {
        "category": RuleCategory.ATTENDANCE_PENALTY.value,
        "rule_name": "考勤扣款默认规则",
        "rules_json": DEFAULT_ATTENDANCE_PENALTY,
        "description": "迟到50元/次，旷工200元/天，早退30元/次",
    },
    {
        "category": RuleCategory.SENIORITY_SUBSIDY.value,
        "rule_name": "工龄补贴默认4档",
        "rules_json": {"tiers": DEFAULT_SENIORITY_TIERS},
        "description": "13-24月50元，24-36月100元，36-48月150元，48月以上200元",
    },
    {
        "category": RuleCategory.OVERTIME_RATE.value,
        "rule_name": "加班倍数默认规则",
        "rules_json": DEFAULT_OVERTIME_RATE,
        "description": "工作日1.5倍，周末2倍，法定节假日3倍",
    },
    {
        "category": RuleCategory.FULL_ATTENDANCE.value,
        "rule_name": "全勤奖默认规则",
        "rules_json": {"enabled": True, "bonus_fen": 30000},
        "description": "全勤奖300元/月",
    },
    {
        "category": RuleCategory.MEAL_SUBSIDY.value,
        "rule_name": "餐补默认规则",
        "rules_json": {"per_day_fen": 1500, "workday_only": True},
        "description": "每工作日餐补15元",
    },
]


class HRRuleEngine:
    """HR业务规则引擎 — 三级继承查询 + 系统默认兜底"""

    def __init__(self, brand_id: str, store_id: str):
        self.brand_id = brand_id
        self.store_id = store_id

    async def get_rule(
        self,
        db: AsyncSession,
        category: str,
        position: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> dict:
        """
        获取生效规则（七级降级查询）

        按匹配精度计算优先级分数，取最高分的规则。
        匹配分数:
          store_id 匹配 +100
          position 匹配 +10
          employment_type 匹配 +1
          priority 字段作为二级排序
        """
        conditions = [
            HRBusinessRule.brand_id == self.brand_id,
            HRBusinessRule.category == category,
            HRBusinessRule.is_active.is_(True),
        ]

        # 品牌级 or 门店级
        store_filter = or_(
            HRBusinessRule.store_id.is_(None),
            HRBusinessRule.store_id == self.store_id,
        )
        conditions.append(store_filter)

        # 岗位：匹配指定岗位 or 通用
        if position:
            conditions.append(
                or_(
                    HRBusinessRule.position.is_(None),
                    HRBusinessRule.position == position,
                )
            )
        else:
            conditions.append(HRBusinessRule.position.is_(None))

        # 用工类型：匹配指定类型 or 通用
        if employment_type:
            conditions.append(
                or_(
                    HRBusinessRule.employment_type.is_(None),
                    HRBusinessRule.employment_type == employment_type,
                )
            )
        else:
            conditions.append(HRBusinessRule.employment_type.is_(None))

        # 计算匹配精度分数用于排序
        match_score = (
            case(
                (HRBusinessRule.store_id == self.store_id, 100),
                else_=0,
            )
            + case(
                (HRBusinessRule.position == position, 10) if position else (HRBusinessRule.position.is_(None), 0),
                else_=0,
            )
            + case(
                (
                    (HRBusinessRule.employment_type == employment_type, 1)
                    if employment_type
                    else (HRBusinessRule.employment_type.is_(None), 0)
                ),
                else_=0,
            )
        )

        stmt = (
            select(HRBusinessRule)
            .where(and_(*conditions))
            .order_by(
                desc(match_score),
                desc(HRBusinessRule.priority),
            )
            .limit(1)
        )

        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if rule:
            logger.debug(
                "hr_rule_resolved",
                category=category,
                rule_name=rule.rule_name,
                store_id=rule.store_id,
                position=rule.position,
            )
            return dict(rule.rules_json)

        # 第7级：系统硬编码默认值
        logger.debug(
            "hr_rule_fallback_to_system_default",
            category=category,
            brand_id=self.brand_id,
            store_id=self.store_id,
        )
        return dict(_SYSTEM_DEFAULTS.get(category, {}))

    # ── 便捷方法 ──────────────────────────────────────────

    async def get_late_deduction_fen(
        self,
        db: AsyncSession,
        position: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> int:
        """获取迟到扣款金额（分）"""
        rule = await self.get_rule(db, RuleCategory.ATTENDANCE_PENALTY.value, position, employment_type)
        return rule.get("late_per_time_fen", 5000)

    async def get_absent_deduction_fen(
        self,
        db: AsyncSession,
        position: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> int:
        """获取旷工扣款金额（分/天）"""
        rule = await self.get_rule(db, RuleCategory.ATTENDANCE_PENALTY.value, position, employment_type)
        return rule.get("absent_per_day_fen", 20000)

    async def get_early_leave_deduction_fen(
        self,
        db: AsyncSession,
        position: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> int:
        """获取早退扣款金额（分/次）"""
        rule = await self.get_rule(db, RuleCategory.ATTENDANCE_PENALTY.value, position, employment_type)
        return rule.get("early_leave_per_time_fen", 3000)

    async def get_seniority_subsidy_fen(
        self,
        db: AsyncSession,
        seniority_months: int,
        position: Optional[str] = None,
    ) -> int:
        """获取工龄补贴（分）— 按工龄月数匹配阶梯"""
        rule = await self.get_rule(db, RuleCategory.SENIORITY_SUBSIDY.value, position)
        tiers = rule.get("tiers", DEFAULT_SENIORITY_TIERS)
        # 从高阶梯往低阶梯匹配，取首个满足 min_months 的
        for tier in sorted(tiers, key=lambda t: t["min_months"], reverse=True):
            if seniority_months >= tier["min_months"]:
                return tier["amount_fen"]
        return 0

    async def get_overtime_rates(
        self,
        db: AsyncSession,
        position: Optional[str] = None,
    ) -> dict:
        """获取加班倍数 — 返回 {weekday, weekend, holiday}"""
        rule = await self.get_rule(db, RuleCategory.OVERTIME_RATE.value, position)
        return {
            "weekday": rule.get("weekday", 1.5),
            "weekend": rule.get("weekend", 2.0),
            "holiday": rule.get("holiday", 3.0),
        }

    async def get_full_attendance_bonus_fen(
        self,
        db: AsyncSession,
        position: Optional[str] = None,
    ) -> int:
        """获取全勤奖（分）— 未启用返回 0"""
        rule = await self.get_rule(db, RuleCategory.FULL_ATTENDANCE.value, position)
        if rule.get("enabled", False):
            return rule.get("bonus_fen", 0)
        return 0

    async def get_meal_subsidy_fen(
        self,
        db: AsyncSession,
        attendance_days: int,
        position: Optional[str] = None,
    ) -> int:
        """获取餐补总额（分）= 每日餐补 × 出勤天数"""
        rule = await self.get_rule(db, RuleCategory.MEAL_SUBSIDY.value, position)
        per_day = rule.get("per_day_fen", 0)
        return per_day * attendance_days

    async def get_position_allowance_fen(
        self,
        db: AsyncSession,
        position: str,
    ) -> int:
        """获取岗位津贴（分）"""
        rule = await self.get_rule(db, RuleCategory.POSITION_ALLOWANCE.value)
        return rule.get(position, 0)

    async def get_all_effective_rules(
        self,
        db: AsyncSession,
        position: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> dict[str, dict]:
        """获取所有类别的生效规则（用于前端预览）"""
        result = {}
        for cat in RuleCategory:
            rule = await self.get_rule(db, cat.value, position, employment_type)
            result[cat.value] = rule
        return result

    async def seed_default_rules(self, db: AsyncSession) -> int:
        """
        初始化品牌默认规则（首次配置用）

        仅在该品牌尚未配置任何规则时才插入种子数据。
        返回插入的规则数量。
        """
        # 检查是否已有规则
        stmt = select(HRBusinessRule.id).where(HRBusinessRule.brand_id == self.brand_id).limit(1)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            logger.info("hr_rules_seed_skipped", brand_id=self.brand_id, reason="rules_exist")
            return 0

        count = 0
        for seed in _SEED_RULES:
            rule = HRBusinessRule(
                id=uuid_mod.uuid4(),
                brand_id=self.brand_id,
                store_id=None,
                position=None,
                employment_type=None,
                category=seed["category"],
                rule_name=seed["rule_name"],
                rules_json=seed["rules_json"],
                priority=0,
                is_active=True,
                description=seed["description"],
            )
            db.add(rule)
            count += 1

        await db.flush()
        logger.info("hr_rules_seeded", brand_id=self.brand_id, count=count)
        return count
