"""BOM 配方与工艺库 — 从原料到出品的全链路标准。

核心解决：
- 菜品做法不一致、成本无法精确核算
- 出品稳定性差、门店培训依赖老师傅
- 工艺/损耗/份量无法沉淀、食安控制点无法系统化

表结构：
- bom_recipes          配方主表
- bom_recipe_items     配方物料明细（BOM行）
- bom_recipe_process_steps  工艺步骤
- bom_recipe_serving_standards  出品标准
- bom_recipe_storage_rules  储存与保质规则
- bom_recipe_versions  版本快照
- bom_recipe_cost_calcs 成本计算结果
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
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


class BOMRecipe(Base, TimestampMixin):
    """配方主表 — 统一管理原料/半成品/成品/套餐配方。"""

    __tablename__ = "kb_bom_recipes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "recipe_code", name="uq_kb_bom_recipe_code"),
        Index("ix_kb_bom_recipe_status", "tenant_id", "status"),
        Index("ix_kb_bom_recipe_brand", "tenant_id", "brand_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # 基本信息
    recipe_code = Column(String(64), nullable=False, comment="配方编码")
    recipe_name = Column(String(128), nullable=False, comment="配方名称")
    recipe_alias = Column(String(128), comment="别名/市场名")
    recipe_type = Column(
        String(32), nullable=False,
        comment="配方类型: raw_material/semi_finished/finished/set_meal",
    )
    recipe_level = Column(
        String(32), nullable=False,
        comment="层级: material/semi/finished",
    )

    # 归属
    brand_id = Column(UUID(as_uuid=True), comment="品牌ID")
    org_id = Column(UUID(as_uuid=True), comment="组织ID")
    category_id = Column(UUID(as_uuid=True), comment="菜品分类ID")
    cuisine_type = Column(String(64), comment="菜系")
    dish_type = Column(String(64), comment="菜品类型")

    # 适用范围
    channel_scope = Column(
        String(32), nullable=False, default="all",
        comment="适用渠道: dine_in/takeaway/all",
    )
    applicable_store_type = Column(String(32), comment="适用门店类型")

    # 产出标准
    output_qty = Column(Numeric(12, 3), nullable=False, default=1, comment="标准产出量")
    output_unit = Column(String(32), nullable=False, comment="标准产出单位")
    portion_qty = Column(Numeric(12, 3), comment="标准份量")
    portion_unit = Column(String(32), comment="标准份量单位")

    # 成本
    standard_cost = Column(Numeric(12, 2), comment="标准成本(分)")
    estimated_cost = Column(Numeric(12, 2), comment="估算成本(分)")

    # 版本与状态
    version_no = Column(Integer, nullable=False, default=1, comment="当前版本号")
    status = Column(
        String(32), nullable=False, default="draft",
        comment="状态: draft/pending_review/approved/published/disabled/archived",
    )
    effective_from = Column(DateTime, comment="生效时间")
    effective_to = Column(DateTime, comment="失效时间")

    # 归属人
    owner_dept_id = Column(UUID(as_uuid=True), comment="归属部门")
    owner_user_id = Column(UUID(as_uuid=True), comment="负责人")
    created_by = Column(UUID(as_uuid=True), comment="创建人")
    updated_by = Column(UUID(as_uuid=True), comment="更新人")

    remark = Column(Text, comment="备注")
    is_deleted = Column(Boolean, nullable=False, default=False)

    # 关系
    items = relationship("BOMRecipeItem", back_populates="recipe", cascade="all, delete-orphan")
    process_steps = relationship("BOMRecipeProcessStep", back_populates="recipe", cascade="all, delete-orphan")
    serving_standard = relationship(
        "BOMRecipeServingStandard", back_populates="recipe",
        uselist=False, cascade="all, delete-orphan",
    )
    storage_rule = relationship(
        "BOMRecipeStorageRule", back_populates="recipe",
        uselist=False, cascade="all, delete-orphan",
    )
    versions = relationship("BOMRecipeVersion", back_populates="recipe", cascade="all, delete-orphan")
    cost_calcs = relationship("BOMRecipeCostCalc", back_populates="recipe", cascade="all, delete-orphan")


class BOMRecipeItem(Base, TimestampMixin):
    """配方物料明细 — BOM 行项目。

    关键字段说明：
    - qty_ap: As Purchased，毛重/领用量
    - qty_ep: Edible Portion，可食用量/净料量
    - loss_rate_trim: 修整损耗率
    - loss_rate_cook: 烹调损耗率
    - net_qty: 净用量 = qty_ep * (1 - loss_rate_cook)
    """

    __tablename__ = "kb_bom_recipe_items"
    __table_args__ = (
        Index("ix_kb_bom_item_recipe", "recipe_id", "sort_order"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("kb_bom_recipes.id"), nullable=False)

    line_no = Column(Integer, nullable=False, comment="行号")
    material_id = Column(UUID(as_uuid=True), comment="物料ID（关联食材主档）")
    material_code = Column(String(64), nullable=False, comment="物料编码")
    material_name = Column(String(128), nullable=False, comment="物料名称")
    material_type = Column(
        String(32), nullable=False,
        comment="物料类型: main/sub/seasoning/packaging",
    )
    usage_stage = Column(String(32), comment="使用阶段: prep/cook/plating/package")

    # 用量
    qty_ap = Column(Numeric(12, 3), comment="毛重用量AP")
    qty_ep = Column(Numeric(12, 3), comment="净料用量EP")
    base_unit = Column(String(32), nullable=False, comment="基础单位")
    loss_rate_trim = Column(Numeric(8, 4), comment="修整损耗率")
    loss_rate_cook = Column(Numeric(8, 4), comment="烹调损耗率")
    net_qty = Column(Numeric(12, 3), nullable=False, comment="净用量")

    # 成本
    unit_cost = Column(Numeric(12, 4), comment="单位成本(分)")
    line_cost = Column(Numeric(12, 2), comment="行成本(分)")

    # 替代与属性
    substitute_group_code = Column(String(64), comment="替代组编码")
    is_optional = Column(Boolean, nullable=False, default=False, comment="是否可选")
    is_key_material = Column(Boolean, nullable=False, default=False, comment="是否关键原料")
    allergen_tags = Column(String(255), comment="过敏原标签(逗号分隔)")

    sort_order = Column(Integer, nullable=False, default=0)
    remark = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    recipe = relationship("BOMRecipe", back_populates="items")


class BOMRecipeProcessStep(Base, TimestampMixin):
    """工艺步骤 — 烹饪SOP与食安关键控制点。

    CCP(Critical Control Point)是HACCP体系的关键控制点，
    常见CCP：烹调温度、冷却速率、复热温度、保温时间。
    """

    __tablename__ = "kb_bom_recipe_process_steps"
    __table_args__ = (
        Index("ix_kb_bom_process_recipe", "recipe_id", "sort_order"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("kb_bom_recipes.id"), nullable=False)

    line_no = Column(Integer, nullable=False, comment="步骤序号")
    process_stage = Column(
        String(32), nullable=False,
        comment="阶段: prep/marinate/cook/plating/reheat/package",
    )
    step_name = Column(String(128), nullable=False, comment="步骤名称")
    step_desc = Column(Text, comment="步骤说明")
    action_standard = Column(Text, comment="动作标准")

    # 设备
    equipment_id = Column(UUID(as_uuid=True), comment="设备ID")
    equipment_name = Column(String(128), comment="设备名称")
    tool_name = Column(String(128), comment="工器具")

    # 工艺参数
    target_temp = Column(Numeric(8, 2), comment="目标温度")
    temp_unit = Column(String(16), default="℃", comment="温度单位")
    target_time_sec = Column(Integer, comment="目标时长(秒)")
    fire_level = Column(String(32), comment="火力档位")
    speed_level = Column(String(32), comment="转速/搅拌档位")

    # 质控
    qc_point = Column(Text, comment="质检点描述")
    is_ccp = Column(Boolean, nullable=False, default=False, comment="是否HACCP关键控制点")
    ccp_limit = Column(String(255), comment="CCP临界值")
    deviation_action = Column(Text, comment="偏差纠正动作")

    media_url = Column(String(500), comment="图片/视频URL")
    sort_order = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    recipe = relationship("BOMRecipe", back_populates="process_steps")


class BOMRecipeServingStandard(Base, TimestampMixin):
    """出品标准 — 份量/摆盘/感官/温度标准。"""

    __tablename__ = "kb_bom_recipe_serving_standards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_bom_recipes.id"),
        nullable=False, unique=True,
    )

    portion_weight = Column(Numeric(12, 3), comment="标准份量(g/ml)")
    portion_count = Column(Numeric(12, 3), comment="标准份数")
    serving_temp = Column(Numeric(8, 2), comment="出品温度(℃)")
    plating_desc = Column(Text, comment="摆盘说明")
    garnish_rule = Column(Text, comment="点缀规则")
    container_type = Column(String(64), comment="餐具/外卖盒类型")
    sensory_color = Column(String(255), comment="色泽标准")
    sensory_aroma = Column(String(255), comment="香气标准")
    sensory_texture = Column(String(255), comment="口感标准")
    standard_image_url = Column(String(500), comment="标准出品图URL")
    remark = Column(Text)

    recipe = relationship("BOMRecipe", back_populates="serving_standard")


class BOMRecipeStorageRule(Base, TimestampMixin):
    """储存与保质规则 — 温度/时效/解冻/复热/报废。"""

    __tablename__ = "kb_bom_recipe_storage_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_bom_recipes.id"),
        nullable=False, unique=True,
    )

    storage_temp_min = Column(Numeric(8, 2), comment="存储最低温(℃)")
    storage_temp_max = Column(Numeric(8, 2), comment="存储最高温(℃)")
    shelf_life_hours = Column(Integer, comment="保质时长(小时)")
    hold_time_minutes = Column(Integer, comment="售卖保温时长(分钟)")
    thaw_rule = Column(Text, comment="解冻规则")
    reheat_rule = Column(Text, comment="复热规则")
    discard_rule = Column(Text, comment="报废规则")
    batch_size = Column(Numeric(12, 3), comment="建议批量")
    prep_window = Column(String(128), comment="预制时间窗")

    recipe = relationship("BOMRecipe", back_populates="storage_rule")


class BOMRecipeVersion(Base, TimestampMixin):
    """配方版本快照 — 支持版本追溯与审批流。"""

    __tablename__ = "kb_bom_recipe_versions"
    __table_args__ = (
        UniqueConstraint("recipe_id", "version_no", name="uq_kb_bom_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("kb_bom_recipes.id"), nullable=False, index=True)

    version_no = Column(Integer, nullable=False, comment="版本号")
    status = Column(
        String(32), nullable=False,
        comment="draft/pending_review/approved/published/archived",
    )
    snapshot_json = Column(JSON, nullable=False, comment="全量快照JSON")
    change_summary = Column(Text, comment="变更摘要")

    submitted_by = Column(UUID(as_uuid=True), comment="提交人")
    submitted_at = Column(DateTime, comment="提交时间")
    reviewed_by = Column(UUID(as_uuid=True), comment="审核人")
    reviewed_at = Column(DateTime, comment="审核时间")
    published_by = Column(UUID(as_uuid=True), comment="发布人")
    published_at = Column(DateTime, comment="发布时间")

    recipe = relationship("BOMRecipe", back_populates="versions")


class BOMRecipeCostCalc(Base, TimestampMixin):
    """配方成本计算结果 — 每次重算记录一条。

    成本拆分：原料 + 调料 + 包材 + 加工 = 标准总成本。
    所有金额单位：分(fen)。
    """

    __tablename__ = "kb_bom_recipe_cost_calcs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("kb_bom_recipes.id"), nullable=False, index=True)

    version_no = Column(Integer, nullable=False, comment="版本号")
    material_cost = Column(Numeric(12, 2), comment="原料成本(分)")
    seasoning_cost = Column(Numeric(12, 2), comment="调料成本(分)")
    packaging_cost = Column(Numeric(12, 2), comment="包材成本(分)")
    process_cost = Column(Numeric(12, 2), comment="加工成本(分)")
    total_std_cost = Column(Numeric(12, 2), comment="标准总成本(分)")
    output_qty = Column(Numeric(12, 3), comment="产出量")
    cost_per_portion = Column(Numeric(12, 2), comment="单份成本(分)")
    calc_time = Column(DateTime, default=datetime.utcnow, comment="计算时间")
    calc_snapshot = Column(JSON, comment="计算明细快照")

    recipe = relationship("BOMRecipe", back_populates="cost_calcs")
