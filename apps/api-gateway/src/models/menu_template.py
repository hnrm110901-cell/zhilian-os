"""
集团菜单模板中心模型

MenuTemplate        — 集团菜单模板（品牌级）
MenuTemplateItem    — 模板菜品条目
StoreMenuDeployment — 门店部署记录
StoreDishOverride   — 门店菜品个性化
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class MenuTemplate(Base, TimestampMixin):
    """
    集团菜单模板 menu_templates

    品牌级菜单模板，可发布到全部或指定门店。
    version 每次重新发布时递增，支持版本追溯。
    """

    __tablename__ = "menu_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    brand_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    status = Column(
        Enum("draft", "active", "archived", name="menu_template_status"),
        nullable=False,
        default="draft",
    )
    apply_scope = Column(
        Enum("all_stores", "selected_stores", name="menu_template_apply_scope"),
        nullable=False,
        default="all_stores",
    )
    version = Column(Integer, nullable=False, default=1)
    published_at = Column(DateTime, nullable=True)

    # 关联
    items = relationship(
        "MenuTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    deployments = relationship(
        "StoreMenuDeployment",
        back_populates="template",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_menu_template_brand_id", "brand_id"),
        Index("idx_menu_template_status", "status"),
    )

    def __repr__(self):
        return f"<MenuTemplate(id={self.id}, name={self.name}, status={self.status})>"


class MenuTemplateItem(Base, TimestampMixin):
    """
    模板菜品条目 menu_template_items

    allow_store_adjust=True 时门店可在 max_adjust_rate 范围内调价；
    is_required=True 表示总部强制菜品，门店不能下架。
    """

    __tablename__ = "menu_template_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("menu_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dish_master_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    category = Column(String(100), nullable=False, default="")
    base_price_fen = Column(Integer, nullable=False)  # 基准价格（分）
    sort_order = Column(Integer, nullable=False, default=0)
    allow_store_adjust = Column(Boolean, nullable=False, default=True)
    max_adjust_rate = Column(Float, nullable=False, default=0.2)  # 最大调价幅度，如 0.2=20%
    is_required = Column(Boolean, nullable=False, default=False)  # 总部强制菜品

    # 关联
    template = relationship("MenuTemplate", back_populates="items")
    store_overrides = relationship(
        "StoreDishOverride",
        back_populates="template_item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_menu_template_item_template_id", "template_id"),
        Index("idx_menu_template_item_dish_master_id", "dish_master_id"),
    )

    def __repr__(self):
        return (
            f"<MenuTemplateItem(template_id={self.template_id}, "
            f"dish_master_id={self.dish_master_id}, base_price={self.base_price_fen})>"
        )


class StoreMenuDeployment(Base, TimestampMixin):
    """
    门店菜单部署记录 store_menu_deployments

    记录哪个门店部署了哪个模板，以及门店个性化覆盖次数。
    UniqueConstraint 确保同一门店同一模板只有一条部署记录。
    """

    __tablename__ = "store_menu_deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("menu_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deployed_at = Column(DateTime, nullable=False)
    deployed_by = Column(UUID(as_uuid=True), nullable=False)
    override_count = Column(Integer, nullable=False, default=0)

    # 关联
    template = relationship("MenuTemplate", back_populates="deployments")

    __table_args__ = (
        UniqueConstraint("store_id", "template_id", name="uq_store_menu_deployment"),
        Index("idx_store_menu_deployment_store_id", "store_id"),
        Index("idx_store_menu_deployment_template_id", "template_id"),
    )

    def __repr__(self):
        return (
            f"<StoreMenuDeployment(store_id={self.store_id}, "
            f"template_id={self.template_id})>"
        )


class StoreDishOverride(Base, TimestampMixin):
    """
    门店菜品个性化 store_dish_overrides

    门店对模板条目的个性化设置：自定义价格、是否上架、自定义名称。
    UniqueConstraint 确保同一门店同一模板条目只有一条覆盖记录。
    """

    __tablename__ = "store_dish_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("menu_template_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    custom_price_fen = Column(Integer, nullable=True)  # null=使用模板基准价
    is_available = Column(Boolean, nullable=False, default=True)
    custom_name = Column(String(200), nullable=True)
    updated_at = Column(DateTime, nullable=True)

    # 关联
    template_item = relationship("MenuTemplateItem", back_populates="store_overrides")

    __table_args__ = (
        UniqueConstraint(
            "store_id", "template_item_id", name="uq_store_dish_override"
        ),
        Index("idx_store_dish_override_store_id", "store_id"),
        Index("idx_store_dish_override_template_item_id", "template_item_id"),
    )

    def __repr__(self):
        return (
            f"<StoreDishOverride(store_id={self.store_id}, "
            f"template_item_id={self.template_item_id}, "
            f"price={self.custom_price_fen})>"
        )
