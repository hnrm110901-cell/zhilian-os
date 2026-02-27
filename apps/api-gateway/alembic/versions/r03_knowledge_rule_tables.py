"""
Phase 3-M3.3 — 推理规则库表

Revision ID: r03_knowledge_rule_tables
Revises: r02_security_tables
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'r03_knowledge_rule_tables'
down_revision = 'r02_security_tables'
branch_labels = None
depends_on = None

_RULE_CATEGORIES = ('waste', 'efficiency', 'quality', 'cost', 'traffic', 'inventory', 'compliance', 'benchmark')
_RULE_TYPES = ('threshold', 'pattern', 'anomaly', 'causal', 'benchmark')
_RULE_STATUSES = ('draft', 'active', 'inactive', 'archived')


def upgrade() -> None:
    rule_cat_enum = postgresql.ENUM(*_RULE_CATEGORIES, name='rulecategory')
    rule_cat_enum.create(op.get_bind(), checkfirst=True)
    rule_type_enum = postgresql.ENUM(*_RULE_TYPES, name='ruletype')
    rule_type_enum.create(op.get_bind(), checkfirst=True)
    rule_status_enum = postgresql.ENUM(*_RULE_STATUSES, name='rulestatus')
    rule_status_enum.create(op.get_bind(), checkfirst=True)

    # ── knowledge_rules ────────────────────────────────────────────────────────
    op.create_table(
        'knowledge_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rule_code', sa.String(50), unique=True, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', rule_cat_enum, nullable=False),
        sa.Column('rule_type', rule_type_enum, nullable=False, server_default='threshold'),
        sa.Column('condition', postgresql.JSON(), nullable=False),
        sa.Column('conclusion', postgresql.JSON(), nullable=False),
        sa.Column('base_confidence', sa.Float(), nullable=False, server_default='0.7'),
        sa.Column('weight', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('applicable_store_ids', postgresql.JSON(), nullable=True),
        sa.Column('applicable_dish_categories', postgresql.JSON(), nullable=True),
        sa.Column('industry_type', sa.String(50), nullable=True),
        sa.Column('status', rule_status_enum, nullable=False, server_default='draft'),
        sa.Column('hit_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('correct_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('accuracy_rate', sa.Float(), nullable=True),
        sa.Column('last_hit_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source', sa.String(50), nullable=True, server_default='expert'),
        sa.Column('contributed_by', sa.String(100), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tags', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_rule_category_status', 'knowledge_rules', ['category', 'status'])
    op.create_index('idx_rule_industry_type', 'knowledge_rules', ['industry_type'])
    op.create_index('idx_rule_source', 'knowledge_rules', ['source'])

    # ── rule_executions ────────────────────────────────────────────────────────
    op.create_table(
        'rule_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rule_code', sa.String(50), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('event_id', sa.String(100), nullable=True),
        sa.Column('dish_id', sa.String(100), nullable=True),
        sa.Column('condition_values', postgresql.JSON(), nullable=True),
        sa.Column('conclusion_output', postgresql.JSON(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('verified_by', sa.String(100), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_rule_exec_store_date', 'rule_executions', ['store_id', 'executed_at'])
    op.create_index('idx_rule_exec_rule_id', 'rule_executions', ['rule_id'])

    # ── industry_benchmarks ────────────────────────────────────────────────────
    op.create_table(
        'industry_benchmarks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('industry_type', sa.String(50), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_category', rule_cat_enum, nullable=False),
        sa.Column('p25_value', sa.Float(), nullable=True),
        sa.Column('p50_value', sa.Float(), nullable=True),
        sa.Column('p75_value', sa.Float(), nullable=True),
        sa.Column('p90_value', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(20), nullable=True),
        sa.Column('direction', sa.String(10), nullable=True),
        sa.Column('data_source', sa.String(200), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('industry_type', 'metric_name', name='uq_benchmark_type_metric'),
    )
    op.create_index('idx_benchmark_type', 'industry_benchmarks', ['industry_type'])


def downgrade() -> None:
    op.drop_table('industry_benchmarks')
    op.drop_table('rule_executions')
    op.drop_table('knowledge_rules')
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS rulestatus"))
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS ruletype"))
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS rulecategory"))
