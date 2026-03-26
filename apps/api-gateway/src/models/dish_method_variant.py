"""
菜品做法变体模型 — 同一海鲜不同做法对应不同BOM/工位/时间/成本

设计要点：
  - 同一道菜（如东星斑）可有多种做法（清蒸/红烧/刺身/椒盐）
  - 每种做法关联独立的 BOM 模板（用料不同）
  - 每种做法路由到不同 KDS 工位（蒸柜/炒锅/凉菜间）
  - extra_cost_fen 记录做法附加费（如刺身加工费）
  - 金额单位：分（fen），展示时 /100 转元
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class DishMethodVariant(Base, TimestampMixin):
    """
    菜品做法变体 — 同一海鲜不同做法对应不同BOM/工位/时间/成本

    业务示例（东星斑）：
      清蒸 → 蒸柜, 12min, BOM-v1, +0分
      红烧 → 炒锅, 15min, BOM-v2, +0分
      刺身 → 凉菜, 5min, BOM-v3, +2000分
      椒盐 → 油炸, 10min, BOM-v4, +0分
    """

    __tablename__ = "dish_method_variants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 菜品关联
    dish_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 做法名称：清蒸/红烧/白灼/椒盐/蒜蓉/避风塘/刺身/铁板/干锅
    method_name = Column(String(50), nullable=False)

    # KDS 工位：蒸柜/炒锅/凉菜间/油炸/铁板/干锅
    kitchen_station = Column(String(50), nullable=False)

    # 制作时间（分钟）
    prep_time_minutes = Column(Integer, nullable=False, default=10)

    # 关联 BOM 模板（不同做法用料不同，可为空表示暂未配置BOM）
    bom_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bom_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 做法附加费（分），如铁板+500分、刺身+2000分
    extra_cost_fen = Column(Integer, nullable=False, default=0)

    # 是否默认做法（每道菜应有且仅有一个默认做法）
    is_default = Column(Boolean, nullable=False, default=False)

    # 是否可选（临时下架某做法）
    is_available = Column(Boolean, nullable=False, default=True)

    # 前端排序
    display_order = Column(Integer, nullable=False, default=0)

    # 做法说明（如"清蒸保留原味，推荐鲜活海鲜"）
    description = Column(Text, nullable=True)

    # 关联关系
    dish = relationship("src.models.dish.Dish", foreign_keys=[dish_id])
    bom_template = relationship("BOMTemplate", foreign_keys=[bom_template_id])

    __table_args__ = (
        UniqueConstraint("dish_id", "method_name", name="uq_dish_method_variant"),
        Index("idx_dmv_dish_id", "dish_id"),
        Index("idx_dmv_bom_template_id", "bom_template_id"),
        Index("idx_dmv_dish_available", "dish_id", "is_available"),
        Index("idx_dmv_kitchen_station", "kitchen_station"),
    )

    def __repr__(self):
        return (
            f"<DishMethodVariant(dish_id={self.dish_id}, "
            f"method={self.method_name}, station={self.kitchen_station})>"
        )

    @property
    def extra_cost_yuan(self) -> float:
        """附加费（元），保留2位小数"""
        return round(self.extra_cost_fen / 100, 2)
