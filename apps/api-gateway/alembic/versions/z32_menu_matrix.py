"""z32 — 菜品组合矩阵分析引擎 (BCG Menu Matrix)

Phase 6 Month 10

Table:
  menu_matrix_results — 按期对全菜品做 BCG 四象限分类
    revenue_percentile : 当期营收在门店内的百分位 (0-100)
    growth_percentile  : 营收增长率在门店内的百分位 (0-100)
    matrix_quadrant    : star / cash_cow / question_mark / dog
    optimization_action: promote / maintain / develop / retire
    action_priority    : high / medium / low
    expected_impact_yuan: 推荐动作预期带来的 ¥ 影响
    UNIQUE: store_id + period + dish_id
"""

revision      = 'z32'
down_revision = 'z31'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        'menu_matrix_results',
        sa.Column('id',              sa.Integer,      primary_key=True),
        sa.Column('store_id',        sa.String(64),   nullable=False),
        sa.Column('period',          sa.String(7),    nullable=False),
        sa.Column('prev_period',     sa.String(7),    nullable=False),
        sa.Column('dish_id',         sa.String(128),  nullable=False),
        sa.Column('dish_name',       sa.String(128),  nullable=False),
        sa.Column('category',        sa.String(64),   nullable=True),
        # 当期营收
        sa.Column('revenue_yuan',        sa.Numeric(14, 2), nullable=False),
        sa.Column('order_count',         sa.Integer,        nullable=False),
        sa.Column('menu_contribution_pct', sa.Numeric(6, 2), nullable=True),
        # 增长
        sa.Column('prev_revenue_yuan',   sa.Numeric(14, 2), nullable=True),
        sa.Column('revenue_delta_pct',   sa.Numeric(7, 2),  nullable=True),
        # 百分位
        sa.Column('revenue_percentile',  sa.Numeric(5, 1),  nullable=False),
        sa.Column('growth_percentile',   sa.Numeric(5, 1),  nullable=False),
        # 矩阵
        sa.Column('matrix_quadrant',     sa.String(16),     nullable=False),
        sa.Column('optimization_action', sa.String(16),     nullable=False),
        sa.Column('action_priority',     sa.String(8),      nullable=False),
        sa.Column('expected_impact_yuan', sa.Numeric(14, 2), nullable=True),
        # 时间
        sa.Column('computed_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at',  sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_menu_matrix_store_period_dish',
        'menu_matrix_results',
        ['store_id', 'period', 'dish_id'],
    )
    op.create_index('ix_menu_matrix_store_period',
                    'menu_matrix_results', ['store_id', 'period'])
    op.create_index('ix_menu_matrix_store_period_quadrant',
                    'menu_matrix_results', ['store_id', 'period', 'matrix_quadrant'])
    op.create_index('ix_menu_matrix_store_period_priority',
                    'menu_matrix_results', ['store_id', 'period', 'action_priority'])


def downgrade() -> None:
    op.drop_index('ix_menu_matrix_store_period_priority',
                  table_name='menu_matrix_results')
    op.drop_index('ix_menu_matrix_store_period_quadrant',
                  table_name='menu_matrix_results')
    op.drop_index('ix_menu_matrix_store_period',
                  table_name='menu_matrix_results')
    op.drop_constraint('uq_menu_matrix_store_period_dish',
                       'menu_matrix_results', type_='unique')
    op.drop_table('menu_matrix_results')
