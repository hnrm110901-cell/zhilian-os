"""三角对账模型 — Order ↔ Payment ↔ Bank Statement ↔ Invoice 四方匹配记录"""

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class TriReconciliationRecord(Base, TimestampMixin):
    """三角对账匹配记录 — 一条代表一组已匹配/未匹配的跨系统关联"""

    __tablename__ = "tri_reconciliation_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)

    # 对账日期（交易发生日）
    match_date = Column(Date, nullable=False, index=True)

    # 订单侧
    order_id = Column(String(100), nullable=True, index=True)
    order_amount_fen = Column(Integer, nullable=True)

    # 支付侧
    payment_id = Column(String(100), nullable=True, index=True)
    payment_amount_fen = Column(Integer, nullable=True)

    # 银行流水侧
    bank_statement_id = Column(String(100), nullable=True, index=True)
    bank_amount_fen = Column(Integer, nullable=True)

    # 发票侧
    invoice_id = Column(String(100), nullable=True, index=True)
    invoice_amount_fen = Column(Integer, nullable=True)

    # 匹配级别: full_match(4方) / triple_match(3方) / double_match(2方) / single(未匹配)
    match_level = Column(String(20), nullable=False, default="single", index=True)

    # 差异金额（已匹配金额中的最大差值，单位：分）
    discrepancy_fen = Column(Integer, nullable=False, default=0)

    # 状态: auto_matched / manual_matched / disputed / resolved
    status = Column(String(20), nullable=False, default="auto_matched", index=True)

    # 备注（手动匹配/争议解决时填写）
    notes = Column(Text, nullable=True)

    # 匹配完成时间
    matched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_tri_recon_brand_date", "brand_id", "match_date"),
        Index("idx_tri_recon_brand_level", "brand_id", "match_level"),
        Index("idx_tri_recon_brand_status", "brand_id", "status"),
    )

    def __repr__(self):
        return (
            f"<TriReconciliationRecord(date='{self.match_date}', "
            f"level='{self.match_level}', discrepancy={self.discrepancy_fen})>"
        )
