"""
竞争分析数据模型
存储竞品门店信息和价格记录，支持市场份额分析和竞品对比
"""
import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Text, JSON, ForeignKey, Integer, Numeric, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class CompetitorStore(Base, TimestampMixin):
    """
    竞品门店
    记录竞争对手的基本信息，关联到我方门店
    """

    __tablename__ = "competitor_stores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联我方门店
    our_store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 竞品信息
    name = Column(String(100), nullable=False)           # 竞品名称
    brand = Column(String(100), nullable=True)           # 品牌
    cuisine_type = Column(String(50), nullable=True)     # 菜系类型
    address = Column(String(200), nullable=True)         # 地址
    distance_meters = Column(Integer, nullable=True)     # 距离（米）
    avg_price_per_person = Column(Numeric(10, 2), nullable=True)  # 人均消费
    rating = Column(Numeric(3, 1), nullable=True)        # 评分（0-5）
    monthly_customers = Column(Integer, nullable=True)   # 月均客流量（估算）
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    # 关系
    our_store = relationship("Store")
    price_records = relationship("CompetitorPrice", back_populates="competitor", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_competitor_our_store", "our_store_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "our_store_id": self.our_store_id,
            "name": self.name,
            "brand": self.brand,
            "cuisine_type": self.cuisine_type,
            "address": self.address,
            "distance_meters": self.distance_meters,
            "avg_price_per_person": float(self.avg_price_per_person) if self.avg_price_per_person else None,
            "rating": float(self.rating) if self.rating else None,
            "monthly_customers": self.monthly_customers,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CompetitorPrice(Base, TimestampMixin):
    """
    竞品价格记录
    记录竞品的菜品价格，用于价格对比和敏感度分析
    """

    __tablename__ = "competitor_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitor_stores.id"), nullable=False, index=True)

    # 菜品信息
    dish_name = Column(String(100), nullable=False)      # 菜品名称
    category = Column(String(50), nullable=True)         # 分类
    price = Column(Numeric(10, 2), nullable=False)       # 价格
    record_date = Column(Date, nullable=False)           # 记录日期

    # 对应我方菜品（可选，用于直接对比）
    our_dish_id = Column(UUID(as_uuid=True), ForeignKey("dishes.id"), nullable=True)

    # 关系
    competitor = relationship("CompetitorStore", back_populates="price_records")

    __table_args__ = (
        Index("idx_competitor_price_competitor", "competitor_id"),
        Index("idx_competitor_price_date", "record_date"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "competitor_id": str(self.competitor_id),
            "dish_name": self.dish_name,
            "category": self.category,
            "price": float(self.price) if self.price else None,
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "our_dish_id": str(self.our_dish_id) if self.our_dish_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
