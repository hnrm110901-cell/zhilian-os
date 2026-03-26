"""
菜品规格模型 — 同一菜品多规格多单位定价

设计要点：
  - 同一菜品（如东星斑）支持多规格（时价/斤、整条/条）
  - 每种规格独立定价（price_fen）和成本核算（cost_fen）
  - bom_multiplier 控制 BOM 扣减系数（大份=1.5, 中份=1.0, 小份=0.7）
  - 金额单位：分（fen），展示时 /100 转元
"""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class DishSpecification(Base, TimestampMixin):
    """
    菜品规格 — 同一菜品多规格多单位

    业务示例（东星斑）：
      时价/斤  → price_fen=按斤称重, bom_multiplier=1.0, unit=斤
      整条/条  → price_fen=固定价, bom_multiplier=1.0, unit=条

    业务示例（回锅肉）：
      大份 → price_fen=6800, bom_multiplier=1.5, unit=份
      中份 → price_fen=4800, bom_multiplier=1.0, unit=份
      小份 → price_fen=3200, bom_multiplier=0.7, unit=份
    """

    __tablename__ = "dish_specifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 菜品关联
    dish_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 规格名称：大份/中份/小份/例/半份/斤/只/条/位
    spec_name = Column(String(50), nullable=False)

    # 该规格售价（分）
    price_fen = Column(Integer, nullable=False)

    # 该规格成本（分），可为空表示尚未核算
    cost_fen = Column(Integer, nullable=True)

    # BOM 系数（大份=1.5, 中份=1.0, 小份=0.7）
    bom_multiplier = Column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("1.00"),
    )

    # 计量单位：份/斤/只/条/位/克
    unit = Column(String(20), nullable=False, default="份")

    # 最小点单量（如龙虾至少点2只）
    min_order_qty = Column(Integer, nullable=False, default=1)

    # 是否默认规格（每道菜应有且仅有一个默认规格）
    is_default = Column(Boolean, nullable=False, default=False)

    # 是否可选（临时下架某规格）
    is_available = Column(Boolean, nullable=False, default=True)

    # 前端排序
    display_order = Column(Integer, nullable=False, default=0)

    # 关联关系
    dish = relationship("src.models.dish.Dish", foreign_keys=[dish_id])

    __table_args__ = (
        UniqueConstraint("dish_id", "spec_name", name="uq_dish_specification"),
        Index("idx_dspec_dish_id", "dish_id"),
        Index("idx_dspec_dish_available", "dish_id", "is_available"),
    )

    def __repr__(self):
        return (
            f"<DishSpecification(dish_id={self.dish_id}, "
            f"spec={self.spec_name}, price={self.price_fen}分)>"
        )

    @property
    def price_yuan(self) -> float:
        """售价（元），保留2位小数"""
        return round(self.price_fen / 100, 2)

    @property
    def cost_yuan(self) -> float | None:
        """成本（元），保留2位小数"""
        if self.cost_fen is None:
            return None
        return round(self.cost_fen / 100, 2)

    @property
    def profit_margin(self) -> float | None:
        """毛利率（%），保留2位小数"""
        if self.cost_fen is None or self.price_fen <= 0:
            return None
        return round((self.price_fen - self.cost_fen) / self.price_fen * 100, 2)
