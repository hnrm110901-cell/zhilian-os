"""
屯象OS 行业公共字典 — 供应商/采购统一模型
"""

from typing import TypedDict, Optional, List, Dict


class UnifiedSupplier(TypedDict, total=False):
    """统一供应商格式"""
    id: str
    external_id: str
    source: str

    name: str
    contact_name: str
    contact_phone: str
    categories: List[str]
    address: str
    is_active: bool


class UnifiedPurchaseOrder(TypedDict, total=False):
    """统一采购单格式"""
    id: str
    external_id: str
    source: str
    store_id: str
    supplier_id: str

    order_date: str
    expected_delivery: str
    total_amount: float
    status: str
    items: List[Dict]
    remark: str
