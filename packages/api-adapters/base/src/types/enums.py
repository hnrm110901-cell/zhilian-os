"""
屯象OS 行业公共字典 — 全局枚举

基于连锁餐饮行业通用语义定义，不跟随任何一家三方系统。
覆盖已知系统（易订/客必得/宴秘书/品智/奥琦玮/美团/饿了么等）的枚举全集。
"""

from enum import Enum


class ReservationStatus(str, Enum):
    """预订状态 — 行业统一状态机

    状态流转：
    PENDING → CONFIRMED → ARRIVED → SEATED → COMPLETED
                  ↓           ↓        ↓
              CANCELLED    NO_SHOW  TABLE_CHANGE
    """
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    SEATED = "seated"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    TABLE_CHANGE = "table_change"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderType(str, Enum):
    """订单类型"""
    DINE_IN = "dine_in"
    TAKEOUT = "takeout"
    DELIVERY = "delivery"
    PRE_ORDER = "pre_order"


class ReservationType(str, Enum):
    """预订类型"""
    REGULAR = "regular"
    BANQUET = "banquet"
    WEDDING = "wedding"
    BIRTHDAY = "birthday"
    CORPORATE = "corporate"
    APPRECIATION = "appreciation"
    CELEBRATION = "celebration"
    PRIVATE_ROOM = "private_room"
    GOVERNMENT = "government"
    CLASSMATE = "classmate"


class TableType(str, Enum):
    """桌位类型"""
    STANDARD_ROOM = "standard_room"
    DELUXE_ROOM = "deluxe_room"
    CONNECTED_ROOM = "connected_room"
    HALL_TABLE = "hall_table"
    BOOTH = "booth"
    BANQUET_HALL = "banquet_hall"
    MULTI_FUNCTION = "multi_function"
    SMALL_HALL = "small_hall"


class TableStatus(str, Enum):
    """桌位状态"""
    AVAILABLE = "available"
    RESERVED = "reserved"
    OCCUPIED = "occupied"
    CLEANING = "cleaning"
    DISABLED = "disabled"
    LOCKED = "locked"


class MealPeriod(str, Enum):
    """餐别"""
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    TEA = "tea"
    LATE_NIGHT = "late_night"


class PaymentMethod(str, Enum):
    """支付方式"""
    CASH = "cash"
    CARD = "card"
    WECHAT = "wechat"
    ALIPAY = "alipay"
    MEMBER_CARD = "member_card"
    POINTS = "points"
    CREDIT = "credit"
    DEPOSIT = "deposit"
    COUPON = "coupon"
    OTHER = "other"


class ChannelSource(str, Enum):
    """获客渠道"""
    PHONE = "phone"
    WALK_IN = "walk_in"
    MEITUAN = "meituan"
    DIANPING = "dianping"
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    WECHAT = "wechat"
    MINI_PROGRAM = "mini_program"
    REFERRAL = "referral"
    YIDING = "yiding"
    KEBIDE = "kebide"
    YANMISHU = "yanmishu"
    ELEME = "eleme"
    INTERNAL = "internal"
    OTHER = "other"


class Gender(str, Enum):
    """性别"""
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class CustomerLevel(str, Enum):
    """客户生命周期分层"""
    NEW = "new"
    ACTIVE = "active"
    LOYAL = "loyal"
    VIP = "vip"
    SLEEPING = "sleeping"
    LOST = "lost"
    POTENTIAL = "potential"


class DishCategory(str, Enum):
    """菜品大类"""
    HOT_DISH = "hot_dish"
    COLD_DISH = "cold_dish"
    SOUP = "soup"
    STAPLE = "staple"
    DESSERT = "dessert"
    BEVERAGE = "beverage"
    WINE = "wine"
    SNACK = "snack"
    SET_MEAL = "set_meal"
    OTHER = "other"
