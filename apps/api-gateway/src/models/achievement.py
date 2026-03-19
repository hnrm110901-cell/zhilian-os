"""
Achievement — 技能认证记录（Person × SkillNode）

记录员工通过认证的技能节点，包含认证证据和验证人。
构成员工的"技能护照"，支持跨店调动时技能携带。
"""
import uuid
from sqlalchemy import Column, String, Date, DateTime, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class Achievement(Base, TimestampMixin):
    __tablename__ = "achievements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False, index=True,
                       comment="关联 Person")
    skill_node_id = Column(UUID(as_uuid=True), ForeignKey("skill_nodes.id"), nullable=False, index=True,
                           comment="关联 SkillNode")

    # 认证信息
    level = Column(Integer, default=1, comment="达成等级")
    achieved_at = Column(DateTime, nullable=False, comment="认证时间")
    evidence = Column(JSON, default=dict, comment="认证证据 {type: 'exam/observation/certificate', url: '...', score: 95}")

    # 验证
    verified_by = Column(UUID(as_uuid=True), nullable=True, comment="验证人 Person ID")
    verified_at = Column(DateTime, comment="验证时间")
    verification_method = Column(String(50), comment="验证方式: exam/observation/peer_review/auto")

    # 有效期
    expires_at = Column(DateTime, comment="认证过期时间（如食品安全证需年检）")
    is_valid = Column(String(20), default="valid", comment="状态: valid/expired/revoked")

    # 备注
    remark = Column(Text, comment="备注")

    def __repr__(self):
        return f"<Achievement person={self.person_id} skill={self.skill_node_id} L{self.level}>"
