"""
OrgConfig — 组织节点配置存储
每行 = 某节点在某 config_key 上的配置值
ConfigResolver 负责按继承链读取最终生效值
"""
import uuid
import json
from sqlalchemy import Column, String, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


# 已知 config_key 常量（不枚举，允许自由扩展）
class ConfigKey:
    # ── 排班规则 ──────────────────────────────────
    MAX_CONSECUTIVE_WORK_DAYS = "max_consecutive_work_days"   # int, 默认 6
    MIN_REST_HOURS_BETWEEN_SHIFTS = "min_rest_hours"          # int, 默认 8
    SPLIT_SHIFT_ALLOWED = "split_shift_allowed"               # bool, 默认 false
    OVERTIME_MULTIPLIER = "overtime_multiplier"               # float, 默认 1.5
    WEEKEND_PREMIUM = "weekend_premium"                       # float, 默认 1.0

    # ── 人力成本 ──────────────────────────────────
    LABOR_COST_RATIO_TARGET = "labor_cost_ratio_target"       # float, 默认 0.30
    MIN_HOURLY_WAGE = "min_hourly_wage"                       # float（元/小时）

    # ── 试用期规则 ────────────────────────────────
    PROBATION_DAYS = "probation_days"                         # int, 默认 90
    TRIAL_DAYS = "trial_days"                                 # int, 默认 3

    # ── KPI 基线 ──────────────────────────────────
    CUSTOMER_SATISFACTION_TARGET = "csat_target"             # float, 默认 4.5
    FOOD_COST_RATIO_TARGET = "food_cost_ratio_target"         # float, 默认 0.35

    # ── 企业微信 ──────────────────────────────────
    WECHAT_CORP_ID = "wechat_corp_id"                         # str
    WECHAT_AGENT_ID = "wechat_agent_id"                       # str

    # ── 考勤 ──────────────────────────────────────
    ATTENDANCE_GRACE_MINUTES = "attendance_grace_minutes"     # int, 默认 5（迟到宽限）
    ATTENDANCE_MODE = "attendance_mode"                       # str: wechat/machine/manual

    # ── KPI 权重（JSON，按岗位） ──────────────────────────────
    ROLE_KPI_CONFIG = "role_kpi_config"           # json: {role: [{key,weight,target,higher},...]}
    PERF_RATING_THRESHOLDS = "perf_rating_thresholds"  # json: [[score, rating], ...]

    # ── 成本告警阈值 ──────────────────────────────────────────
    FOOD_COST_ALERT_THRESHOLD = "food_cost_alert_threshold"       # float, 默认 0.42
    LABOR_COST_ALERT_THRESHOLD = "labor_cost_alert_threshold"     # float, 默认 0.35
    LABOR_COST_WARNING_THRESHOLD = "labor_cost_warning_threshold" # float, 默认 0.32
    WASTE_RATE_TARGET = "waste_rate_target"                       # float, 默认 0.03
    FOOD_COST_RATIO_ALERT = "food_cost_ratio_alert"               # float, 默认 0.42

    # ── 营收目标与趋势告警 ──────────────────────────────────
    REVENUE_GROWTH_TARGET = "revenue_growth_target"               # float, 默认 0.15
    REVENUE_TREND_INCREASE_THRESHOLD = "revenue_trend_increase"   # float, 默认 0.15
    REVENUE_TREND_DECREASE_THRESHOLD = "revenue_trend_decrease"   # float, 默认 -0.15

    # ── 排班时段定义（JSON） ──────────────────────────────────
    SHIFT_MORNING_START = "shift_morning_start"   # str "06:00"
    SHIFT_MORNING_END   = "shift_morning_end"     # str "14:00"
    SHIFT_AFTERNOON_START = "shift_afternoon_start"  # str "14:00"
    SHIFT_AFTERNOON_END   = "shift_afternoon_end"    # str "22:00"
    SHIFT_EVENING_START = "shift_evening_start"   # str "18:00"
    SHIFT_EVENING_END   = "shift_evening_end"     # str "02:00"
    SHIFT_FULLDAY_START = "shift_fullday_start"   # str "09:00"
    SHIFT_FULLDAY_END   = "shift_fullday_end"     # str "21:00"
    PEAK_HOURS = "peak_hours"                     # json: [{"start":"12:00","end":"13:00"},...]

    # ── 会员体系 ──────────────────────────────────────────────
    MEMBER_LEVEL_THRESHOLDS = "member_level_thresholds"  # json: {level: min_visits}
    MEMBER_FIRST_SPEND_THRESHOLD = "member_first_spend_threshold"  # float, 默认 100.0
    MEMBER_CONSECUTIVE_MONTHS = "member_consecutive_months"        # int, 默认 3
    POINTS_EXPIRING_ALERT_DAYS = "points_expiring_alert_days"      # int, 默认 7
    MEMBER_DISCOUNT_RATE = "member_discount_rate"                  # float, 默认 0.10
    COUPON_DISCOUNT_AMOUNT = "coupon_discount_amount"              # float, 默认 10.0

    # ── 动态定价 ────────────────────────────────────────────
    DYNAMIC_PRICING_FACTORS = "dynamic_pricing_factors"  # json: {high:1.2, normal:1.0, low:0.95}

    # ── 排班约束 ────────────────────────────────────────────
    SCHEDULE_MIN_SHIFT_HOURS = "schedule_min_shift_hours"   # int, 默认 4
    SCHEDULE_MAX_SHIFT_HOURS = "schedule_max_shift_hours"   # int, 默认 8
    SCHEDULE_MAX_WEEKLY_HOURS = "schedule_max_weekly_hours" # int, 默认 40
    SCHEDULE_SCORING_WEIGHTS = "schedule_scoring_weights"   # json: {preference:0.35,skill:0.35,...}

    # ── 供应商评分 ───────────────────────────────────────────
    SUPPLIER_SCORE_WEIGHTS = "supplier_score_weights"  # json: {price:0.30,quality:0.35,delivery:0.25,service:0.10}
    SUPPLIER_PRICE_TOLERANCE = "supplier_price_tolerance"   # float, 默认 0.10
    SUPPLIER_EXCELLENT_THRESHOLD = "supplier_excellent_threshold"  # float, 默认 1.5

    # ── 库存告警 ─────────────────────────────────────────────
    INVENTORY_LOW_STOCK_RATIO = "inventory_low_stock_ratio"   # float, 默认 0.30
    INVENTORY_CRITICAL_RATIO = "inventory_critical_ratio"     # float, 默认 0.10
    INVENTORY_EXPIRING_DAYS = "inventory_expiring_days"       # int, 默认 7
    INVENTORY_URGENT_DAYS = "inventory_urgent_days"           # int, 默认 3

    # ── 菜品质量 ─────────────────────────────────────────────
    DISH_RETURN_RATE_ALERT = "dish_return_rate_alert"        # float, 默认 0.15
    DISH_MIN_GROSS_MARGIN = "dish_min_gross_margin"          # float, 默认 0.50
    DISH_RECOMMENDATION_WEIGHTS = "dish_recommendation_weights"  # json

    # ── 裂变营销 ─────────────────────────────────────────────
    REFERRAL_BIRTHDAY_DELAY_HOURS = "referral_birthday_delay_hours"  # int, 默认 24
    REFERRAL_FAMILY_MIN_PARTY = "referral_family_min_party"          # int, 默认 6
    REFERRAL_BUSINESS_MIN_PARTY = "referral_business_min_party"      # int, 默认 4
    REFERRAL_SUPER_FAN_FREQUENCY = "referral_super_fan_frequency"    # int, 默认 4 (30天内次数)
    REFERRAL_VIRAL_COEFFICIENTS = "referral_viral_coefficients"      # json: {birthday:3.2,...}

    # ── 营销内容 ─────────────────────────────────────────────
    CONTENT_PUBLISH_HOURS = "content_publish_hours"          # json: [11, 18]
    HOLIDAY_PROMOTION_ADVANCE_DAYS = "holiday_promotion_advance_days"  # int, 默认 3
    MEALTIME_SEGMENTS = "mealtime_segments"                  # json: [{name,start_hour,end_hour},...]

    # ── 绩效计件 ─────────────────────────────────────────────
    PIECE_RATE_TIERS = "piece_rate_tiers"                    # json: [{max_orders, rate_per_order}, ...]
    KPI_ACHIEVEMENT_MAX_CAP = "kpi_achievement_max_cap"      # float, 默认 2.0
    BASELINE_TABLE_TURNOVER = "baseline_table_turnover"      # float, 默认 3.0
    BASELINE_REVENUE_PER_EMPLOYEE = "baseline_revenue_per_employee"  # float, 默认 1200.0

    # ── 考勤告警 ─────────────────────────────────────────────
    ATTENDANCE_ABSENT_CRITICAL_COUNT = "attendance_absent_critical_count"  # int, 默认 3
    ATTENDANCE_EARLY_LEAVE_WARNING_COUNT = "attendance_early_leave_warning_count"  # int, 默认 2


class OrgConfig(Base, TimestampMixin):
    """
    组织节点配置行
    唯一约束：(org_node_id, config_key)
    """
    __tablename__ = "org_configs"
    __table_args__ = (
        UniqueConstraint("org_node_id", "config_key", name="uq_org_config_node_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_node_id  = Column(String(64), ForeignKey("org_nodes.id"), nullable=False, index=True)
    config_key   = Column(String(128), nullable=False, index=True)
    config_value = Column(Text, nullable=False)           # 序列化为字符串存储
    value_type   = Column(String(16), default="str")      # str / int / float / bool / json
    description  = Column(Text, nullable=True)            # 可选说明
    is_override  = Column(Boolean, default=False)         # True = 明确覆盖父节点（不继续向上查找）
    set_by       = Column(String(64), nullable=True)      # 设置人 user_id

    # 关系
    org_node = relationship("OrgNode", back_populates="configs")

    def typed_value(self):
        """返回强类型值"""
        v = self.config_value
        if self.value_type == "int":
            return int(v)
        if self.value_type == "float":
            return float(v)
        if self.value_type == "bool":
            return v.lower() in ("true", "1", "yes")
        if self.value_type == "json":
            return json.loads(v)
        return v  # str

    def __repr__(self):
        return f"<OrgConfig(node='{self.org_node_id}', key='{self.config_key}', value='{self.config_value}')>"
