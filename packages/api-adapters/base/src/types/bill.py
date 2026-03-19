"""
屯象OS 行业公共字典 — 账单/支付统一模型
"""

from typing import TypedDict, Optional, List, Dict


class UnifiedBill(TypedDict, total=False):
    """统一账单格式"""
    id: str
    external_id: str
    source: str
    store_id: str
    order_id: str

    total_amount: float
    paid_amount: float
    discount_amount: float
    service_charge: float
    deposit_amount: float
    credit_amount: float
    points_amount: float
    other_amount: float
    net_income: float

    payment_method: str
    payment_methods: List[Dict[str, float]]

    party_size: int
    table_count: int
    table_code: str
    area_code: str
    meal_period: str

    bill_date: str
    trade_time: str

    items: List[Dict]
