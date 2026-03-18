"""Person — 全局人员档案（跨门店唯一自然人身份）"""
import uuid
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    emergency_contact = Column(JSONB, nullable=True, default=dict)
    career_stage = Column(String(20), nullable=True, default="probation",
                          comment="probation/regular/senior/lead/manager")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name={self.name!r})>"
