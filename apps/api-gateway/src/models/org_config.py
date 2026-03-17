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
