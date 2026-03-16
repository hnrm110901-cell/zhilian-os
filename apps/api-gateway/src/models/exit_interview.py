"""
Exit Interview Model — 离职回访记录
结构化回访：原因→目前状况→是否愿意回来
"""

import uuid

from sqlalchemy import Boolean, Column, Date, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class ExitInterview(Base, TimestampMixin):
    """离职回访记录"""

    __tablename__ = "exit_interviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    employee_name = Column(String(100), nullable=True)

    resign_date = Column(Date, nullable=False)
    resign_reason = Column(String(50), nullable=False)  # personal/salary/development/management/relocation/other
    resign_detail = Column(Text, nullable=True)

    interview_date = Column(Date, nullable=True)
    current_status = Column(Text, nullable=True)  # 目前情况
    willing_to_return = Column(String(20), nullable=True)  # yes/no/maybe
    return_conditions = Column(Text, nullable=True)  # 回来的条件

    interviewer = Column(String(50), nullable=True)  # 回访人
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<ExitInterview(employee='{self.employee_id}', reason='{self.resign_reason}')>"
