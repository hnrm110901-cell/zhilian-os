"""z23 — 菜品盈利能力分析引擎

Phase 6 Month 1

Tables:
  dish_profitability_records — 门店级菜品月度盈利能力快照
    UNIQUE: store_id + period + dish_id
    BCG 四象限：star / cash_cow / question_mark / dog
"""

revision      = 'z23'
down_revision = 'z22'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'dish_profitability_records',
        sa.Column('id',                    sa.Integer,      primary_key=True),
        sa.Column('store_id',              sa.String(64),   nullable=False),
        sa.Column('period',                sa.String(7),    nullable=False),   # YYYY-MM
        sa.Column('dish_id',               sa.String(64),   nullable=False),
        sa.Column('dish_name',             sa.String(128),  nullable=False),
        sa.Column('category',              sa.String(64),   nullable=True),
        # 销售量
        sa.Column('order_count',           sa.Integer,      nullable=False, server_default='0'),
        sa.Column('avg_selling_price',     sa.Numeric(10, 2), nullable=True),  # 均售价
        # 收入与成本
        sa.Column('revenue_yuan',          sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('food_cost_yuan',        sa.Numeric(14, 2), nullable=True),
        sa.Column('food_cost_rate',        sa.Numeric(6, 2),  nullable=True),   # %
        # 毛利
        sa.Column('gross_profit_yuan',     sa.Numeric(14, 2), nullable=True),
        sa.Column('gross_profit_margin',   sa.Numeric(6, 2),  nullable=True),   # %
        # 排名与百分位（在同店同期所有菜品中）
        sa.Column('popularity_rank',       sa.Integer,      nullable=True),     # by order_count
        sa.Column('profitability_rank',    sa.Integer,      nullable=True),     # by gross_profit_margin
        sa.Column('popularity_percentile', sa.Numeric(5, 1), nullable=True),
        sa.Column('profit_percentile',     sa.Numeric(5, 1), nullable=True),
        # BCG 四象限
        sa.Column('bcg_quadrant',          sa.String(16),   nullable=True),
        # star / cash_cow / question_mark / dog
        # 时间
        sa.Column('computed_at',           sa.DateTime,     server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at',            sa.DateTime,     server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_dish_profit_store_period_dish',
        'dish_profitability_records',
        ['store_id', 'period', 'dish_id'],
    )
    op.create_index('ix_dish_profit_store_period',   'dish_profitability_records', ['store_id', 'period'])
    op.create_index('ix_dish_profit_bcg',            'dish_profitability_records', ['store_id', 'period', 'bcg_quadrant'])


def downgrade() -> None:
    op.drop_index('ix_dish_profit_bcg',          table_name='dish_profitability_records')
    op.drop_index('ix_dish_profit_store_period', table_name='dish_profitability_records')
    op.drop_constraint('uq_dish_profit_store_period_dish', 'dish_profitability_records', type_='unique')
    op.drop_table('dish_profitability_records')
