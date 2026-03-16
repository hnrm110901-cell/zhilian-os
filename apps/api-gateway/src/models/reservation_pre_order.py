"""
预排菜模型 — 预订关联菜品（P0 预排菜功能补齐）

支持预订时提前选菜、锁定菜品、备注口味偏好。
用于：
1. 客户预订时提前选菜（H5/小程序）
2. 宴会预订锁定套餐菜单
3. 厨房提前备料（提升出餐效率）
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class PreOrderStatus(str, enum.Enum):
    """预排菜状态"""

    DRAFT = "draft"  # 草稿（客户选择中）
    CONFIRMED = "confirmed"  # 已确认（客户/门店确认）
    PREPARING = "preparing"  # 备料中（厨房已接单）
    CANCELLED = "cancelled"  # 已取消


class ReservationPreOrder(Base, TimestampMixin):
    """预订预排菜关联表"""

    __tablename__ = "reservation_pre_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reservation_id = Column(String(50), ForeignKey("reservations.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 菜品信息（快照，避免菜品删改后丢失）
    dish_id = Column(UUID(as_uuid=True), ForeignKey("dishes.id"), nullable=True)
    dish_name = Column(String(100), nullable=False)
    dish_code = Column(String(50), nullable=True)
    unit_price = Column(Integer, nullable=False)  # 单价（分）

    # 数量与金额
    quantity = Column(Integer, nullable=False, default=1)
    subtotal = Column(Integer, nullable=False, default=0)  # 小计（分）= unit_price * quantity

    # 口味与备注
    taste_note = Column(String(200), nullable=True)  # 口味要求：少盐/加辣/不要香菜
    serving_size = Column(String(50), nullable=True)  # 规格：大份/中份/小份

    # 状态
    status = Column(Enum(PreOrderStatus), default=PreOrderStatus.DRAFT, nullable=False)
    is_locked = Column(Boolean, default=False)  # 锁定后不可修改（宴会确认后锁定）

    # 排序
    sort_order = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_pre_order_reservation", "reservation_id"),
        Index("idx_pre_order_store", "store_id"),
        Index("idx_pre_order_dish", "dish_id"),
    )

    def __repr__(self):
        return f"<ReservationPreOrder(reservation={self.reservation_id}, dish={self.dish_name}, qty={self.quantity})>"
