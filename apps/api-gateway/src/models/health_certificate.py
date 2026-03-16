"""健康证管理模型 — 员工健康证录入/到期预警/合规追踪"""

import uuid

from sqlalchemy import Column, Date, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class HealthCertificate(Base, TimestampMixin):
    __tablename__ = "health_certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # 员工信息
    employee_id = Column(String(50), nullable=False, index=True)
    employee_name = Column(String(50), nullable=False)

    # 健康证基本信息
    certificate_number = Column(String(50), nullable=True)  # 健康证编号
    issue_date = Column(Date, nullable=False)  # 发证日期
    expiry_date = Column(Date, nullable=False, index=True)  # 到期日期
    issuing_authority = Column(String(100), nullable=True)  # 发证机构
    certificate_image_url = Column(String(500), nullable=True)  # 证件照片URL

    # 状态：valid / expiring_soon / expired / revoked
    status = Column(String(20), nullable=False, default="valid", index=True)

    # 体检信息
    physical_exam_date = Column(Date, nullable=True)  # 体检日期
    physical_exam_result = Column(String(20), nullable=True)  # passed / failed

    # 备注
    notes = Column(Text, nullable=True)
