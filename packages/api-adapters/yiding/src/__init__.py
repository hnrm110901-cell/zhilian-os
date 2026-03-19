"""
易订预订系统适配器 - YiDing Reservation System Adapter

基于易订开放API（https://open.zhidianfan.com/yidingopen/）
"""

from .adapter import YiDingAdapter
from .client import YiDingClient, YiDingAPIError
from .mapper import YiDingMapper
from .cache import YiDingCache
from .types import (
    YiDingConfig,
    UnifiedReservation,
    UnifiedCustomer,
    UnifiedTable,
    UnifiedBill,
    UnifiedDish,
    ReservationStats,
    ReservationStatus,
    TableType,
    TableStatus,
    CreateReservationDTO,
)

__version__ = "1.0.0"

__all__ = [
    "YiDingAdapter",
    "YiDingClient",
    "YiDingAPIError",
    "YiDingMapper",
    "YiDingCache",
    "YiDingConfig",
    "UnifiedReservation",
    "UnifiedCustomer",
    "UnifiedTable",
    "UnifiedBill",
    "UnifiedDish",
    "ReservationStats",
    "ReservationStatus",
    "TableType",
    "TableStatus",
    "CreateReservationDTO",
]
