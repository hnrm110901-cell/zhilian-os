"""
易订适配器类型定义

统一类型（UnifiedReservation等）已迁移到 base.src.types 行业公共字典。
本文件保留易订特有的配置类型，并re-export公共字典类型以保持向后兼容。
"""

import sys
import os

# 确保 base.src.types 可导入
_adapters_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _adapters_dir not in sys.path:
    sys.path.insert(0, _adapters_dir)

from typing import TypedDict, Optional, List, Dict, Any

# ============================================
# 从行业公共字典re-export（向后兼容）
# ============================================
from base.src.types import (                         # noqa: F401, E402
    ReservationStatus,
    ReservationType,
    TableType,
    TableStatus,
    MealPeriod,
    ChannelSource,
    Gender,
    CustomerLevel,
    UnifiedReservation,
    UnifiedCustomer,
    UnifiedTable,
    UnifiedBill,
    UnifiedDish,
    UnifiedDishMethod,
    UnifiedSetMeal,
    ReservationStats,
    CreateReservationRequest,
)


# ============================================
# 易订特有类型（不属于公共字典）
# ============================================

class CreateReservationDTO(TypedDict, total=False):
    """创建/更新预订DTO（对应2.4 线下预订订单更新）"""
    resv_order: str              # 易订订单号（新建时不传）
    resv_date: str               # 就餐日期
    table_code: str              # 桌位编码
    resv_num: int                # 人数
    vip_phone: str               # 手机号
    vip_name: str                # 姓名
    vip_sex: str                 # 性别
    meal_type_code: str          # 餐别编码
    meal_type_name: str          # 餐别名称
    status: int                  # 1预订 2入座 3结账 4退订 6换台
    order_type: int              # 1普通 2宴会
    remark: str                  # 备注
    app_user_code: str           # 操作员编码
    app_user_name: str           # 操作员姓名
    payamount: float             # 结账金额
    billPhone: str               # 结账手机号


# ============================================
# 易订特有配置（不属于公共字典）
# ============================================

class YiDingConfig(TypedDict, total=False):
    """易订适配器配置"""
    base_url: str                # API基础URL (https://open.zhidianfan.com/yidingopen)
    appid: str                   # 应用ID（账号）
    secret: str                  # 应用密钥（密码）
    hotel_id: str                # 门店ID（多店时可选）
    timeout: int                 # 超时时间(秒)，默认10
    max_retries: int             # 最大重试次数，默认3
    cache_ttl: int               # 缓存过期时间(秒)，默认300
