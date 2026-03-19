"""
屯象OS 行业公共字典

连锁餐饮行业统一数据模型，所有外部系统适配器映射到此字典。
不跟随任何一家三方系统的字段定义。
"""

from .enums import (
    ReservationStatus,
    OrderStatus,
    OrderType,
    ReservationType,
    TableType,
    TableStatus,
    MealPeriod,
    PaymentMethod,
    ChannelSource,
    Gender,
    CustomerLevel,
    DishCategory,
)
from .reservation import (
    UnifiedReservation,
    ReservationStats,
    CreateReservationRequest,
)
from .customer import UnifiedCustomer
from .table import UnifiedTable
from .order import UnifiedOrder, UnifiedOrderItem
from .bill import UnifiedBill
from .dish import UnifiedDish, UnifiedDishMethod, UnifiedSetMeal
from .inventory import UnifiedIngredient, UnifiedInventoryRecord
from .supplier import UnifiedSupplier, UnifiedPurchaseOrder

__all__ = [
    # Enums
    "ReservationStatus",
    "OrderStatus",
    "OrderType",
    "ReservationType",
    "TableType",
    "TableStatus",
    "MealPeriod",
    "PaymentMethod",
    "ChannelSource",
    "Gender",
    "CustomerLevel",
    "DishCategory",
    # Reservation
    "UnifiedReservation",
    "ReservationStats",
    "CreateReservationRequest",
    # Customer
    "UnifiedCustomer",
    # Table
    "UnifiedTable",
    # Order
    "UnifiedOrder",
    "UnifiedOrderItem",
    # Bill
    "UnifiedBill",
    # Dish
    "UnifiedDish",
    "UnifiedDishMethod",
    "UnifiedSetMeal",
    # Inventory
    "UnifiedIngredient",
    "UnifiedInventoryRecord",
    # Supplier
    "UnifiedSupplier",
    "UnifiedPurchaseOrder",
]
