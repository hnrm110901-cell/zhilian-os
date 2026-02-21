"""
Reconciliation Model
对账记录模型
"""
from sqlalchemy import Column, String, Integer, Float, Text, Date, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import date

from .base import Base, TimestampMixin


class ReconciliationStatus(str, enum.Enum):
    """对账状态"""
    PENDING = "pending"  # 待对账
    MATCHED = "matched"  # 已匹配
    MISMATCHED = "mismatched"  # 有差异
    CONFIRMED = "confirmed"  # 已确认
    INVESTIGATING = "investigating"  # 调查中


class ReconciliationRecord(Base, TimestampMixin):
    """对账记录模型"""

    __tablename__ = "reconciliation_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本信息
    store_id = Column(String(50), nullable=False, index=True)
    reconciliation_date = Column(Date, nullable=False, index=True)  # 对账日期

    # POS数据
    pos_total_amount = Column(Integer, default=0)  # POS总金额（分）
    pos_order_count = Column(Integer, default=0)  # POS订单数
    pos_transaction_count = Column(Integer, default=0)  # POS交易笔数

    # 实际数据
    actual_total_amount = Column(Integer, default=0)  # 实际总金额（分）
    actual_order_count = Column(Integer, default=0)  # 实际订单数
    actual_transaction_count = Column(Integer, default=0)  # 实际交易笔数

    # 差异数据
    diff_amount = Column(Integer, default=0)  # 金额差异（分）
    diff_ratio = Column(Float, default=0.0)  # 差异比例（%）
    diff_order_count = Column(Integer, default=0)  # 订单数差异
    diff_transaction_count = Column(Integer, default=0)  # 交易笔数差异

    # 状态和处理
    status = Column(
        Enum(ReconciliationStatus, values_callable=lambda x: [e.value for e in x]),
        default=ReconciliationStatus.PENDING,
        nullable=False,
        index=True
    )

    # 差异详情
    discrepancies = Column(JSON)  # 差异明细（JSON格式）
    notes = Column(Text)  # 备注说明

    # 处理信息
    confirmed_by = Column(UUID(as_uuid=True))  # 确认人
    confirmed_at = Column(String(50))  # 确认时间
    resolution = Column(Text)  # 解决方案

    # 预警信息
    alert_sent = Column(String(10), default="false")  # 是否已发送预警
    alert_sent_at = Column(String(50))  # 预警发送时间

    def __repr__(self):
        return f"<ReconciliationRecord(store_id='{self.store_id}', date='{self.reconciliation_date}', status='{self.status}')>"
