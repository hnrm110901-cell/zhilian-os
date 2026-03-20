"""定价策略与折扣规则库 — 执行价格、促销策略、毛利保护。

核心能力：
- 基于BOM成本自动建议定价（目标食材成本率反推）
- 多渠道差异化定价（堂食/外卖/团购）
- 促销规则引擎（满减/折扣/赠品/优惠券）
- 毛利保护底线（floor_price / gross_margin_floor）
- 定价执行快照（每笔订单的实际命中策略记录）
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class PricingStrategy(Base, TimestampMixin):
    """定价策略主表 — 一套定价规则集合。"""

    __tablename__ = "kb_pricing_strategies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "strategy_code", name="uq_kb_pricing_strategy_code"),
        Index("ix_kb_pricing_strategy_status", "tenant_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    strategy_code = Column(String(64), nullable=False, comment="策略编码")
    strategy_name = Column(String(128), nullable=False, comment="策略名称")
    strategy_type = Column(
        String(32), nullable=False,
        comment="策略类型: cost_plus/market/value/competitor/dynamic",
    )
    target_scope = Column(
        String(32), nullable=False,
        comment="适用范围: brand/store/category/dish",
    )
    brand_id = Column(UUID(as_uuid=True), comment="品牌ID")
    store_id = Column(UUID(as_uuid=True), comment="门店ID")
    channel_scope = Column(String(32), default="all", comment="渠道: dine_in/takeaway/all")
    priority = Column(Integer, nullable=False, default=100, comment="优先级(数字越小越优先)")

    version_no = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="draft",
                    comment="draft/published/disabled/archived")
    effective_from = Column(DateTime)
    effective_to = Column(DateTime)
    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    dish_rules = relationship("PricingDishRule", back_populates="strategy", cascade="all, delete-orphan")
    versions = relationship("PricingStrategyVersion", back_populates="strategy", cascade="all, delete-orphan")


class PricingDishRule(Base, TimestampMixin):
    """菜品定价规则 — 基于成本反推建议价格。

    定价公式：
    - cost_plus: suggested_price = base_cost / target_food_cost_ratio
    - 毛利保护: final_price >= floor_price
    - contribution_margin = final_price - base_cost
    """

    __tablename__ = "kb_pricing_dish_rules"
    __table_args__ = (
        Index("ix_kb_pricing_dish_rule_strategy", "strategy_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("kb_pricing_strategies.id"), nullable=False)

    dish_id = Column(UUID(as_uuid=True), comment="菜品ID")
    recipe_id = Column(UUID(as_uuid=True), comment="关联配方ID(取成本)")
    price_type = Column(
        String(32), nullable=False, default="standard",
        comment="standard/seasonal/promotional/new_launch",
    )

    # 成本与定价
    base_cost = Column(Numeric(12, 2), comment="基础成本(分) — 来自BOM配方")
    target_food_cost_ratio = Column(Numeric(8, 4), comment="目标食材成本率(如0.32)")
    target_contribution_margin = Column(Numeric(12, 2), comment="目标贡献利润(分)")
    suggested_price = Column(Numeric(12, 2), comment="建议售价(分)")
    final_price = Column(Numeric(12, 2), comment="最终定价(分)")
    floor_price = Column(Numeric(12, 2), comment="价格底线(分) — 毛利保护")

    status = Column(String(32), nullable=False, default="draft")
    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)

    strategy = relationship("PricingStrategy", back_populates="dish_rules")


class PricingStrategyVersion(Base, TimestampMixin):
    """定价策略版本快照。"""

    __tablename__ = "kb_pricing_strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_no", name="uq_kb_pricing_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("kb_pricing_strategies.id"), nullable=False, index=True)

    version_no = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    snapshot_json = Column(JSON, nullable=False)
    change_summary = Column(Text)

    strategy = relationship("PricingStrategy", back_populates="versions")


class PromotionRule(Base, TimestampMixin):
    """促销规则 — 满减/折扣/赠品/限时优惠。

    核心约束：
    - gross_margin_floor: 任何促销后毛利不得低于此底线
    - contribution_floor: 贡献利润底线
    - stackable_flag: 是否可叠加
    - exclusive_group_code: 互斥组(同组规则只能命中一个)
    """

    __tablename__ = "kb_promotion_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "promo_code", name="uq_kb_promo_code"),
        Index("ix_kb_promo_status", "tenant_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    promo_code = Column(String(64), nullable=False, comment="促销编码")
    promo_name = Column(String(128), nullable=False, comment="促销名称")
    promo_type = Column(
        String(32), nullable=False,
        comment="类型: full_reduction/discount/gift/bundle/flash_sale/new_customer",
    )
    target_scope = Column(String(32), comment="适用范围: all/brand/store/category/dish")

    # 触发条件与优惠内容(JSONB灵活配置)
    trigger_condition_json = Column(
        JSON, comment="触发条件: {min_amount, min_qty, time_range, channel, ...}",
    )
    benefit_rule_json = Column(
        JSON, comment="优惠规则: {discount_type, value, free_dish_id, ...}",
    )

    # 约束
    stackable_flag = Column(Boolean, nullable=False, default=False, comment="是否可叠加")
    exclusive_group_code = Column(String(64), comment="互斥组编码")
    gross_margin_floor = Column(Numeric(8, 4), comment="毛利底线(如0.20=20%)")
    contribution_floor = Column(Numeric(12, 2), comment="贡献利润底线(分)")
    budget_limit = Column(Numeric(14, 2), comment="预算上限(分)")
    used_budget = Column(Numeric(14, 2), default=0, comment="已使用预算(分)")

    status = Column(String(32), nullable=False, default="draft",
                    comment="draft/published/disabled/archived")
    effective_from = Column(DateTime)
    effective_to = Column(DateTime)
    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))


class CouponTemplate(Base, TimestampMixin):
    """优惠券模板 — 定义券种和核销规则。"""

    __tablename__ = "kb_coupon_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "coupon_code", name="uq_kb_coupon_code"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    coupon_code = Column(String(64), nullable=False, comment="券编码")
    coupon_name = Column(String(128), nullable=False, comment="券名称")
    coupon_type = Column(
        String(32), nullable=False,
        comment="类型: full_reduction/discount/free_dish/cash",
    )

    # 使用条件
    threshold_amount = Column(Numeric(12, 2), comment="满额门槛(分)")
    discount_amount = Column(Numeric(12, 2), comment="减免金额(分)")
    discount_ratio = Column(Numeric(8, 4), comment="折扣比例(如0.85=85折)")
    max_discount = Column(Numeric(12, 2), comment="最大优惠金额(分)")

    # 发放约束
    new_customer_only = Column(Boolean, default=False, comment="仅新客")
    total_quota = Column(Integer, comment="总发放量")
    issued_count = Column(Integer, default=0, comment="已发放量")
    valid_days = Column(Integer, comment="有效天数(自领取起)")
    valid_from = Column(DateTime, comment="固定生效开始")
    valid_to = Column(DateTime, comment="固定生效结束")

    status = Column(String(32), nullable=False, default="draft",
                    comment="draft/published/disabled/archived")
    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))


class PricingExecutionSnapshot(Base, TimestampMixin):
    """定价执行快照 — 记录每笔订单实际命中的策略与价格。

    用于事后审计：哪些促销规则被命中、最终结算价是多少、
    毛利保护是否生效。
    """

    __tablename__ = "kb_pricing_execution_snapshots"
    __table_args__ = (
        Index("ix_kb_pricing_exec_date", "tenant_id", "biz_date"),
        Index("ix_kb_pricing_exec_store", "store_id", "biz_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    store_id = Column(UUID(as_uuid=True), nullable=False)
    biz_date = Column(Date, nullable=False)
    dish_id = Column(UUID(as_uuid=True), nullable=False)
    order_id = Column(UUID(as_uuid=True), comment="订单ID")
    channel_type = Column(String(32), comment="渠道")

    # 价格链
    base_price = Column(Numeric(12, 2), comment="基础价(分)")
    strategy_price = Column(Numeric(12, 2), comment="策略调整价(分)")
    promo_price = Column(Numeric(12, 2), comment="促销后价(分)")
    coupon_deduction = Column(Numeric(12, 2), comment="优惠券抵扣(分)")
    final_settlement_price = Column(Numeric(12, 2), comment="最终结算价(分)")

    # 命中记录
    matched_strategy_id = Column(UUID(as_uuid=True), comment="命中的定价策略ID")
    matched_promo_id = Column(UUID(as_uuid=True), comment="命中的促销规则ID")
    matched_coupon_id = Column(UUID(as_uuid=True), comment="命中的优惠券ID")
    margin_check_result = Column(String(32), comment="毛利检查结果: pass/floor_hit/override")

    snapshot_json = Column(JSON, comment="完整命中链路快照")
