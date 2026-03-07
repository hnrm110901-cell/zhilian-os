"""z30 — 菜品综合健康评分引擎

Phase 6 Month 8

Table:
  dish_health_scores — 整合盈利/成长/对标/预测 4 维度，输出综合健康评分
    UNIQUE: store_id + period + dish_id
    health_tier: excellent / good / fair / poor
    action_priority: immediate / monitor / maintain / promote
"""

revision      = 'z30'
down_revision = 'z29'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'dish_health_scores',
        sa.Column('id',              sa.Integer,      primary_key=True),
        sa.Column('store_id',        sa.String(64),   nullable=False),
        sa.Column('period',          sa.String(7),    nullable=False),
        sa.Column('dish_id',         sa.String(128),  nullable=False),
        sa.Column('dish_name',       sa.String(128),  nullable=False),
        sa.Column('category',        sa.String(64),   nullable=True),
        # 4 维度评分 (各 0-25)
        sa.Column('profitability_score', sa.Numeric(5, 1), nullable=False),
        sa.Column('growth_score',        sa.Numeric(5, 1), nullable=False),
        sa.Column('benchmark_score',     sa.Numeric(5, 1), nullable=False),
        sa.Column('forecast_score',      sa.Numeric(5, 1), nullable=False),
        # 综合
        sa.Column('total_score',     sa.Numeric(5, 1),  nullable=False),
        sa.Column('health_tier',     sa.String(16),     nullable=False),
        sa.Column('top_strength',    sa.String(32),     nullable=True),
        sa.Column('top_weakness',    sa.String(32),     nullable=True),
        # 行动建议
        sa.Column('action_priority',    sa.String(16),   nullable=False),
        sa.Column('action_label',       sa.String(32),   nullable=True),
        sa.Column('action_description', sa.Text,         nullable=True),
        sa.Column('expected_impact_yuan', sa.Numeric(14, 2), nullable=True),
        # 辅助字段（用于前端显示，不重新 JOIN）
        sa.Column('lifecycle_phase', sa.String(16),   nullable=True),
        sa.Column('revenue_yuan',    sa.Numeric(14, 2), nullable=True),
        # 时间
        sa.Column('computed_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at',  sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_dish_health_store_period_dish',
        'dish_health_scores',
        ['store_id', 'period', 'dish_id'],
    )
    op.create_index('ix_dish_health_store_period',
                    'dish_health_scores', ['store_id', 'period'])
    op.create_index('ix_dish_health_store_period_tier',
                    'dish_health_scores', ['store_id', 'period', 'health_tier'])
    op.create_index('ix_dish_health_store_period_priority',
                    'dish_health_scores', ['store_id', 'period', 'action_priority'])


def downgrade() -> None:
    op.drop_index('ix_dish_health_store_period_priority',
                  table_name='dish_health_scores')
    op.drop_index('ix_dish_health_store_period_tier',
                  table_name='dish_health_scores')
    op.drop_index('ix_dish_health_store_period',
                  table_name='dish_health_scores')
    op.drop_constraint('uq_dish_health_store_period_dish',
                       'dish_health_scores', type_='unique')
    op.drop_table('dish_health_scores')
