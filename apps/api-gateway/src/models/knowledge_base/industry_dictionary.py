"""行业字典 — 餐饮行业标准枚举与分类树。

统一管理所有行业级分类数据：
- 菜品分类树(一级/二级/三级)
- 菜系树(中国菜系/国际菜系)
- 烹饪方法树(20+种)
- 风味树(18+种)
- 原料分类树
- 过敏原枚举
- 膳食标签枚举
- 成本分类树(一级/二级)
- 门店业态枚举
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from src.models.base import Base, TimestampMixin


class IndustryDictionary(Base, TimestampMixin):
    """行业字典 — 统一的分类与枚举管理。

    通过 dict_type + parent_code 构建树形结构。
    dict_type 枚举：
    - dish_category      菜品分类(热菜/凉菜/汤羹/主食/...)
    - cuisine            菜系(川菜/粤菜/湘菜/日料/...)
    - cooking_method     烹饪方法(炒/蒸/煮/烤/...)
    - flavor             风味(麻辣/咸鲜/酱香/...)
    - ingredient_category 原料分类(肉禽/水产/蔬菜/...)
    - allergen           过敏原(花生/大豆/乳制品/...)
    - dietary_tag        膳食标签(素食/清真/无麸质/...)
    - cost_category      成本分类(食材/人工/房租/...)
    - business_type      业态(正餐/快餐/火锅/烧烤/...)
    - serving_temp       食用温度(hot/warm/cold/iced)
    - serving_size       份型(small/regular/large/share)
    - price_band         价格带(low/mid/high/premium)
    - menu_role          菜单角色(traffic/profit/filler/anchor)
    - process_stage      工艺阶段(prep/marinate/cook/...)
    - material_type      物料类型(main/sub/seasoning/packaging)
    """

    __tablename__ = "kb_industry_dictionaries"
    __table_args__ = (
        UniqueConstraint("dict_type", "dict_code", name="uq_kb_industry_dict"),
        Index("ix_kb_industry_dict_type", "dict_type"),
        Index("ix_kb_industry_dict_parent", "dict_type", "parent_code"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    dict_type = Column(String(32), nullable=False, comment="字典类型")
    dict_code = Column(String(64), nullable=False, comment="字典编码")
    dict_name_zh = Column(String(128), nullable=False, comment="中文名")
    dict_name_en = Column(String(128), comment="英文名")

    # 树形结构
    parent_code = Column(String(64), comment="父级编码(null=顶级)")
    level = Column(Integer, nullable=False, default=1, comment="层级(1=一级)")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序")

    # 扩展
    description = Column(Text, comment="说明")
    icon = Column(String(128), comment="图标URL/标识")
    extra_json = Column(Text, comment="扩展属性JSON")

    is_active = Column(Boolean, nullable=False, default=True)
    is_system = Column(Boolean, nullable=False, default=True,
                       comment="是否系统预置(不可删除)")
