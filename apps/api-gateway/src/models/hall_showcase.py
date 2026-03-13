"""
宴会厅实景展示模型 — Phase P3 (宴小猪能力)
面向客户的厅位展示：照片、VR、参数、价格
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, Column, Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.models.base import Base, TimestampMixin


class HallShowcase(Base, TimestampMixin):
    """宴会厅线上展示（面向客户展示精美版）"""

    __tablename__ = "hall_showcases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    hall_id = Column(String(100), nullable=True, comment="关联 BanquetHall ID（可选）")

    # 基本信息
    hall_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # 容量参数
    capacity_min = Column(Integer, nullable=True, comment="最少容纳人数")
    capacity_max = Column(Integer, nullable=True, comment="最多容纳人数")
    table_count_max = Column(Integer, nullable=True, comment="最大桌数")
    area_sqm = Column(Numeric(8, 2), nullable=True, comment="面积（m²）")
    ceiling_height = Column(Numeric(4, 2), nullable=True, comment="层高（m）")

    # 设施
    has_led_screen = Column(Boolean, default=False)
    has_stage = Column(Boolean, default=False)
    has_natural_light = Column(Boolean, default=False)
    has_independent_entrance = Column(Boolean, default=False)

    # 展示素材
    images = Column(JSONB, default=list, comment="实景照片 URL 列表")
    virtual_tour_url = Column(String(500), nullable=True, comment="VR 全景链接")

    # 价格
    price_range = Column(String(100), nullable=True, comment="价格范围，如 ¥2888-¥5888/桌")
    min_price_fen = Column(Integer, nullable=True, comment="最低桌价（分）")
    max_price_fen = Column(Integer, nullable=True, comment="最高桌价（分）")

    # 标签与亮点
    features = Column(JSONB, default=list, comment='亮点标签，如 ["宽敞", "有舞台", "含LED"]')

    # 排序与展示控制
    sort_order = Column(Integer, default=0, comment="排序权重")
    is_active = Column(Boolean, default=True, comment="是否展示")
