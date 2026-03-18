"""DailyAttendance — 日考勤计算结果"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Date, Integer, Boolean, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class DailyAttendance(Base):
    __tablename__ = "daily_attendances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="normal",
                    server_default="'normal'",
                    comment="normal/late/early_leave/absent/leave/holiday/overtime")
    work_minutes = Column(Integer, nullable=False, default=0, server_default="0",
                          comment="实际工作分钟")
    overtime_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    late_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    early_leave_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    calculated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                           nullable=False)
    locked = Column(Boolean, nullable=False, default=False, server_default="false",
                    comment="月结后锁定")
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (f"<DailyAttendance(id={self.id}, assignment_id={self.assignment_id}, "
                f"date={self.date}, status={self.status!r})>")
