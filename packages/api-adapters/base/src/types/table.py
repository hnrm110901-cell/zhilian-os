"""
屯象OS 行业公共字典 — 桌位统一模型
"""

from typing import TypedDict, Optional


class UnifiedTable(TypedDict, total=False):
    """统一桌位格式"""
    id: str
    external_id: str
    erp_desk_id: str
    source: str
    store_id: str

    name: str
    area_code: str
    area_name: str
    table_type: str
    capacity: int
    min_capacity: int
    sort_order: int

    status: str
    is_updated: bool
