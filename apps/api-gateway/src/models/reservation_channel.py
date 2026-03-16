"""
预订渠道追踪模型 — Phase P1 (易订PRO能力)
追踪每个预订的来源渠道，支持全渠道统计分析
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class ChannelType(str, enum.Enum):
    """预订渠道类型"""

    MEITUAN = "meituan"  # 美团
    DIANPING = "dianping"  # 大众点评
    DOUYIN = "douyin"  # 抖音
    XIAOHONGSHU = "xiaohongshu"  # 小红书
    WECHAT = "wechat"  # 微信/企微
    PHONE = "phone"  # 电话
    WALK_IN = "walk_in"  # 到店
    REFERRAL = "referral"  # 老客推荐
    YIDING = "yiding"  # 易订
    MINI_PROGRAM = "mini_program"  # 小程序
    OTHER = "other"


class ReservationChannel(Base, TimestampMixin):
    """预订渠道记录"""

    __tablename__ = "reservation_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reservation_id = Column(String(50), ForeignKey("reservations.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 渠道信息
    channel = Column(Enum(ChannelType), nullable=False, index=True)
    external_order_id = Column(String(100), nullable=True)  # 外部平台订单号
    channel_commission_rate = Column(Numeric(5, 4), nullable=True)  # 佣金比例 0.0000~1.0000
    channel_commission_amount = Column(Numeric(10, 2), nullable=True)  # 佣金金额(元)

    # 营销追踪
    source_url = Column(String(500), nullable=True)
    utm_source = Column(String(100), nullable=True)
    utm_medium = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)

    # 转化追踪
    first_touch_at = Column(DateTime, nullable=True)  # 首次接触时间
    converted_at = Column(DateTime, nullable=True)  # 转化时间

    __table_args__ = (
        Index("idx_channel_store_date", "store_id", "created_at"),
        Index("idx_channel_type_store", "channel", "store_id"),
    )
