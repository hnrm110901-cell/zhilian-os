"""
Training Models — 培训课程/报名/考试/认证
对标麦麦e学：课程→学习→考试→认证→学分
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime, Date,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSON

from .base import Base, TimestampMixin


class TrainingCourse(Base, TimestampMixin):
    """培训课程"""

    __tablename__ = "training_courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)  # NULL=品牌通用

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # safety/service/cooking/management/culture
    course_type = Column(String(30), nullable=False, default="online")  # online/offline/practice
    applicable_positions = Column(JSON, nullable=True)  # ["waiter","chef"]
    duration_minutes = Column(Integer, nullable=False, default=60)
    content_url = Column(String(500), nullable=True)  # 课件链接
    pass_score = Column(Integer, default=60)
    credits = Column(Integer, default=1)  # 学分
    is_mandatory = Column(Boolean, default=False)  # 必修/选修
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<TrainingCourse(title='{self.title}', category='{self.category}')>"


class TrainingEnrollment(Base, TimestampMixin):
    """培训报名/学习记录"""

    __tablename__ = "training_enrollments"
    __table_args__ = (
        UniqueConstraint("employee_id", "course_id", name="uq_training_enrollment"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("training_courses.id"), nullable=False, index=True)

    status = Column(String(20), nullable=False, default="enrolled")  # enrolled/in_progress/completed/failed
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress_pct = Column(Integer, default=0)  # 0-100
    score = Column(Integer, nullable=True)  # 考试分数
    certificate_no = Column(String(50), nullable=True)
    certified_at = Column(Date, nullable=True)

    def __repr__(self):
        return f"<TrainingEnrollment(emp='{self.employee_id}', status='{self.status}')>"


class TrainingExam(Base, TimestampMixin):
    """考试/测验"""

    __tablename__ = "training_exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("training_courses.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    questions = Column(JSON, nullable=False)  # [{q, options, answer, score}]
    total_score = Column(Integer, nullable=False, default=100)
    pass_score = Column(Integer, nullable=False, default=60)
    time_limit_minutes = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<TrainingExam(title='{self.title}')>"


class ExamAttempt(Base, TimestampMixin):
    """考试记录"""

    __tablename__ = "exam_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("training_exams.id"), nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    answers = Column(JSON, nullable=True)
    score = Column(Integer, nullable=False, default=0)
    passed = Column(Boolean, nullable=False, default=False)
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ExamAttempt(exam='{self.exam_id}', score={self.score})>"
