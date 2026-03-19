"""
SkillNode — 技能图谱节点（知识OS骨架）

构建餐饮行业技能知识图谱：
- 每个节点代表一个可学习的技能（如"川菜颠锅"、"食材验收"）
- 节点间有前置依赖关系（prerequisites）
- 关联培训课程（related_trainings）
- 量化技能对 KPI 的影响（kpi_impact）
- 预估技能带来的营收提升（estimated_revenue_lift）
"""
import uuid
from sqlalchemy import Column, String, Float, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY
from src.models.base import Base, TimestampMixin


class SkillNode(Base, TimestampMixin):
    __tablename__ = "skill_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 技能身份
    skill_id = Column(String(50), unique=True, nullable=False, comment="技能编码（如 SKILL_COOK_WOK_001）")
    name = Column(String(100), nullable=False, index=True, comment="技能名称")
    category = Column(String(50), index=True, comment="技能分类: cooking/service/management/safety/finance")

    # 图谱关系
    prerequisites = Column(JSON, default=list, comment="前置技能 [skill_id, ...]")
    related_trainings = Column(JSON, default=list, comment="关联培训课程 [training_id, ...]")
    parent_skill_id = Column(UUID(as_uuid=True), nullable=True, comment="上级技能节点")

    # KPI影响量化
    kpi_impact = Column(JSON, default=dict, comment="""
        KPI影响: {
            waste_rate: -0.5,           // 损耗率降低0.5%
            customer_satisfaction: +2,   // 客户满意度+2分
            speed_of_service: +10       // 出餐速度+10%
        }
    """)
    estimated_revenue_lift = Column(Float, default=0.0, comment="预估年营收提升(元)")

    # 技能等级定义
    max_level = Column(Integer, default=5, comment="最高等级")
    level_criteria = Column(JSON, default=dict, comment="各等级达标标准 {1: {...}, 2: {...}}")

    # 适用范围
    applicable_positions = Column(JSON, default=list, comment="适用岗位 [waiter, chef, ...]")
    industry_scope = Column(String(50), default="general", comment="行业范围: general/seafood/hotpot/...")

    # 状态
    is_active = Column(Boolean, default=True, comment="是否启用")
    description = Column(Text, comment="技能描述")

    def __repr__(self):
        return f"<SkillNode {self.name} ({self.skill_id})>"
