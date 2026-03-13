"""
演职人员调度模型 — Phase P3 (宴小猪能力)
司仪/摄影/摄像/花艺/灯光/DJ 等外部人员的调度与确认
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID

from src.models.base import Base, TimestampMixin


class StaffRole(str, enum.Enum):
    MC = "mc"                    # 司仪
    PHOTOGRAPHER = "photographer"  # 摄影师
    VIDEOGRAPHER = "videographer"  # 摄像师
    FLORIST = "florist"          # 花艺师
    LIGHTING = "lighting"        # 灯光师
    DJ = "dj"                    # DJ
    OTHER = "other"              # 其他


class StaffConfirmStatus(str, enum.Enum):
    PENDING = "pending"          # 待确认
    CONFIRMED = "confirmed"      # 已确认
    DECLINED = "declined"        # 已拒绝
    CANCELLED = "cancelled"      # 已取消


class EventStaff(Base, TimestampMixin):
    """宴会演职人员调度记录"""

    __tablename__ = "event_staff"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    event_order_id = Column(String(100), nullable=False, index=True, comment="关联 BEO ID")
    event_date = Column(DateTime, nullable=True, comment="宴会日期")

    # 人员信息
    role = Column(String(20), nullable=False, comment="角色：mc/photographer/videographer/florist/lighting/dj/other")
    staff_name = Column(String(100), nullable=False)
    staff_phone = Column(String(20), nullable=True)
    company = Column(String(200), nullable=True, comment="所属公司/工作室")

    # 费用
    fee_fen = Column(Integer, nullable=False, default=0, comment="费用（分）")

    # 确认状态
    confirm_status = Column(
        String(20), nullable=False,
        default=StaffConfirmStatus.PENDING.value,
        comment="确认状态",
    )
    confirmed_at = Column(DateTime, nullable=True)

    # 备注
    notes = Column(Text, nullable=True)
