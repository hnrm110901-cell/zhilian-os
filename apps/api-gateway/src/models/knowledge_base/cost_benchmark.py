"""成本结构基准库 — 品牌/业态/门店/菜品成本分析与预警。

核心解决：
- 不同门店口径不统一，无法横向比较
- 食材/人工/平台扣点/租金无标准参照
- 总部不知道哪些店的成本结构失控
- 菜品盈利好坏没有统一评估标准

行业参考指标：
- Food Cost: 28%-35% 为健康区间
- Prime Cost (食材+人工): 控在 65% 以内
- Contribution Margin: 菜品级贡献利润
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


class CostBenchmark(Base, TimestampMixin):
    """成本基准主表 — 定义一套成本结构标准。

    适用维度：企业级/品牌级/区域级/门店级/菜品级。
    """

    __tablename__ = "kb_cost_benchmarks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "benchmark_code", name="uq_kb_cost_benchmark_code"),
        Index("ix_kb_cost_bm_scope", "tenant_id", "benchmark_scope"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    benchmark_code = Column(String(64), nullable=False, comment="基准编码")
    benchmark_name = Column(String(128), nullable=False, comment="基准名称")
    benchmark_scope = Column(
        String(32), nullable=False,
        comment="适用范围: enterprise/brand/region/store/dish",
    )
    business_type = Column(String(64), comment="业态: fine_dining/fast_casual/hotpot/bbq/tea/catering")
    brand_id = Column(UUID(as_uuid=True), comment="品牌ID")
    store_id = Column(UUID(as_uuid=True), comment="门店ID(门店级基准)")
    channel_type = Column(String(32), comment="渠道: dine_in/takeaway/all")

    version_no = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="draft",
                    comment="draft/published/disabled/archived")
    effective_from = Column(DateTime, comment="生效时间")
    effective_to = Column(DateTime, comment="失效时间")
    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    items = relationship("CostBenchmarkItem", back_populates="benchmark", cascade="all, delete-orphan")
    versions = relationship("CostBenchmarkVersion", back_populates="benchmark", cascade="all, delete-orphan")


class CostBenchmarkItem(Base, TimestampMixin):
    """成本基准明细 — 每个成本项的目标值与预警阈值。

    成本一级分类(18项)：
    食材/包材/饮品耗材/调料耗材/人工/房租物业/水电燃气/
    外卖平台佣金/支付手续费/营销投放/设备折旧/损耗报废/
    仓配物流/清洁消杀/维修维保/信息化费用/总部管理分摊/税费
    """

    __tablename__ = "kb_cost_benchmark_items"
    __table_args__ = (
        Index("ix_kb_cost_bm_item_bm", "benchmark_id", "line_no"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    benchmark_id = Column(UUID(as_uuid=True), ForeignKey("kb_cost_benchmarks.id"), nullable=False)

    line_no = Column(Integer, nullable=False, comment="行号")
    cost_category_lv1 = Column(String(64), nullable=False, comment="一级成本分类")
    cost_category_lv2 = Column(String(64), comment="二级成本分类")
    basis_type = Column(
        String(32), nullable=False, default="ratio",
        comment="基准类型: ratio(占比)/amount(金额)/per_unit(单位成本)",
    )

    # 目标与预警
    target_ratio = Column(Numeric(8, 4), comment="目标占比(如 0.3200 = 32%)")
    target_amount = Column(Numeric(14, 2), comment="目标金额(分)")
    warning_ratio_yellow = Column(Numeric(8, 4), comment="黄色预警阈值")
    warning_ratio_red = Column(Numeric(8, 4), comment="红色预警阈值")

    # 行业参考
    industry_p25 = Column(Numeric(8, 4), comment="行业25分位")
    industry_p50 = Column(Numeric(8, 4), comment="行业50分位(中位数)")
    industry_p75 = Column(Numeric(8, 4), comment="行业75分位")
    industry_p90 = Column(Numeric(8, 4), comment="行业90分位")

    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)

    benchmark = relationship("CostBenchmark", back_populates="items")


class CostBenchmarkVersion(Base, TimestampMixin):
    """成本基准版本快照。"""

    __tablename__ = "kb_cost_benchmark_versions"
    __table_args__ = (
        UniqueConstraint("benchmark_id", "version_no", name="uq_kb_cost_bm_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    benchmark_id = Column(UUID(as_uuid=True), ForeignKey("kb_cost_benchmarks.id"), nullable=False, index=True)

    version_no = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    snapshot_json = Column(JSON, nullable=False, comment="全量快照")
    change_summary = Column(Text)

    benchmark = relationship("CostBenchmark", back_populates="versions")


class CostStoreDailyFact(Base, TimestampMixin):
    """门店日级成本事实表 — 每日门店经营成本结构汇总。

    prime_cost = food_cost + labor_cost
    prime_cost_ratio = prime_cost / revenue_total
    行业目标: prime_cost_ratio < 65%
    """

    __tablename__ = "kb_cost_store_daily_facts"
    __table_args__ = (
        UniqueConstraint("store_id", "biz_date", name="uq_kb_cost_store_daily"),
        Index("ix_kb_cost_store_daily_date", "tenant_id", "biz_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    biz_date = Column(Date, nullable=False, comment="营业日期")

    # 核心指标(分)
    revenue_total = Column(Numeric(14, 2), comment="营业收入(分)")
    cogs_food = Column(Numeric(14, 2), comment="食材成本(分)")
    cogs_packaging = Column(Numeric(14, 2), comment="包材成本(分)")
    cogs_beverage = Column(Numeric(14, 2), comment="饮品耗材(分)")
    cogs_seasoning = Column(Numeric(14, 2), comment="调料耗材(分)")
    labor_cost = Column(Numeric(14, 2), comment="人工成本(分)")
    rent_cost = Column(Numeric(14, 2), comment="房租物业(分)")
    utility_cost = Column(Numeric(14, 2), comment="水电燃气(分)")
    platform_commission = Column(Numeric(14, 2), comment="外卖平台佣金(分)")
    payment_fee = Column(Numeric(14, 2), comment="支付手续费(分)")
    marketing_cost = Column(Numeric(14, 2), comment="营销投放(分)")
    waste_cost = Column(Numeric(14, 2), comment="损耗报废(分)")

    # 汇总指标
    prime_cost = Column(Numeric(14, 2), comment="Prime Cost = 食材 + 人工(分)")
    prime_cost_ratio = Column(Numeric(8, 4), comment="Prime Cost 占比")
    food_cost_ratio = Column(Numeric(8, 4), comment="食材成本率")
    labor_cost_ratio = Column(Numeric(8, 4), comment="人工成本率")
    op_profit = Column(Numeric(14, 2), comment="经营利润(分)")
    op_profit_ratio = Column(Numeric(8, 4), comment="经营利润率")

    calc_status = Column(String(32), default="calculated", comment="计算状态")
    detail_json = Column(JSON, comment="成本明细快照")


class CostDishDailyFact(Base, TimestampMixin):
    """菜品日级成本事实表 — 每日每道菜的销售与成本。

    menu_class 基于 BCG 矩阵分类：
    - star: 高利润+高销量
    - cash_cow: 高利润+低销量
    - puzzle: 低利润+高销量
    - dog: 低利润+低销量
    """

    __tablename__ = "kb_cost_dish_daily_facts"
    __table_args__ = (
        UniqueConstraint("store_id", "biz_date", "dish_id", name="uq_kb_cost_dish_daily"),
        Index("ix_kb_cost_dish_daily_date", "tenant_id", "biz_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    store_id = Column(UUID(as_uuid=True), nullable=False)
    biz_date = Column(Date, nullable=False)
    dish_id = Column(UUID(as_uuid=True), nullable=False, comment="菜品ID")
    recipe_id = Column(UUID(as_uuid=True), comment="关联配方ID")

    sold_qty = Column(Numeric(12, 2), comment="售出份数")
    revenue_amount = Column(Numeric(14, 2), comment="销售收入(分)")
    std_cost_amount = Column(Numeric(14, 2), comment="标准成本(分)")
    actual_cost_amount = Column(Numeric(14, 2), comment="实际成本(分)")
    contribution_margin = Column(Numeric(14, 2), comment="贡献利润(分)")
    contribution_margin_ratio = Column(Numeric(8, 4), comment="贡献利润率")
    food_cost_ratio = Column(Numeric(8, 4), comment="食材成本率")

    menu_class = Column(String(32), comment="菜单分类: star/cash_cow/puzzle/dog")
    detail_json = Column(JSON, comment="计算明细")


class CostWarningRecord(Base, TimestampMixin):
    """成本预警记录 — 实际值突破基准阈值时触发。"""

    __tablename__ = "kb_cost_warning_records"
    __table_args__ = (
        Index("ix_kb_cost_warning_date", "tenant_id", "biz_date"),
        Index("ix_kb_cost_warning_status", "tenant_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)

    warning_code = Column(String(64), nullable=False, comment="预警编码")
    warning_type = Column(
        String(32), nullable=False,
        comment="预警类型: food_cost/labor_cost/prime_cost/waste/dish_cost",
    )
    scope_type = Column(String(32), nullable=False, comment="范围: store/brand/dish")
    scope_id = Column(UUID(as_uuid=True), nullable=False, comment="范围ID")
    biz_date = Column(Date, nullable=False)

    target_value = Column(Numeric(8, 4), comment="目标值")
    actual_value = Column(Numeric(8, 4), comment="实际值")
    deviation = Column(Numeric(8, 4), comment="偏差")
    warning_level = Column(String(16), nullable=False, comment="yellow/red")

    status = Column(String(32), nullable=False, default="open",
                    comment="open/acknowledged/resolved/ignored")
    resolved_by = Column(UUID(as_uuid=True))
    resolved_at = Column(DateTime)
    resolution_note = Column(Text)
    detail_json = Column(JSON, comment="预警详情")
