"""
屯象OS 行业公共字典 — 库存/食材统一模型
"""

from typing import TypedDict, Optional, List


class UnifiedIngredient(TypedDict, total=False):
    """统一食材格式"""
    id: str
    external_id: str
    source: str
    store_id: str

    name: str
    category: str
    unit: str
    unit_price: float
    specification: str
    shelf_life_days: int
    storage_condition: str
    is_available: bool


class UnifiedInventoryRecord(TypedDict, total=False):
    """统一库存记录"""
    id: str
    ingredient_id: str
    store_id: str

    quantity: float
    unit: str
    batch_no: str
    expiry_date: str
    location: str

    last_check_date: str
    last_check_quantity: float
