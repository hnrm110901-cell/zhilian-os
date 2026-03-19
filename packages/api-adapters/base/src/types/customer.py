"""
屯象OS 行业公共字典 — 客户/会员统一模型
"""

from typing import TypedDict, Optional, List


class UnifiedCustomer(TypedDict, total=False):
    """统一客户/会员格式"""
    # ── 标识 ──
    id: str
    consumer_id: str
    external_id: str
    source: str

    # ── 基础信息 ──
    phone: str
    name: str
    gender: str
    birthday: str
    company: str
    address: str
    short_phone: str

    # ── 消费画像 ──
    total_amount: float
    total_visits: int
    per_capita: float
    last_visit_date: str

    # ── 分层 ──
    customer_level: str
    sub_level: str
    member_card_no: str
    points: int
    balance: float

    # ── 偏好/忌口 ──
    preference: str
    allergy: str
    tags: List[str]
    remark: str

    # ── 营销归属 ──
    manager_name: str
    manager_phone: str

    # ── 时间 ──
    created_at: str
    updated_at: str
