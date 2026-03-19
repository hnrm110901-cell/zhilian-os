"""AttendanceRule — 考勤规则配置（被EmploymentContract引用）"""
import uuid
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class AttendanceRule(Base):
    __tablename__ = "attendance_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    rule_config = Column(JSONB, nullable=False, default=dict)
    # NULL = 全集团通用规则
    org_node_id = Column(String(64), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<AttendanceRule(id={self.id}, name={self.name!r})>"
