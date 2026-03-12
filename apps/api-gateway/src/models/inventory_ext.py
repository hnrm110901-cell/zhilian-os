"""
Inventory extensions: Batch tracking & Physical counts
"""
from sqlalchemy import Column, String, Integer, Numeric, Boolean, Text, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base, TimestampMixin


class InventoryBatch(Base, TimestampMixin):
    """库存批次 — FIFO/先到期先出追踪"""
    __tablename__ = "inventory_batches"

    batch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    purchase_order_id = Column(String(50))
    supplier_id = Column(String(50))
    batch_no = Column(String(50))                           # 供应商批次号
    received_date = Column(Date, nullable=False)
    production_date = Column(Date)
    expiry_date = Column(Date)
    received_qty = Column(Numeric(12, 4), nullable=False)
    remaining_qty = Column(Numeric(12, 4), nullable=False)
    unit_cost_fen = Column(Integer, nullable=False)
    quality_grade = Column(String(10))                      # A/B/C
    inspection_result = Column(String(20))                  # passed/partial_reject/full_reject
    inspection_notes = Column(Text)
    status = Column(String(20), nullable=False, default="active")  # active/depleted/expired/recalled


class InventoryCount(Base, TimestampMixin):
    """盘点记录"""
    __tablename__ = "inventory_counts"

    count_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    count_date = Column(Date, nullable=False)
    count_type = Column(String(20), nullable=False)          # daily_close/weekly/monthly/spot_check
    item_id = Column(String(50), nullable=False)
    system_qty = Column(Numeric(12, 4), nullable=False)
    actual_qty = Column(Numeric(12, 4), nullable=False)
    variance_qty = Column(Numeric(12, 4), nullable=False)
    variance_cost_fen = Column(Integer)
    variance_reason = Column(String(30))                     # normal_loss/theft/measurement_error/...
    counted_by = Column(String(50), nullable=False)
    verified_by = Column(String(50))
    photo_url = Column(Text)
