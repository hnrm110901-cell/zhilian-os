"""
屯象OS 行业公共字典 — 菜品/套餐统一模型
"""

from typing import TypedDict, Optional, List, Dict, Any


class UnifiedDishMethod(TypedDict, total=False):
    """菜品做法"""
    method_id: str
    method_name: str
    price: float
    quantity: int


class UnifiedDish(TypedDict, total=False):
    """统一菜品格式"""
    id: str
    external_id: str
    source: str
    store_id: str

    name: str
    category_code: str
    category_name: str
    subcategory_code: str
    subcategory_name: str
    price: float
    unit: str
    pinyin_code: str
    specification: str

    methods: List[UnifiedDishMethod]

    is_available: bool


class UnifiedSetMeal(TypedDict, total=False):
    """统一套餐格式"""
    set_meal_id: str
    set_meal_name: str
    price: float
    quantity: int
    dishes: List[UnifiedDish]
