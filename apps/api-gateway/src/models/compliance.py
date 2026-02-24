"""
合规证照模型
Compliance License Model

管理餐饮门店的各类证照到期日，确保无任何证照静默过期。

证照类型：
- 食品经营许可证（年检）
- 健康证（员工，每年）
- 营业执照（年检）
- 消防验收合格证
- 排污许可证
"""
import enum
from datetime import datetime
from sqlalchemy import Column, String, Date, DateTime, Text, Enum as SQLEnum, ForeignKey, Integer
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class LicenseType(str, enum.Enum):
    """证照类型"""
    FOOD_OPERATION = "food_operation"        # 食品经营许可证
    HEALTH_CERT = "health_cert"              # 健康证（员工）
    BUSINESS_LICENSE = "business_license"   # 营业执照
    FIRE_SAFETY = "fire_safety"             # 消防验收合格证
    SEWAGE_PERMIT = "sewage_permit"         # 排污许可证
    OTHER = "other"                          # 其他


class LicenseStatus(str, enum.Enum):
    """证照状态"""
    VALID = "valid"           # 有效
    EXPIRE_SOON = "expire_soon"  # 即将到期（30天内）
    EXPIRED = "expired"       # 已过期
    UNKNOWN = "unknown"       # 未录入/未知


class ComplianceLicense(Base, TimestampMixin):
    """合规证照表"""
    __tablename__ = "compliance_licenses"

    id = Column(String(36), primary_key=True)

    # 关联门店
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    store = relationship("Store", backref="compliance_licenses")

    # 证照信息
    license_type = Column(SQLEnum(LicenseType), nullable=False, index=True, comment="证照类型")
    license_name = Column(String(100), nullable=False, comment="证照名称（显示用）")
    license_number = Column(String(100), comment="证照编号")

    # 持有人（健康证场景）
    holder_name = Column(String(50), comment="持证人姓名（健康证填员工姓名）")
    holder_employee_id = Column(String(36), ForeignKey("employees.id"), nullable=True, comment="持证员工ID")

    # 有效期
    issue_date = Column(Date, comment="发证日期")
    expiry_date = Column(Date, nullable=False, index=True, comment="到期日期")

    # 状态（由系统自动计算，冗余存储用于查询性能）
    status = Column(SQLEnum(LicenseStatus), default=LicenseStatus.VALID, index=True, comment="当前状态")

    # 提醒配置
    remind_days_before = Column(
        Integer,
        default=30,
        comment="提前多少天提醒（默认30天）"
    )
    last_reminded_at = Column(DateTime, comment="最近一次提醒时间")

    # 备注
    notes = Column(Text, comment="备注")

    def __repr__(self):
        return f"<ComplianceLicense(id={self.id}, type={self.license_type}, expiry={self.expiry_date})>"

    def to_dict(self):
        return {
            "id": self.id,
            "store_id": self.store_id,
            "license_type": self.license_type,
            "license_name": self.license_name,
            "license_number": self.license_number,
            "holder_name": self.holder_name,
            "holder_employee_id": self.holder_employee_id,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "status": self.status,
            "remind_days_before": self.remind_days_before,
            "last_reminded_at": self.last_reminded_at.isoformat() if self.last_reminded_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
