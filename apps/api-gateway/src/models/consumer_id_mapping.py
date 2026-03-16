"""
CDP Consumer ID Mapping Model — Sprint 1 地基层

一个 ConsumerIdentity 可以拥有多个外部ID映射。
例如：同一个人在品智POS的会员ID、美团的UID、微信的OpenID 都映射到同一个 consumer_id。
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class IdType(str, enum.Enum):
    """11种外部ID类型"""

    PHONE = "phone"  # 手机号（主键级别）
    WECHAT_OPENID = "wechat_openid"  # 微信公众号/小程序 OpenID
    WECHAT_UNIONID = "wechat_unionid"  # 微信 UnionID（跨公众号）
    POS_MEMBER_ID = "pos_member_id"  # POS系统会员ID（品智/天财/奥琦玮）
    MEITUAN_UID = "meituan_uid"  # 美团用户ID
    DIANPING_UID = "dianping_uid"  # 大众点评用户ID
    DOUYIN_UID = "douyin_uid"  # 抖音用户ID
    XIAOHONGSHU_UID = "xiaohongshu_uid"  # 小红书用户ID
    LOYALTY_CARD = "loyalty_card"  # 实体会员卡号
    ENTERPRISE_WECHAT = "enterprise_wechat"  # 企业微信外部联系人ID
    CUSTOM = "custom"  # 自定义ID类型


class ConsumerIdMapping(Base, TimestampMixin):
    """
    外部ID → consumer_id 映射表

    每条记录代表一个外部系统中的ID与统一consumer_id的绑定关系。
    同一个 (id_type, external_id) 只能对应一个 consumer_id（唯一约束）。
    """

    __tablename__ = "consumer_id_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to ConsumerIdentity
    consumer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consumer_identities.id"),
        nullable=False,
        index=True,
    )

    # 外部ID标识
    id_type = Column(String(50), nullable=False, index=True)  # IdType enum value
    external_id = Column(String(200), nullable=False)  # 外部系统中的ID值

    # 来源门店（可选，有些ID跨门店）
    store_id = Column(String(50), nullable=True, index=True)

    # 来源系统标识（如 "pinzhi", "meituan", "wechat_mp"）
    source_system = Column(String(50), nullable=True)

    # 置信度（自动识别 vs 人工确认）
    confidence = Column(Integer, default=100)  # 0-100
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(50), nullable=True)

    # 映射是否活跃（取消绑定时置 False，不物理删除）
    is_active = Column(Boolean, default=True, index=True)
    deactivated_at = Column(DateTime, nullable=True)

    # Relationship
    consumer = relationship("ConsumerIdentity", back_populates="id_mappings")

    __table_args__ = (
        # 同一个外部ID只能映射到一个 consumer（活跃状态下）
        UniqueConstraint("id_type", "external_id", name="uq_id_type_external_id"),
        Index("idx_cim_type_ext", "id_type", "external_id"),
        Index("idx_cim_consumer_active", "consumer_id", "is_active"),
    )

    def __repr__(self):
        return f"<ConsumerIdMapping(consumer={self.consumer_id}, " f"type={self.id_type}, ext={self.external_id})>"
