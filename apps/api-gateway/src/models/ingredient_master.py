"""
Ingredient Master Data — 食材主档
"""
from sqlalchemy import Column, String, Integer, Numeric, Boolean, Text
from sqlalchemy.dialects.postgresql import ARRAY

from .base import Base, TimestampMixin


class IngredientMaster(Base, TimestampMixin):
    """食材主档 — 全集团统一的食材字典"""
    __tablename__ = "ingredient_masters"

    ingredient_id = Column(String(50), primary_key=True)  # ING_LY_001
    canonical_name = Column(String(100), nullable=False)   # 鲈鱼
    aliases = Column(ARRAY(String(100)))                   # {海鲈鱼,花鲈,七星鲈}
    category = Column(String(30), nullable=False)          # seafood/meat/vegetable/...
    sub_category = Column(String(30))                      # 淡水鱼
    base_unit = Column(String(10), nullable=False)         # kg/L/个
    spec_desc = Column(String(100))                        # 鲜活, 500-700g/条
    shelf_life_days = Column(Integer)
    storage_type = Column(String(20), nullable=False)      # frozen/chilled/ambient/live
    storage_temp_min = Column(Numeric(5, 1))               # 0.0 ℃
    storage_temp_max = Column(Numeric(5, 1))               # 4.0 ℃
    is_traceable = Column(Boolean, nullable=False, default=False)
    allergen_tags = Column(ARRAY(String(30)))               # {鱼类}
    seasonality = Column(ARRAY(String(2)))                  # {3,4,5,9,10}
    typical_waste_pct = Column(Numeric(5, 2))               # 8.00
    typical_yield_rate = Column(Numeric(5, 4))              # 0.6500
    is_active = Column(Boolean, nullable=False, default=True)
