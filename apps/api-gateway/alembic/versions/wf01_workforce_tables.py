"""wf01 — Phase 8 人力经营决策层：6张核心表

Tables:
  labor_demand_forecasts      — 客流预测 → 各岗位人数推荐（LaborDemandService 输出）
  labor_cost_snapshots        — 每日人工成本率快照（LaborCostService 输出）
  staffing_advice             — AI 排班建议卡 + 3条推理链（WorkforcePushService 输出）
  staffing_advice_confirmations — 店长确认/拒绝/修改行为追踪（采纳率计算）
  store_labor_budgets         — 门店月度人力预算配置
  labor_cost_rankings         — 跨店成本率排名快照（支持"你在X家中排第Y"）

Enum types (PostgreSQL native):
  meal_period_type, staffing_advice_status, confirmation_action,
  budget_period_type, ranking_period_type
"""

revision      = 'wf01'
down_revision = 'z34'
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # ── Enum 类型 ─────────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            CREATE TYPE meal_period_type AS ENUM ('morning','lunch','dinner','all_day');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("CREATE TYPE staffing_advice_status AS ENUM ('pending','confirmed','rejected','expired')")
    op.execute("CREATE TYPE confirmation_action AS ENUM ('confirmed','rejected','modified')")
    op.execute("CREATE TYPE budget_period_type AS ENUM ('monthly','weekly')")
    op.execute("CREATE TYPE ranking_period_type AS ENUM ('daily','weekly','monthly')")

    # ── 1. labor_demand_forecasts ────────────────────────
    op.create_table(
        'labor_demand_forecasts',
        sa.Column('id',            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id',      sa.String(50),  sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('forecast_date', sa.Date,        nullable=False),
        sa.Column('meal_period',   postgresql.ENUM('morning','lunch','dinner','all_day',
                                                   name='meal_period_type', create_type=False),
                  nullable=False),

        sa.Column('predicted_customer_count', sa.Integer,        nullable=False),
        sa.Column('predicted_revenue_yuan',   sa.Numeric(12, 2), nullable=True),
        sa.Column('confidence_score',         sa.Numeric(4, 3),  nullable=False),

        sa.Column('position_requirements',  sa.JSON, nullable=False, server_default='{}'),
        sa.Column('total_headcount_needed', sa.Integer, nullable=False),

        sa.Column('factor_holiday_weight', sa.Numeric(5, 3), nullable=True),
        sa.Column('factor_weather_score',  sa.Numeric(5, 3), nullable=True),
        sa.Column('factor_historical_avg', sa.Integer,       nullable=True),

        sa.Column('model_version', sa.String(32), nullable=True),

        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ldf_store_date', 'labor_demand_forecasts', ['store_id', 'forecast_date'])
    op.create_unique_constraint(
        'uq_ldf_store_date_period',
        'labor_demand_forecasts',
        ['store_id', 'forecast_date', 'meal_period'],
    )

    # ── 2. labor_cost_snapshots ──────────────────────────
    op.create_table(
        'labor_cost_snapshots',
        sa.Column('id',            sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('store_id',      sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('snapshot_date', sa.Date, nullable=False),

        sa.Column('actual_revenue_yuan',     sa.Numeric(14, 2), nullable=False),
        sa.Column('actual_labor_cost_yuan',  sa.Numeric(12, 2), nullable=False),
        sa.Column('actual_labor_cost_rate',  sa.Numeric(6, 2),  nullable=False),

        sa.Column('budgeted_labor_cost_yuan', sa.Numeric(12, 2), nullable=True),
        sa.Column('budgeted_labor_cost_rate', sa.Numeric(6, 2),  nullable=True),

        sa.Column('variance_yuan', sa.Numeric(12, 2), nullable=True),
        sa.Column('variance_pct',  sa.Numeric(6, 2),  nullable=True),

        sa.Column('headcount_actual',    sa.Integer,        nullable=True),
        sa.Column('headcount_scheduled', sa.Integer,        nullable=True),
        sa.Column('overtime_hours',      sa.Numeric(6, 2),  nullable=True),
        sa.Column('overtime_cost_yuan',  sa.Numeric(10, 2), nullable=True),

        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_lcs_store_date', 'labor_cost_snapshots', ['store_id', 'snapshot_date'])
    op.create_unique_constraint(
        'uq_lcs_store_date',
        'labor_cost_snapshots',
        ['store_id', 'snapshot_date'],
    )

    # ── 3. staffing_advice ───────────────────────────────
    op.create_table(
        'staffing_advice',
        sa.Column('id',          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id',    sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('advice_date', sa.Date, nullable=False),
        sa.Column('meal_period', postgresql.ENUM('morning','lunch','dinner','all_day',
                                                 name='meal_period_type', create_type=False),
                  nullable=False),

        sa.Column('status', postgresql.ENUM('pending','confirmed','rejected','expired',
                                            name='staffing_advice_status', create_type=False),
                  nullable=False, server_default='pending'),

        sa.Column('recommended_headcount',       sa.Integer, nullable=False),
        sa.Column('current_scheduled_headcount', sa.Integer, nullable=True),
        sa.Column('headcount_delta',             sa.Integer, nullable=True),

        sa.Column('estimated_saving_yuan',    sa.Numeric(10, 2), nullable=True),
        sa.Column('estimated_overspend_yuan', sa.Numeric(10, 2), nullable=True),

        sa.Column('reason_1', sa.Text, nullable=True),
        sa.Column('reason_2', sa.Text, nullable=True),
        sa.Column('reason_3', sa.Text, nullable=True),

        sa.Column('confidence_score',    sa.Numeric(4, 3), nullable=True),
        sa.Column('position_breakdown',  sa.JSON, nullable=True, server_default='{}'),

        sa.Column('push_sent_at', sa.DateTime, nullable=True),
        sa.Column('expires_at',   sa.DateTime, nullable=True),

        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_sa_store_date',   'staffing_advice', ['store_id', 'advice_date'])
    op.create_index('ix_sa_status',       'staffing_advice', ['status'])

    # ── 4. staffing_advice_confirmations ────────────────
    op.create_table(
        'staffing_advice_confirmations',
        sa.Column('id',        sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('advice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('staffing_advice.id'), nullable=False),
        sa.Column('store_id',  sa.String(50), nullable=False),

        sa.Column('confirmed_by', sa.String(100), nullable=True),
        sa.Column('action', postgresql.ENUM('confirmed','rejected','modified',
                                            name='confirmation_action', create_type=False),
                  nullable=False),

        sa.Column('modified_headcount', sa.Integer,        nullable=True),
        sa.Column('rejection_reason',   sa.Text,           nullable=True),

        sa.Column('response_time_seconds', sa.Integer,        nullable=True),
        sa.Column('actual_saving_yuan',    sa.Numeric(10, 2), nullable=True),

        sa.Column('confirmed_at', sa.DateTime, nullable=False),
        sa.Column('created_at',   sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_sac_advice_id', 'staffing_advice_confirmations', ['advice_id'])
    op.create_index('ix_sac_store_id',  'staffing_advice_confirmations', ['store_id'])

    # ── 5. store_labor_budgets ───────────────────────────
    op.create_table(
        'store_labor_budgets',
        sa.Column('id',            sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('store_id',      sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('budget_period', sa.String(7),  nullable=False),
        sa.Column('budget_type',   postgresql.ENUM('monthly','weekly',
                                                   name='budget_period_type', create_type=False),
                  nullable=False, server_default='monthly'),

        sa.Column('target_labor_cost_rate', sa.Numeric(6, 2),  nullable=False),
        sa.Column('max_labor_cost_yuan',    sa.Numeric(14, 2), nullable=False),
        sa.Column('daily_budget_yuan',      sa.Numeric(12, 2), nullable=True),

        sa.Column('alert_threshold_pct', sa.Numeric(5, 2), nullable=False, server_default='90.0'),
        sa.Column('approved_by',         sa.String(100),   nullable=True),
        sa.Column('is_active',           sa.Boolean,       nullable=False, server_default='true'),

        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_slb_store_period', 'store_labor_budgets', ['store_id', 'budget_period'])
    op.create_unique_constraint(
        'uq_slb_store_period_type',
        'store_labor_budgets',
        ['store_id', 'budget_period', 'budget_type'],
    )

    # ── 6. labor_cost_rankings ───────────────────────────
    op.create_table(
        'labor_cost_rankings',
        sa.Column('id',           sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('store_id',     sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('ranking_date', sa.Date, nullable=False),
        sa.Column('period_type',  postgresql.ENUM('daily','weekly','monthly',
                                                  name='ranking_period_type', create_type=False),
                  nullable=False),

        sa.Column('labor_cost_rate',       sa.Numeric(6, 2), nullable=False),
        sa.Column('rank_in_group',         sa.Integer,       nullable=False),
        sa.Column('total_stores_in_group', sa.Integer,       nullable=False),
        sa.Column('percentile_score',      sa.Numeric(5, 1), nullable=True),
        sa.Column('group_avg_rate',        sa.Numeric(6, 2), nullable=True),
        sa.Column('group_median_rate',     sa.Numeric(6, 2), nullable=True),
        sa.Column('best_rate_in_group',    sa.Numeric(6, 2), nullable=True),

        sa.Column('brand_id',   sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime,   server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_lcr_store_date', 'labor_cost_rankings', ['store_id', 'ranking_date'])
    op.create_index('ix_lcr_brand_date', 'labor_cost_rankings', ['brand_id', 'ranking_date'])
    op.create_unique_constraint(
        'uq_lcr_store_date_period',
        'labor_cost_rankings',
        ['store_id', 'ranking_date', 'period_type'],
    )


def downgrade() -> None:
    # 按依赖倒序删除
    op.drop_constraint('uq_lcr_store_date_period', 'labor_cost_rankings', type_='unique')
    op.drop_index('ix_lcr_brand_date', table_name='labor_cost_rankings')
    op.drop_index('ix_lcr_store_date', table_name='labor_cost_rankings')
    op.drop_table('labor_cost_rankings')

    op.drop_constraint('uq_slb_store_period_type', 'store_labor_budgets', type_='unique')
    op.drop_index('ix_slb_store_period', table_name='store_labor_budgets')
    op.drop_table('store_labor_budgets')

    op.drop_index('ix_sac_store_id',  table_name='staffing_advice_confirmations')
    op.drop_index('ix_sac_advice_id', table_name='staffing_advice_confirmations')
    op.drop_table('staffing_advice_confirmations')

    op.drop_index('ix_sa_status',     table_name='staffing_advice')
    op.drop_index('ix_sa_store_date', table_name='staffing_advice')
    op.drop_table('staffing_advice')

    op.drop_constraint('uq_lcs_store_date', 'labor_cost_snapshots', type_='unique')
    op.drop_index('ix_lcs_store_date', table_name='labor_cost_snapshots')
    op.drop_table('labor_cost_snapshots')

    op.drop_constraint('uq_ldf_store_date_period', 'labor_demand_forecasts', type_='unique')
    op.drop_index('ix_ldf_store_date', table_name='labor_demand_forecasts')
    op.drop_table('labor_demand_forecasts')

    op.execute("DROP TYPE IF EXISTS ranking_period_type")
    op.execute("DROP TYPE IF EXISTS budget_period_type")
    op.execute("DROP TYPE IF EXISTS confirmation_action")
    op.execute("DROP TYPE IF EXISTS staffing_advice_status")
    # meal_period_type is shared by pre-existing meal-period tables/migrations.
