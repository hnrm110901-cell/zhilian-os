"""
BOM（物料清单）模型 — 版本化配方管理

设计要点：
  - BOMTemplate (dish_id, version) 构成复合唯一键，支持时间旅行查询
  - effective_date / expiry_date 实现有效期管理
  - SUCCEEDED_BY 版本链由 Neo4j 本体层维护
  - BOMItem 记录每版 BOM 对每种食材的标准用量
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Numeric, Text, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class BOMTemplate(Base, TimestampMixin):
    """
    BOM 版本主表

    同一道菜可以有多个版本（price change / season change / supplier change）。
    某一时刻只有一个版本处于 is_active=True 的"当前版本"。
    """
    __tablename__ = "bom_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 菜品关联
    dish_id = Column(UUID(as_uuid=True), ForeignKey("dishes.id"), nullable=False, index=True)

    # 版本标识（语义版本：v1、v2；或日期：2026-03）
    version = Column(String(20), nullable=False)

    # 有效期管理（支持时间旅行查询）
    effective_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    expiry_date = Column(DateTime, nullable=True)  # None 表示当前版本

    # 配方属性
    yield_rate = Column(Numeric(5, 4), nullable=False, default=1.0)  # 出成率 0.0~1.0
    standard_portion = Column(Numeric(8, 3))  # 标准份重（克）
    prep_time_minutes = Column(Integer)  # 制作工时（分钟）

    # 状态
    is_active = Column(Boolean, nullable=False, default=True)  # 当前有效版本
    is_approved = Column(Boolean, nullable=False, default=False)  # 已审核
    approved_by = Column(String(100))  # 审核人
    approved_at = Column(DateTime)

    # 元数据
    notes = Column(Text)
    created_by = Column(String(100))

    # 关联
    items = relationship(
        "BOMItem",
        back_populates="bom_template",
        cascade="all, delete-orphan",
    )
    dish = relationship("Dish", foreign_keys=[dish_id])

    __table_args__ = (
        UniqueConstraint("dish_id", "version", name="uq_bom_dish_version"),
        Index("idx_bom_store_id", "store_id"),
        Index("idx_bom_dish_id", "dish_id"),
        Index("idx_bom_active", "dish_id", "is_active"),
        Index("idx_bom_effective_date", "effective_date"),
    )

    def __repr__(self):
        return f"<BOMTemplate(dish_id={self.dish_id}, version={self.version}, active={self.is_active})>"

    @property
    def total_cost(self) -> float:
        """计算 BOM 食材总成本（分）"""
        return sum(
            (item.standard_qty * (item.unit_cost or 0))
            for item in self.items
        )


class BOMItem(Base, TimestampMixin):
    """
    BOM 明细行 — 每版配方中每种食材的标准用量

    与 InventoryItem 通过 ingredient_id 关联；
    unit_cost 在 BOMItem 层面快照（与 InventoryItem.unit_cost 保持同步）。
    """
    __tablename__ = "bom_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bom_id = Column(UUID(as_uuid=True), ForeignKey("bom_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 食材关联（对应 InventoryItem.id）
    ingredient_id = Column(String(50), ForeignKey("inventory_items.id"), nullable=False, index=True)

    # 用量信息
    standard_qty = Column(Numeric(10, 4), nullable=False)  # 标准用量（含出成损耗已换算）
    raw_qty = Column(Numeric(10, 4))  # 毛料用量（未处理）
    unit = Column(String(20), nullable=False)  # 克、毫升、个、份

    # 成本快照（采购时价格快照，用于历史成本核算）
    unit_cost = Column(Integer)  # 分/单位

    # 属性
    is_key_ingredient = Column(Boolean, default=False)  # 核心食材（损耗监控重点）
    is_optional = Column(Boolean, default=False)  # 可选配料
    waste_factor = Column(Numeric(5, 4), default=0.0)  # 预期损耗系数

    # 备注
    prep_notes = Column(Text)  # 加工说明

    # 关联
    bom_template = relationship("BOMTemplate", back_populates="items")
    ingredient = relationship("InventoryItem", foreign_keys=[ingredient_id])

    __table_args__ = (
        UniqueConstraint("bom_id", "ingredient_id", name="uq_bom_item_ingredient"),
        Index("idx_bom_item_bom_id", "bom_id"),
        Index("idx_bom_item_ingredient_id", "ingredient_id"),
        Index("idx_bom_item_store_id", "store_id"),
    )

    def __repr__(self):
        return f"<BOMItem(bom_id={self.bom_id}, ingredient_id={self.ingredient_id}, qty={self.standard_qty})>"
