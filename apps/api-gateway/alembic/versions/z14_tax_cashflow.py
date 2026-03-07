"""z14 — 业财税资金 Phase 5 Month 2: 税务智能引擎 + 现金流预测

Revision ID: z14
Revises: z13
Create Date: 2026-03-07

Adds:
  tax_calculations   — 按期/按税种的税务计算结果（含税率、应纳税额）
  cashflow_forecasts — 未来30天现金流预测（每日入账/出账/净额/余额）
  agent_action_log   — 智能体动作记录（L1提醒/L2建议/L3执行）
"""
from alembic import op
import sqlalchemy as sa

revision = 'z14'
down_revision = 'z13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 税务计算结果 ──────────────────────────────────────────────────────────
    op.create_table(
        'tax_calculations',
        sa.Column('id',           sa.String(36),  primary_key=True),
        sa.Column('store_id',     sa.String(36),  nullable=False),
        sa.Column('brand_id',     sa.String(36),  nullable=True),
        sa.Column('period',       sa.String(7),   nullable=False),  # YYYY-MM
        sa.Column('calc_date',    sa.Date,        nullable=False),
        # 税种
        sa.Column('tax_type',     sa.String(32),  nullable=False),
        # vat_small / vat_general / income_tax / stamp_duty
        sa.Column('tax_name',     sa.String(64),  nullable=False),
        sa.Column('tax_rate',     sa.Numeric(6, 4), nullable=False),
        # 计税基础
        sa.Column('taxable_base_yuan', sa.Numeric(14, 2), nullable=False, server_default='0'),
        # 应纳税额（计算值）
        sa.Column('tax_amount_yuan',   sa.Numeric(14, 2), nullable=False, server_default='0'),
        # 已实际申报/缴纳（来自发票事件）
        sa.Column('declared_yuan',     sa.Numeric(14, 2), nullable=False, server_default='0'),
        # 差异 = 应纳 - 已申报（正值=少申报，负值=多申报）
        sa.Column('deviation_yuan',    sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('deviation_pct',     sa.Numeric(6, 2),  nullable=True),  # %
        # 风险等级
        sa.Column('risk_level',        sa.String(8),       nullable=False, server_default='low'),
        # low / medium / high / critical
        # 参考税务规则
        sa.Column('tax_rule_id',       sa.String(36),      nullable=True),
        # 计算说明 JSON
        sa.Column('calc_detail',       sa.Text,            nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('store_id', 'period', 'tax_type',
                            name='uq_tc_store_period_type'),
    )
    op.create_index('ix_tc_store_period',  'tax_calculations', ['store_id', 'period'])
    op.create_index('ix_tc_risk_level',    'tax_calculations', ['risk_level', 'calc_date'])

    # ── 现金流预测 ────────────────────────────────────────────────────────────
    op.create_table(
        'cashflow_forecasts',
        sa.Column('id',              sa.String(36),  primary_key=True),
        sa.Column('store_id',        sa.String(36),  nullable=False),
        sa.Column('forecast_date',   sa.Date,        nullable=False),  # 预测哪一天
        sa.Column('generated_on',    sa.Date,        nullable=False),  # 生成日期
        # 预测金额（元）
        sa.Column('inflow_yuan',     sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('outflow_yuan',    sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('net_yuan',        sa.Numeric(14, 2), nullable=False, server_default='0'),
        # 累计余额（当日期初 + net）
        sa.Column('balance_yuan',    sa.Numeric(14, 2), nullable=False, server_default='0'),
        # 置信度（0-1）
        sa.Column('confidence',      sa.Numeric(4, 3),  nullable=False, server_default='0.8'),
        # 预测方法
        sa.Column('method',          sa.String(32),    nullable=False, server_default='moving_avg'),
        # moving_avg / seasonal / ml
        # 入账/出账明细 JSON
        sa.Column('inflow_detail',   sa.Text,           nullable=True),
        sa.Column('outflow_detail',  sa.Text,           nullable=True),
        # 实际值（事后填充，用于回测）
        sa.Column('actual_inflow_yuan',  sa.Numeric(14, 2), nullable=True),
        sa.Column('actual_outflow_yuan', sa.Numeric(14, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('store_id', 'forecast_date', 'generated_on',
                            name='uq_cf_store_date_gen'),
    )
    op.create_index('ix_cf_store_date',    'cashflow_forecasts', ['store_id', 'forecast_date'])
    op.create_index('ix_cf_generated_on',  'cashflow_forecasts', ['store_id', 'generated_on'])
    # 快速查负值（现金缺口预警）
    op.create_index(
        'ix_cf_negative_balance',
        'cashflow_forecasts',
        ['store_id', 'forecast_date'],
        postgresql_where=sa.text("balance_yuan < 0"),
    )

    # ── Agent 动作日志 ────────────────────────────────────────────────────────
    op.create_table(
        'agent_action_log',
        sa.Column('id',             sa.String(36), primary_key=True),
        sa.Column('store_id',       sa.String(36), nullable=True),
        sa.Column('brand_id',       sa.String(36), nullable=True),
        # 执行层级
        sa.Column('action_level',   sa.String(4),  nullable=False),
        # L1=提醒 / L2=建议 / L3=执行
        # 触发来源
        sa.Column('agent_name',     sa.String(64), nullable=False),
        # ProfitAgent / TaxAgent / CashAgent / SettlementAgent / RiskAgent
        sa.Column('trigger_type',   sa.String(64), nullable=False),
        # tax_deviation / cash_gap / profit_drop / unusual_refund / ...
        # 动作内容
        sa.Column('title',          sa.String(256), nullable=False),
        sa.Column('description',    sa.Text,        nullable=True),
        sa.Column('recommended_action', sa.Text,    nullable=True),
        # 预期¥影响（Rule 6）
        sa.Column('expected_impact_yuan', sa.Numeric(14, 2), nullable=True),
        sa.Column('confidence',     sa.Numeric(4, 3), nullable=False, server_default='0.8'),
        # 关联资源
        sa.Column('ref_type',       sa.String(32),  nullable=True),
        # tax_calculation / cashflow_forecast / profit_attribution / risk_task
        sa.Column('ref_id',         sa.String(36),  nullable=True),
        # 状态
        sa.Column('status',         sa.String(16),  nullable=False, server_default='pending'),
        # pending → accepted / dismissed / auto_executed
        sa.Column('responded_at',   sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_note',  sa.Text,        nullable=True),
        sa.Column('period',         sa.String(7),   nullable=True),  # YYYY-MM
        sa.Column('created_at',     sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_aal_store_level',   'agent_action_log', ['store_id', 'action_level'])
    op.create_index('ix_aal_agent',         'agent_action_log', ['agent_name', 'trigger_type'])
    op.create_index('ix_aal_status',        'agent_action_log', ['status', 'created_at'])
    op.create_index(
        'ix_aal_pending',
        'agent_action_log',
        ['store_id', 'created_at'],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table('agent_action_log')
    op.drop_table('cashflow_forecasts')
    op.drop_table('tax_calculations')
