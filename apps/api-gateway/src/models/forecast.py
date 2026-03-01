"""
FEAT-002: 预测性备料引擎 — 数据模型

ForecastResult 和 ForecastItem SQLAlchemy 模型（存库供模型评估）
"""
import uuid
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import Column, String, Float, Integer, JSON, DateTime, Date, Boolean
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class ForecastResult(Base):
    """
    预测结果存库模型

    记录每次预测的结果，用于后续模型评估（预测 vs 实际）。
    """
    __tablename__ = "forecast_results"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), index=True)
    target_date = Column(Date, nullable=False, index=True)
    metric = Column(String(50), nullable=False, default="revenue")   # revenue/orders/traffic
    predicted_value = Column(Float, nullable=False)
    confidence = Column(String(20), nullable=False)                   # low/medium/high
    basis = Column(String(50), nullable=False)                        # rule_based/statistical/ml
    estimated_revenue = Column(Float)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    items = Column(JSON, default=list)                                # List[ForecastItemData]

    # 事后评估字段（实际发生后回填）
    actual_value = Column(Float)
    accuracy_pct = Column(Float)   # |actual - predicted| / actual * 100
    evaluated_at = Column(DateTime)

    def __repr__(self):
        return (
            f"<ForecastResult(store={self.store_id}, date={self.target_date}, "
            f"confidence={self.confidence}, basis={self.basis})>"
        )
