"""
Attendance Models — 考勤记录 + 班次模板 + 考勤规则
"""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID

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

    # ── W1-1 新增字段 ─────────────────────────────────────
    shift_template_id = Column(UUID(as_uuid=True), nullable=True)  # 关联班次模板
    scheduled_start = Column(DateTime(timezone=True), nullable=True)  # 排班开始
    scheduled_end = Column(DateTime(timezone=True), nullable=True)  # 排班结束
    early_leave_minutes = Column(Integer, nullable=True)
    gps_clock_in = Column(JSON, nullable=True)  # {"lat": x, "lng": y, "accuracy": z}
    gps_clock_out = Column(JSON, nullable=True)
    is_cross_day = Column(Boolean, default=False)  # 跨天打卡标记
    deduction_fen = Column(Integer, default=0)  # 本日扣款金额（分）
    deduction_reason = Column(String(200), nullable=True)  # 扣款原因


class ShiftTemplate(Base, TimestampMixin):
    """班次模板 — 品牌/门店级可配置"""

    __tablename__ = "shift_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True)  # NULL=品牌通用
    name = Column(String(50), nullable=False)  # 早班/中班/晚班/通宵班
    code = Column(String(20), nullable=False)  # morning/afternoon/evening/overnight
    start_time = Column(Time, nullable=False)  # 排班开始时间
    end_time = Column(Time, nullable=False)  # 排班结束时间
    is_cross_day = Column(Boolean, default=False)  # 是否跨天(夜班)
    break_minutes = Column(Integer, default=60)  # 休息时长
    min_work_hours = Column(Numeric(4, 1))  # 最少工作时长
    late_threshold_minutes = Column(Integer, default=5)  # 迟到容忍分钟
    early_leave_threshold_minutes = Column(Integer, default=5)  # 早退容忍
    applicable_positions = Column(JSON, default=list)  # 适用岗位
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    def __repr__(self):
        return f"<ShiftTemplate(name='{self.name}', code='{self.code}')>"


# AttendanceRule 已迁移到 models/hr/attendance_rule.py，此处 re-export 保持向后兼容
from .hr.attendance_rule import AttendanceRule  # noqa: F401
