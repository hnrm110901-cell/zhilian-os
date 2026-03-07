"""z31 — 菜品营收归因引擎 (Price-Volume-Mix)

Phase 6 Month 9

Table:
  dish_revenue_attribution — 逐期对比，将营收变化拆解为价格/销量/交互三个效应
    UNIQUE: store_id + period + dish_id
    period:      当前比较期 (YYYY-MM)
    prev_period: 对比基准期 (YYYY-MM)
    primary_driver: price / volume / interaction / mixed / stable
"""

revision      = 'z31'
down_revision = 'z30'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'dish_revenue_attribution',
        sa.Column('id',              sa.Integer,      primary_key=True),
        sa.Column('store_id',        sa.String(64),   nullable=False),
        sa.Column('period',          sa.String(7),    nullable=False),
        sa.Column('prev_period',     sa.String(7),    nullable=False),
        sa.Column('dish_id',         sa.String(128),  nullable=False),
        sa.Column('dish_name',       sa.String(128),  nullable=False),
        sa.Column('category',        sa.String(64),   nullable=True),
        # 当期 vs 上期数值
        sa.Column('current_revenue', sa.Numeric(14, 2), nullable=False),
        sa.Column('prev_revenue',    sa.Numeric(14, 2), nullable=False),
        sa.Column('revenue_delta',   sa.Numeric(14, 2), nullable=False),
        sa.Column('revenue_delta_pct', sa.Numeric(7, 2), nullable=True),
        sa.Column('current_orders',  sa.Integer,        nullable=False),
        sa.Column('prev_orders',     sa.Integer,        nullable=False),
        sa.Column('order_delta',     sa.Integer,        nullable=False),
        sa.Column('order_delta_pct', sa.Numeric(7, 2),  nullable=True),
        sa.Column('current_avg_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('prev_avg_price',    sa.Numeric(10, 2), nullable=True),
        sa.Column('price_delta',       sa.Numeric(10, 2), nullable=True),
        sa.Column('price_delta_pct',   sa.Numeric(7, 2),  nullable=True),
        # PVM 归因 (¥，可负)
        sa.Column('price_effect_yuan',  sa.Numeric(14, 2), nullable=True),
        sa.Column('volume_effect_yuan', sa.Numeric(14, 2), nullable=True),
        sa.Column('interaction_yuan',   sa.Numeric(14, 2), nullable=True),
        # 主要驱动因子
        sa.Column('primary_driver', sa.String(16), nullable=False),
        # 时间
        sa.Column('computed_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at',  sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_dish_attribution_store_period_dish',
        'dish_revenue_attribution',
        ['store_id', 'period', 'dish_id'],
    )
    op.create_index('ix_dish_attr_store_period',
                    'dish_revenue_attribution', ['store_id', 'period'])
    op.create_index('ix_dish_attr_store_period_driver',
                    'dish_revenue_attribution', ['store_id', 'period', 'primary_driver'])


def downgrade() -> None:
    op.drop_index('ix_dish_attr_store_period_driver',
                  table_name='dish_revenue_attribution')
    op.drop_index('ix_dish_attr_store_period',
                  table_name='dish_revenue_attribution')
    op.drop_constraint('uq_dish_attribution_store_period_dish',
                       'dish_revenue_attribution', type_='unique')
    op.drop_table('dish_revenue_attribution')
