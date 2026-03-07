"""z26 — 跨店菜品对标引擎

Phase 6 Month 4

Table:
  dish_benchmark_records — 同名菜品跨门店横向对标
    UNIQUE: period + dish_name + store_id
    记录每家门店在该菜品维度的 FCR/GPM 排名、分位、与最优门店的差距¥
"""

revision      = 'z26'
down_revision = 'z25'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'dish_benchmark_records',
        sa.Column('id',          sa.Integer,      primary_key=True),
        sa.Column('period',      sa.String(7),    nullable=False),     # YYYY-MM
        sa.Column('dish_name',   sa.String(128),  nullable=False),
        sa.Column('store_id',    sa.String(64),   nullable=False),
        sa.Column('store_count', sa.Integer,      nullable=False, server_default='0'),
        # 本店当期指标快照
        sa.Column('food_cost_rate',      sa.Numeric(6, 2),  nullable=True),
        sa.Column('gross_profit_margin', sa.Numeric(6, 2),  nullable=True),
        sa.Column('order_count',         sa.Integer,        nullable=True),
        sa.Column('revenue_yuan',        sa.Numeric(14, 2), nullable=True),
        # FCR 对标（lower is better）
        sa.Column('fcr_rank',            sa.Integer,        nullable=True),
        sa.Column('fcr_percentile',      sa.Numeric(5, 1),  nullable=True),
        sa.Column('fcr_tier',            sa.String(16),     nullable=True),
        # top / above_avg / below_avg / laggard
        sa.Column('best_fcr_value',      sa.Numeric(6, 2),  nullable=True),
        sa.Column('best_fcr_store_id',   sa.String(64),     nullable=True),
        sa.Column('fcr_gap_pp',          sa.Numeric(6, 2),  nullable=True),   # 本店-最优 pp
        sa.Column('fcr_gap_yuan_impact', sa.Numeric(14, 2), nullable=True),   # ¥ 潜力
        # GPM 对标（higher is better）
        sa.Column('gpm_rank',            sa.Integer,        nullable=True),
        sa.Column('gpm_percentile',      sa.Numeric(5, 1),  nullable=True),
        sa.Column('gpm_tier',            sa.String(16),     nullable=True),
        sa.Column('best_gpm_value',      sa.Numeric(6, 2),  nullable=True),
        sa.Column('best_gpm_store_id',   sa.String(64),     nullable=True),
        sa.Column('gpm_gap_pp',          sa.Numeric(6, 2),  nullable=True),   # 最优-本店 pp
        sa.Column('gpm_gap_yuan_impact', sa.Numeric(14, 2), nullable=True),
        # 时间
        sa.Column('computed_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at',  sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_dish_bench_period_dish_store',
        'dish_benchmark_records',
        ['period', 'dish_name', 'store_id'],
    )
    op.create_index('ix_dish_bench_period_store',
                    'dish_benchmark_records', ['period', 'store_id'])
    op.create_index('ix_dish_bench_period_dish',
                    'dish_benchmark_records', ['period', 'dish_name'])
    op.create_index('ix_dish_bench_tier',
                    'dish_benchmark_records', ['period', 'store_id', 'fcr_tier'])


def downgrade() -> None:
    op.drop_index('ix_dish_bench_tier',         table_name='dish_benchmark_records')
    op.drop_index('ix_dish_bench_period_dish',  table_name='dish_benchmark_records')
    op.drop_index('ix_dish_bench_period_store', table_name='dish_benchmark_records')
    op.drop_constraint('uq_dish_bench_period_dish_store',
                       'dish_benchmark_records', type_='unique')
    op.drop_table('dish_benchmark_records')
