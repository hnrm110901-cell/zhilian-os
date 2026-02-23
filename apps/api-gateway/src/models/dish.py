"""
菜品主档模型
餐饮ERP的核心实体，连接菜单、库存、成本、销售四个维度
"""
from sqlalchemy import Column, String, Numeric, Integer, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSON
from sqlalchemy.orm import relationship
import uuid

from src.models.base import Base, TimestampMixin


class DishCategory(Base, TimestampMixin):
    """
    菜品分类表
    """
    __tablename__ = "dish_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 分类名称：热菜、凉菜、主食、饮品等
    code = Column(String(50))  # 分类编码
    parent_id = Column(UUID(as_uuid=True), ForeignKey("dish_categories.id"))  # 父分类（支持多级分类）
    sort_order = Column(Integer, default=0)  # 排序
    description = Column(Text)  # 分类描述
    is_active = Column(Boolean, default=True)  # 是否启用

    # 关联关系
    dishes = relationship("Dish", back_populates="category")
    parent = relationship("DishCategory", remote_side=[id], backref="children")

    __table_args__ = (
        Index("idx_dish_category_store_id", "store_id"),
        Index("idx_dish_category_parent_id", "parent_id"),
    )

    def __repr__(self):
        return f"<DishCategory(id={self.id}, name={self.name}, store_id={self.store_id})>"


class Dish(Base, TimestampMixin):
    """
    菜品主档表
    餐饮ERP的核心实体
    """
    __tablename__ = "dishes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 基本信息
    name = Column(String(100), nullable=False)  # 菜品名称
    code = Column(String(50), unique=True, nullable=False)  # 菜品编码（唯一）
    category_id = Column(UUID(as_uuid=True), ForeignKey("dish_categories.id"))  # 分类
    description = Column(Text)  # 菜品描述
    image_url = Column(String(500))  # 菜品图片URL

    # 价格信息
    price = Column(Numeric(10, 2), nullable=False)  # 售价
    original_price = Column(Numeric(10, 2))  # 原价（用于显示折扣）
    cost = Column(Numeric(10, 2))  # 成本价
    profit_margin = Column(Numeric(5, 2))  # 毛利率（%）

    # 规格信息
    unit = Column(String(20), default="份")  # 单位：份、例、斤等
    serving_size = Column(String(50))  # 规格：大份、中份、小份
    spicy_level = Column(Integer, default=0)  # 辣度等级：0-5

    # 营养信息
    calories = Column(Integer)  # 卡路里
    protein = Column(Numeric(5, 2))  # 蛋白质（克）
    fat = Column(Numeric(5, 2))  # 脂肪（克）
    carbohydrate = Column(Numeric(5, 2))  # 碳水化合物（克）

    # 标签和属性
    tags = Column(ARRAY(String))  # 标签：招牌菜、新品、特价、素食等
    allergens = Column(ARRAY(String))  # 过敏原：花生、海鲜、乳制品等
    dietary_info = Column(ARRAY(String))  # 饮食信息：素食、清真、无麸质等

    # 销售信息
    is_available = Column(Boolean, default=True)  # 是否可售
    is_recommended = Column(Boolean, default=False)  # 是否推荐
    is_seasonal = Column(Boolean, default=False)  # 是否季节性菜品
    season = Column(String(20))  # 季节：春、夏、秋、冬
    sort_order = Column(Integer, default=0)  # 排序

    # 制作信息
    preparation_time = Column(Integer)  # 制作时间（分钟）
    cooking_method = Column(String(50))  # 烹饪方法：炒、炸、蒸、煮等
    kitchen_station = Column(String(50))  # 厨房工位：炒锅、蒸锅、凉菜间等

    # 统计信息
    total_sales = Column(Integer, default=0)  # 总销量
    total_revenue = Column(Numeric(12, 2), default=0)  # 总营收
    rating = Column(Numeric(3, 2))  # 评分（1-5）
    review_count = Column(Integer, default=0)  # 评价数量

    # 库存关联
    requires_inventory = Column(Boolean, default=True)  # 是否需要库存管理
    low_stock_threshold = Column(Integer)  # 低库存阈值

    # 额外信息
    notes = Column(Text)  # 备注
    dish_metadata = Column(JSON)  # 扩展字段

    # 关联关系
    category = relationship("DishCategory", back_populates="dishes")
    ingredients = relationship("DishIngredient", back_populates="dish", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_dish_store_id", "store_id"),
        Index("idx_dish_code", "code"),
        Index("idx_dish_category_id", "category_id"),
        Index("idx_dish_store_available", "store_id", "is_available"),
        Index("idx_dish_store_category", "store_id", "category_id"),
    )

    def __repr__(self):
        return f"<Dish(id={self.id}, name={self.name}, code={self.code}, price={self.price})>"

    def calculate_profit_margin(self):
        """计算毛利率"""
        if self.price and self.cost:
            self.profit_margin = ((self.price - self.cost) / self.price) * 100
        return self.profit_margin


class DishIngredient(Base, TimestampMixin):
    """
    菜品-食材关联表
    记录每道菜需要哪些食材以及用量
    """
    __tablename__ = "dish_ingredients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 关联信息
    dish_id = Column(UUID(as_uuid=True), ForeignKey("dishes.id"), nullable=False)
    ingredient_id = Column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False)

    # 用量信息
    quantity = Column(Numeric(10, 3), nullable=False)  # 用量
    unit = Column(String(20), nullable=False)  # 单位：克、毫升、个等
    cost_per_serving = Column(Numeric(10, 2))  # 每份成本

    # 是否必需
    is_required = Column(Boolean, default=True)  # 是否必需食材
    is_substitutable = Column(Boolean, default=False)  # 是否可替代
    substitute_ids = Column(ARRAY(UUID(as_uuid=True)))  # 可替代食材ID列表

    # 备注
    notes = Column(Text)

    # 关联关系
    dish = relationship("Dish", back_populates="ingredients")
    ingredient = relationship("InventoryItem")

    __table_args__ = (
        Index("idx_dish_ingredient_dish_id", "dish_id"),
        Index("idx_dish_ingredient_ingredient_id", "ingredient_id"),
        Index("idx_dish_ingredient_store_id", "store_id"),
    )

    def __repr__(self):
        return f"<DishIngredient(dish_id={self.dish_id}, ingredient_id={self.ingredient_id}, quantity={self.quantity})>"
