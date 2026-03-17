"""
WarningRule — 预警规则表
配置各经营指标的红黄绿阈值。
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, Date
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class WarningRule(Base, TimestampMixin):
    """预警规则表"""
    __tablename__ = "warning_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code = Column(String(64), unique=True, nullable=False, index=True)
    rule_name = Column(String(128), nullable=False)
    business_scope = Column(String(32), nullable=False)  # store/region/brand
    metric_code = Column(String(64), nullable=False)      # 指标编码
    compare_operator = Column(String(16), nullable=False) # gt/gte/lt/lte/between
    yellow_threshold = Column(String(64))                 # 黄灯阈值
    red_threshold = Column(String(64))                    # 红灯阈值
    baseline_type = Column(String(32))                    # fixed/mom/yoy/rolling_7d_avg
    rule_expression = Column(Text)                        # 复杂规则表达式
    priority = Column(Integer, default=0, nullable=False)
    is_mandatory_comment = Column(Boolean, default=True, nullable=False)  # 是否必须说明
    is_auto_task = Column(Boolean, default=True, nullable=False)          # 是否自动生成任务
    enabled = Column(Boolean, default=True, nullable=False)
    effective_start_date = Column(Date)
    effective_end_date = Column(Date)
    created_by = Column(String(64), nullable=False)

    def __repr__(self):
        return f"<WarningRule(rule_code='{self.rule_code}', metric='{self.metric_code}')>"
