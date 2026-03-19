"""
智能采购模型
ProcurementRule（采购规则）+ ProcurementExecution（执行记录）
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from src.models.base import Base
from src.models.mixins import TimestampMixin


class ProcurementRule(Base, TimestampMixin):
    """采购规则：定义食材的自动补货阈值和供应商"""

    __tablename__ = "procurement_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True)  # null = 适用所有门店

    ingredient_id = Column(String(50), nullable=False)
    ingredient_name = Column(String(100), nullable=False)

    supplier_id = Column(String(50), nullable=False)
    supplier_name = Column(String(100), nullable=False)

    # 最低库存触发阈值
    min_stock_qty = Column(Numeric(10, 2), nullable=False)
    # 补货数量
    reorder_qty = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(20), nullable=False, default="kg")
    # 单价（分）
    unit_price_fen = Column(Integer, nullable=False, default=0)

    # 供应商交货天数
    lead_days = Column(Integer, nullable=False, default=1)

    is_enabled = Column(Boolean, nullable=False, default=True)
    last_triggered_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_proc_rule_brand_store", "brand_id", "store_id"),
        Index("ix_proc_rule_ingredient", "brand_id", "ingredient_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "brand_id": self.brand_id,
            "store_id": self.store_id,
            "ingredient_id": self.ingredient_id,
            "ingredient_name": self.ingredient_name,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "min_stock_qty": float(self.min_stock_qty) if self.min_stock_qty else 0,
            "reorder_qty": float(self.reorder_qty) if self.reorder_qty else 0,
            "unit": self.unit,
            "unit_price_fen": self.unit_price_fen,
            "lead_days": self.lead_days,
            "is_enabled": self.is_enabled,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProcurementExecution(Base, TimestampMixin):
    """采购执行记录：每次触发的建议/审批/下单"""

    __tablename__ = "procurement_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("procurement_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # auto_low_stock / auto_forecast / manual
    trigger_type = Column(String(20), nullable=False)

    ingredient_name = Column(String(100), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)

    # 关联生成的采购单
    generated_order_id = Column(UUID(as_uuid=True), nullable=True)

    # suggested / approved / ordered / skipped
    status = Column(String(20), nullable=False, default="suggested")

    reason = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_proc_exec_brand_status", "brand_id", "status"),
        Index("ix_proc_exec_store", "brand_id", "store_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "rule_id": str(self.rule_id) if self.rule_id else None,
            "brand_id": self.brand_id,
            "store_id": self.store_id,
            "trigger_type": self.trigger_type,
            "ingredient_name": self.ingredient_name,
            "quantity": float(self.quantity) if self.quantity else 0,
            "generated_order_id": str(self.generated_order_id) if self.generated_order_id else None,
            "status": self.status,
            "reason": self.reason,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
