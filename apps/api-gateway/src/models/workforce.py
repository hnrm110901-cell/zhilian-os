"""
Workforce Models — Phase 8
人力经营决策层：客流预测 → 排班建议 → 成本监控 → 采纳追踪
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class MealPeriodType(str, enum.Enum):
    MORNING = "morning"
    LUNCH = "lunch"
    DINNER = "dinner"
    ALL_DAY = "all_day"


class StaffingAdviceStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ConfirmationAction(str, enum.Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    MODIFIED = "modified"


class BudgetPeriodType(str, enum.Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"


class RankingPeriodType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ─────────────────────────────────────────────────────────
# 1. labor_demand_forecasts — 客流预测 → 各岗位人数推荐
# ─────────────────────────────────────────────────────────
class LaborDemandForecast(Base, TimestampMixin):
    """
    LaborDemandService 的输出：给定门店/日期/餐段，
    预测客流并推荐各岗位人数。
    """

    __tablename__ = "labor_demand_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    forecast_date = Column(Date, nullable=False, index=True)
    meal_period = Column(SAEnum(MealPeriodType, name="meal_period_type"), nullable=False)

    # 预测结果
    predicted_customer_count = Column(Integer, nullable=False)
    predicted_revenue_yuan = Column(Numeric(12, 2), nullable=True)
    confidence_score = Column(Numeric(4, 3), nullable=False)  # 0.000–1.000

    # 岗位人数推荐：{"waiter": 3, "chef": 2, "cashier": 1}
    position_requirements = Column(JSON, nullable=False, default=dict)
    total_headcount_needed = Column(Integer, nullable=False)

    # 推理依据（3条因子，透明可解释）
    factor_holiday_weight = Column(Numeric(5, 3), nullable=True)  # 节假日权重
    factor_weather_score = Column(Numeric(5, 3), nullable=True)  # 天气影响系数
    factor_historical_avg = Column(Integer, nullable=True)  # 历史同类日均客流

    model_version = Column(String(32), nullable=True)

    def __repr__(self):
        return (
            f"<LaborDemandForecast(store='{self.store_id}', "
            f"date='{self.forecast_date}', period='{self.meal_period}', "
            f"headcount={self.total_headcount_needed})>"
        )


# ─────────────────────────────────────────────────────────
# 2. labor_cost_snapshots — 每日人工成本率快照
# ─────────────────────────────────────────────────────────
class LaborCostSnapshot(Base, TimestampMixin):
    """
    LaborCostService 的输出：每日一条，记录实际 vs 预算的
    人工成本率，计算偏差¥及加班情况。
    UNIQUE: store_id + snapshot_date
    """

    __tablename__ = "labor_cost_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)

    # 实际数据
    actual_revenue_yuan = Column(Numeric(14, 2), nullable=False)
    actual_labor_cost_yuan = Column(Numeric(12, 2), nullable=False)
    actual_labor_cost_rate = Column(Numeric(6, 2), nullable=False)  # %

    # 预算数据
    budgeted_labor_cost_yuan = Column(Numeric(12, 2), nullable=True)
    budgeted_labor_cost_rate = Column(Numeric(6, 2), nullable=True)  # %

    # 偏差（正数=超支，负数=节省）
    variance_yuan = Column(Numeric(12, 2), nullable=True)
    variance_pct = Column(Numeric(6, 2), nullable=True)  # 百分点差

    # 出勤情况
    headcount_actual = Column(Integer, nullable=True)
    headcount_scheduled = Column(Integer, nullable=True)
    overtime_hours = Column(Numeric(6, 2), nullable=True)
    overtime_cost_yuan = Column(Numeric(10, 2), nullable=True)

    def __repr__(self):
        return (
            f"<LaborCostSnapshot(store='{self.store_id}', "
            f"date='{self.snapshot_date}', rate={self.actual_labor_cost_rate}%)>"
        )


# ─────────────────────────────────────────────────────────
# 3. staffing_advice — AI 生成的排班建议卡
# ─────────────────────────────────────────────────────────
class StaffingAdvice(Base, TimestampMixin):
    """
    WorkforcePushService 输出：每日 07:00 为每个门店/餐段
    生成一条建议。包含¥节省/超支预估 + 3条可解释推理链。
    """

    __tablename__ = "staffing_advice"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    advice_date = Column(Date, nullable=False, index=True)
    meal_period = Column(SAEnum(MealPeriodType, name="meal_period_type"), nullable=False)

    status = Column(
        SAEnum(StaffingAdviceStatus, name="staffing_advice_status"),
        nullable=False,
        default=StaffingAdviceStatus.PENDING,
        index=True,
    )

    # 人数建议
    recommended_headcount = Column(Integer, nullable=False)
    current_scheduled_headcount = Column(Integer, nullable=True)
    headcount_delta = Column(Integer, nullable=True)  # recommended - current

    # ¥影响（Rule 6）
    estimated_saving_yuan = Column(Numeric(10, 2), nullable=True)  # 节省¥（正值）
    estimated_overspend_yuan = Column(Numeric(10, 2), nullable=True)  # 超支¥（正值）

    # 3条可解释推理链
    reason_1 = Column(Text, nullable=True)  # 客流因子
    reason_2 = Column(Text, nullable=True)  # 历史同类日
    reason_3 = Column(Text, nullable=True)  # 节假日权重

    confidence_score = Column(Numeric(4, 3), nullable=True)

    # 各岗位明细：{"waiter": {"current": 3, "recommended": 4, "delta": 1}}
    position_breakdown = Column(JSON, nullable=True, default=dict)

    push_sent_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # 关联
    confirmations = relationship(
        "StaffingAdviceConfirmation",
        back_populates="advice",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<StaffingAdvice(store='{self.store_id}', " f"date='{self.advice_date}', status='{self.status}')>"


# ─────────────────────────────────────────────────────────
# 4. staffing_advice_confirmations — 店长确认行为追踪
# ─────────────────────────────────────────────────────────
class StaffingAdviceConfirmation(Base):
    """
    记录每次店长对排班建议的确认/拒绝/修改行为。
    用于 BehaviorScoreEngine 计算人力 AI 的采纳率。
    """

    __tablename__ = "staffing_advice_confirmations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    advice_id = Column(UUID(as_uuid=True), ForeignKey("staffing_advice.id"), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    confirmed_by = Column(String(100), nullable=True)  # user_id or role
    action = Column(
        SAEnum(ConfirmationAction, name="confirmation_action"),
        nullable=False,
    )

    # 修改场景
    modified_headcount = Column(Integer, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # 效果追踪
    response_time_seconds = Column(Integer, nullable=True)  # 店长响应时长
    actual_saving_yuan = Column(Numeric(10, 2), nullable=True)  # 事后核算节省¥

    confirmed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)

    advice = relationship("StaffingAdvice", back_populates="confirmations")

    def __repr__(self):
        return f"<StaffingAdviceConfirmation(advice='{self.advice_id}', " f"action='{self.action}')>"


# ─────────────────────────────────────────────────────────
# 5. store_labor_budgets — 门店人力预算配置
# ─────────────────────────────────────────────────────────
class StoreLaborBudget(Base, TimestampMixin):
    """
    门店月度/周度人力预算上限。
    超过 alert_threshold_pct 时触发推送。
    UNIQUE: store_id + budget_period + budget_type
    """

    __tablename__ = "store_labor_budgets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    budget_period = Column(String(7), nullable=False)  # YYYY-MM
    budget_type = Column(
        SAEnum(BudgetPeriodType, name="budget_period_type"),
        nullable=False,
        default=BudgetPeriodType.MONTHLY,
    )

    target_labor_cost_rate = Column(Numeric(6, 2), nullable=False)  # 目标成本率 %
    max_labor_cost_yuan = Column(Numeric(14, 2), nullable=False)  # 最高成本¥
    daily_budget_yuan = Column(Numeric(12, 2), nullable=True)  # 日参考预算¥

    alert_threshold_pct = Column(Numeric(5, 2), nullable=False, default=90.0)  # 预警阈值 %
    approved_by = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return (
            f"<StoreLaborBudget(store='{self.store_id}', "
            f"period='{self.budget_period}', target={self.target_labor_cost_rate}%)>"
        )


# ─────────────────────────────────────────────────────────
# 6. labor_cost_rankings — 跨店成本率排名快照
# ─────────────────────────────────────────────────────────
class LaborCostRanking(Base):
    """
    每日跨店排名快照，支持"你在X家门店中排第Y"的差异化话术。
    UNIQUE: store_id + ranking_date + period_type
    """

    __tablename__ = "labor_cost_rankings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    ranking_date = Column(Date, nullable=False, index=True)
    period_type = Column(
        SAEnum(RankingPeriodType, name="ranking_period_type"),
        nullable=False,
    )

    labor_cost_rate = Column(Numeric(6, 2), nullable=False)  # 本店成本率 %
    rank_in_group = Column(Integer, nullable=False)  # 排名（1=最优）
    total_stores_in_group = Column(Integer, nullable=False)
    percentile_score = Column(Numeric(5, 1), nullable=True)  # 0–100, 越高越好
    group_avg_rate = Column(Numeric(6, 2), nullable=True)  # 组均值 %
    group_median_rate = Column(Numeric(6, 2), nullable=True)  # 组中位值 %
    best_rate_in_group = Column(Numeric(6, 2), nullable=True)  # 组最优 %

    brand_id = Column(String(50), nullable=True, index=True)  # 品牌分组
    created_at = Column(DateTime, nullable=False)

    def __repr__(self):
        return (
            f"<LaborCostRanking(store='{self.store_id}', "
            f"date='{self.ranking_date}', rank={self.rank_in_group}"
            f"/{self.total_stores_in_group})>"
        )


# ─────────────────────────────────────────────────────────
# 7. staffing_patterns — 历史最优排班模板库
# ─────────────────────────────────────────────────────────
class StaffingPattern(Base, TimestampMixin):
    """
    从历史最优排班中抽取的模板，按 weekday/weekend/holiday 分组。
    快速用于相似日期排班。
    """

    __tablename__ = "staffing_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    pattern_name = Column(String(100), nullable=False)
    day_type = Column(String(20), nullable=False, index=True)  # weekday/weekend/holiday
    meal_period = Column(String(20), nullable=False, default="all_day")

    # 模板内容：
    # [
    #   {"shift_type":"morning","position":"waiter","required_count":3,"start":"08:00","end":"14:00"},
    #   ...
    # ]
    shifts_template = Column(JSON, nullable=False, default=list)

    source_start_date = Column(Date, nullable=True)
    source_end_date = Column(Date, nullable=True)
    sample_days = Column(Integer, nullable=False, default=0)
    avg_labor_cost_rate = Column(Numeric(6, 2), nullable=True)
    performance_score = Column(Numeric(6, 2), nullable=True)  # 越高越优先
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return (
            f"<StaffingPattern(store='{self.store_id}', name='{self.pattern_name}', "
            f"day_type='{self.day_type}', score={self.performance_score})>"
        )
