"""
PersonContract — 合同（绑定 Assignment 的劳动/劳务合同）

每个 Assignment 可有多份合同（续签历史）。
合同包含薪酬方案(pay_scheme)和考勤规则(attendance_rule_id)。

与旧 EmployeeContract 的区别：
- 旧: employee_id → employees
- 新: assignment_id → assignments
- 新增: pay_scheme JSON（结构化薪酬方案）
- 新增: attendance_rule_id（关联考勤规则）

两表共存至 M4 阶段。
"""
import uuid
import enum
from sqlalchemy import Column, String, Date, DateTime, Integer, Boolean, Text, Float, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class ContractType(str, enum.Enum):
    FULL_TIME = "full_time"          # 全职劳动合同
    PART_TIME = "part_time"          # 非全日制合同
    HOURLY = "hourly"                # 小时工协议
    OUTSOURCE = "outsource"          # 外包服务协议
    DISPATCH = "dispatch"            # 劳务派遣合同
    PARTNER = "partner"              # 合伙协议
    INTERNSHIP = "internship"        # 实习协议


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRING = "expiring"            # 即将到期（30天内）
    EXPIRED = "expired"
    TERMINATED = "terminated"
    RENEWED = "renewed"


class PersonContract(Base, TimestampMixin):
    __tablename__ = "person_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联任职关系
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id"), nullable=False, index=True,
                           comment="关联 Assignment")

    # 合同类型
    contract_type = Column(SAEnum(ContractType, name="person_contract_type_enum", create_type=False),
                           nullable=False, comment="合同类型")
    status = Column(SAEnum(ContractStatus, name="person_contract_status_enum", create_type=False),
                    default=ContractStatus.DRAFT, index=True, comment="合同状态")

    # 合同期限
    contract_no = Column(String(50), unique=True, comment="合同编号")
    sign_date = Column(Date, comment="签订日期")
    valid_from = Column(Date, nullable=False, comment="生效日期")
    valid_to = Column(Date, comment="到期日期（null=无固定期限）")

    # 薪酬方案（结构化JSON）
    pay_scheme = Column(JSON, default=dict, comment="""
        薪酬方案: {
            base_salary_fen: 500000,     // 基本工资（分）
            meal_allowance_fen: 30000,   // 餐补
            housing_allowance_fen: 0,    // 住房补贴
            overtime_rate: 1.5,          // 加班倍率
            commission_rules: [...],     // 提成规则
            bonus_scheme: {...}          // 奖金方案
        }
    """)

    # 考勤规则关联
    attendance_rule_id = Column(UUID(as_uuid=True), nullable=True,
                                comment="关联考勤规则ID")

    # 试用期
    probation_salary_pct = Column(Integer, default=80, comment="试用期薪资比例(%)")

    # 续签
    renewal_count = Column(Integer, default=0, comment="续签次数")
    previous_contract_id = Column(UUID(as_uuid=True), nullable=True,
                                   comment="上一份合同ID")

    # 终止
    termination_date = Column(Date, comment="终止日期")
    termination_reason = Column(Text, comment="终止原因")

    # 电子签
    esign_status = Column(String(20), default="pending", comment="电签状态: pending/signed/rejected")
    esign_url = Column(String(500), comment="电签链接")
    signed_pdf_url = Column(String(500), comment="已签合同PDF")

    # 备注
    remark = Column(Text, comment="备注")

    def __repr__(self):
        return f"<PersonContract {self.contract_no} ({self.status})>"
