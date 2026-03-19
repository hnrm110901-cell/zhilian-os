"""
Person — 全局人员档案（跨门店唯一）

HR架构重构核心模型：将旧 Employee 的"人"的属性抽离为独立实体。
一个 Person 可以在多个门店有多个 Assignment（任职关系）。

迁移路径：employees.name/phone/id_card → persons
"""
import uuid
from sqlalchemy import Column, String, Date, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class Person(Base, TimestampMixin):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本身份
    name = Column(String(100), nullable=False, index=True, comment="姓名")
    id_number = Column(String(18), unique=True, nullable=True, comment="身份证号(加密存储)")
    phone = Column(String(20), index=True, comment="手机号")
    photo_url = Column(String(500), comment="头像URL")

    # 个人信息
    gender = Column(String(10), comment="性别")
    birth_date = Column(Date, comment="出生日期")
    education = Column(String(20), comment="学历: 博士/硕士/本科/大专/高中/中专/初中")
    ethnicity = Column(String(20), comment="民族")
    marital_status = Column(String(20), comment="婚姻状况")
    hukou_type = Column(String(20), comment="户口类型: 城镇/农村")
    hukou_location = Column(String(200), comment="户籍地")

    # 紧急联系人
    emergency_contact = Column(String(50), comment="紧急联系人")
    emergency_phone = Column(String(20), comment="紧急联系电话")
    emergency_relation = Column(String(20), comment="与本人关系")

    # 银行信息（加密）
    bank_name = Column(String(100), comment="开户行")
    bank_account = Column(String(50), comment="银行账号(加密)")
    bank_branch = Column(String(200), comment="支行")

    # IM集成
    wechat_userid = Column(String(100), index=True, comment="企业微信UserID")
    dingtalk_userid = Column(String(100), index=True, comment="钉钉UserID")

    # 合规
    health_cert_expiry = Column(Date, comment="健康证到期日")
    health_cert_attachment = Column(String(500), comment="健康证附件路径")
    id_card_expiry = Column(Date, comment="身份证到期日")
    background_check = Column(String(20), default="pending", comment="背调状态: pending/passed/failed")

    # 技能档案（关联 SkillNode）
    skills_snapshot = Column(JSON, default=list, comment="技能快照 [{skill_id, level, achieved_at}]")

    # 来源追踪
    source = Column(String(50), comment="来源: recruitment/import/manual")
    is_active = Column(Boolean, default=True, comment="是否活跃（有至少一个active Assignment）")

    def __repr__(self):
        return f"<Person {self.name} ({self.id})>"
