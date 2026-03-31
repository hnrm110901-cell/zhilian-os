"""
BrandConsumerProfile — 品牌维度的会员消费档案
支持 One ID 跨品牌全景：同一个消费者在不同品牌下各有独立档案，
通过 consumer_id 关联到唯一 ConsumerIdentity 实现跨品牌整合。
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class BrandConsumerProfile(Base):
    """品牌维度消费档案

    每条记录代表：某消费者（consumer_id）在某品牌（brand_id）下的全量行为快照。
    UNIQUE(consumer_id, brand_id) 确保一消费者一品牌只有一条档案。
    跨品牌分析时，按 consumer_id + group_id 聚合各品牌档案。
    """

    __tablename__ = "brand_consumer_profiles"

    # ---------- 主键 ----------
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ---------- 关联维度 ----------
    # One ID 锚点：关联 consumer_identities 表
    consumer_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK -> consumer_identities.id，One ID 锚点",
    )

    # 品牌
    brand_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="FK -> brands.brand_id",
    )

    # 集团（冗余字段，避免跨表JOIN，提升跨品牌聚合性能）
    group_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="冗余 group_id，来自 brands.group_id",
    )

    # ---------- 品牌内会员身份 ----------
    brand_member_no = Column(
        String(100),
        nullable=True,
        comment="品牌内会员编号（如POS系统分配）",
    )

    # 会员等级：普通/银卡/金卡/钻石
    brand_level = Column(
        String(30),
        nullable=False,
        default="普通",
        comment="品牌会员等级：普通/银卡/金卡/钻石",
    )

    # ---------- 积分与余额（单位：分） ----------
    brand_points = Column(
        Integer,
        nullable=False,
        default=0,
        comment="品牌积分余额（整点）",
    )
    brand_balance_fen = Column(
        BigInteger,
        nullable=False,
        default=0,
        comment="品牌储值余额（分）",
    )

    # ---------- 消费统计 ----------
    brand_order_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="在该品牌的累计订单数",
    )
    brand_order_amount_fen = Column(
        BigInteger,
        nullable=False,
        default=0,
        comment="在该品牌的累计消费金额（分）",
    )
    brand_first_order_at = Column(
        DateTime,
        nullable=True,
        comment="首次在该品牌消费时间",
    )
    brand_last_order_at = Column(
        DateTime,
        nullable=True,
        comment="最近在该品牌消费时间",
    )

    # ---------- 生命周期 ----------
    # lead/registered/repeat/vip/at_risk/dormant/lost
    lifecycle_state = Column(
        String(30),
        nullable=False,
        default="registered",
        index=True,
        comment="生命周期状态：lead/registered/repeat/vip/at_risk/dormant/lost",
    )

    # ---------- 注册渠道 ----------
    registration_channel = Column(
        String(50),
        nullable=False,
        default="manual",
        comment="注册渠道：wechat_mp/pos/manual/meituan",
    )

    # ---------- 微信身份（品牌维度） ----------
    # 注意：品牌级 openid 与集团级 unionid 不同，需分开存储
    brand_wechat_openid = Column(
        String(100),
        nullable=True,
        comment="该品牌公众号/小程序的 OpenID",
    )
    brand_wechat_unionid = Column(
        String(100),
        nullable=True,
        comment="微信 UnionID（同集团各品牌共享）",
    )

    # ---------- 状态 ----------
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="档案是否有效（注销/黑名单时置 False）",
    )

    # ---------- 时间戳 ----------
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ---------- 约束 ----------
    __table_args__ = (
        # 核心唯一约束：一个消费者在一个品牌只有一条档案
        UniqueConstraint(
            "consumer_id",
            "brand_id",
            name="uq_brand_consumer_profile_consumer_brand",
        ),
        # 复合索引：跨品牌分析（One ID 视图）
        Index(
            "ix_bcp_consumer_group",
            "consumer_id",
            "group_id",
        ),
        # 复合索引：品牌级生命周期查询
        Index(
            "ix_bcp_brand_lifecycle",
            "brand_id",
            "lifecycle_state",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BrandConsumerProfile("
            f"consumer_id='{self.consumer_id}', "
            f"brand_id='{self.brand_id}', "
            f"level='{self.brand_level}', "
            f"state='{self.lifecycle_state}')>"
        )
