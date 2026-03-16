"""
Recruitment Models — 招聘管理
职位发布、候选人、面试、Offer
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    OPEN = "open"
    FILLED = "filled"
    CLOSED = "closed"
    ON_HOLD = "on_hold"


class CandidateStage(str, enum.Enum):
    NEW = "new"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InterviewResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"
    STRONG_PASS = "strong_pass"


class OfferStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


# ── 1. 职位发布 ────────────────────────────────────────────


class JobPosting(Base, TimestampMixin):
    """招聘职位"""

    __tablename__ = "job_postings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), nullable=True, index=True)

    title = Column(String(100), nullable=False)
    position = Column(String(50), nullable=False)  # waiter, chef, etc.
    department = Column(String(50), nullable=True)
    headcount = Column(Integer, nullable=False, default=1)
    hired_count = Column(Integer, nullable=False, default=0)

    status = Column(
        SAEnum(JobStatus, name="job_status_enum"),
        nullable=False,
        default=JobStatus.OPEN,
        index=True,
    )

    # 薪资范围（分）
    salary_min_fen = Column(Integer, nullable=True)
    salary_max_fen = Column(Integer, nullable=True)
    salary_type = Column(String(20), default="monthly")  # monthly/hourly

    # 要求
    requirements = Column(Text, nullable=True)
    skills_required = Column(JSON, nullable=True)
    experience_years = Column(Integer, nullable=True)

    # 招聘渠道
    channels = Column(JSON, nullable=True)  # ["boss", "58", "referral"]

    urgent = Column(Boolean, default=False)
    deadline = Column(Date, nullable=True)
    publisher_id = Column(String(50), nullable=True)

    def __repr__(self):
        return f"<JobPosting(title='{self.title}', headcount={self.headcount}, status='{self.status}')>"


# ── 2. 候选人 ──────────────────────────────────────────────


class Candidate(Base, TimestampMixin):
    """候选人档案"""

    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id"), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    gender = Column(String(10), nullable=True)
    age = Column(Integer, nullable=True)

    stage = Column(
        SAEnum(CandidateStage, name="candidate_stage_enum"),
        nullable=False,
        default=CandidateStage.NEW,
        index=True,
    )

    # 简历
    resume_url = Column(String(500), nullable=True)
    work_experience = Column(JSON, nullable=True)
    education = Column(String(100), nullable=True)
    skills = Column(JSON, nullable=True)

    # 来源
    source = Column(String(50), nullable=True)  # boss/58/referral/walk_in
    referrer_id = Column(String(50), nullable=True)  # 推荐人员工ID

    # 评分
    screening_score = Column(Integer, nullable=True)  # 简历筛选分 0-100
    interview_score = Column(Integer, nullable=True)  # 面试综合分 0-100

    rejection_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Candidate(name='{self.name}', stage='{self.stage}')>"


# ── 3. 面试记录 ────────────────────────────────────────────


class Interview(Base, TimestampMixin):
    """面试记录"""

    __tablename__ = "interviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    round = Column(Integer, nullable=False, default=1)  # 面试轮次
    interview_date = Column(DateTime, nullable=False)
    interviewer_id = Column(String(50), nullable=True)
    interviewer_name = Column(String(100), nullable=True)

    result = Column(
        SAEnum(InterviewResult, name="interview_result_enum"),
        nullable=False,
        default=InterviewResult.PENDING,
    )

    # 评估维度
    skill_score = Column(Integer, nullable=True)  # 技能分 0-100
    attitude_score = Column(Integer, nullable=True)  # 态度分 0-100
    experience_score = Column(Integer, nullable=True)  # 经验分 0-100
    overall_score = Column(Integer, nullable=True)  # 综合分 0-100

    feedback = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Interview(candidate='{self.candidate_id}', round={self.round}, result='{self.result}')>"


# ── 4. Offer ───────────────────────────────────────────────


class Offer(Base, TimestampMixin):
    """录用通知"""

    __tablename__ = "offers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id"), nullable=False)
    store_id = Column(String(50), nullable=False, index=True)

    status = Column(
        SAEnum(OfferStatus, name="offer_status_enum"),
        nullable=False,
        default=OfferStatus.DRAFT,
        index=True,
    )

    position = Column(String(50), nullable=False)
    salary_fen = Column(Integer, nullable=False)
    salary_type = Column(String(20), default="monthly")
    start_date = Column(Date, nullable=False)
    probation_months = Column(Integer, default=3)
    probation_salary_pct = Column(Integer, default=80)  # 试用期薪资百分比

    benefits = Column(JSON, nullable=True)
    contract_type = Column(String(20), default="fixed")  # fixed/open_ended
    contract_years = Column(Integer, nullable=True)

    sent_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    expire_date = Column(Date, nullable=True)

    # 审批
    approval_instance_id = Column(UUID(as_uuid=True), nullable=True)
    approved_by = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<Offer(candidate='{self.candidate_id}', status='{self.status}')>"
