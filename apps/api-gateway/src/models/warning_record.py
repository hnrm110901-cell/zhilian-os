"""
WarningRecord — 预警记录表
存储某门店某天命中的具体预警。
"""
from sqlalchemy import Column, String, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class WarningRecord(Base, TimestampMixin):
    """预警记录表"""
    __tablename__ = "warning_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(String(10), nullable=False, index=True)
    settlement_id = Column(UUID(as_uuid=True))            # 关联日结单（可为空）
    rule_id = Column(UUID(as_uuid=True), nullable=False)  # 关联规则
    rule_code = Column(String(64), nullable=False)
    rule_name = Column(String(128), nullable=False)
    warning_type = Column(String(64), nullable=False)     # 预警类型
    metric_code = Column(String(64), nullable=False)      # 指标编码
    actual_value = Column(Integer)                        # 实际值×10000
    baseline_value = Column(Integer)                      # 基准值×10000
    yellow_threshold_value = Column(String(64))
    red_threshold_value = Column(String(64))
    warning_level = Column(String(16), nullable=False)    # green/yellow/red
    reason_code = Column(String(64))
    reason_text = Column(String(256))
    # 状态：active/linked_task/explained/resolved/ignored
    status = Column(String(32), default="active", nullable=False, index=True)
    related_task_id = Column(UUID(as_uuid=True))

    def __repr__(self):
        return f"<WarningRecord(store_id='{self.store_id}', biz_date='{self.biz_date}', level='{self.warning_level}')>"
