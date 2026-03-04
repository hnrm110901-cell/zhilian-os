"""
集团菜品主档模型

DishMaster  — 集团级 SKU 主档（canonical_name / floor_price / allergens）
BrandMenu   — 品牌层价格覆盖
StoreMenu   — 门店层价格覆盖（继承链：集团→品牌→门店）
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class DishMaster(Base, TimestampMixin):
    """
    集团菜品主档表 dish_master

    sku_code 是集团内唯一业务编码；
    floor_price 是最低售价保护（分），防止门店低于成本定价；
    brand_id=null 表示全品牌通用 SKU。
    """

    __tablename__ = "dish_master"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku_code = Column(String(50), unique=True, nullable=False)          # 集团唯一SKU编码
    canonical_name = Column(String(200), nullable=False)                # 标准菜品名
    category_name = Column(String(100), nullable=False)                 # 分类名称
    floor_price = Column(Integer, nullable=False, default=0)            # 最低售价保护（分）
    allergens = Column(ARRAY(String), nullable=False, server_default='{}')
    brand_id = Column(String(50), nullable=True, index=True)            # null=全品牌通用
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)

    # 关联
    brand_menus = relationship("BrandMenu", back_populates="dish_master",
                               cascade="all, delete-orphan")
    store_menus = relationship("StoreMenu", back_populates="dish_master",
                               cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_dish_master_sku_code", "sku_code"),
        Index("idx_dish_master_brand_id", "brand_id"),
        Index("idx_dish_master_is_active", "is_active"),
    )

    def __repr__(self):
        return f"<DishMaster(sku_code={self.sku_code}, name={self.canonical_name})>"


class BrandMenu(Base, TimestampMixin):
    """
    品牌层菜单配置 brand_menus

    price_fen=null 表示继承 DishMaster.floor_price 逻辑（实际业务中继承主档推荐价）。
    """

    __tablename__ = "brand_menus"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    dish_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dish_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price_fen = Column(Integer, nullable=True)           # null=继承主档
    is_available = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)

    # 关联
    dish_master = relationship("DishMaster", back_populates="brand_menus")

    __table_args__ = (
        UniqueConstraint("brand_id", "dish_master_id", name="uq_brand_menu_brand_dish"),
        Index("idx_brand_menu_brand_id", "brand_id"),
        Index("idx_brand_menu_dish_master_id", "dish_master_id"),
    )

    def __repr__(self):
        return f"<BrandMenu(brand_id={self.brand_id}, dish_master_id={self.dish_master_id})>"


class StoreMenu(Base, TimestampMixin):
    """
    门店层菜单配置 store_menus

    price_fen=null 表示继承品牌层价格。
    """

    __tablename__ = "store_menus"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    dish_master_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dish_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price_fen = Column(Integer, nullable=True)           # null=继承品牌层
    is_available = Column(Boolean, nullable=False, default=True)

    # 关联
    dish_master = relationship("DishMaster", back_populates="store_menus")

    __table_args__ = (
        UniqueConstraint("store_id", "dish_master_id", name="uq_store_menu_store_dish"),
        Index("idx_store_menu_store_id", "store_id"),
        Index("idx_store_menu_dish_master_id", "dish_master_id"),
    )

    def __repr__(self):
        return f"<StoreMenu(store_id={self.store_id}, dish_master_id={self.dish_master_id})>"
