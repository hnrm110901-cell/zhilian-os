"""
大众点评评论模型
存储从大众点评/美团/Google等平台同步的用户评论数据
"""
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Numeric, String, Text,
    Index,
)
from sqlalchemy.dialects.postgresql import JSON, UUID

from src.models.base import Base, TimestampMixin


class DianpingReview(Base, TimestampMixin):
    """
    大众点评评论表
    存储来自多平台的用户评论，支持情感分析和商家回复
    """
    __tablename__ = "dianping_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # 点评原始ID（平台唯一）
    review_id = Column(String(100), unique=True, nullable=False)

    # 评论者信息
    author_name = Column(String(50), nullable=False)
    author_avatar_url = Column(String(500), nullable=True)

    # 评分与内容
    rating = Column(Integer, nullable=False)  # 1-5星
    content = Column(Text, nullable=False)
    images = Column(JSON, nullable=True)  # [url字符串列表]
    review_date = Column(DateTime, nullable=False)

    # AI情感分析
    sentiment = Column(String(20), nullable=True)  # positive/neutral/negative
    sentiment_score = Column(Numeric(5, 4), nullable=True)  # 0.0-1.0
    keywords = Column(JSON, nullable=True)  # 提取的关键词列表

    # 商家回复
    reply_content = Column(Text, nullable=True)
    reply_date = Column(DateTime, nullable=True)

    # 状态
    is_read = Column(Boolean, default=False, nullable=False)

    # 来源平台
    source = Column(String(20), default="dianping", nullable=False)  # dianping/meituan/google

    __table_args__ = (
        Index("idx_dianping_review_brand_store", "brand_id", "store_id"),
        Index("idx_dianping_review_rating", "rating"),
        Index("idx_dianping_review_sentiment", "sentiment"),
        Index("idx_dianping_review_is_read", "is_read"),
        Index("idx_dianping_review_review_date", "review_date"),
        Index("idx_dianping_review_source", "source"),
    )

    def __repr__(self):
        return (
            f"<DianpingReview(id={self.id}, review_id={self.review_id}, "
            f"rating={self.rating}, sentiment={self.sentiment})>"
        )
