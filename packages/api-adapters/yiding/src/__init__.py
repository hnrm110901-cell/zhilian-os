"""
易订适配器 - YiDing Adapter

智链OS与易订预订系统的集成适配器
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
    ReservationStats,
    CreateReservationDTO,
    UpdateReservationDTO,
    CreateCustomerDTO,
    UpdateCustomerDTO,
    ReservationStatus,
    TableType,
    TableStatus
)

__version__ = "0.1.0"

__all__ = [
    # Main adapter
    "YiDingAdapter",

    # Components
    "YiDingClient",
    "YiDingMapper",
    "YiDingCache",

    # Exceptions
    "YiDingAPIError",

    # Types
    "YiDingConfig",
    "UnifiedReservation",
    "UnifiedCustomer",
    "UnifiedTable",
    "ReservationStats",
    "CreateReservationDTO",
    "UpdateReservationDTO",
    "CreateCustomerDTO",
    "UpdateCustomerDTO",

    # Enums
    "ReservationStatus",
    "TableType",
    "TableStatus",
]
