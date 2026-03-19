"""PersonAchievement — 技能认证记录（技能图谱的可见外衣）"""
import uuid
from sqlalchemy import Column, String, Date, Text, ForeignKey, UniqueConstraint, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class PersonAchievement(Base):
    __tablename__ = "person_achievements"
    __table_args__ = (
        UniqueConstraint("person_id", "skill_node_id",
                         name="uq_person_skill"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    skill_node_id = Column(UUID(as_uuid=True),
                           ForeignKey("skill_nodes.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    achieved_at = Column(Date, nullable=False)
    evidence = Column(Text, nullable=True)
    verified_by = Column(UUID(as_uuid=True), nullable=True)
    trigger_type = Column(String(30), nullable=True, default="manual")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<PersonAchievement(id={self.id}, person_id={self.person_id})>"
