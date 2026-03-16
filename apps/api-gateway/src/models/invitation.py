"""
AI邀请函模型
支持5套主题模板 + AI文案生成 + RSVP回执
"""

import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class InvitationTemplate(str, enum.Enum):
    """邀请函主题模板"""

    WEDDING_RED = "wedding_red"  # 婚宴红金
    BIRTHDAY_GOLD = "birthday_gold"  # 寿宴暖金
    CORPORATE_BLUE = "corporate_blue"  # 商务深蓝
    FULL_MOON_PINK = "full_moon_pink"  # 满月粉色
    GRADUATION_GREEN = "graduation_green"  # 升学翠绿


class RSVPStatus(str, enum.Enum):
    """回执状态"""

    ATTENDING = "attending"
    DECLINED = "declined"
    PENDING = "pending"


class Invitation(Base, TimestampMixin):
    """邀请函"""

    __tablename__ = "invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 宴请主人
    host_name = Column(String(100), nullable=False)
    host_phone = Column(String(20), nullable=False)

    # 宴请信息
    event_type = Column(String(50), nullable=False)  # 商务宴请/生日宴/婚宴/...
    event_title = Column(String(200), nullable=False)
    event_date = Column(DateTime, nullable=False)
    venue_name = Column(String(200), nullable=False)
    venue_address = Column(String(500))
    venue_lat = Column(Float, nullable=True)
    venue_lng = Column(Float, nullable=True)

    # 模板与文案
    template = Column(Enum(InvitationTemplate), default=InvitationTemplate.CORPORATE_BLUE)
    custom_message = Column(Text, default="")
    ai_generated_message = Column(Text, default="")
    cover_image_url = Column(String(500), default="")

    # AI生成参数
    ai_params = Column(JSON, default=dict)  # genre, mood, emotion, guest_name, age_range, etc.

    # 分享
    share_token = Column(String(32), unique=True, nullable=False, index=True)
    view_count = Column(Integer, default=0)
    rsvp_count = Column(Integer, default=0)
    is_published = Column(Boolean, default=False)

    def __repr__(self):
        return f"<Invitation(id={self.id}, event='{self.event_title}')>"


class InvitationRSVP(Base, TimestampMixin):
    """邀请函RSVP回执"""

    __tablename__ = "invitation_rsvps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invitation_id = Column(UUID(as_uuid=True), ForeignKey("invitations.id"), nullable=False, index=True)

    guest_name = Column(String(100), nullable=False)
    guest_phone = Column(String(20))
    party_size = Column(Integer, default=1)
    dietary_restrictions = Column(String(255))
    message = Column(Text, default="")  # 祝福语
    status = Column(Enum(RSVPStatus), default=RSVPStatus.ATTENDING)
