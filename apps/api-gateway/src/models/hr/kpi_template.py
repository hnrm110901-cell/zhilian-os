"""KpiTemplate — KPI模板配置（被EmploymentContract引用）"""
import uuid
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class KpiTemplate(Base):
    __tablename__ = "kpi_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    template_config = Column(JSONB, nullable=False, default=dict)
    # NULL = 全集团通用模板
    org_node_id = Column(String(64), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<KpiTemplate(id={self.id}, name={self.name!r})>"
