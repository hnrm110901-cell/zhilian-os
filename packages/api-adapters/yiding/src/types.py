"""
易订适配器类型定义 - YiDing Adapter Types

定义易订系统的数据类型和统一接口格式
"""

from typing import TypedDict, Optional, List, Literal
from datetime import datetime
from enum import Enum


# ============================================
# 统一数据格式 (Unified Data Models)
# ============================================

class ReservationStatus(str, Enum):
    """预订状态"""
    PENDING = "pending"          # 待确认
    CONFIRMED = "confirmed"      # 已确认
    SEATED = "seated"            # 已入座
    COMPLETED = "completed"      # 已完成
    CANCELLED = "cancelled"      # 已取消
    NO_SHOW = "no_show"         # 未到店


class TableType(str, Enum):
    """桌型"""
    SMALL = "small"              # 小桌(2-4人)
    MEDIUM = "medium"            # 中桌(4-6人)
    LARGE = "large"              # 大桌(6-10人)
    ROUND = "round"              # 圆桌(10-12人)
    PRIVATE_ROOM = "private_room"  # 包间


class TableStatus(str, Enum):
    """桌台状态"""
    AVAILABLE = "available"      # 可用
    OCCUPIED = "occupied"        # 占用中
    RESERVED = "reserved"        # 已预订
    MAINTENANCE = "maintenance"  # 维护中


class UnifiedReservation(TypedDict):
    """统一预订格式"""
    id: str                      # 智链OS内部ID
    external_id: str             # 易订系统ID
    source: Literal["yiding"]    # 来源系统
    store_id: str                # 门店ID

    # 客户信息
    customer_id: str
    customer_name: str
    customer_phone: str

    # 预订信息
    reservation_date: str        # YYYY-MM-DD
    reservation_time: str        # HH:mm
    party_size: int              # 人数
    table_type: TableType        # 桌型
    table_number: Optional[str]  # 桌号

    # 状态
    status: ReservationStatus

    # 金额
    deposit_amount: int          # 定金(分)
    estimated_amount: int        # 预估消费(分)

    # 备注
    special_requests: Optional[str]
    note: Optional[str]

    # 时间戳
    created_at: str
    updated_at: str
    confirmed_at: Optional[str]
    seated_at: Optional[str]
    completed_at: Optional[str]


class UnifiedCustomer(TypedDict):
    """统一客户格式"""
    id: str
    external_id: str
    source: Literal["yiding"]

    phone: str
    name: str
    gender: Optional[Literal["male", "female"]]
    birthday: Optional[str]

    # 会员信息
    member_level: Optional[str]
    member_points: Optional[int]
    balance: Optional[int]

    # 统计
    total_visits: int
    total_spent: int
    last_visit: Optional[str]

    # 偏好
    preferences: Optional[dict]
    tags: Optional[List[str]]

    created_at: str
    updated_at: str


class UnifiedTable(TypedDict):
    """统一桌台格式"""
    id: str
    table_number: str
    table_type: TableType
    capacity: int
    min_capacity: int
    status: TableStatus
    location: Optional[str]
    features: Optional[List[str]]


class ReservationStats(TypedDict):
    """预订统计"""
    store_id: str
    period_start: str
    period_end: str
    total_reservations: int
    confirmed_count: int
    cancelled_count: int
    no_show_count: int
    confirmation_rate: float
    cancellation_rate: float
    no_show_rate: float
    average_party_size: float
    peak_hours: List[str]
    revenue_from_reservations: int


# ============================================
# 易订原始数据格式 (YiDing Raw Data Models)
# ============================================

class YiDingReservation(TypedDict):
    """易订预订原始格式"""
    id: str
    store_id: str
    customer_id: str
    customer_name: str
    customer_phone: str
    reservation_date: str
    reservation_time: str
    party_size: int
    table_type: str
    table_number: Optional[str]
    status: str
    deposit_amount: Optional[int]
    estimated_amount: Optional[int]
    special_requests: Optional[str]
    note: Optional[str]
    created_at: str
    updated_at: str
    confirmed_at: Optional[str]
    seated_at: Optional[str]
    completed_at: Optional[str]


class YiDingCustomer(TypedDict):
    """易订客户原始格式"""
    id: str
    phone: str
    name: str
    gender: Optional[str]
    birthday: Optional[str]
    member_level: Optional[str]
    points: Optional[int]
    balance: Optional[int]
    visit_count: Optional[int]
    total_spent: Optional[int]
    last_visit_date: Optional[str]
    favorite_dishes: Optional[List[str]]
    preferred_table: Optional[str]
    preferred_time: Optional[str]
    dietary_restrictions: Optional[List[str]]
    tags: Optional[List[str]]
    created_at: str
    updated_at: str


class YiDingTable(TypedDict):
    """易订桌台原始格式"""
    id: str
    table_number: str
    table_type: str
    capacity: int
    min_capacity: int
    status: str
    location: Optional[str]
    features: Optional[List[str]]


# ============================================
# DTO (Data Transfer Objects)
# ============================================

class CreateReservationDTO(TypedDict):
    """创建预订DTO"""
    store_id: str
    customer_name: str
    customer_phone: str
    reservation_date: str
    reservation_time: str
    party_size: int
    table_type: Optional[TableType]
    special_requests: Optional[str]


class UpdateReservationDTO(TypedDict, total=False):
    """更新预订DTO"""
    reservation_date: str
    reservation_time: str
    party_size: int
    table_type: TableType
    table_number: str
    special_requests: str
    status: ReservationStatus


class CreateCustomerDTO(TypedDict):
    """创建客户DTO"""
    phone: str
    name: str
    gender: Optional[Literal["male", "female"]]
    birthday: Optional[str]


class UpdateCustomerDTO(TypedDict, total=False):
    """更新客户DTO"""
    name: str
    gender: Literal["male", "female"]
    birthday: str
    tags: List[str]


# ============================================
# 配置类型
# ============================================

class YiDingConfig(TypedDict):
    """易订适配器配置"""
    base_url: str                # API基础URL
    app_id: str                  # 应用ID
    app_secret: str              # 应用密钥
    timeout: Optional[int]       # 超时时间(秒)
    max_retries: Optional[int]   # 最大重试次数
    cache_ttl: Optional[int]     # 缓存过期时间(秒)
