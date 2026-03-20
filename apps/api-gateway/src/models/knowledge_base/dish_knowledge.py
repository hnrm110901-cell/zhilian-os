"""菜品知识库主档 — 行业级菜品字典与菜谱标准。

五层模型：
1. 菜品主档 DishKnowledge      — 定义一道菜"是什么"
2. 菜谱版本 DishRecipeVersion   — 定义一道菜"怎么做"
3. 原料主档 IndustryIngredientMaster — 定义"材料是什么"
4. 标签与分类 DishKnowledgeTaxonomyTag — 定义"属于什么类别"
5. 经营画像 DishKnowledgeOperationProfile — 定义"卖得怎么样"

区别于门店级 Dish 模型：
- DishKnowledge 是行业级标准字典（1000+道菜基础库）
- Dish 是门店实际在售菜品
- DishKnowledge.id 可被 Dish.dish_knowledge_id 引用
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
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class DishKnowledge(Base, TimestampMixin):
    """菜品知识库主档 — 行业级菜品标准定义。

    字段设计参考：
    - 菜品ID编码规则: DISH_{国家}_{菜系}_{序号}，如 DISH_CN_SC_0001
    - 包含标准化等级(A/B/C)用于评估连锁推广可行性
    - 多维适配评分(1-5)覆盖堂食/外卖/宴席/时段
    """

    __tablename__ = "kb_dish_knowledge"
    __table_args__ = (
        UniqueConstraint("dish_code", name="uq_kb_dish_knowledge_code"),
        Index("ix_kb_dish_knowledge_cuisine", "cuisine_region"),
        Index("ix_kb_dish_knowledge_category", "category_l1", "category_l2"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本标识
    dish_code = Column(String(64), nullable=False, comment="菜品编码 如 SC-HOT-0001")
    dish_name_zh = Column(String(128), nullable=False, comment="菜品中文标准名")
    dish_name_en = Column(String(200), comment="菜品英文名")
    alias_names = Column(ARRAY(String), comment="别名集合")
    dish_status = Column(String(32), nullable=False, default="active",
                         comment="active/test/offline")
    launch_type = Column(String(32), default="listed",
                         comment="listed/test/seasonal/retired")

    # 地域/菜系
    cuisine_country = Column(String(64), default="中国", comment="所属国家")
    cuisine_region = Column(String(64), nullable=False, comment="所属菜系/区域")

    # 分类
    category_l1 = Column(String(64), nullable=False, comment="一级分类: 热菜/凉菜/汤羹/主食/...")
    category_l2 = Column(String(64), comment="二级分类: 鸡肉类/牛肉类/...")
    category_l3 = Column(String(64), comment="三级分类: 炒鸡类/...")
    main_ingredient_group = Column(String(64), comment="主原料组: 鸡肉/牛肉/...")
    dish_type = Column(String(32), default="a_la_carte",
                       comment="单点/套餐/小吃/汤品/主食")

    # 出品属性
    serving_temp = Column(String(16), comment="食用温度: hot/warm/cold/iced")
    serving_size_type = Column(String(16), comment="份型: small/regular/large/share")
    cooking_method = Column(String(64), comment="主烹饪方法: 炒/蒸/煮/烤/...")

    # 风味
    taste_profile_primary = Column(String(64), comment="主风味: 麻辣/咸鲜/...")
    taste_profile_secondary = Column(ARRAY(String), comment="次风味")
    color_profile = Column(String(64), comment="成品颜色: 红亮/金黄/...")
    texture_profile = Column(ARRAY(String), comment="口感标签: 嫩/脆/香/...")
    spicy_level = Column(Integer, comment="辣度等级 0-5")

    # 装盘
    plating_style = Column(String(32), comment="装盘风格: 盘装/碗装/锅仔/砂锅")

    # 标识
    is_signature = Column(Boolean, default=False, comment="是否招牌菜")
    is_classic = Column(Boolean, default=False, comment="是否经典名菜")
    is_chain_friendly = Column(Boolean, default=True, comment="是否适合连锁经营")

    # 标准化评估
    standardization_level = Column(String(1), comment="标准化等级: A/B/C")
    prep_complexity = Column(String(1), comment="出品复杂度: A低/B中/C高")

    # 多维适配评分(1-5)
    dine_in_fit = Column(Integer, comment="堂食适配(1-5)")
    takeaway_fit = Column(Integer, comment="外卖适配(1-5)")
    catering_fit = Column(Integer, comment="宴席适配(1-5)")
    breakfast_fit = Column(Integer, comment="早餐适配(1-5)")
    lunch_fit = Column(Integer, comment="午市适配(1-5)")
    dinner_fit = Column(Integer, comment="晚市适配(1-5)")
    supper_fit = Column(Integer, comment="夜宵适配(1-5)")
    seasonality = Column(String(16), default="all_year",
                         comment="季节性: spring/summer/autumn/winter/all_year")

    # 过敏原与膳食
    allergen_flags = Column(ARRAY(String), comment="过敏原标签")
    dietary_flags = Column(ARRAY(String), comment="膳食标签: 素食/清真/...")

    # 文化与搜索
    culture_story = Column(Text, comment="菜品文化故事")
    search_keywords = Column(ARRAY(String), comment="搜索关键词")
    embedding_text = Column(Text, comment="向量检索聚合文本")

    # 关系
    recipe_versions = relationship("DishRecipeVersion", back_populates="dish_knowledge", cascade="all, delete-orphan")
    nutrition = relationship(
        "DishKnowledgeNutrition", back_populates="dish_knowledge",
        uselist=False, cascade="all, delete-orphan",
    )
    operation_profile = relationship(
        "DishKnowledgeOperationProfile", back_populates="dish_knowledge",
        uselist=False, cascade="all, delete-orphan",
    )
    taxonomy_tags = relationship("DishKnowledgeTaxonomyTag", back_populates="dish_knowledge", cascade="all, delete-orphan")


class DishRecipeVersion(Base, TimestampMixin):
    """菜谱版本 — 一道菜可以有多个版本的制作方法。"""

    __tablename__ = "kb_dish_recipe_versions"
    __table_args__ = (
        UniqueConstraint("dish_knowledge_id", "version_no", name="uq_kb_dish_recipe_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_knowledge_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_dish_knowledge.id"),
        nullable=False, index=True,
    )

    version_no = Column(String(16), nullable=False, comment="版本号 如 V1.0")
    version_status = Column(String(32), nullable=False, default="current",
                            comment="current/draft/archived")
    serving_count = Column(Numeric(8, 2), default=1, comment="标准份数")
    net_weight_g = Column(Numeric(12, 2), comment="净重(g)")
    gross_weight_g = Column(Numeric(12, 2), comment="毛重(g)")
    yield_rate = Column(Numeric(8, 4), comment="出成率")

    # 时间
    prep_time_min = Column(Integer, comment="备料时长(分钟)")
    cook_time_min = Column(Integer, comment="烹制时长(分钟)")
    total_time_min = Column(Integer, comment="总时长(分钟)")

    # 工位与设备
    wok_station_type = Column(String(64), comment="工位类型: 炒锅/蒸柜/烤箱/...")
    equipment_required = Column(ARRAY(String), comment="设备要求")

    # SOP
    step_text = Column(Text, comment="工艺步骤文本")
    critical_control_points = Column(ARRAY(String), comment="关键控制点")
    plating_standard = Column(Text, comment="装盘标准")
    garnish_standard = Column(Text, comment="点缀标准")
    taste_target = Column(Text, comment="风味目标描述")
    photo_ref = Column(String(500), comment="标准出品图URL")

    # 关系
    dish_knowledge = relationship("DishKnowledge", back_populates="recipe_versions")
    ingredients = relationship("DishRecipeIngredient", back_populates="recipe_version", cascade="all, delete-orphan")


class DishRecipeIngredient(Base, TimestampMixin):
    """菜谱原料明细 — 每个版本配方的原料用量。

    去重规则：
    - 同一标准原料在同一配方中只出现一次
    - 通过 ingredient_canonical_name 去重
    - 不同切法/预处理通过 cut_style/pre_process 区分
    """

    __tablename__ = "kb_dish_recipe_ingredients"
    __table_args__ = (
        Index("ix_kb_dish_recipe_ing_recipe", "recipe_version_id", "sort_no"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipe_version_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_dish_recipe_versions.id"),
        nullable=False,
    )

    ingredient_id = Column(UUID(as_uuid=True), comment="关联原料主档ID")
    ingredient_canonical_name = Column(String(128), nullable=False, comment="原料标准名(去重)")
    ingredient_variant_name = Column(String(128), comment="原料变体名(显示用)")
    ingredient_role = Column(
        String(32), nullable=False,
        comment="角色: main/sub/seasoning/garnish/sauce",
    )

    part_used = Column(String(64), comment="使用部位: 鸡胸/猪里脊/...")
    cut_style = Column(String(32), comment="切配方式: 丁/丝/片/块/末/段")
    pre_process = Column(String(64), comment="预处理: 腌制/焯水/炸制/泡发")
    quantity = Column(Numeric(12, 3), nullable=False, comment="用量")
    unit = Column(String(16), nullable=False, comment="单位: g/ml/个/张/勺")
    loss_rate = Column(Numeric(8, 4), comment="损耗率")
    substitution_group = Column(String(64), comment="替代组")
    is_optional = Column(Boolean, default=False, comment="是否可选")
    sort_no = Column(Integer, nullable=False, default=0, comment="排序")

    recipe_version = relationship("DishRecipeVersion", back_populates="ingredients")


class IndustryIngredientMaster(Base, TimestampMixin):
    """行业级原料主档 — 食材标准字典。

    与门店级 IngredientMaster 的区别：
    - 本表是行业通用标准（如"花生"、"鸡胸肉"）
    - IngredientMaster 是门店实际采购的SKU（如"XXX品牌冷冻鸡胸500g/袋"）
    """

    __tablename__ = "kb_industry_ingredient_masters"
    __table_args__ = (
        UniqueConstraint("ingredient_code", name="uq_kb_industry_ingredient_code"),
        Index("ix_kb_industry_ing_category", "category_l1", "category_l2"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    ingredient_code = Column(String(64), nullable=False, comment="原料编码 如 ING_PEANUT_01")
    ingredient_name_zh = Column(String(128), nullable=False, comment="原料中文标准名")
    ingredient_name_en = Column(String(128), comment="原料英文名")
    aliases = Column(ARRAY(String), comment="别名: 花生米/落花生/...")

    # 分类
    category_l1 = Column(String(64), nullable=False, comment="一级分类: 坚果豆制/肉禽/水产/...")
    category_l2 = Column(String(64), comment="二级分类: 坚果/鸡肉/...")
    species_source = Column(String(128), comment="物种来源: 落花生/黄羽鸡/...")

    # 单位与储存
    default_unit = Column(String(16), nullable=False, default="g", comment="默认单位")
    storage_type = Column(String(16), comment="储存方式: fresh/chilled/frozen/dry")
    shelf_life_rule = Column(String(200), comment="保质规则描述")

    # 过敏原
    allergen_flag = Column(Boolean, default=False, comment="是否过敏原")
    allergen_type = Column(ARRAY(String), comment="过敏原类型")
    dietary_flags = Column(ARRAY(String), comment="膳食属性: 植物来源/动物来源/清真/...")

    # 经济属性
    cost_grade = Column(String(1), comment="成本等级: A高/B中/C低")
    standard_sku_code = Column(String(64), comment="标准SKU编码(采购映射)")

    is_active = Column(Boolean, default=True)


class DishKnowledgeNutrition(Base, TimestampMixin):
    """菜品营养信息 — 每份营养成分。"""

    __tablename__ = "kb_dish_knowledge_nutrition"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_knowledge_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_dish_knowledge.id"),
        nullable=False, unique=True,
    )

    kcal = Column(Numeric(8, 1), comment="热量(千卡/份)")
    protein_g = Column(Numeric(8, 1), comment="蛋白质(g/份)")
    fat_g = Column(Numeric(8, 1), comment="脂肪(g/份)")
    carbs_g = Column(Numeric(8, 1), comment="碳水化合物(g/份)")
    sodium_mg = Column(Numeric(8, 1), comment="钠(mg/份)")
    sugar_g = Column(Numeric(8, 1), comment="糖(g/份)")
    fiber_g = Column(Numeric(8, 1), comment="膳食纤维(g/份)")
    nutrition_note = Column(Text, comment="营养备注(估算值说明)")

    dish_knowledge = relationship("DishKnowledge", back_populates="nutrition")


class DishKnowledgeOperationProfile(Base, TimestampMixin):
    """菜品经营画像 — 连锁经营适配评估。"""

    __tablename__ = "kb_dish_knowledge_operation_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_knowledge_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_dish_knowledge.id"),
        nullable=False, unique=True,
    )

    price_band = Column(String(16), comment="价格带: low/mid/high/premium")
    food_cost_rate = Column(Numeric(8, 4), comment="目标食材成本率")
    gross_margin_rate = Column(Numeric(8, 4), comment="目标毛利率")

    # 经营评分(1-5)
    sales_volume_potential = Column(Integer, comment="销量潜力")
    standardization_score = Column(Integer, comment="标准化评分")
    training_difficulty = Column(Integer, comment="培训难度")
    peak_hour_pressure = Column(Integer, comment="高峰出餐压力")
    pre_make_fit = Column(Integer, comment="预制适配度")
    central_kitchen_fit = Column(Integer, comment="中央厨房适配度")

    menu_role = Column(String(32), comment="菜单角色: traffic/profit/filler/anchor")

    dish_knowledge = relationship("DishKnowledge", back_populates="operation_profile")


class DishKnowledgeTaxonomyTag(Base, TimestampMixin):
    """菜品标签 — 多维度标签体系。

    tag_type 枚举：
    - occasion: 场景(家庭聚餐/商务宴请/朋友聚会)
    - season: 季节(春/夏/秋/冬)
    - crowd: 人群(儿童/老人/年轻人)
    - cuisine_sub: 菜系细分(传统川菜/江湖川菜)
    - cooking: 烹饪标签(快炒/慢炖/生食)
    - health: 健康标签(低脂/高蛋白/无麸质)
    """

    __tablename__ = "kb_dish_knowledge_taxonomy_tags"
    __table_args__ = (
        Index("ix_kb_dish_tag_type", "tag_type", "tag_value"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_knowledge_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_dish_knowledge.id"),
        nullable=False, index=True,
    )

    tag_type = Column(String(32), nullable=False, comment="标签类型")
    tag_value = Column(String(128), nullable=False, comment="标签值")
    tag_source = Column(String(16), default="system", comment="来源: system/manual/ai")

    dish_knowledge = relationship("DishKnowledge", back_populates="taxonomy_tags")
