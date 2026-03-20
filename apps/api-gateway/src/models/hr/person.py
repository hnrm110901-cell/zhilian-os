"""Person — 全局人员档案（跨门店唯一自然人身份）"""
import uuid
from sqlalchemy import Boolean, Column, Date, Integer, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from ..base import Base


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legacy_employee_id = Column(String(50), nullable=True, index=True,
                                comment="迁移桥接：原employees.id，M4后删除")
    name = Column(String(100), nullable=False)
    id_number = Column(String(18), nullable=True,
                       comment="身份证号，应用层加密后存储")
    phone = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    photo_url = Column(String(500), nullable=True)
    preferences = Column(JSONB, nullable=True, default=dict)
    emergency_contact = Column(JSONB, nullable=True, default=dict,
                               comment="紧急联系人 {name, phone, relation}")
    career_stage = Column(String(20), nullable=True, default="probation",
                          comment="probation/regular/senior/lead/manager")
    # IM 字段（z64 迁移新增，用于消息推送和考勤同步）
    wechat_userid = Column(String(100), nullable=True, index=True,
                           comment="企业微信 userid")
    dingtalk_userid = Column(String(100), nullable=True, index=True,
                             comment="钉钉 userid")
    # 过渡期兼容字段（最终由 EmploymentAssignment 替代）
    store_id = Column(String(50), nullable=True, index=True,
                      comment="主门店ID，过渡期兼容，最终由 EmploymentAssignment.org_node_id 替代")
    is_active = Column(Boolean, nullable=False, default=True,
                       comment="是否在职，过渡期兼容，最终由 EmploymentAssignment.status 替代")

    # ── ORM relationships ──────────────────────────────────────
    assignments = relationship(
        "EmploymentAssignment", back_populates="person",
        lazy="select", order_by="EmploymentAssignment.start_date.desc()",
    )

    # ── z65 档案字段 ──────────────────────────────────────────
    gender = Column(String(10), nullable=True, comment="性别")
    birth_date = Column(Date, nullable=True, comment="出生日期")
    health_cert_expiry = Column(Date, nullable=True, comment="健康证到期日")
    health_cert_attachment = Column(String(500), nullable=True, comment="健康证附件URL")
    id_card_expiry = Column(Date, nullable=True, comment="身份证到期日")
    bank_name = Column(String(100), nullable=True, comment="开户行")
    bank_account = Column(String(50), nullable=True, comment="银行账号（应用层加密）")
    bank_branch = Column(String(200), nullable=True, comment="支行")
    background_check = Column(String(100), nullable=True, comment="背景调查状态")
    accommodation = Column(String(200), nullable=True, comment="住宿安排")
    union_member = Column(Boolean, nullable=True, default=False, comment="工会会员")
    profile_ext = Column(JSONB, nullable=True, default=dict, server_default="'{}'"
                         , comment="低频档案扩展：education/ethnicity/hukou等")

    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    # ── 便捷 property 访问器（从 JSONB 读取，兼容旧 Employee 字段名） ──

    @property
    def emergency_phone(self) -> str:
        return (self.emergency_contact or {}).get("phone", "")

    @property
    def emergency_relation(self) -> str:
        return (self.emergency_contact or {}).get("relation", "")

    @property
    def emergency_contact_name(self) -> str:
        return (self.emergency_contact or {}).get("name", "")

    @property
    def education(self) -> str:
        return (self.profile_ext or {}).get("education", "")

    @property
    def graduation_school(self) -> str:
        return (self.profile_ext or {}).get("graduation_school", "")

    @property
    def major(self) -> str:
        return (self.profile_ext or {}).get("major", "")

    @property
    def professional_cert(self) -> str:
        return (self.profile_ext or {}).get("professional_cert", "")

    @property
    def marital_status(self) -> str:
        return (self.profile_ext or {}).get("marital_status", "")

    @property
    def ethnicity(self) -> str:
        return (self.profile_ext or {}).get("ethnicity", "")

    @property
    def hukou_type(self) -> str:
        return (self.profile_ext or {}).get("hukou_type", "")

    @property
    def hukou_location(self) -> str:
        return (self.profile_ext or {}).get("hukou_location", "")

    @property
    def political_status(self) -> str:
        return (self.profile_ext or {}).get("political_status", "")

    @property
    def height_cm(self):
        return (self.profile_ext or {}).get("height_cm", 0)

    @property
    def weight_kg(self):
        return (self.profile_ext or {}).get("weight_kg", 0)

    @property
    def regular_date(self) -> str:
        return (self.profile_ext or {}).get("regular_date", "")

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name={self.name!r})>"
