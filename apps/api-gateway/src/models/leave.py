"""
Leave & Overtime Models — 假勤管理
请假类型、假期余额、请假单、加班单
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin

# ── Enums ──────────────────────────────────────────────────


class LeaveCategory(str, enum.Enum):
    """假期类别"""

    ANNUAL = "annual"  # 年假
    SICK = "sick"  # 病假
    PERSONAL = "personal"  # 事假
    MATERNITY = "maternity"  # 产假
    PATERNITY = "paternity"  # 陪产假
    MARRIAGE = "marriage"  # 婚假
    BEREAVEMENT = "bereavement"  # 丧假
    COMPENSATORY = "compensatory"  # 调休
    OTHER = "other"  # 其他


class LeaveRequestStatus(str, enum.Enum):
    """请假单状态"""

    DRAFT = "draft"
    PENDING = "pending"  # 审批中
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OvertimeType(str, enum.Enum):
    """加班类型"""

    WEEKDAY = "weekday"  # 工作日加班
    WEEKEND = "weekend"  # 周末加班
    HOLIDAY = "holiday"  # 节假日加班


class OvertimeRequestStatus(str, enum.Enum):
    """加班单状态"""

    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ── 1. 假期类型配置 ────────────────────────────────────────


class LeaveTypeConfig(Base, TimestampMixin):
    """
    假期类型配置：定义每种假期的规则。
    可按门店/品牌覆盖全局默认。
    """

    __tablename__ = "leave_type_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=True, index=True)  # NULL = 全局配置
    brand_id = Column(String(50), nullable=True, index=True)

    category = Column(
        SAEnum(LeaveCategory, name="leave_category_enum"),
        nullable=False,
    )
    name = Column(String(50), nullable=False)  # 显示名称
    is_paid = Column(Boolean, default=True)  # 是否带薪
    max_days_per_year = Column(Numeric(5, 1), nullable=True)  # 年度上限
    min_unit_hours = Column(Numeric(4, 1), default=4)  # 最小请假单位（小时）
    need_approval = Column(Boolean, default=True)
    need_certificate = Column(Boolean, default=False)  # 是否需要证明
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<LeaveTypeConfig(category='{self.category}', name='{self.name}')>"


# ── 2. 假期余额 ────────────────────────────────────────────


# LeaveBalance 已迁移到 models/hr/leave_balance.py，此处 re-export 保持向后兼容
from .hr.leave_balance import LeaveBalance  # noqa: F401


# ── 3. 请假单 ──────────────────────────────────────────────


# LeaveRequest 已迁移到 models/hr/leave_request.py，此处 re-export 保持向后兼容
from .hr.leave_request import LeaveRequest  # noqa: F401


# ── 4. 加班单 ──────────────────────────────────────────────


class OvertimeRequest(Base, TimestampMixin):
    """加班申请单"""

    __tablename__ = "overtime_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    overtime_type = Column(
        SAEnum(OvertimeType, name="overtime_type_enum"),
        nullable=False,
    )
    status = Column(
        SAEnum(OvertimeRequestStatus, name="overtime_request_status_enum"),
        nullable=False,
        default=OvertimeRequestStatus.DRAFT,
        index=True,
    )

    work_date = Column(Date, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    hours = Column(Numeric(5, 1), nullable=False)

    # 加班费倍率（工作日1.5x，周末2x，节假日3x）
    pay_rate = Column(Numeric(3, 1), nullable=False, default=1.5)

    reason = Column(Text, nullable=False)
    compensatory = Column(Boolean, default=False)  # 是否转调休

    # 审批关联
    approval_instance_id = Column(UUID(as_uuid=True), nullable=True)

    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return (
            f"<OvertimeRequest(employee='{self.employee_id}', "
            f"date={self.work_date}, hours={self.hours}, "
            f"status='{self.status}')>"
        )
