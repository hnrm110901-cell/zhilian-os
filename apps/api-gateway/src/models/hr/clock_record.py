"""ClockRecord — 打卡原始记录（来自企微/钉钉/手工）"""
import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class ClockRecord(Base):
    __tablename__ = "clock_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    clock_type = Column(String(20), nullable=False,
                        comment="in/out/break_start/break_end")
    clock_time = Column(TIMESTAMP(timezone=True), nullable=False)
    source = Column(String(30), nullable=False,
                    comment="wechat_work/dingtalk/manual/face_recognition")
    location = Column(JSONB, nullable=True, comment="{lat, lng, address}")
    is_anomaly = Column(Boolean, nullable=False, default=False, server_default="false",
                        comment="异常打卡标记")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<ClockRecord(id={self.id}, assignment_id={self.assignment_id}, "
                f"clock_type={self.clock_type!r})>")
