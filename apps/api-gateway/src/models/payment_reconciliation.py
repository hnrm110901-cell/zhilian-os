"""支付对账模型 — 支付流水/对账批次/差异记录"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class PaymentChannel(str, enum.Enum):
    WECHAT = "wechat"
    ALIPAY = "alipay"
    CASH = "cash"
    CARD = "card"
    MEITUAN = "meituan"
    ELEME = "eleme"
    DOUYIN = "douyin"
    UNION_PAY = "union_pay"
    OTHER = "other"


class MatchStatus(str, enum.Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    PARTIAL = "partial"
    DISPUTED = "disputed"


class PaymentRecord(Base, TimestampMixin):
    """支付流水记录（从第三方渠道账单导入）"""

    __tablename__ = "payment_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)
    channel = Column(String(20), nullable=False, index=True)  # PaymentChannel
    trade_no = Column(String(100), nullable=False)  # 第三方交易号
    out_trade_no = Column(String(100), nullable=True)  # 商户订单号
    amount_fen = Column(Integer, nullable=False)  # 交易金额(分)
    fee_fen = Column(Integer, nullable=False, default=0)  # 手续费(分)
    settle_amount_fen = Column(Integer, nullable=False, default=0)  # 结算金额(分)
    trade_time = Column(DateTime, nullable=False)
    settle_date = Column(Date, nullable=True)
    trade_type = Column(String(20), nullable=False, default="payment")  # payment/refund
    matched_order_id = Column(String(50), nullable=True)
    match_status = Column(String(20), nullable=False, default=MatchStatus.UNMATCHED.value)
    import_batch_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    def __repr__(self):
        return f"<PaymentRecord(trade_no='{self.trade_no}', " f"channel='{self.channel}', amount={self.amount_fen})>"


class ReconciliationBatch(Base, TimestampMixin):
    """对账批次 — 每次执行对账生成一条"""

    __tablename__ = "reconciliation_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    channel = Column(String(20), nullable=False)
    reconcile_date = Column(Date, nullable=False)

    # POS侧
    pos_total_count = Column(Integer, nullable=False, default=0)
    pos_total_fen = Column(Integer, nullable=False, default=0)

    # 渠道侧
    channel_total_count = Column(Integer, nullable=False, default=0)
    channel_total_fen = Column(Integer, nullable=False, default=0)
    channel_fee_fen = Column(Integer, nullable=False, default=0)

    # 对账结果
    matched_count = Column(Integer, nullable=False, default=0)
    unmatched_pos_count = Column(Integer, nullable=False, default=0)  # POS有渠道无
    unmatched_channel_count = Column(Integer, nullable=False, default=0)  # 渠道有POS无
    diff_fen = Column(Integer, nullable=False, default=0)  # 差异金额
    match_rate = Column(Float, nullable=True)  # 匹配率 0~1

    status = Column(String(20), nullable=False, default="pending")  # pending/running/completed/failed
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<ReconciliationBatch(channel='{self.channel}', " f"date='{self.reconcile_date}', status='{self.status}')>"


class ReconciliationDiff(Base, TimestampMixin):
    """对账差异记录"""

    __tablename__ = "reconciliation_diffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reconciliation_batches.id"),
        nullable=False,
        index=True,
    )
    diff_type = Column(String(30), nullable=False)  # pos_only/channel_only/amount_mismatch
    trade_no = Column(String(100), nullable=True)
    pos_amount_fen = Column(Integer, nullable=True)
    channel_amount_fen = Column(Integer, nullable=True)
    diff_amount_fen = Column(Integer, nullable=True)
    order_id = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ReconciliationDiff(type='{self.diff_type}', " f"trade_no='{self.trade_no}', diff={self.diff_amount_fen})>"
