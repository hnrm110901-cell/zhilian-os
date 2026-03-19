"""
屯象OS 行业公共字典 — 订单统一模型
"""

from typing import TypedDict, Optional, List, Dict, Any


class UnifiedOrderItem(TypedDict, total=False):
    """统一订单明细"""
    dish_id: str
    dish_name: str
    category: str
    quantity: float
    unit: str
    unit_price: float
    subtotal: float
    specification: str
    methods: List[Dict[str, Any]]
    remark: str


class UnifiedOrder(TypedDict, total=False):
    """统一订单格式"""
    id: str
    external_id: str
    source: str
    store_id: str
    brand_id: str

    order_number: str
    order_type: str
    order_status: str
    table_number: str
    customer_phone: str

    subtotal: float
    discount: float
    service_charge: float
    total: float
    paid: float

    items: List[UnifiedOrderItem]

    waiter_name: str
    cashier_name: str

    created_at: str
    paid_at: str
    completed_at: str
