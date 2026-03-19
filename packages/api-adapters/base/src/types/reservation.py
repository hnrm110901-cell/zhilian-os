"""
屯象OS 行业公共字典 — 预订统一模型
"""

from typing import TypedDict, Optional, Dict, List, Any


class UnifiedReservation(TypedDict, total=False):
    """统一预订格式 — 所有预订系统映射到此结构"""
    # ── 标识 ──
    id: str
    external_id: str
    source: str
    store_id: str
    store_name: str

    # ── 客户 ──
    customer_name: str
    customer_phone: str
    gender: str
    company: str

    # ── 预订信息 ──
    reservation_date: str
    reservation_time: str
    party_size: int
    reservation_type: str
    meal_period: str
    meal_period_name: str

    # ── 桌位 ──
    table_ids: List[str]
    table_area_name: str
    table_name: str
    table_area_code: str
    table_code: str

    # ── 状态 ──
    status: str
    raw_status: Any

    # ── 金额 ──
    has_deposit: bool
    deposit_amount: float
    meal_standard: str
    pay_amount: float
    pay_detail: Dict[str, float]

    # ── 点菜 ──
    has_pre_order: bool
    pre_order_dishes: List[Dict[str, Any]]

    # ── 人员 ──
    sales_name: str
    sales_code: str
    operator_name: str

    # ── 渠道 ──
    source_channel: str
    source_channel_name: str

    # ── 备注 ──
    remark: str

    # ── 时间戳 ──
    created_at: str
    updated_at: str
    arrived_at: str
    seated_at: str
    completed_at: str
    cancelled_at: str


class ReservationStats(TypedDict, total=False):
    """预订统计"""
    store_id: str
    period_start: str
    period_end: str
    total_reservations: int
    total_party_size: int
    average_party_size: float
    total_deposit: float
    total_pay_amount: float
    status_breakdown: Dict[str, int]
    channel_breakdown: Dict[str, int]
    type_breakdown: Dict[str, int]


class CreateReservationRequest(TypedDict, total=False):
    """创建/更新预订的请求DTO"""
    reservation_date: str
    reservation_time: str
    party_size: int
    customer_name: str
    customer_phone: str
    gender: str
    company: str
    table_ids: List[str]
    reservation_type: str
    meal_period: str
    deposit_amount: float
    meal_standard: str
    remark: str
    sales_name: str
    operator_name: str
