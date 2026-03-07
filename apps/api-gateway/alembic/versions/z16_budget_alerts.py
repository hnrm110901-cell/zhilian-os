"""z16 — 预算管理 + 财务预警体系

Phase 5 Month 4

Tables:
  budget_plans           — 预算计划 (draft→approved→active→closed FSM)
  budget_line_items      — 预算明细行（按类目）
  financial_alert_rules  — 财务预警规则
  financial_alert_events — 预警事件 (open→acknowledged→resolved FSM)

Revision ID: z16
Revises: z15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision    = 'z16'
down_revision = 'z15'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── budget_plans ──────────────────────────────────────────────────────────
    op.create_table(
        'budget_plans',
        sa.Column('id',                   sa.String(36),      primary_key=True),
        sa.Column('store_id',             sa.String(64),      nullable=False),
        sa.Column('brand_id',             sa.String(64)),
        sa.Column('period',               sa.String(7),       nullable=False),   # YYYY-MM
        sa.Column('period_type',          sa.String(20),      nullable=False,  server_default='monthly'),
        sa.Column('status',               sa.String(20),      nullable=False,  server_default='draft'),
        sa.Column('total_revenue_budget', sa.Numeric(15, 2),  server_default='0'),
        sa.Column('total_cost_budget',    sa.Numeric(15, 2),  server_default='0'),
        sa.Column('profit_budget',        sa.Numeric(15, 2),  server_default='0'),
        sa.Column('notes',                sa.Text()),
        sa.Column('approved_at',          sa.DateTime(timezone=True)),
        sa.Column('created_at',           sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at',           sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_budget_plans_store_period', 'budget_plans', ['store_id', 'period'])
    op.create_unique_constraint(
        'uq_budget_plans_store_period_type', 'budget_plans',
        ['store_id', 'period', 'period_type'],
    )

    # ── budget_line_items ─────────────────────────────────────────────────────
    op.create_table(
        'budget_line_items',
        sa.Column('id',           sa.String(36),     primary_key=True),
        sa.Column('plan_id',      sa.String(36),     nullable=False),
        sa.Column('category',     sa.String(50),     nullable=False),
        sa.Column('sub_category', sa.String(100)),
        sa.Column('budget_yuan',  sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('period',       sa.String(7),      nullable=False),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['plan_id'], ['budget_plans.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_budget_line_items_plan', 'budget_line_items', ['plan_id'])

    # ── financial_alert_rules ─────────────────────────────────────────────────
    op.create_table(
        'financial_alert_rules',
        sa.Column('id',               sa.String(36),      primary_key=True),
        sa.Column('store_id',         sa.String(64),      nullable=False),
        sa.Column('brand_id',         sa.String(64)),
        sa.Column('metric',           sa.String(64),      nullable=False),
        sa.Column('threshold_type',   sa.String(20),      nullable=False),   # above/below/abs_above
        sa.Column('threshold_value',  sa.Numeric(15, 4),  nullable=False),
        sa.Column('severity',         sa.String(20),      nullable=False, server_default='warning'),
        sa.Column('enabled',          sa.Boolean(),       nullable=False, server_default='true'),
        sa.Column('cooldown_minutes', sa.Integer(),       nullable=False, server_default='60'),
        sa.Column('created_at',       sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at',       sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_fin_alert_rules_store', 'financial_alert_rules', ['store_id'])
    # Partial index: only enabled rules (reduces lock contention during evaluation)
    op.create_index(
        'ix_fin_alert_rules_enabled', 'financial_alert_rules', ['store_id'],
        postgresql_where=sa.text("enabled = true"),
    )

    # ── financial_alert_events ────────────────────────────────────────────────
    op.create_table(
        'financial_alert_events',
        sa.Column('id',              sa.String(36),      primary_key=True),
        sa.Column('rule_id',         sa.String(36),      nullable=False),
        sa.Column('store_id',        sa.String(64),      nullable=False),
        sa.Column('metric',          sa.String(64),      nullable=False),
        sa.Column('current_value',   sa.Numeric(15, 4)),
        sa.Column('threshold_value', sa.Numeric(15, 4)),
        sa.Column('severity',        sa.String(20),      nullable=False),
        sa.Column('message',         sa.Text()),
        sa.Column('status',          sa.String(20),      nullable=False, server_default='open'),
        sa.Column('period',          sa.String(7)),
        sa.Column('triggered_at',    sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True)),
        sa.Column('resolved_at',     sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['rule_id'], ['financial_alert_rules.id'], ondelete='CASCADE'),
    )
    op.create_index(
        'ix_fin_alert_events_store_status', 'financial_alert_events', ['store_id', 'status'],
    )
    # Partial index: open alerts only (hot path for dashboard queries)
    op.create_index(
        'ix_fin_alert_events_open', 'financial_alert_events', ['store_id'],
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_table('financial_alert_events')
    op.drop_table('financial_alert_rules')
    op.drop_table('budget_line_items')
    op.drop_table('budget_plans')
