"""
Performance Review Models — 绩效考核
考核模板、考核周期、考核评分
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class ReviewCycle(str, enum.Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"


class ReviewStatus(str, enum.Enum):
    DRAFT = "draft"
    SELF_REVIEW = "self_review"  # 自评中
    MANAGER_REVIEW = "manager"  # 上级评中
    COMPLETED = "completed"
    APPEALED = "appealed"  # 申诉中


class ReviewLevel(str, enum.Enum):
    """绩效等级"""

    S = "S"  # 卓越
    A = "A"  # 优秀
    B = "B"  # 良好
    C = "C"  # 合格
    D = "D"  # 待改进


# ── 1. 考核模板 ────────────────────────────────────────────


class PerformanceTemplate(Base, TimestampMixin):
    """
    考核模板：定义考核维度和权重。
    可按岗位配置不同模板。
    """

    __tablename__ = "performance_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=True, index=True)
    brand_id = Column(String(50), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    position = Column(String(50), nullable=True)  # 适用岗位，NULL=通用
    cycle = Column(
        SAEnum(ReviewCycle, name="review_cycle_enum"),
        nullable=False,
        default=ReviewCycle.MONTHLY,
    )

    # 考核维度（JSON数组）
    # [
    #   {"name": "销售业绩", "weight": 30, "metric_key": "sales_achievement", "description": "月度销售目标达成率"},
    #   {"name": "服务质量", "weight": 20, "metric_key": "service_score", "description": "顾客评分"},
    #   {"name": "出勤纪律", "weight": 20, "metric_key": "attendance_rate", "description": "出勤率"},
    #   {"name": "团队协作", "weight": 15, "metric_key": "teamwork", "description": "团队贡献"},
    #   {"name": "技能提升", "weight": 15, "metric_key": "skill_growth", "description": "培训完成率"}
    # ]
    dimensions = Column(JSON, nullable=False, default=list)

    # 等级划分规则
    # {"S": [90, 100], "A": [80, 89], "B": [70, 79], "C": [60, 69], "D": [0, 59]}
    level_rules = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<PerformanceTemplate(name='{self.name}', position='{self.position}')>"


# ── 2. 考核记录 ────────────────────────────────────────────


class PerformanceReview(Base, TimestampMixin):
    """
    员工考核记录：每个考核周期一条。
    打通现有KPI监控数据，自动填充业务指标维度。
    """

    __tablename__ = "performance_reviews"
    __table_args__ = (UniqueConstraint("employee_id", "review_period", name="uq_perf_review_period"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("performance_templates.id"), nullable=True)

    review_period = Column(String(10), nullable=False, index=True)  # "2026-Q1" / "2026-03"

    status = Column(
        SAEnum(ReviewStatus, name="review_status_enum"),
        nullable=False,
        default=ReviewStatus.DRAFT,
        index=True,
    )

    # 各维度评分（JSON）
    # {"sales_achievement": {"score": 85, "comment": "达成率92%"},
    #  "service_score": {"score": 90, "comment": "顾客好评率95%"}}
    dimension_scores = Column(JSON, nullable=True)

    # 综合分
    total_score = Column(Numeric(5, 1), nullable=True)
    level = Column(
        SAEnum(ReviewLevel, name="review_level_enum"),
        nullable=True,
    )

    # 自评
    self_score = Column(Numeric(5, 1), nullable=True)
    self_comment = Column(Text, nullable=True)

    # 上级评
    manager_score = Column(Numeric(5, 1), nullable=True)
    manager_comment = Column(Text, nullable=True)
    reviewer_id = Column(String(50), nullable=True)
    reviewer_name = Column(String(100), nullable=True)

    # 绩效系数（连接薪酬）
    performance_coefficient = Column(Numeric(4, 2), nullable=True)

    # 改进计划
    improvement_plan = Column(Text, nullable=True)

    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<PerformanceReview(employee='{self.employee_id}', " f"period='{self.review_period}', level='{self.level}')>"
