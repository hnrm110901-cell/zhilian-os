"""
Employee Model
"""

import uuid

from sqlalchemy import JSON, Boolean, Column, Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from .base import Base, TimestampMixin


class Employee(Base, TimestampMixin):
    """Employee model"""

    __tablename__ = "employees"

    id = Column(String(50), primary_key=True)  # e.g., EMP001
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))

    # Employment details
    position = Column(String(50))  # waiter, chef, cashier, manager
    skills = Column(ARRAY(String), default=list)  # List of skills
    hire_date = Column(Date)
    is_active = Column(Boolean, default=True, nullable=False)

    # 员工阶段: trial(试岗) / probation(试用) / regular(正式) / resigned(离职)
    employment_status = Column(String(20), default="regular")

    # IM 平台用户ID（OAuth + 通讯录同步关联）
    wechat_userid = Column(String(100), nullable=True, index=True)
    dingtalk_userid = Column(String(100), nullable=True, index=True)

    # 试用期结束日期
    probation_end_date = Column(Date, nullable=True)

    # ── 用工类型扩展 ──
    employment_type = Column(
        String(30), default="regular"
    )  # regular/part_time/intern/trainee/rehire/temp/outsource/outsource_flex
    grade_level = Column(String(50), nullable=True)  # 职级：门店初级/门店中级/子公司中高级A档...

    # ── 合规字段（餐饮强制） ──
    health_cert_expiry = Column(Date, nullable=True)  # 健康证到期日
    health_cert_attachment = Column(String(500), nullable=True)  # 附件路径
    id_card_no = Column(String(200), nullable=True)  # 身份证号（AES-256-GCM 加密存储）
    id_card_expiry = Column(Date, nullable=True)  # 身份证到期日
    background_check = Column(String(50), nullable=True)  # 背调状态: pending/passed/failed

    # ── 个人扩展 ──
    gender = Column(String(10), nullable=True)
    birth_date = Column(Date, nullable=True)
    education = Column(String(20), nullable=True)  # 博士/硕士/本科/大专/高中/中专/初中
    marital_status = Column(String(20), nullable=True)
    ethnicity = Column(String(20), nullable=True)  # 民族
    hukou_type = Column(String(30), nullable=True)  # 城镇户口/农业家庭户口
    hukou_location = Column(String(200), nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)
    political_status = Column(String(30), nullable=True)

    # ── 紧急联系人 ──
    emergency_contact = Column(String(50), nullable=True)
    emergency_phone = Column(String(20), nullable=True)
    emergency_relation = Column(String(20), nullable=True)

    # ── 银行信息 ──
    bank_name = Column(String(100), nullable=True)
    bank_account = Column(String(200), nullable=True)  # 银行卡号（AES-256-GCM 加密存储）
    bank_branch = Column(String(200), nullable=True)

    # ── 工作相关 ──
    daily_wage_standard_fen = Column(Integer, nullable=True)  # 日薪标准（分）
    work_hour_type = Column(String(30), nullable=True)  # 标准工时/综合工时/不定时
    first_work_date = Column(Date, nullable=True)  # 首次工作日期
    regular_date = Column(Date, nullable=True)  # 转正日期
    seniority_months = Column(Integer, nullable=True)  # 司龄（月）

    # ── 住宿 ──
    accommodation = Column(String(100), nullable=True)  # 宿舍信息

    # ── 工会 ──
    union_member = Column(Boolean, default=False)
    union_cadre = Column(Boolean, default=False)

    # ── 学历/专业 ──
    major = Column(String(100), nullable=True)  # 所学专业
    graduation_school = Column(String(100), nullable=True)
    professional_cert = Column(String(200), nullable=True)  # 专业证书

    # ── 组织架构 ──
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # 关联 organizations 表

    # Work preferences
    preferences = Column(JSON, default=dict)  # Preferred shifts, days off, etc.

    # Performance metrics
    performance_score = Column(String(10))  # Stored as string
    training_completed = Column(ARRAY(String), default=list)

    def __repr__(self):
        return f"<Employee(id='{self.id}', name='{self.name}', position='{self.position}')>"
