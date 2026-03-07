"""z34 — 菜品经营综合月报引擎

Phase 6 Month 12（Phase 6 收官）

Table:
  dish_monthly_summaries — 聚合所有菜品分析引擎的月度汇总报表
    从以下数据源拉取：
      dish_profitability_records  → 营收/成本基线
      dish_health_scores          → 健康评分分布（如已计算）
      menu_matrix_results         → BCG 矩阵分布（如已计算）
      dish_revenue_attribution    → PVM 归因汇总（如已计算）
      dish_cost_compression       → 成本压缩机会（如已计算）
    data_sources_available: 可用数据源数量（最高 5）
    insight_text: 规则驱动的经营洞察文本
    UNIQUE: store_id + period
"""

revision      = 'z34'
down_revision = 'z33'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'dish_monthly_summaries',
        sa.Column('id',       sa.Integer,    primary_key=True),
        sa.Column('store_id', sa.String(64), nullable=False),
        sa.Column('period',   sa.String(7),  nullable=False),
        sa.Column('prev_period', sa.String(7), nullable=True),

        # ── 营收基线 ─────────────────────────────────────────
        sa.Column('total_dishes',      sa.Integer,        nullable=False),
        sa.Column('total_revenue',     sa.Numeric(14, 2), nullable=False),
        sa.Column('prev_revenue',      sa.Numeric(14, 2), nullable=True),
        sa.Column('revenue_delta_pct', sa.Numeric(7, 2),  nullable=True),

        # ── 健康评分（dish_health_scores）──────────────────
        sa.Column('avg_health_score',      sa.Numeric(5, 1), nullable=True),
        sa.Column('excellent_count',       sa.Integer,       nullable=True),
        sa.Column('good_count',            sa.Integer,       nullable=True),
        sa.Column('fair_count',            sa.Integer,       nullable=True),
        sa.Column('poor_count',            sa.Integer,       nullable=True),
        sa.Column('immediate_action_count', sa.Integer,      nullable=True),

        # ── BCG 矩阵（menu_matrix_results）────────────────
        sa.Column('star_count',          sa.Integer,        nullable=True),
        sa.Column('cash_cow_count',      sa.Integer,        nullable=True),
        sa.Column('question_mark_count', sa.Integer,        nullable=True),
        sa.Column('dog_count',           sa.Integer,        nullable=True),
        sa.Column('matrix_total_impact_yuan', sa.Numeric(14, 2), nullable=True),

        # ── PVM 归因（dish_revenue_attribution）───────────
        sa.Column('pvm_dish_count',        sa.Integer,        nullable=True),
        sa.Column('total_pvm_delta',       sa.Numeric(14, 2), nullable=True),
        sa.Column('total_price_effect',    sa.Numeric(14, 2), nullable=True),
        sa.Column('total_volume_effect',   sa.Numeric(14, 2), nullable=True),
        sa.Column('dominant_driver',       sa.String(16),     nullable=True),

        # ── 成本压缩（dish_cost_compression）──────────────
        sa.Column('compression_dish_count',         sa.Integer,        nullable=True),
        sa.Column('total_compression_opportunity',  sa.Numeric(14, 2), nullable=True),
        sa.Column('total_expected_saving',          sa.Numeric(14, 2), nullable=True),
        sa.Column('renegotiate_count',              sa.Integer,        nullable=True),
        sa.Column('worsening_fcr_count',            sa.Integer,        nullable=True),

        # ── 报告元数据 ───────────────────────────────────
        sa.Column('data_sources_available', sa.Integer,    nullable=False),
        sa.Column('insight_text',           sa.Text,        nullable=True),
        sa.Column('generated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at',   sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_dish_monthly_summaries_store_period',
        'dish_monthly_summaries',
        ['store_id', 'period'],
    )
    op.create_index('ix_dms_store_period',
                    'dish_monthly_summaries', ['store_id', 'period'])


def downgrade() -> None:
    op.drop_index('ix_dms_store_period', table_name='dish_monthly_summaries')
    op.drop_constraint('uq_dish_monthly_summaries_store_period',
                       'dish_monthly_summaries', type_='unique')
    op.drop_table('dish_monthly_summaries')
