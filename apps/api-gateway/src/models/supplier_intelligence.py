"""
供应商智能评分卡模型
SupplierScorecard — 跨系统供应商综合评分（B2B采购 + 食品安全溯源 + 价格趋势）
"""

import uuid

from sqlalchemy import Column, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from src.models.base import Base
from src.models.mixins import TimestampMixin


class SupplierScorecard(Base, TimestampMixin):
    """
    供应商评分卡（月度）。
    融合 B2BPurchaseOrder（交付）、FoodTraceRecord（质量）、
    SupplierProfile（主数据）三大数据源，按四维度打分。
    """

    __tablename__ = "supplier_scorecards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    supplier_id = Column(String(50), nullable=False, index=True)
    supplier_name = Column(String(100), nullable=False)

    # 评分周期，格式 "2026-03"
    score_period = Column(String(10), nullable=False)

    # 四维度评分（0-100）
    delivery_score = Column(Integer, nullable=False, default=0)  # 准时交付率
    quality_score = Column(Integer, nullable=False, default=0)  # 食安合格率 + 温控达标
    price_score = Column(Integer, nullable=False, default=0)  # 价格稳定性 + 竞争力
    service_score = Column(Integer, nullable=False, default=0)  # 响应速度 + 问题解决

    # 综合评分（加权平均）
    overall_score = Column(Integer, nullable=False, default=0)

    # 评级：A >= 85, B >= 70, C >= 50, D < 50
    tier = Column(String(10), nullable=False, default="D")

    # 统计摘要
    order_count = Column(Integer, nullable=False, default=0)
    total_amount_fen = Column(Integer, nullable=False, default=0)
    defect_count = Column(Integer, nullable=False, default=0)
    late_delivery_count = Column(Integer, nullable=False, default=0)

    # 价格趋势：up / stable / down
    price_trend = Column(String(10), nullable=False, default="stable")

    # AI 推荐动作列表，如 ["加强温控监管", "考虑替代供应商"]
    recommendations = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_scorecard_brand_period", "brand_id", "score_period"),
        Index("ix_scorecard_brand_supplier_period", "brand_id", "supplier_id", "score_period", unique=True),
        Index("ix_scorecard_tier", "brand_id", "tier"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "brand_id": self.brand_id,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "score_period": self.score_period,
            "delivery_score": self.delivery_score,
            "quality_score": self.quality_score,
            "price_score": self.price_score,
            "service_score": self.service_score,
            "overall_score": self.overall_score,
            "tier": self.tier,
            "order_count": self.order_count,
            "total_amount_fen": self.total_amount_fen,
            "total_amount_yuan": round(self.total_amount_fen / 100, 2),
            "defect_count": self.defect_count,
            "late_delivery_count": self.late_delivery_count,
            "price_trend": self.price_trend,
            "recommendations": self.recommendations or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
