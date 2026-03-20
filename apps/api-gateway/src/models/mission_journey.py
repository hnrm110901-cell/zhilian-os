"""
Mission Journey Models — 业人成长使命旅程引擎
把入职→试岗→转正→技能升级→晋升→带徒串成连贯的叙事旅程

设计哲学：每位餐饮人都是自己职业故事的主角，
屯象OS帮TA记录每一个高光时刻，让成长可见、可量化、可分享。
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.sql import func

from .base import Base, TimestampMixin


# ── Enums ──────────────────────────────────────────────


class JourneyType(str, enum.Enum):
    """旅程类型"""
    CAREER = "career"            # 职业成长旅程（默认）
    SKILL = "skill"              # 专项技能旅程
    LEADERSHIP = "leadership"    # 管理能力旅程
    CULTURE = "culture"          # 企业文化旅程
    ONBOARDING = "onboarding"    # 新人融入旅程


class StageStatus(str, enum.Enum):
    """阶段状态"""
    LOCKED = "locked"            # 未解锁
    ACTIVE = "active"            # 进行中
    COMPLETED = "completed"      # 已完成
    SKIPPED = "skipped"          # 跳过


class JourneyStatus(str, enum.Enum):
    """旅程实例状态"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"
    TERMINATED = "terminated"


class NarrativeType(str, enum.Enum):
    """叙事类型"""
    MILESTONE_ACHIEVED = "milestone_achieved"   # 里程碑达成
    STAGE_COMPLETED = "stage_completed"          # 阶段完成
    SKILL_UPGRADED = "skill_upgraded"            # 技能升级
    PRAISE_RECEIVED = "praise_received"          # 收到表扬
    MENTOR_ASSIGNED = "mentor_assigned"          # 导师指定
    FIRST_SOLO = "first_solo"                    # 首次独立操作
    COST_SAVED = "cost_saved"                    # 成本节省贡献
    ZERO_WASTE = "zero_waste"                    # 零损耗达成
    PROMOTION = "promotion"                      # 晋升
    ANNIVERSARY = "anniversary"                  # 周年纪念
    CUSTOM = "custom"                            # 自定义


# ── 1. 旅程模板 ────────────────────────────────────────


class JourneyTemplate(Base, TimestampMixin):
    """
    旅程模板（品牌/企业级别定义）。
    定义一种成长旅程的所有阶段、里程碑和推进规则。
    例：「厨师成长之路」模板适用于所有厨师岗。
    """
    __tablename__ = "mj_journey_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=True, index=True,
                      comment="品牌ID，NULL=平台通用模板")
    store_id = Column(String(50), nullable=True,
                      comment="门店ID，NULL=品牌通用")

    name = Column(String(200), nullable=False,
                  comment="模板名称，如'厨师成长之路'")
    journey_type = Column(
        SAEnum(JourneyType, name="journey_type_enum", create_constraint=False),
        nullable=False, default=JourneyType.CAREER,
    )
    description = Column(Text, nullable=True)
    applicable_positions = Column(JSON, nullable=True,
                                  comment='适用岗位列表 ["chef","sous_chef"]')

    # 模板配置
    total_stages = Column(Integer, default=0, comment="总阶段数")
    estimated_months = Column(Integer, nullable=True,
                              comment="预计完成月数")
    auto_advance = Column(Boolean, default=True,
                          comment="是否自动推进（满足条件自动进入下一阶段）")

    # 激励配置
    completion_reward_fen = Column(Integer, default=0,
                                  comment="完成旅程奖励金额（分）")
    completion_badge = Column(String(100), nullable=True,
                              comment="完成旅程徽章")

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1)

    def __repr__(self):
        return f"<JourneyTemplate(name='{self.name}', type='{self.journey_type}')>"


# ── 2. 阶段定义 ────────────────────────────────────────


class JourneyStageDefinition(Base, TimestampMixin):
    """
    旅程阶段定义（模板的子表）。
    例：入职阶段 → 试岗阶段 → 转正阶段 → 熟手阶段 → ...
    每个阶段有进入条件、完成条件、时间窗口。
    """
    __tablename__ = "mj_stage_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True),
                         ForeignKey("mj_journey_templates.id", ondelete="CASCADE"),
                         nullable=False, index=True)

    sequence = Column(Integer, nullable=False, comment="阶段顺序（从1开始）")
    name = Column(String(200), nullable=False, comment="阶段名，如'新人融入期'")
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True, comment="阶段图标")

    # 时间约束
    min_days = Column(Integer, nullable=True, comment="最少天数")
    max_days = Column(Integer, nullable=True, comment="最长天数（超时预警）")
    target_days = Column(Integer, nullable=True, comment="目标完成天数")

    # 进入条件（JSON规则引擎格式）
    entry_conditions = Column(JSON, nullable=True,
                              comment='进入条件 [{"type":"prev_stage_done"}]')

    # 完成条件
    completion_conditions = Column(JSON, nullable=True,
                                   comment='完成条件 [{"type":"skill_level","skill":"knife","min_level":"journeyman"}]')

    # 阶段任务清单
    tasks = Column(JSON, nullable=True,
                   comment='任务列表 [{"name":"完成食品安全培训","type":"training","required":true}]')

    # 该阶段的关键里程碑ID列表
    milestone_types = Column(JSON, nullable=True,
                             comment='关联里程碑类型 ["trial_pass","first_praise"]')

    # 激励
    stage_reward_fen = Column(Integer, default=0, comment="阶段完成奖励（分）")
    stage_badge = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<StageDefinition(seq={self.sequence}, name='{self.name}')>"


# ── 3. 员工旅程实例 ────────────────────────────────────


class EmployeeJourney(Base, TimestampMixin):
    """
    员工的旅程实例。
    一个员工可以同时有多条旅程（职业+技能+文化等）。
    """
    __tablename__ = "mj_employee_journeys"
    __table_args__ = (
        UniqueConstraint("person_id", "template_id",
                         name="uq_person_journey_template"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), nullable=False, index=True,
                       comment="关联persons.id")
    store_id = Column(String(50), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True),
                         ForeignKey("mj_journey_templates.id"),
                         nullable=False, index=True)

    status = Column(
        SAEnum(JourneyStatus, name="journey_status_enum", create_constraint=False),
        nullable=False, default=JourneyStatus.NOT_STARTED,
    )

    # 当前进度
    current_stage_seq = Column(Integer, default=0,
                               comment="当前所在阶段序号（0=未开始）")
    current_stage_name = Column(String(200), nullable=True)
    progress_pct = Column(Numeric(5, 1), default=0,
                          comment="总进度百分比")

    # 时间线
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)

    # 统计
    total_milestones = Column(Integer, default=0)
    achieved_milestones = Column(Integer, default=0)
    total_narratives = Column(Integer, default=0)

    # 导师
    mentor_person_id = Column(UUID(as_uuid=True), nullable=True,
                              comment="导师的person_id")
    mentor_name = Column(String(100), nullable=True)

    def __repr__(self):
        return (f"<EmployeeJourney(person={self.person_id}, "
                f"stage={self.current_stage_seq}, progress={self.progress_pct}%)>")


# ── 4. 员工阶段进度 ────────────────────────────────────


class EmployeeStageProgress(Base, TimestampMixin):
    """
    员工在每个阶段的具体进度。
    记录任务完成情况、时间、评价。
    """
    __tablename__ = "mj_stage_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journey_id = Column(UUID(as_uuid=True),
                        ForeignKey("mj_employee_journeys.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    stage_def_id = Column(UUID(as_uuid=True),
                          ForeignKey("mj_stage_definitions.id"),
                          nullable=False)
    stage_seq = Column(Integer, nullable=False)

    status = Column(
        SAEnum(StageStatus, name="stage_status_enum", create_constraint=False),
        nullable=False, default=StageStatus.LOCKED,
    )

    # 时间
    entered_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    days_spent = Column(Integer, nullable=True, comment="实际花费天数")

    # 任务完成追踪
    task_progress = Column(JSON, nullable=True,
                           comment='任务完成状态 [{"name":"...","done":true,"done_at":"..."}]')
    tasks_total = Column(Integer, default=0)
    tasks_done = Column(Integer, default=0)

    # 评价
    evaluator_name = Column(String(100), nullable=True)
    evaluation_score = Column(Integer, nullable=True, comment="阶段评分0-100")
    evaluation_comment = Column(Text, nullable=True)

    # 奖励发放
    reward_issued = Column(Boolean, default=False)
    reward_fen = Column(Integer, default=0)

    def __repr__(self):
        return f"<StageProgress(journey={self.journey_id}, seq={self.stage_seq}, status={self.status})>"


# ── 5. 成长叙事 ────────────────────────────────────────


class GrowthNarrative(Base, TimestampMixin):
    """
    成长叙事记录 — 把每个成长事件转化为可读的故事片段。
    用于员工个人成长时间线、企微推送庆祝、团队文化墙。

    示例叙事：
    「小王在入职第30天完成了食品安全培训，获得了'安全卫士'徽章！
     导师李师傅评价：学习速度很快，已经能独立操作切配岗。」
    """
    __tablename__ = "mj_growth_narratives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    journey_id = Column(UUID(as_uuid=True),
                        ForeignKey("mj_employee_journeys.id", ondelete="SET NULL"),
                        nullable=True, index=True)

    narrative_type = Column(
        SAEnum(NarrativeType, name="narrative_type_enum", create_constraint=False),
        nullable=False,
    )

    # 叙事内容
    title = Column(String(300), nullable=False,
                   comment="标题，如'小王完成了试岗考核'")
    content = Column(Text, nullable=False,
                     comment="叙事正文（支持Markdown）")
    emoji = Column(String(10), nullable=True,
                   comment="配套emoji表情")

    # 关联实体
    related_entity_type = Column(String(50), nullable=True,
                                 comment="关联实体类型")
    related_entity_id = Column(String(100), nullable=True)

    # 经济价值（如果该事件有直接¥影响）
    value_fen = Column(Integer, nullable=True,
                       comment="该事件的¥价值影响（分）")

    # 可见性
    is_public = Column(Boolean, default=True,
                       comment="是否在团队文化墙可见")
    is_pushed = Column(Boolean, default=False,
                       comment="是否已企微推送")
    pushed_at = Column(DateTime, nullable=True)

    # 点赞
    likes_count = Column(Integer, default=0)

    occurred_at = Column(DateTime, nullable=False, server_default=func.now(),
                         comment="事件发生时间")

    def __repr__(self):
        return f"<GrowthNarrative(person={self.person_id}, type='{self.narrative_type}')>"


# ── 6. 旅程里程碑实例 ──────────────────────────────────


class JourneyMilestone(Base, TimestampMixin):
    """
    旅程中的里程碑实例（与 employee_milestones 互补）。
    employee_milestones 是独立的成就记录；
    JourneyMilestone 是旅程上下文中的里程碑，关联到具体阶段。
    """
    __tablename__ = "mj_journey_milestones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journey_id = Column(UUID(as_uuid=True),
                        ForeignKey("mj_employee_journeys.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    stage_seq = Column(Integer, nullable=True,
                       comment="所属阶段序号（NULL=旅程级里程碑）")

    person_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    store_id = Column(String(50), nullable=False)

    # 里程碑信息
    milestone_code = Column(String(50), nullable=False,
                            comment="里程碑代码，如 trial_pass")
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    # 达成信息
    achieved = Column(Boolean, default=False)
    achieved_at = Column(DateTime, nullable=True)
    evidence = Column(Text, nullable=True, comment="达成证据/评语")

    # 奖励
    reward_fen = Column(Integer, default=0)
    badge_icon = Column(String(50), nullable=True)
    badge_name = Column(String(100), nullable=True)

    # 通知
    notified = Column(Boolean, default=False)

    def __repr__(self):
        return f"<JourneyMilestone(code='{self.milestone_code}', achieved={self.achieved})>"


# ── 7. 旅程统计快照 ────────────────────────────────────


class JourneyStats(Base, TimestampMixin):
    """
    门店/品牌级旅程统计快照（每日生成）。
    用于总部仪表板展示企业人才成长健康度。
    """
    __tablename__ = "mj_journey_stats"
    __table_args__ = (
        UniqueConstraint("store_id", "snapshot_date",
                         name="uq_journey_stats_store_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), nullable=True)
    snapshot_date = Column(Date, nullable=False, index=True)

    # 人员统计
    total_employees = Column(Integer, default=0)
    active_journeys = Column(Integer, default=0)
    completed_journeys = Column(Integer, default=0)

    # 里程碑统计
    milestones_achieved_mtd = Column(Integer, default=0,
                                     comment="本月达成里程碑数")
    narratives_created_mtd = Column(Integer, default=0,
                                    comment="本月生成叙事数")

    # 成长指标
    avg_journey_progress_pct = Column(Numeric(5, 1), default=0,
                                      comment="平均旅程进度")
    avg_stage_days = Column(Numeric(6, 1), nullable=True,
                            comment="平均阶段耗时（天）")
    retention_rate_pct = Column(Numeric(5, 1), nullable=True,
                                comment="在旅程中的员工留存率")

    # 对标
    industry_avg_progress_pct = Column(Numeric(5, 1), nullable=True,
                                       comment="行业平均旅程进度")

    def __repr__(self):
        return (f"<JourneyStats(store={self.store_id}, "
                f"date={self.snapshot_date}, active={self.active_journeys})>")
