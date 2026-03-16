"""
桌台平面图模型
定义桌台位置、形状、容量等信息
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class TableShape(str, enum.Enum):
    """桌台形状"""

    RECT = "rect"
    CIRCLE = "circle"


class TableStatus(str, enum.Enum):
    """桌台状态"""

    AVAILABLE = "available"  # 空闲
    RESERVED = "reserved"  # 已预订（未到场）
    OCCUPIED = "occupied"  # 在座
    MAINTENANCE = "maintenance"  # 维护/停用


class TableDefinition(Base, TimestampMixin):
    """桌台定义"""

    __tablename__ = "table_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 基本信息
    table_number = Column(String(20), nullable=False)
    table_type = Column(String(50), default="大厅")  # 大厅/包厢/VIP
    min_capacity = Column(Integer, default=1)
    max_capacity = Column(Integer, default=4)

    # 平面图位置（百分比坐标 0-100）
    pos_x = Column(Float, default=50.0)
    pos_y = Column(Float, default=50.0)
    width = Column(Float, default=8.0)
    height = Column(Float, default=8.0)
    rotation = Column(Float, default=0.0)
    shape = Column(Enum(TableShape), default=TableShape.RECT)

    # 区域
    floor = Column(Integer, default=1)
    area_name = Column(String(50), default="")

    # 状态
    status = Column(Enum(TableStatus), default=TableStatus.AVAILABLE)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_table_store_floor", "store_id", "floor"),
        Index("idx_table_store_number", "store_id", "table_number", unique=True),
    )

    def __repr__(self):
        return f"<TableDefinition(store={self.store_id}, number={self.table_number})>"
