"""z17 — 财务健康评分系统

Phase 5 Month 5

Tables:
  finance_health_scores — 5维度综合健康评分（按门店+期间唯一）
  finance_insights      — AI文字洞察条目

Scoring dimensions:
  profit_score       /30  — 利润率健康度
  cash_score         /20  — 现金流健康度
  tax_score          /20  — 税务合规度
  settlement_score   /15  — 结算稳定性
  budget_score       /15  — 预算执行度
  total_score        /100
  grade              A(≥80) / B(60-79) / C(40-59) / D(<40)

Revision ID: z17
Revises: z16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = 'z17'
down_revision = 'z16'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── finance_health_scores ─────────────────────────────────────────────────
    op.create_table(
        'finance_health_scores',
        sa.Column('id',               sa.String(36),     primary_key=True),
        sa.Column('store_id',         sa.String(64),     nullable=False),
        sa.Column('period',           sa.String(7),      nullable=False),   # YYYY-MM
        sa.Column('total_score',      sa.Numeric(5, 2),  nullable=False),
        sa.Column('grade',            sa.String(2),      nullable=False),   # A/B/C/D
        sa.Column('profit_score',     sa.Numeric(5, 2),  server_default='0'),
        sa.Column('cash_score',       sa.Numeric(5, 2),  server_default='0'),
        sa.Column('tax_score',        sa.Numeric(5, 2),  server_default='0'),
        sa.Column('settlement_score', sa.Numeric(5, 2),  server_default='0'),
        sa.Column('budget_score',     sa.Numeric(5, 2),  server_default='0'),
        # Raw metric snapshots for display
        sa.Column('profit_margin_pct',    sa.Numeric(8, 2)),
        sa.Column('net_revenue_yuan',     sa.Numeric(15, 2)),
        sa.Column('cash_gap_days',        sa.Integer()),
        sa.Column('avg_tax_deviation_pct',sa.Numeric(8, 2)),
        sa.Column('high_risk_settlement', sa.Integer()),
        sa.Column('budget_achievement_pct', sa.Numeric(8, 2)),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint(
        'uq_finance_health_store_period', 'finance_health_scores', ['store_id', 'period'],
    )
    op.create_index('ix_finance_health_store', 'finance_health_scores', ['store_id'])

    # ── finance_insights ──────────────────────────────────────────────────────
    op.create_table(
        'finance_insights',
        sa.Column('id',           sa.String(36),  primary_key=True),
        sa.Column('store_id',     sa.String(64),  nullable=False),
        sa.Column('period',       sa.String(7),   nullable=False),
        sa.Column('insight_type', sa.String(50),  nullable=False),
        sa.Column('priority',     sa.String(20),  nullable=False, server_default='medium'),
        sa.Column('content',      sa.Text(),      nullable=False),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_finance_insights_store_period', 'finance_insights', ['store_id', 'period'])


def downgrade() -> None:
    op.drop_table('finance_insights')
    op.drop_table('finance_health_scores')
