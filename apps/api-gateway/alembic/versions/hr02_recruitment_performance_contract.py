"""hr02 — HR业人一体化第2批：招聘+绩效+合同（7张表）

Tables:
  job_postings              — 招聘职位
  candidates                — 候选人档案
  interviews                — 面试记录
  offers                    — 录用通知
  performance_templates     — 考核模板
  performance_reviews       — 考核记录
  employee_contracts        — 劳动合同

Enum types (PostgreSQL native):
  job_status_enum, candidate_stage_enum, interview_result_enum, offer_status_enum,
  review_cycle_enum, review_status_enum, review_level_enum,
  contract_type_enum, contract_status_enum
"""

revision = 'hr02'
down_revision = 'hr01'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def _create_enum_safe(name: str, values: list[str]) -> None:
    op.execute(f"""
        DO $$
        BEGIN
            CREATE TYPE {name} AS ENUM ({', '.join(f"'{v}'" for v in values)});
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)


def upgrade() -> None:
    # ── Enum 类型 ─────────────────────────────────────────
    _create_enum_safe('job_status_enum', ['open', 'filled', 'closed', 'on_hold'])
    _create_enum_safe('candidate_stage_enum', [
        'new', 'screening', 'interview', 'offer', 'hired', 'rejected', 'withdrawn',
    ])
    _create_enum_safe('interview_result_enum', ['pass', 'fail', 'pending', 'strong_pass'])
    _create_enum_safe('offer_status_enum', ['draft', 'sent', 'accepted', 'rejected', 'expired'])

    _create_enum_safe('review_cycle_enum', ['monthly', 'quarterly', 'semi_annual', 'annual'])
    _create_enum_safe('review_status_enum', ['draft', 'self_review', 'manager', 'completed', 'appealed'])
    _create_enum_safe('review_level_enum', ['S', 'A', 'B', 'C', 'D'])

    _create_enum_safe('contract_type_enum', [
        'fixed_term', 'open_ended', 'part_time', 'internship', 'probation',
    ])
    _create_enum_safe('contract_status_enum', [
        'draft', 'active', 'expiring', 'expired', 'terminated', 'renewed',
    ])

    # ── 1. job_postings ───────────────────────────────────
    op.create_table(
        'job_postings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('brand_id', sa.String(50), nullable=True),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('position', sa.String(50), nullable=False),
        sa.Column('department', sa.String(50), nullable=True),
        sa.Column('headcount', sa.Integer, nullable=False, server_default='1'),
        sa.Column('hired_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('open', 'filled', 'closed', 'on_hold',
                                             name='job_status_enum', create_type=False),
                  nullable=False, server_default='open'),
        sa.Column('salary_min_fen', sa.Integer, nullable=True),
        sa.Column('salary_max_fen', sa.Integer, nullable=True),
        sa.Column('salary_type', sa.String(20), server_default='monthly'),
        sa.Column('requirements', sa.Text, nullable=True),
        sa.Column('skills_required', sa.JSON, nullable=True),
        sa.Column('experience_years', sa.Integer, nullable=True),
        sa.Column('channels', sa.JSON, nullable=True),
        sa.Column('urgent', sa.Boolean, server_default='false'),
        sa.Column('deadline', sa.Date, nullable=True),
        sa.Column('publisher_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_jp_store_id', 'job_postings', ['store_id'])
    op.create_index('ix_jp_brand_id', 'job_postings', ['brand_id'])
    op.create_index('ix_jp_status', 'job_postings', ['status'])

    # ── 2. candidates ─────────────────────────────────────
    op.create_table(
        'candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('job_postings.id'), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(100), nullable=True),
        sa.Column('gender', sa.String(10), nullable=True),
        sa.Column('age', sa.Integer, nullable=True),
        sa.Column('stage', postgresql.ENUM(
            'new', 'screening', 'interview', 'offer', 'hired', 'rejected', 'withdrawn',
            name='candidate_stage_enum', create_type=False),
            nullable=False, server_default='new'),
        sa.Column('resume_url', sa.String(500), nullable=True),
        sa.Column('work_experience', sa.JSON, nullable=True),
        sa.Column('education', sa.String(100), nullable=True),
        sa.Column('skills', sa.JSON, nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('referrer_id', sa.String(50), nullable=True),
        sa.Column('screening_score', sa.Integer, nullable=True),
        sa.Column('interview_score', sa.Integer, nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_cand_job_id', 'candidates', ['job_id'])
    op.create_index('ix_cand_store_id', 'candidates', ['store_id'])
    op.create_index('ix_cand_stage', 'candidates', ['stage'])

    # ── 3. interviews ─────────────────────────────────────
    op.create_table(
        'interviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('round', sa.Integer, nullable=False, server_default='1'),
        sa.Column('interview_date', sa.DateTime, nullable=False),
        sa.Column('interviewer_id', sa.String(50), nullable=True),
        sa.Column('interviewer_name', sa.String(100), nullable=True),
        sa.Column('result', postgresql.ENUM('pass', 'fail', 'pending', 'strong_pass',
                                             name='interview_result_enum', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('skill_score', sa.Integer, nullable=True),
        sa.Column('attitude_score', sa.Integer, nullable=True),
        sa.Column('experience_score', sa.Integer, nullable=True),
        sa.Column('overall_score', sa.Integer, nullable=True),
        sa.Column('feedback', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_int_candidate_id', 'interviews', ['candidate_id'])
    op.create_index('ix_int_store_id', 'interviews', ['store_id'])

    # ── 4. offers ─────────────────────────────────────────
    op.create_table(
        'offers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('job_postings.id'), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('status', postgresql.ENUM('draft', 'sent', 'accepted', 'rejected', 'expired',
                                             name='offer_status_enum', create_type=False),
                  nullable=False, server_default='draft'),
        sa.Column('position', sa.String(50), nullable=False),
        sa.Column('salary_fen', sa.Integer, nullable=False),
        sa.Column('salary_type', sa.String(20), server_default='monthly'),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('probation_months', sa.Integer, server_default='3'),
        sa.Column('probation_salary_pct', sa.Integer, server_default='80'),
        sa.Column('benefits', sa.JSON, nullable=True),
        sa.Column('contract_type', sa.String(20), server_default='fixed'),
        sa.Column('contract_years', sa.Integer, nullable=True),
        sa.Column('sent_at', sa.DateTime, nullable=True),
        sa.Column('responded_at', sa.DateTime, nullable=True),
        sa.Column('expire_date', sa.Date, nullable=True),
        sa.Column('approval_instance_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_off_candidate_id', 'offers', ['candidate_id'])
    op.create_index('ix_off_store_id', 'offers', ['store_id'])
    op.create_index('ix_off_status', 'offers', ['status'])

    # ── 5. performance_templates ──────────────────────────
    op.create_table(
        'performance_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('brand_id', sa.String(50), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('position', sa.String(50), nullable=True),
        sa.Column('cycle', postgresql.ENUM('monthly', 'quarterly', 'semi_annual', 'annual',
                                            name='review_cycle_enum', create_type=False),
                  nullable=False, server_default='monthly'),
        sa.Column('dimensions', sa.JSON, nullable=False, server_default='[]'),
        sa.Column('level_rules', sa.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_pt_store_id', 'performance_templates', ['store_id'])
    op.create_index('ix_pt_brand_id', 'performance_templates', ['brand_id'])

    # ── 6. performance_reviews ────────────────────────────
    op.create_table(
        'performance_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('performance_templates.id'), nullable=True),
        sa.Column('review_period', sa.String(10), nullable=False),
        sa.Column('status', postgresql.ENUM('draft', 'self_review', 'manager', 'completed', 'appealed',
                                             name='review_status_enum', create_type=False),
                  nullable=False, server_default='draft'),
        sa.Column('dimension_scores', sa.JSON, nullable=True),
        sa.Column('total_score', sa.Numeric(5, 1), nullable=True),
        sa.Column('level', postgresql.ENUM('S', 'A', 'B', 'C', 'D',
                                            name='review_level_enum', create_type=False),
                  nullable=True),
        sa.Column('self_score', sa.Numeric(5, 1), nullable=True),
        sa.Column('self_comment', sa.Text, nullable=True),
        sa.Column('manager_score', sa.Numeric(5, 1), nullable=True),
        sa.Column('manager_comment', sa.Text, nullable=True),
        sa.Column('reviewer_id', sa.String(50), nullable=True),
        sa.Column('reviewer_name', sa.String(100), nullable=True),
        sa.Column('performance_coefficient', sa.Numeric(4, 2), nullable=True),
        sa.Column('improvement_plan', sa.Text, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_prvw_store_id', 'performance_reviews', ['store_id'])
    op.create_index('ix_prvw_employee_id', 'performance_reviews', ['employee_id'])
    op.create_index('ix_prvw_period', 'performance_reviews', ['review_period'])
    op.create_index('ix_prvw_status', 'performance_reviews', ['status'])
    op.create_unique_constraint('uq_perf_review_period', 'performance_reviews',
                                ['employee_id', 'review_period'])

    # ── 7. employee_contracts ─────────────────────────────
    op.create_table(
        'employee_contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('contract_type', postgresql.ENUM(
            'fixed_term', 'open_ended', 'part_time', 'internship', 'probation',
            name='contract_type_enum', create_type=False), nullable=False, server_default='fixed_term'),
        sa.Column('status', postgresql.ENUM(
            'draft', 'active', 'expiring', 'expired', 'terminated', 'renewed',
            name='contract_status_enum', create_type=False),
            nullable=False, server_default='draft'),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=True),
        sa.Column('sign_date', sa.Date, nullable=True),
        sa.Column('probation_end_date', sa.Date, nullable=True),
        sa.Column('probation_salary_pct', sa.Integer, server_default='80'),
        sa.Column('contract_no', sa.String(50), nullable=True, unique=True),
        sa.Column('agreed_salary_fen', sa.Integer, nullable=True),
        sa.Column('salary_type', sa.String(20), server_default='monthly'),
        sa.Column('position', sa.String(50), nullable=True),
        sa.Column('department', sa.String(50), nullable=True),
        sa.Column('work_location', sa.String(100), nullable=True),
        sa.Column('renewal_count', sa.Integer, server_default='0'),
        sa.Column('previous_contract_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('renewal_reminder_sent', sa.Boolean, server_default='false'),
        sa.Column('esign_status', sa.String(20), nullable=True),
        sa.Column('esign_url', sa.String(500), nullable=True),
        sa.Column('signed_pdf_url', sa.String(500), nullable=True),
        sa.Column('termination_date', sa.Date, nullable=True),
        sa.Column('termination_reason', sa.Text, nullable=True),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ectr_store_id', 'employee_contracts', ['store_id'])
    op.create_index('ix_ectr_employee_id', 'employee_contracts', ['employee_id'])
    op.create_index('ix_ectr_status', 'employee_contracts', ['status'])


def downgrade() -> None:
    op.drop_index('ix_ectr_status', table_name='employee_contracts')
    op.drop_index('ix_ectr_employee_id', table_name='employee_contracts')
    op.drop_index('ix_ectr_store_id', table_name='employee_contracts')
    op.drop_table('employee_contracts')

    op.drop_constraint('uq_perf_review_period', 'performance_reviews', type_='unique')
    op.drop_index('ix_prvw_status', table_name='performance_reviews')
    op.drop_index('ix_prvw_period', table_name='performance_reviews')
    op.drop_index('ix_prvw_employee_id', table_name='performance_reviews')
    op.drop_index('ix_prvw_store_id', table_name='performance_reviews')
    op.drop_table('performance_reviews')

    op.drop_index('ix_pt_brand_id', table_name='performance_templates')
    op.drop_index('ix_pt_store_id', table_name='performance_templates')
    op.drop_table('performance_templates')

    op.drop_index('ix_off_status', table_name='offers')
    op.drop_index('ix_off_store_id', table_name='offers')
    op.drop_index('ix_off_candidate_id', table_name='offers')
    op.drop_table('offers')

    op.drop_index('ix_int_store_id', table_name='interviews')
    op.drop_index('ix_int_candidate_id', table_name='interviews')
    op.drop_table('interviews')

    op.drop_index('ix_cand_stage', table_name='candidates')
    op.drop_index('ix_cand_store_id', table_name='candidates')
    op.drop_index('ix_cand_job_id', table_name='candidates')
    op.drop_table('candidates')

    op.drop_index('ix_jp_status', table_name='job_postings')
    op.drop_index('ix_jp_brand_id', table_name='job_postings')
    op.drop_index('ix_jp_store_id', table_name='job_postings')
    op.drop_table('job_postings')

    op.execute("DROP TYPE IF EXISTS contract_status_enum")
    op.execute("DROP TYPE IF EXISTS contract_type_enum")
    op.execute("DROP TYPE IF EXISTS review_level_enum")
    op.execute("DROP TYPE IF EXISTS review_status_enum")
    op.execute("DROP TYPE IF EXISTS review_cycle_enum")
    op.execute("DROP TYPE IF EXISTS offer_status_enum")
    op.execute("DROP TYPE IF EXISTS interview_result_enum")
    op.execute("DROP TYPE IF EXISTS candidate_stage_enum")
    op.execute("DROP TYPE IF EXISTS job_status_enum")
