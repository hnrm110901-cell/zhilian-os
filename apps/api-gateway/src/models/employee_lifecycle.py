"""
Employee Lifecycle — 员工生命周期
入职、转正、调岗、离职等变动记录
"""

import enum
import uuid

from sqlalchemy import Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class ChangeType(str, enum.Enum):
    """变动类型"""

    TRIAL = "trial"  # 试岗
    ONBOARD = "onboard"  # 正式入职
    PROBATION_PASS = "probation"  # 转正
    TRANSFER = "transfer"  # 调岗/调店
    PROMOTION = "promotion"  # 晋升
    DEMOTION = "demotion"  # 降级
    SALARY_ADJUST = "salary_adj"  # 薪资调整
    RESIGN = "resign"  # 主动离职
    DISMISS = "dismiss"  # 辞退
    RETIRE = "retire"  # 退休


class EmployeeChange(Base, TimestampMixin):
    """
    员工变动记录：每次入/离/转/调/升/降创建一条。
    构成员工完整的职业时间线。
    """

    __tablename__ = "employee_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    change_type = Column(
        SAEnum(ChangeType, name="employee_change_type_enum"),
        nullable=False,
        index=True,
    )
    effective_date = Column(Date, nullable=False)

    # 变动前后
    from_position = Column(String(50), nullable=True)
    to_position = Column(String(50), nullable=True)
    from_store_id = Column(String(50), nullable=True)
    to_store_id = Column(String(50), nullable=True)
    from_salary_fen = Column(Integer, nullable=True)
    to_salary_fen = Column(Integer, nullable=True)

    # 离职特有
    resign_reason = Column(Text, nullable=True)
    last_work_date = Column(Date, nullable=True)
    handover_to = Column(String(50), nullable=True)  # 交接人员工ID
    handover_completed = Column(String(10), default="no")  # yes/no/partial

    # 审批
    approval_instance_id = Column(UUID(as_uuid=True), nullable=True)
    approved_by = Column(String(100), nullable=True)

    remark = Column(Text, nullable=True)
    attachments = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<EmployeeChange(employee='{self.employee_id}', " f"type='{self.change_type}', date='{self.effective_date}')>"
