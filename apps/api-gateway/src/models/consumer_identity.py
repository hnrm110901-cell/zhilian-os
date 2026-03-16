"""
CDP Consumer Identity Model — Sprint 1 地基层

CDP宪法：
1. 任何消费者记录必须经 IdentityResolutionService.resolve() 获取 consumer_id
2. consumer_id 不可修改，只能 merge()
3. 所有渠道消费行为必须归因到 consumer_id
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class ConsumerIdentity(Base, TimestampMixin):
    """
    统一消费者身份 — CDP 地基表

    每个自然人对应一条记录。primary_phone 为业务键（中国餐饮场景手机号最可靠）。
    consumer_id（UUID）是全系统唯一标识，不可修改，仅在 merge 时标记 merged_into。
    """

    __tablename__ = "consumer_identities"

    # 全局唯一ID — 不可修改，只能 merge
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 业务键：手机号（中国大陆11位）
    primary_phone = Column(String(20), nullable=False, unique=True, index=True)

    # 聚合 profile
    display_name = Column(String(100), nullable=True)
    gender = Column(String(10), nullable=True)  # male/female/unknown
    birth_date = Column(Date, nullable=True)

    # 微信体系
    wechat_openid = Column(String(128), nullable=True, index=True)
    wechat_unionid = Column(String(128), nullable=True, index=True)
    wechat_nickname = Column(String(100), nullable=True)
    wechat_avatar_url = Column(String(500), nullable=True)

    # 聚合统计（定期由 backfill 刷新）
    total_order_count = Column(Integer, default=0)
    total_order_amount_fen = Column(Integer, default=0)  # 分
    total_reservation_count = Column(Integer, default=0)
    first_order_at = Column(DateTime, nullable=True)
    last_order_at = Column(DateTime, nullable=True)
    first_store_id = Column(String(50), nullable=True)  # 首次消费门店

    # RFM 快照（由 IdentityResolutionService.refresh_profile 更新）
    rfm_recency_days = Column(Integer, nullable=True)
    rfm_frequency = Column(Integer, nullable=True)
    rfm_monetary_fen = Column(Integer, nullable=True)

    # 标签（JSON数组，如 ["高频","家庭聚餐","宴会客户"]）
    tags = Column(JSON, default=list)

    # merge 支持 — 被合并的记录标记 merged_into，不物理删除
    is_merged = Column(Boolean, default=False, index=True)
    merged_into = Column(UUID(as_uuid=True), nullable=True, index=True)
    merged_at = Column(DateTime, nullable=True)

    # 数据来源追踪
    source = Column(String(50), nullable=True)  # pos/wechat/manual/meituan
    confidence_score = Column(Float, default=1.0)  # 身份置信度 0-1

    # 扩展元数据
    extra = Column(JSON, default=dict)

    # Relationships
    id_mappings = relationship(
        "ConsumerIdMapping",
        back_populates="consumer",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_ci_phone_active", "primary_phone", "is_merged"),
        Index("idx_ci_wechat_unionid", "wechat_unionid"),
        Index("idx_ci_last_order", "last_order_at"),
    )

    def __repr__(self):
        return f"<ConsumerIdentity(id={self.id}, phone={self.primary_phone})>"
