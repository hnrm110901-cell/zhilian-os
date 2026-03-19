"""hr10 — 培训课程/报名/考试/师徒表

Revision ID: hr10
Revises: hr09
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr10'
down_revision = 'hr09'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 培训课程 ──
    op.create_table(
        'training_courses',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('store_id', sa.String(50), nullable=True, index=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('course_type', sa.String(30), nullable=False, server_default='online'),
        sa.Column('applicable_positions', JSON, nullable=True),
        sa.Column('duration_minutes', sa.Integer, nullable=False, server_default='60'),
        sa.Column('content_url', sa.String(500), nullable=True),
        sa.Column('pass_score', sa.Integer, server_default='60'),
        sa.Column('credits', sa.Integer, server_default='1'),
        sa.Column('is_mandatory', sa.Boolean, server_default='false'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ── 培训报名 ──
    op.create_table(
        'training_enrollments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('employee_id', sa.String(50), nullable=False, index=True),
        sa.Column('course_id', UUID(as_uuid=True), sa.ForeignKey('training_courses.id'), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='enrolled'),
        sa.Column('enrolled_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('progress_pct', sa.Integer, server_default='0'),
        sa.Column('score', sa.Integer, nullable=True),
        sa.Column('certificate_no', sa.String(50), nullable=True),
        sa.Column('certified_at', sa.Date, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('employee_id', 'course_id', name='uq_training_enrollment'),
    )

    # ── 考试 ──
    op.create_table(
        'training_exams',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('course_id', UUID(as_uuid=True), sa.ForeignKey('training_courses.id'), nullable=False, index=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('questions', JSON, nullable=False),
        sa.Column('total_score', sa.Integer, nullable=False, server_default='100'),
        sa.Column('pass_score', sa.Integer, nullable=False, server_default='60'),
        sa.Column('time_limit_minutes', sa.Integer, nullable=False, server_default='30'),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ── 考试记录 ──
    op.create_table(
        'exam_attempts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('exam_id', UUID(as_uuid=True), sa.ForeignKey('training_exams.id'), nullable=False, index=True),
        sa.Column('employee_id', sa.String(50), nullable=False, index=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('answers', JSON, nullable=True),
        sa.Column('score', sa.Integer, nullable=False, server_default='0'),
        sa.Column('passed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('attempted_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ── 师徒制 ──
    op.create_table(
        'mentorships',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('target_position', sa.String(50), nullable=False),
        sa.Column('mentor_id', sa.String(50), nullable=False, index=True),
        sa.Column('mentor_name', sa.String(50), nullable=True),
        sa.Column('apprentice_id', sa.String(50), nullable=False, index=True),
        sa.Column('apprentice_name', sa.String(50), nullable=True),
        sa.Column('enrolled_at', sa.Date, nullable=False),
        sa.Column('training_start', sa.Date, nullable=True),
        sa.Column('training_end', sa.Date, nullable=True),
        sa.Column('expected_review_date', sa.Date, nullable=True),
        sa.Column('actual_review_date', sa.Date, nullable=True),
        sa.Column('review_result', sa.String(20), nullable=True),
        sa.Column('reward_fen', sa.Integer, server_default='0'),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('mentorships')
    op.drop_table('exam_attempts')
    op.drop_table('training_exams')
    op.drop_table('training_enrollments')
    op.drop_table('training_courses')
