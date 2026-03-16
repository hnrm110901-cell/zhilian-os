"""
Attendance Log — 考勤记录
"""

import uuid

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class AttendanceLog(Base, TimestampMixin):
    """考勤记录"""

    __tablename__ = "attendance_logs"
    __table_args__ = (UniqueConstraint("store_id", "employee_id", "work_date"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    work_date = Column(Date, nullable=False)
    clock_in = Column(DateTime(timezone=True), nullable=False)
    clock_out = Column(DateTime(timezone=True))
    break_minutes = Column(Integer)
    actual_hours = Column(Numeric(5, 2))
    overtime_hours = Column(Numeric(5, 2))
    status = Column(String(20), nullable=False)  # normal/late/early_leave/absent/leave
    late_minutes = Column(Integer)
    leave_type = Column(String(20))  # annual/sick/personal/maternity
    source = Column(String(20))  # fingerprint/face/wechat/manual
