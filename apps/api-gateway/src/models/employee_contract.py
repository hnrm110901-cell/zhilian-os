"""
Employee Contract Models — 合同管理
劳动合同、续签提醒、电子签章
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class ContractType(str, enum.Enum):
    FIXED_TERM = "fixed_term"  # 固定期限
    OPEN_ENDED = "open_ended"  # 无固定期限
    PART_TIME = "part_time"  # 兼职
    INTERNSHIP = "internship"  # 实习
    PROBATION = "probation"  # 试用


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRING = "expiring"  # 即将到期（30天内）
    EXPIRED = "expired"
    TERMINATED = "terminated"  # 提前终止
    RENEWED = "renewed"  # 已续签


class EmployeeContract(Base, TimestampMixin):
    """
    劳动合同记录。
    """

    __tablename__ = "employee_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    contract_type = Column(
        SAEnum(ContractType, name="contract_type_enum"),
        nullable=False,
        default=ContractType.FIXED_TERM,
    )
    status = Column(
        SAEnum(ContractStatus, name="contract_status_enum"),
        nullable=False,
        default=ContractStatus.DRAFT,
        index=True,
    )

    # 合同期限
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # 无固定期限时为 NULL
    sign_date = Column(Date, nullable=True)

    # 试用期
    probation_end_date = Column(Date, nullable=True)
    probation_salary_pct = Column(Integer, default=80)  # 试用期薪资比例

    # 合同编号
    contract_no = Column(String(50), nullable=True, unique=True)

    # 薪资约定（分）
    agreed_salary_fen = Column(Integer, nullable=True)
    salary_type = Column(String(20), default="monthly")

    # 岗位
    position = Column(String(50), nullable=True)
    department = Column(String(50), nullable=True)
    work_location = Column(String(100), nullable=True)

    # 续签
    renewal_count = Column(Integer, default=0)  # 续签次数
    previous_contract_id = Column(UUID(as_uuid=True), nullable=True)
    renewal_reminder_sent = Column(Boolean, default=False)

    # 电子签章
    esign_status = Column(String(20), nullable=True)  # pending/signed/rejected
    esign_url = Column(String(500), nullable=True)  # 电子签章链接
    signed_pdf_url = Column(String(500), nullable=True)  # 已签合同PDF

    # 终止原因
    termination_date = Column(Date, nullable=True)
    termination_reason = Column(Text, nullable=True)

    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<EmployeeContract(employee='{self.employee_id}', " f"type='{self.contract_type}', status='{self.status}')>"
