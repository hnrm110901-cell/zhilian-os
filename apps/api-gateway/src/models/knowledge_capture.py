"""
KnowledgeCapture — 对话式知识采集

在关键触发时刻（离职面谈/绩效复盘/项目结束）采集员工经验知识：
- 通过对话式交互提取隐性知识
- 结构化为可复用的知识节点
- 关联到 SkillNode/KnowledgeRule 体系

这是"人走知识留"的核心机制。
"""
import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class KnowledgeCapture(Base, TimestampMixin):
    __tablename__ = "knowledge_captures"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联人员
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False, index=True,
                       comment="知识贡献者")

    # 触发场景
    trigger_type = Column(String(30), nullable=False, index=True,
                          comment="触发类型: exit(离职)/review(复盘)/project_end/spontaneous")
    trigger_context = Column(JSON, default=dict, comment="触发上下文 {assignment_id, event_type, ...}")

    # 采集内容
    context = Column(Text, comment="情境描述（什么场景下）")
    action = Column(Text, comment="行动描述（做了什么）")
    result = Column(Text, comment="结果描述（效果如何）")

    # 结构化输出
    structured_output = Column(JSON, default=dict, comment="""
        结构化知识: {
            domain: "inventory",
            pattern: "海鲜类食材周末备货量需增加30%",
            applicable_conditions: ["weekend", "seafood", "summer"],
            expected_impact: {waste_rate: -2.0, revenue: +5000},
            confidence: 0.8
        }
    """)

    # 关联知识体系
    knowledge_node_id = Column(UUID(as_uuid=True), nullable=True,
                               comment="关联到知识规则库的节点ID")
    linked_skill_ids = Column(JSON, default=list, comment="关联技能节点 [skill_node_id, ...]")

    # 采集质量
    quality_score = Column(String(10), comment="质量评级: A/B/C/D")
    reviewed_by = Column(UUID(as_uuid=True), nullable=True, comment="审核人")
    reviewed_at = Column(DateTime, comment="审核时间")

    # 状态
    status = Column(String(20), default="draft", comment="状态: draft/reviewed/published/archived")

    # 采集方式
    capture_method = Column(String(20), default="dialogue",
                            comment="采集方式: dialogue(对话)/form(表单)/auto(自动提取)")
    session_transcript = Column(JSON, nullable=True, comment="对话记录（加密存储）")

    def __repr__(self):
        return f"<KnowledgeCapture person={self.person_id} trigger={self.trigger_type}>"
