"""
菜品研发 Agent — 数据模型
Phase 10（Dish R&D Intelligence System）

5层架构：
  L1 主数据层：Ingredient, SemiProduct, Supplier, DishCategory
  L2 研发过程层：Dish, DishVersion, IdeaProject, Recipe, RecipeVersion,
                 RecipeItem, SOP, NutritionProfile, AllergenProfile
  L3 经营模拟层：CostModel, SupplyAssessment
  L4 反馈复盘层：PilotTest, LaunchProject, DishFeedback, RetrospectiveReport
  L5 事件智能层：DishRdAgentLog
"""

import enum
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from src.models.base import Base
from src.models.mixins import TimestampMixin

# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class DishStatusEnum(str, enum.Enum):
    DRAFT = "draft"  # 草稿
    IDEATION = "ideation"  # 待立项
    IN_DEV = "in_dev"  # 研发中
    SAMPLING = "sampling"  # 打样中
    PILOT_PENDING = "pilot_pending"  # 待试点
    PILOTING = "piloting"  # 试点中
    LAUNCH_READY = "launch_ready"  # 待发布
    LAUNCHED = "launched"  # 已发布
    OPTIMIZING = "optimizing"  # 优化中
    DISCONTINUED = "discontinued"  # 已下架
    ARCHIVED = "archived"  # 已归档


class DishTypeEnum(str, enum.Enum):
    NEW = "new"  # 新品
    UPGRADE = "upgrade"  # 老品升级
    SEASONAL = "seasonal"  # 节令
    REGIONAL = "regional"  # 区域版
    BANQUET = "banquet"  # 宴会版
    DELIVERY = "delivery"  # 外卖版


class PositioningTypeEnum(str, enum.Enum):
    TRAFFIC = "traffic"  # 引流款
    PROFIT = "profit"  # 利润款
    IMAGE = "image"  # 形象款
    STAR = "star"  # 爆品候选
    SEASONAL = "seasonal"  # 节令款


class LifecycleStageEnum(str, enum.Enum):
    INSIGHT = "insight"
    IDEATION = "ideation"
    DEV = "dev"
    SAMPLING = "sampling"
    PILOT = "pilot"
    LAUNCH = "launch"
    REVIEW = "review"
    OPTIMIZE = "optimize"
    RETIRE = "retire"


class VersionTypeEnum(str, enum.Enum):
    DEV = "dev"  # 研发版
    PILOT = "pilot"  # 试点版
    REGIONAL = "regional"  # 区域版
    NATIONAL = "national"  # 全国版
    COST_DOWN = "cost_down"  # 降本版
    DELIVERY = "delivery"  # 外卖版
    SEASONAL = "seasonal"  # 节令版
    DEPRECATED = "deprecated"  # 废弃版


class RecipeTypeEnum(str, enum.Enum):
    MAIN = "main"  # 主菜
    SEMI = "semi"  # 半成品
    SAUCE = "sauce"  # 底料
    DIPPING = "dipping"  # 蘸料
    DELIVERY = "delivery"  # 外卖版
    BANQUET = "banquet"  # 宴会版


class RecipeVersionStatusEnum(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 已通过
    PUBLISHED = "published"  # 已发布
    DEPRECATED = "deprecated"  # 已作废


class SopTypeEnum(str, enum.Enum):
    STANDARD = "standard"  # 标准版
    PEAK = "peak"  # 高峰简化版
    DELIVERY = "delivery"  # 外卖版
    BANQUET = "banquet"  # 宴会版


class SemiTypeEnum(str, enum.Enum):
    BASE = "base"  # 底料
    SAUCE = "sauce"  # 酱料
    PREPARED = "prepared"  # 预制菜
    DIPPING = "dipping"  # 蘸料
    CONDIMENT = "condiment"  # 小料


class SupplierTypeEnum(str, enum.Enum):
    ORIGIN = "origin"  # 产地商
    PROCESSOR = "processor"  # 加工商
    DISTRIBUTOR = "distributor"  # 经销商


class IngredientSeasonEnum(str, enum.Enum):
    ALL_YEAR = "all_year"  # 常年
    SEASONAL = "seasonal"  # 季节性


class TemperatureTypeEnum(str, enum.Enum):
    AMBIENT = "ambient"  # 常温
    CHILLED = "chilled"  # 冷藏
    FROZEN = "frozen"  # 冷冻


class ProjectStatusEnum(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IN_DEV = "in_dev"
    PILOTING = "piloting"
    LAUNCHED = "launched"
    TERMINATED = "terminated"
    CLOSED = "closed"


class PilotStatusEnum(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class PilotDecisionEnum(str, enum.Enum):
    GO = "go"
    REVISE = "revise"
    STOP = "stop"


class LaunchStatusEnum(str, enum.Enum):
    PENDING = "pending"
    LAUNCHING = "launching"
    LAUNCHED = "launched"
    ROLLED_BACK = "rolled_back"


class LaunchTypeEnum(str, enum.Enum):
    NATIONAL = "national"  # 全国
    REGIONAL = "regional"  # 区域
    STORE_GRAY = "store_gray"  # 门店灰度


class FeedbackSourceEnum(str, enum.Enum):
    CUSTOMER = "customer"  # 顾客
    MANAGER = "manager"  # 店长
    CHEF = "chef"  # 厨师
    SUPERVISOR = "supervisor"  # 督导
    TASTER = "taster"  # 试吃官
    SYSTEM = "system"  # 系统导入


class FeedbackTypeEnum(str, enum.Enum):
    TASTE = "taste"
    PLATING = "plating"
    SPEED = "speed"
    COST = "cost"
    EXECUTION = "execution"
    RETURN = "return"
    COMPLAINT = "complaint"
    SUGGESTION = "suggestion"


class LifecycleAssessmentEnum(str, enum.Enum):
    KEEP = "keep"
    OPTIMIZE = "optimize"
    REGIONAL_KEEP = "regional_keep"
    MONITOR = "monitor"
    RETIRE = "retire"


class DishRdAgentTypeEnum(str, enum.Enum):
    COST_SIM = "cost_sim"  # 成本仿真
    PILOT_REC = "pilot_rec"  # 试点推荐
    REVIEW = "review"  # 复盘优化
    LAUNCH_ASSIST = "launch_assist"  # 发布助手
    RISK_ALERT = "risk_alert"  # 风险预警
    ALT_INGREDIENT = "alt_ingredient"  # 替代料建议


class SupplyRecommendationEnum(str, enum.Enum):
    NATIONAL = "national"  # 可全国
    REGIONAL = "regional"  # 可区域
    PILOT_ONLY = "pilot_only"  # 仅试点
    NOT_READY = "not_ready"  # 不建议上市


class RiskLevelEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ─────────────────────────────────────────────
# L1 主数据层
# ─────────────────────────────────────────────


class DishCategory(Base):
    """品类主数据"""

    __tablename__ = "dish_rd_categories"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(String(36), nullable=True)  # 二级品类
    level = Column(Integer, default=1)  # 1=一级, 2=二级
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Ingredient(Base):
    """原料主数据"""

    __tablename__ = "dish_rd_ingredients"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    ingredient_code = Column(String(50), nullable=False, unique=True)
    ingredient_name = Column(String(200), nullable=False)
    alias_names = Column(JSON, default=list)
    category_id = Column(String(36), nullable=True)
    spec_desc = Column(String(200))
    purchase_unit = Column(String(20), nullable=False, default="kg")
    usage_unit = Column(String(20), nullable=False, default="g")
    unit_convert_ratio = Column(Float, default=1000.0)  # 1kg=1000g
    standard_price = Column(Numeric(10, 4), default=0)  # 元/采购单位
    loss_rate = Column(Float, default=0.05)  # 标准损耗率
    seasonality_type = Column(SAEnum(IngredientSeasonEnum), default=IngredientSeasonEnum.ALL_YEAR)
    season_start_month = Column(Integer)
    season_end_month = Column(Integer)
    risk_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.LOW)
    availability_regions = Column(JSON, default=list)  # 可得区域
    temperature_type = Column(SAEnum(TemperatureTypeEnum), default=TemperatureTypeEnum.AMBIENT)
    shelf_life_days = Column(Integer)
    allergen_tags = Column(JSON, default=list)
    nutrition_data = Column(JSON, default=dict)  # per 100g
    supplier_ids = Column(JSON, default=list)
    substitute_ingredient_ids = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Supplier(Base):
    """供应商主数据"""

    __tablename__ = "dish_rd_suppliers"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    supplier_code = Column(String(50), nullable=False, unique=True)
    supplier_name = Column(String(200), nullable=False)
    supplier_type = Column(SAEnum(SupplierTypeEnum), default=SupplierTypeEnum.DISTRIBUTOR)
    region_scope = Column(JSON, default=list)
    delivery_capability = Column(JSON, default=dict)
    price_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.MEDIUM)
    stability_score = Column(Float, default=80.0)  # 0-100
    quality_score = Column(Float, default=80.0)
    contact_info = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SemiProduct(Base):
    """半成品/底料主数据"""

    __tablename__ = "dish_rd_semi_products"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    semi_code = Column(String(50), nullable=False, unique=True)
    semi_name = Column(String(200), nullable=False)
    semi_type = Column(SAEnum(SemiTypeEnum), default=SemiTypeEnum.SAUCE)
    recipe_id = Column(String(36), nullable=True)  # 对应配方
    current_recipe_version_id = Column(String(36), nullable=True)
    standard_cost = Column(Numeric(10, 4), default=0)  # 元/kg or 元/份
    yield_rate = Column(Float, default=1.0)
    storage_type = Column(SAEnum(TemperatureTypeEnum), default=TemperatureTypeEnum.CHILLED)
    shelf_life_days = Column(Integer, default=3)
    used_by_dish_ids = Column(JSON, default=list)
    risk_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.LOW)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# L2 研发过程层
# ─────────────────────────────────────────────


class Dish(Base):
    """菜品主档 — 菜品对象顶层壳体"""

    __tablename__ = "dish_rd_dishes"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    dish_code = Column(String(50), nullable=False, unique=True)
    dish_name = Column(String(200), nullable=False)
    dish_alias = Column(String(200))
    category_id = Column(String(36), nullable=True)
    subcategory_id = Column(String(36), nullable=True)
    dish_type = Column(SAEnum(DishTypeEnum), default=DishTypeEnum.NEW)
    status = Column(SAEnum(DishStatusEnum), default=DishStatusEnum.DRAFT, index=True)
    lifecycle_stage = Column(SAEnum(LifecycleStageEnum), default=LifecycleStageEnum.INSIGHT)
    positioning_type = Column(SAEnum(PositioningTypeEnum), nullable=True)
    target_price_yuan = Column(Numeric(10, 2))  # 目标售价
    target_margin_rate = Column(Float)  # 目标毛利率
    target_audience = Column(JSON, default=list)
    consumption_scene = Column(JSON, default=list)
    region_scope = Column(JSON, default=list)
    store_scope = Column(JSON, default=list)
    owner_user_id = Column(String(36), nullable=True)
    source_type = Column(String(50), default="initiative")  # 主动立项/复盘/竞品/季节
    description = Column(Text)
    highlight_tags = Column(JSON, default=list)
    flavor_tags = Column(JSON, default=list)
    health_tags = Column(JSON, default=list)
    cover_image_url = Column(String(500))
    hero_image_urls = Column(JSON, default=list)
    current_version_id = Column(String(36), nullable=True)
    latest_recipe_version_id = Column(String(36), nullable=True)
    current_sop_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_dish_rd_dishes_brand_status", "brand_id", "status"),)


class DishVersion(Base):
    """菜品版本 — 业务可执行快照"""

    __tablename__ = "dish_rd_dish_versions"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    version_no = Column(String(20), nullable=False)
    version_type = Column(SAEnum(VersionTypeEnum), default=VersionTypeEnum.DEV)
    region_id = Column(String(36), nullable=True)
    store_level_scope = Column(JSON, default=list)
    recipe_version_id = Column(String(36), nullable=True)
    sop_id = Column(String(36), nullable=True)
    cost_model_id = Column(String(36), nullable=True)
    nutrition_profile_id = Column(String(36), nullable=True)
    allergen_profile_id = Column(String(36), nullable=True)
    supply_assessment_id = Column(String(36), nullable=True)
    release_status = Column(String(20), default="unreleased")  # unreleased/pending/released/rolled_back/deprecated
    effective_start_at = Column(DateTime, nullable=True)
    effective_end_at = Column(DateTime, nullable=True)
    parent_version_id = Column(String(36), nullable=True)
    branch_reason = Column(String(50), nullable=True)
    is_current = Column(Boolean, default=False)
    change_summary = Column(Text)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class IdeaProject(Base):
    """立项项目"""

    __tablename__ = "dish_rd_idea_projects"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    project_code = Column(String(50), nullable=False, unique=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=True)
    project_name = Column(String(200), nullable=False)
    project_type = Column(SAEnum(DishTypeEnum), default=DishTypeEnum.NEW)
    initiation_reason = Column(Text)
    business_goal = Column(Text)
    target_launch_date = Column(Date, nullable=True)
    target_region_scope = Column(JSON, default=list)
    target_store_scope = Column(JSON, default=list)
    target_price_yuan = Column(Numeric(10, 2), nullable=True)
    target_margin_rate = Column(Float, nullable=True)
    sponsor_user_id = Column(String(36), nullable=True)
    owner_user_id = Column(String(36), nullable=True)
    collaborator_user_ids = Column(JSON, default=list)
    priority = Column(String(10), default="medium")  # high/medium/low
    project_status = Column(SAEnum(ProjectStatusEnum), default=ProjectStatusEnum.PENDING_APPROVAL, index=True)
    approval_status = Column(String(20), default="pending")  # pending/approved/rejected
    risk_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.LOW)
    attachment_urls = Column(JSON, default=list)
    conclusion = Column(String(20), nullable=True)  # go/revise/stop/close
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)


class Recipe(Base):
    """配方主档容器"""

    __tablename__ = "dish_rd_recipes"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    brand_id = Column(String(36), nullable=False, index=True)
    recipe_code = Column(String(50), nullable=False, unique=True)
    recipe_name = Column(String(200), nullable=False)
    recipe_type = Column(SAEnum(RecipeTypeEnum), default=RecipeTypeEnum.MAIN)
    current_version_id = Column(String(36), nullable=True)
    owner_user_id = Column(String(36), nullable=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecipeVersion(Base):
    """配方版本 — BOM的真正执行版"""

    __tablename__ = "dish_rd_recipe_versions"

    id = Column(String(36), primary_key=True)
    recipe_id = Column(String(36), ForeignKey("dish_rd_recipes.id"), nullable=False, index=True)
    version_no = Column(String(20), nullable=False)
    version_type = Column(SAEnum(VersionTypeEnum), default=VersionTypeEnum.DEV)
    status = Column(SAEnum(RecipeVersionStatusEnum), default=RecipeVersionStatusEnum.DRAFT)
    parent_version_id = Column(String(36), nullable=True)
    change_reason = Column(String(50), nullable=True)
    serving_size = Column(Float, default=1.0)  # 标准份量数
    serving_unit = Column(String(20), default="份")
    yield_rate = Column(Float, default=1.0)  # 出成率
    loss_rate = Column(Float, default=0.05)  # 损耗率
    prep_time_min = Column(Integer, default=5)  # 备料时长(分钟)
    cook_time_min = Column(Integer, default=10)  # 制作时长
    complexity_score = Column(Float, default=3.0)  # 1-5
    difficulty_level = Column(String(10), default="medium")  # low/medium/high
    taste_profile = Column(JSON, default=dict)
    texture_profile = Column(JSON, default=dict)
    visual_standard_desc = Column(Text)
    notes = Column(Text)
    approved_by = Column(String(36), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecipeItem(Base):
    """配方明细项 — BOM行"""

    __tablename__ = "dish_rd_recipe_items"

    id = Column(String(36), primary_key=True)
    recipe_version_id = Column(String(36), ForeignKey("dish_rd_recipe_versions.id"), nullable=False, index=True)
    item_type = Column(String(20), nullable=False)  # ingredient / semi_product
    item_id = Column(String(36), nullable=False)
    item_name_snapshot = Column(String(200), nullable=False)  # 冗余快照
    quantity = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    loss_rate_snapshot = Column(Float, default=0.05)
    yield_rate_snapshot = Column(Float, default=1.0)
    unit_price_snapshot = Column(Numeric(10, 4), default=0)  # 快照价格
    process_stage = Column(String(20), default="cooking")  # prep/cooking/plating/dipping/garnish
    sequence_no = Column(Integer, default=1)
    optional_flag = Column(Boolean, default=False)
    substitute_group_code = Column(String(50), nullable=True)  # 替代组
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class SOP(Base):
    """标准工艺 — 门店可执行标准"""

    __tablename__ = "dish_rd_sops"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    brand_id = Column(String(36), nullable=False, index=True)
    sop_code = Column(String(50), nullable=False, unique=True)
    sop_type = Column(SAEnum(SopTypeEnum), default=SopTypeEnum.STANDARD)
    version_no = Column(String(20), default="v1")
    prep_sop = Column(JSON, default=list)  # [{step, desc, image_url}]
    cook_sop = Column(JSON, default=list)
    plating_sop = Column(JSON, default=list)
    utensil_standard = Column(JSON, default=dict)
    output_image_urls = Column(JSON, default=list)
    output_video_urls = Column(JSON, default=list)
    common_errors = Column(JSON, default=list)
    key_points = Column(JSON, default=list)
    training_points = Column(JSON, default=list)
    expected_time_min = Column(Integer, default=15)
    status = Column(String(20), default="draft")  # draft/approved/published/deprecated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NutritionProfile(Base):
    """营养画像"""

    __tablename__ = "dish_rd_nutrition_profiles"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    recipe_version_id = Column(String(36), nullable=True)
    calories_kcal = Column(Float, default=0)
    protein_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)
    carb_g = Column(Float, default=0)
    sugar_g = Column(Float, default=0)
    sodium_mg = Column(Float, default=0)
    fiber_g = Column(Float, default=0)
    nutrition_tags = Column(JSON, default=list)  # 高蛋白/低脂/低GI等
    calculated_at = Column(DateTime, default=datetime.utcnow)


class AllergenProfile(Base):
    """过敏原画像"""

    __tablename__ = "dish_rd_allergen_profiles"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    recipe_version_id = Column(String(36), nullable=True)
    allergen_tags = Column(JSON, default=list)  # 花生/坚果/麸质/乳制品等
    risk_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.LOW)
    warnings = Column(JSON, default=list)  # 提示文案
    calculated_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# L3 经营模拟层
# ─────────────────────────────────────────────


class CostModel(Base):
    """成本模型 — 单品成本测算结果"""

    __tablename__ = "dish_rd_cost_models"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    recipe_version_id = Column(String(36), nullable=True)
    brand_id = Column(String(36), nullable=False, index=True)
    calculation_basis = Column(String(30), default="theoretical")  # theoretical/pilot/regional/updated
    ingredient_cost_total = Column(Numeric(10, 4), default=0)
    semi_product_cost_total = Column(Numeric(10, 4), default=0)
    packaging_cost_total = Column(Numeric(10, 4), default=0)
    garnish_cost_total = Column(Numeric(10, 4), default=0)
    labor_cost_estimate = Column(Numeric(10, 4), default=0)
    utility_cost_estimate = Column(Numeric(10, 4), default=0)
    total_cost = Column(Numeric(10, 4), default=0)
    suggested_price_yuan = Column(Numeric(10, 2), default=0)
    margin_amount_yuan = Column(Numeric(10, 2), default=0)
    margin_rate = Column(Float, default=0)  # 毛利率 0-1
    price_scenarios = Column(JSON, default=list)  # [{price, margin_rate}]
    item_details = Column(JSON, default=list)  # 逐行成本明细
    calculation_version = Column(String(20), default="v1")
    calculated_at = Column(DateTime, default=datetime.utcnow)
    calculated_by = Column(String(36), nullable=True)


class SupplyAssessment(Base):
    """供应可行性评估"""

    __tablename__ = "dish_rd_supply_assessments"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    brand_id = Column(String(36), nullable=False, index=True)
    region_scope = Column(JSON, default=list)
    supplier_coverage_rate = Column(Float, default=0)  # 供应商覆盖率 0-1
    ingredient_availability_score = Column(Float, default=0)  # 原料可得性 0-100
    cold_chain_score = Column(Float, default=0)
    seasonality_risk_score = Column(Float, default=0)
    substitution_feasibility_score = Column(Float, default=0)
    total_supply_score = Column(Float, default=0)  # 综合供应评分 0-100
    supply_risk_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.MEDIUM)
    restriction_notes = Column(Text)
    recommendation = Column(SAEnum(SupplyRecommendationEnum), default=SupplyRecommendationEnum.REGIONAL)
    assessed_at = Column(DateTime, default=datetime.utcnow)
    assessed_by = Column(String(36), nullable=True)


# ─────────────────────────────────────────────
# L4 反馈复盘层
# ─────────────────────────────────────────────


class PilotTest(Base):
    """试点项目"""

    __tablename__ = "dish_rd_pilot_tests"

    id = Column(String(36), primary_key=True)
    pilot_code = Column(String(50), nullable=False, unique=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    brand_id = Column(String(36), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    recipe_version_id = Column(String(36), nullable=True)
    target_store_ids = Column(JSON, default=list)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    pilot_goal = Column(JSON, default=dict)  # 目标指标
    pilot_status = Column(SAEnum(PilotStatusEnum), default=PilotStatusEnum.PENDING)
    store_feedback_summary = Column(JSON, default=dict)
    avg_taste_score = Column(Float, nullable=True)  # 0-5
    avg_operation_score = Column(Float, nullable=True)
    avg_sales_score = Column(Float, nullable=True)
    avg_margin_score = Column(Float, nullable=True)
    avg_customer_feedback_score = Column(Float, nullable=True)
    decision = Column(SAEnum(PilotDecisionEnum), nullable=True)
    decision_reason = Column(Text)
    report_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LaunchProject(Base):
    """上市项目"""

    __tablename__ = "dish_rd_launch_projects"

    id = Column(String(36), primary_key=True)
    launch_code = Column(String(50), nullable=False, unique=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    brand_id = Column(String(36), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    launch_scope = Column(JSON, default=dict)  # 发布范围
    launch_type = Column(SAEnum(LaunchTypeEnum), default=LaunchTypeEnum.REGIONAL)
    planned_launch_date = Column(Date, nullable=True)
    actual_launch_date = Column(Date, nullable=True)
    checklist_status = Column(String(20), default="incomplete")  # incomplete/partial/complete
    approval_status = Column(String(20), default="pending")
    training_package_status = Column(String(20), default="not_sent")
    procurement_package_status = Column(String(20), default="not_sent")
    operation_notice_status = Column(String(20), default="not_sent")
    launch_status = Column(SAEnum(LaunchStatusEnum), default=LaunchStatusEnum.PENDING, index=True)
    launched_store_count = Column(Integer, default=0)
    abnormal_store_count = Column(Integer, default=0)
    rollback_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DishFeedback(Base):
    """菜品反馈记录"""

    __tablename__ = "dish_rd_feedbacks"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    brand_id = Column(String(36), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    feedback_source = Column(SAEnum(FeedbackSourceEnum), default=FeedbackSourceEnum.MANAGER)
    feedback_type = Column(SAEnum(FeedbackTypeEnum), default=FeedbackTypeEnum.TASTE)
    source_ref_id = Column(String(36), nullable=True)
    rating_score = Column(Float, nullable=True)  # 0-5
    keyword_tags = Column(JSON, default=list)
    content = Column(Text)
    store_id = Column(String(36), nullable=True, index=True)
    region_id = Column(String(36), nullable=True)
    happened_at = Column(DateTime, default=datetime.utcnow)
    severity_level = Column(SAEnum(RiskLevelEnum), default=RiskLevelEnum.LOW)
    handled_status = Column(String(20), default="pending")  # pending/handling/closed
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_dish_rd_feedbacks_dish_type", "dish_id", "feedback_type"),)


class RetrospectiveReport(Base):
    """复盘报告"""

    __tablename__ = "dish_rd_retrospective_reports"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), ForeignKey("dish_rd_dishes.id"), nullable=False, index=True)
    brand_id = Column(String(36), nullable=False, index=True)
    dish_version_id = Column(String(36), nullable=True)
    retrospective_period = Column(String(20), default="30d")  # 30d/60d/90d/phase
    sales_summary = Column(JSON, default=dict)
    margin_summary = Column(JSON, default=dict)
    return_reason_summary = Column(JSON, default=dict)
    feedback_summary = Column(JSON, default=dict)
    execution_summary = Column(JSON, default=dict)
    lifecycle_assessment = Column(SAEnum(LifecycleAssessmentEnum), nullable=True)
    optimization_suggestions = Column(JSON, default=list)
    conclusion = Column(Text)
    generated_by = Column(String(36), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# L5 事件智能层
# ─────────────────────────────────────────────


class DishRdAgentLog(Base):
    """Agent 执行日志"""

    __tablename__ = "dish_rd_agent_logs"

    id = Column(String(36), primary_key=True)
    dish_id = Column(String(36), nullable=True, index=True)
    brand_id = Column(String(36), nullable=False, index=True)
    agent_type = Column(SAEnum(DishRdAgentTypeEnum), nullable=False)
    trigger_reason = Column(String(200))
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    recommendation = Column(Text)
    confidence = Column(Float, default=0.8)
    executed_at = Column(DateTime, default=datetime.utcnow)
    executed_by = Column(String(36), nullable=True)  # None = 系统自动
