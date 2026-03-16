"""
Employee Growth Journey Models — 员工成长旅程
技能矩阵 · 职业路径 · 里程碑 · 成长计划 · 幸福指数

设计哲学：让专业和品牌文化及幸福的人生哲学陪伴员工的工作生命周期全旅程
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID

from .base import Base, TimestampMixin

# ── Enums ──────────────────────────────────────────────


class SkillLevel(str, enum.Enum):
    """技能等级（餐饮五级工匠体系）"""

    NOVICE = "novice"  # 学徒 — 刚接触
    APPRENTICE = "apprentice"  # 熟手 — 能独立操作
    JOURNEYMAN = "journeyman"  # 能手 — 熟练+质量稳定
    EXPERT = "expert"  # 高手 — 能带人+优化流程
    MASTER = "master"  # 匠人 — 行业标杆+创新


class MilestoneType(str, enum.Enum):
    """里程碑类型"""

    ONBOARD = "onboard"  # 入职
    TRIAL_PASS = "trial_pass"  # 试岗通过
    PROBATION_PASS = "probation_pass"  # 转正
    FIRST_PRAISE = "first_praise"  # 首次顾客表扬
    SKILL_UP = "skill_up"  # 技能升级
    ZERO_WASTE_MONTH = "zero_waste_month"  # 零损耗月
    SALES_CHAMPION = "sales_champion"  # 月度销冠
    ANNIVERSARY = "anniversary"  # 周年纪念
    PROMOTION = "promotion"  # 晋升
    MENTOR_FIRST = "mentor_first"  # 首次带徒
    CULTURE_STAR = "culture_star"  # 文化之星
    TRAINING_COMPLETE = "training_complete"  # 培训结业
    PERFECT_ATTENDANCE = "perfect_attendance"  # 全勤
    CUSTOM = "custom"  # 自定义


class GrowthPlanStatus(str, enum.Enum):
    """成长计划状态"""

    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


# ── 1. 技能矩阵 ────────────────────────────────────────


class SkillDefinition(Base, TimestampMixin):
    """
    技能定义（门店/品牌级）。
    定义岗位所需的全部技能项。
    """

    __tablename__ = "skill_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=True, index=True)  # NULL=品牌通用
    brand_id = Column(String(50), nullable=True)

    skill_name = Column(String(100), nullable=False)  # 如 "客户接待"
    skill_category = Column(String(50), nullable=False)  # 服务/烹饪/管理/安全/文化
    applicable_positions = Column(JSON, nullable=True)  # ["waiter","cashier"]
    required_level = Column(
        SAEnum(SkillLevel, name="skill_level_enum", create_constraint=False),
        nullable=False,
        default=SkillLevel.JOURNEYMAN,
    )
    description = Column(Text, nullable=True)
    # 晋升权重（该技能对晋升的重要程度 0-100）
    promotion_weight = Column(Integer, default=50)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<SkillDefinition(name='{self.skill_name}', category='{self.skill_category}')>"


class EmployeeSkill(Base, TimestampMixin):
    """
    员工技能评估记录。
    每次评估一条，保留历史形成成长曲线。
    """

    __tablename__ = "employee_skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skill_definitions.id"), nullable=False)

    current_level = Column(
        SAEnum(SkillLevel, name="skill_level_enum", create_constraint=False),
        nullable=False,
        default=SkillLevel.NOVICE,
    )
    # 技能分（0-100，细粒度）
    score = Column(Integer, default=0)

    # 评估信息
    assessed_by = Column(String(100), nullable=True)  # 评估人
    assessed_at = Column(Date, nullable=True)
    evidence = Column(Text, nullable=True)  # 评估依据
    next_target_level = Column(
        SAEnum(SkillLevel, name="skill_level_enum", create_constraint=False),
        nullable=True,
    )

    def __repr__(self):
        return f"<EmployeeSkill(employee='{self.employee_id}', level='{self.current_level}')>"


# ── 2. 职业路径 ────────────────────────────────────────


class CareerPath(Base, TimestampMixin):
    """
    职业发展路径定义。
    如：服务员 → 领班 → 楼面经理 → 店长
    """

    __tablename__ = "career_paths"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=True, index=True)
    brand_id = Column(String(50), nullable=True)

    path_name = Column(String(100), nullable=False)  # "服务线"
    from_position = Column(String(50), nullable=False)  # "waiter"
    to_position = Column(String(50), nullable=False)  # "shift_leader"
    sequence = Column(Integer, default=0)  # 路径内的顺序

    # 晋升条件
    min_tenure_months = Column(Integer, default=6)  # 最少在岗月数
    required_skills = Column(JSON, nullable=True)  # [{"skill_id":"...", "min_level":"journeyman"}]
    required_training = Column(JSON, nullable=True)  # 必须完成的培训
    min_performance_level = Column(String(10), default="B")  # 最低绩效等级
    min_performance_score = Column(Integer, default=70)  # 最低绩效分

    # 薪资变化
    salary_increase_pct = Column(Numeric(5, 1), default=15.0)  # 晋升加薪比例
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<CareerPath('{self.from_position}' → '{self.to_position}')>"


# ── 3. 员工里程碑 ──────────────────────────────────────


class EmployeeMilestone(Base, TimestampMixin):
    """
    员工里程碑记录 — 工作生命周期中的每个高光时刻。
    自动触发 + 手动颁发，配合企微推送庆祝。
    """

    __tablename__ = "employee_milestones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    milestone_type = Column(
        SAEnum(MilestoneType, name="milestone_type_enum"),
        nullable=False,
    )
    title = Column(String(200), nullable=False)  # "入职100天"
    description = Column(Text, nullable=True)
    achieved_at = Column(Date, nullable=False)

    # 关联数据
    related_entity_type = Column(String(50), nullable=True)  # "performance_review"
    related_entity_id = Column(String(100), nullable=True)

    # 激励
    reward_fen = Column(Integer, default=0)  # 奖励金额（分）
    badge_icon = Column(String(50), nullable=True)  # 徽章图标

    # 通知
    notified = Column(Boolean, default=False)
    notified_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Milestone(employee='{self.employee_id}', type='{self.milestone_type}')>"


# ── 4. 员工成长计划 ────────────────────────────────────


class EmployeeGrowthPlan(Base, TimestampMixin):
    """
    员工个人成长计划。
    AI根据技能差距+职业路径+绩效结果自动生成，也可手动创建。
    """

    __tablename__ = "employee_growth_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    plan_name = Column(String(200), nullable=False)  # "服务技能提升计划（2026Q1）"
    status = Column(
        SAEnum(GrowthPlanStatus, name="growth_plan_status_enum"),
        nullable=False,
        default=GrowthPlanStatus.ACTIVE,
    )

    # 目标
    target_position = Column(String(50), nullable=True)  # 目标岗位
    target_date = Column(Date, nullable=True)  # 预计达成日期

    # 计划内容（结构化任务列表）
    # [{"task": "完成食品安全培训", "type": "training", "due_date": "2026-04-01", "done": false},
    #  {"task": "服务技能达到能手级", "type": "skill_up", "skill_id": "...", "target_level": "journeyman", "done": false}]
    tasks = Column(JSON, nullable=True)

    # 进度
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    progress_pct = Column(Numeric(5, 1), default=0)

    # 指导人
    mentor_id = Column(String(50), nullable=True)  # 导师员工ID
    mentor_name = Column(String(100), nullable=True)

    # AI生成标记
    ai_generated = Column(Boolean, default=False)
    ai_reasoning = Column(Text, nullable=True)  # AI分析理由

    started_at = Column(Date, nullable=True)
    completed_at = Column(Date, nullable=True)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<GrowthPlan(employee='{self.employee_id}', plan='{self.plan_name}')>"


# ── 5. 员工幸福指数 ────────────────────────────────────


class EmployeeWellbeing(Base, TimestampMixin):
    """
    员工幸福指数记录（月度）。
    5维度：工作成就感、团队归属感、成长获得感、生活平衡感、文化认同感。
    """

    __tablename__ = "employee_wellbeing"
    __table_args__ = (UniqueConstraint("employee_id", "period", name="uq_wellbeing_period"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM

    # 五维幸福指数（1-10分）
    achievement_score = Column(Integer, default=0)  # 工作成就感
    belonging_score = Column(Integer, default=0)  # 团队归属感
    growth_score = Column(Integer, default=0)  # 成长获得感
    balance_score = Column(Integer, default=0)  # 生活平衡感
    culture_score = Column(Integer, default=0)  # 文化认同感

    # 综合分（五维加权平均）
    overall_score = Column(Numeric(4, 1), default=0)

    # 开放反馈
    highlights = Column(Text, nullable=True)  # 本月最开心的事
    concerns = Column(Text, nullable=True)  # 本月最困扰的事
    suggestions = Column(Text, nullable=True)  # 对公司的建议

    # 标记
    is_anonymous = Column(Boolean, default=False)  # 是否匿名
    submitted_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Wellbeing(employee='{self.employee_id}', " f"period='{self.period}', score={self.overall_score})>"
