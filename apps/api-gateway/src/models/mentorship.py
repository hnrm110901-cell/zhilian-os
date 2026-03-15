"""
Mentorship Model — 核心岗位师徒培养
师傅+徒弟+培养周期+验收+奖励
"""
import uuid
from sqlalchemy import Column, String, Integer, Date, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class Mentorship(Base, TimestampMixin):
    """核心岗位师徒培养"""

    __tablename__ = "mentorships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), nullable=False, index=True)

    target_position = Column(String(50), nullable=False)  # 培养岗位
    mentor_id = Column(String(50), nullable=False, index=True)  # 师傅
    mentor_name = Column(String(50), nullable=True)
    apprentice_id = Column(String(50), nullable=False, index=True)  # 徒弟
    apprentice_name = Column(String(50), nullable=True)

    enrolled_at = Column(Date, nullable=False)  # 报名时间
    training_start = Column(Date, nullable=True)
    training_end = Column(Date, nullable=True)  # 培养周期截止
    expected_review_date = Column(Date, nullable=True)  # 规定验收时间
    actual_review_date = Column(Date, nullable=True)
    review_result = Column(String(20), nullable=True)  # passed/failed/pending
    reward_fen = Column(Integer, default=0)  # 奖励金额（分）
    status = Column(String(20), default="active")  # active/completed/cancelled
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Mentorship(mentor='{self.mentor_name}', apprentice='{self.apprentice_name}')>"
