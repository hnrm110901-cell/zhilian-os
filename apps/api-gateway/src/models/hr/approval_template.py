"""ApprovalTemplate — HR审批模板定义"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class ApprovalTemplate(Base):
    __tablename__ = "approval_templates"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False,
                  comment="模板名称，如'入职审批'/'离职审批'/'转岗审批'")
    resource_type = Column(String(30), nullable=False, index=True,
                           comment="onboarding/offboarding/transfer")
    org_node_id = Column(String(64), nullable=True, index=True,
                         comment="None=集团通用，有值=门店专属")
    steps = Column(JSONB, nullable=False, default=list,
                   comment="[{level:1, approver_type:'position', role:'store_manager'}]")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (f"<ApprovalTemplate(id={self.id}, name={self.name!r}, "
                f"resource_type={self.resource_type!r})>")
