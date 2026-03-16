"""
Price Benchmark Network — 匿名采购价格基准
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class PriceBenchmarkPool(Base, TimestampMixin):
    """匿名采购价格池 — 聚合输出需≥5个contributor"""

    __tablename__ = "price_benchmark_pool"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingredient_id = Column(String(50), nullable=False, index=True)
    category = Column(String(30), nullable=False)
    city = Column(String(50), nullable=False)
    unit = Column(String(10), nullable=False)
    unit_cost_fen = Column(Integer, nullable=False)
    quality_grade = Column(String(10), nullable=False, default="standard")
    purchase_month = Column(String(7), nullable=False)  # 2026-03
    contributor_hash = Column(String(64), nullable=False)  # SHA256 脱敏


class PriceBenchmarkReport(Base, TimestampMixin):
    """基准报告 — 按门店按月生成"""

    __tablename__ = "price_benchmark_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    report_month = Column(String(7), nullable=False)
    total_items = Column(Integer, nullable=False)
    cheap_count = Column(Integer, nullable=False)
    fair_count = Column(Integer, nullable=False)
    expensive_count = Column(Integer, nullable=False)
    very_expensive_count = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)  # 0-100
    total_saving_potential_yuan = Column(Numeric(12, 2))
    annual_saving_potential_yuan = Column(Numeric(12, 2))
    generated_at = Column(DateTime(timezone=True), nullable=False)
