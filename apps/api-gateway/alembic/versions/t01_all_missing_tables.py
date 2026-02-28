"""Add 21 missing tables

Revision ID: t01_all_missing_tables
Revises: s01_missing_models
Create Date: 2026-02-28

Covers all ORM models that had no migration, in dependency order:
  1.  audit_logs            (audit_log.py)
  2.  queues                (queue.py)
  3.  financial_transactions (finance.py)
  4.  budgets               (finance.py)
  5.  invoices              (finance.py) — FK: stores, suppliers
  6.  financial_reports     (finance.py)
  7.  quality_inspections   (quality.py)
  8.  decision_logs         (decision_log.py) — FK: stores, users
  9.  compliance_licenses   (compliance.py)   — FK: stores, employees
  10. external_systems      (integration.py)
  11. sync_logs             (integration.py)
  12. pos_transactions      (integration.py)
  13. supplier_orders       (integration.py)
  14. member_syncs          (integration.py)
  15. reservation_syncs     (integration.py)
  16. notifications         (notification.py)  — FK: users
  17. notification_preferences (notification.py) — FK: users
  18. notification_rules    (notification.py)  — FK: users
  19. export_jobs           (export_job.py)    — FK: users
  20. report_templates      (report_template.py) — FK: users
  21. scheduled_reports     (report_template.py) — FK: report_templates, users
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 't01_all_missing_tables'
down_revision: str = 's01_missing_models'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── 1. audit_logs ─────────────────────────────────────────────────────────
    op.create_table(
        'audit_logs',
        sa.Column('id',              sa.String(36),   primary_key=True),
        sa.Column('action',          sa.String(100),  nullable=False),
        sa.Column('resource_type',   sa.String(100),  nullable=False),
        sa.Column('resource_id',     sa.String(100)),
        sa.Column('user_id',         sa.String(36),   nullable=False),
        sa.Column('username',        sa.String(100)),
        sa.Column('user_role',       sa.String(50)),
        sa.Column('description',     sa.Text()),
        sa.Column('changes',         sa.JSON()),
        sa.Column('old_value',       sa.JSON()),
        sa.Column('new_value',       sa.JSON()),
        sa.Column('ip_address',      sa.String(45)),
        sa.Column('user_agent',      sa.String(500)),
        sa.Column('request_method',  sa.String(10)),
        sa.Column('request_path',    sa.String(500)),
        sa.Column('status',          sa.String(20),   nullable=False, server_default='success'),
        sa.Column('error_message',   sa.Text()),
        sa.Column('store_id',        sa.String(36)),
        sa.Column('created_at',      sa.DateTime(),   nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_audit_logs_user_id',       'audit_logs', ['user_id'])
    op.create_index('idx_audit_logs_action',        'audit_logs', ['action'])
    op.create_index('idx_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('idx_audit_logs_created_at',    'audit_logs', ['created_at'])
    op.create_index('idx_audit_logs_store_id',      'audit_logs', ['store_id'])
    op.create_index('idx_audit_logs_status',        'audit_logs', ['status'])

    # ── 2. queues ─────────────────────────────────────────────────────────────
    op.create_table(
        'queues',
        sa.Column('queue_id',              sa.String(50),  primary_key=True),
        sa.Column('queue_number',          sa.Integer(),   nullable=False),
        sa.Column('store_id',              sa.String(50),  nullable=False),
        sa.Column('customer_name',         sa.String(100), nullable=False),
        sa.Column('customer_phone',        sa.String(20),  nullable=False),
        sa.Column('party_size',            sa.Integer(),   nullable=False),
        sa.Column('status',                sa.String(20),  nullable=False, server_default='waiting'),
        sa.Column('created_at',            sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('called_at',             sa.DateTime()),
        sa.Column('seated_at',             sa.DateTime()),
        sa.Column('cancelled_at',          sa.DateTime()),
        sa.Column('estimated_wait_time',   sa.Integer()),
        sa.Column('actual_wait_time',      sa.Integer()),
        sa.Column('table_number',          sa.String(20)),
        sa.Column('table_type',            sa.String(50)),
        sa.Column('special_requests',      sa.Text()),
        sa.Column('notes',                 sa.Text()),
        sa.Column('notification_sent',     sa.Boolean(),   server_default='false'),
        sa.Column('notification_method',   sa.String(20)),
        sa.Column('updated_at',            sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_queues_store_id',       'queues', ['store_id'])
    op.create_index('idx_queues_customer_phone', 'queues', ['customer_phone'])
    op.create_index('idx_queues_status',         'queues', ['status'])

    # ── 3. financial_transactions ─────────────────────────────────────────────
    op.create_table(
        'financial_transactions',
        sa.Column('id',               sa.String(),    primary_key=True),
        sa.Column('store_id',         sa.String(),    sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('transaction_date', sa.Date(),      nullable=False),
        sa.Column('transaction_type', sa.String(20),  nullable=False),
        sa.Column('category',         sa.String(50),  nullable=False),
        sa.Column('subcategory',      sa.String(50)),
        sa.Column('amount',           sa.Integer(),   nullable=False),
        sa.Column('description',      sa.Text()),
        sa.Column('reference_id',     sa.String()),
        sa.Column('payment_method',   sa.String(20)),
        sa.Column('created_by',       sa.String()),
        sa.Column('created_at',       sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',       sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index('idx_fin_txn_store_id', 'financial_transactions', ['store_id'])
    op.create_index('idx_fin_txn_date',     'financial_transactions', ['transaction_date'])
    op.create_index('idx_fin_txn_type',     'financial_transactions', ['transaction_type'])
    op.create_index('idx_fin_txn_category', 'financial_transactions', ['category'])

    # ── 4. budgets ────────────────────────────────────────────────────────────
    op.create_table(
        'budgets',
        sa.Column('id',                  sa.String(),  primary_key=True),
        sa.Column('store_id',            sa.String(),  sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('year',                sa.Integer(), nullable=False),
        sa.Column('month',               sa.Integer(), nullable=False),
        sa.Column('category',            sa.String(50), nullable=False),
        sa.Column('budgeted_amount',     sa.Integer(), nullable=False),
        sa.Column('actual_amount',       sa.Integer(), server_default='0'),
        sa.Column('variance',            sa.Integer(), server_default='0'),
        sa.Column('variance_percentage', sa.Float(),   server_default='0.0'),
        sa.Column('notes',               sa.Text()),
        sa.Column('created_by',          sa.String()),
        sa.Column('approved_by',         sa.String()),
        sa.Column('approved_at',         sa.DateTime()),
        sa.Column('created_at',          sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at',          sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_budgets_store_id',      'budgets', ['store_id'])
    op.create_index('idx_budgets_store_year_mon', 'budgets', ['store_id', 'year', 'month'])

    # ── 5. invoices ───────────────────────────────────────────────────────────
    op.create_table(
        'invoices',
        sa.Column('id',             sa.String(),    primary_key=True),
        sa.Column('invoice_number', sa.String(50),  unique=True, nullable=False),
        sa.Column('store_id',       sa.String(),    sa.ForeignKey('stores.id'),    nullable=False),
        sa.Column('invoice_type',   sa.String(20),  nullable=False),
        sa.Column('invoice_date',   sa.Date(),      nullable=False),
        sa.Column('due_date',       sa.Date()),
        sa.Column('supplier_id',    sa.String(),    sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('customer_name',  sa.String(100)),
        sa.Column('tax_number',     sa.String(50)),
        sa.Column('total_amount',   sa.Integer(),   nullable=False),
        sa.Column('tax_amount',     sa.Integer(),   server_default='0'),
        sa.Column('net_amount',     sa.Integer(),   nullable=False),
        sa.Column('status',         sa.String(20),  server_default='pending'),
        sa.Column('items',          sa.JSON()),
        sa.Column('notes',          sa.Text()),
        sa.Column('created_by',     sa.String()),
        sa.Column('created_at',     sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',     sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index('idx_invoices_number',   'invoices', ['invoice_number'], unique=True)
    op.create_index('idx_invoices_store_id', 'invoices', ['store_id'])
    op.create_index('idx_invoices_status',   'invoices', ['status'])
    op.create_index('idx_invoices_date',     'invoices', ['invoice_date'])

    # ── 6. financial_reports ──────────────────────────────────────────────────
    op.create_table(
        'financial_reports',
        sa.Column('id',           sa.String(),   primary_key=True),
        sa.Column('store_id',     sa.String(),   sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('report_type',  sa.String(50), nullable=False),
        sa.Column('period_type',  sa.String(20), nullable=False),
        sa.Column('start_date',   sa.Date(),     nullable=False),
        sa.Column('end_date',     sa.Date(),     nullable=False),
        sa.Column('data',         sa.JSON(),     nullable=False),
        sa.Column('summary',      sa.JSON()),
        sa.Column('generated_by', sa.String()),
        sa.Column('generated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_fin_reports_store_id',    'financial_reports', ['store_id'])
    op.create_index('idx_fin_reports_type_period', 'financial_reports', ['store_id', 'report_type', 'period_type'])

    # ── 7. quality_inspections ────────────────────────────────────────────────
    op.create_table(
        'quality_inspections',
        sa.Column('id',             postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id',       sa.String(50),  nullable=False),
        sa.Column('dish_id',        sa.String(50)),
        sa.Column('dish_name',      sa.String(100), nullable=False),
        sa.Column('image_url',      sa.Text()),
        sa.Column('image_source',   sa.String(20),  server_default='upload'),
        sa.Column('quality_score',  sa.Float(),     nullable=False),
        sa.Column('status',         sa.String(20),  nullable=False),
        sa.Column('issues',         sa.JSON()),
        sa.Column('suggestions',    sa.JSON()),
        sa.Column('llm_reasoning',  sa.Text()),
        sa.Column('inspector',      sa.String(50),  server_default='quality_agent'),
        sa.Column('pass_threshold', sa.Float(),     server_default='75.0'),
        sa.Column('created_at',     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_quality_store_id', 'quality_inspections', ['store_id'])
    op.create_index('idx_quality_dish_id',  'quality_inspections', ['dish_id'])
    op.create_index('idx_quality_status',   'quality_inspections', ['status'])

    # ── 8. decision_logs ─────────────────────────────────────────────────────
    op.create_table(
        'decision_logs',
        sa.Column('id',               sa.String(36),   primary_key=True),
        sa.Column('decision_type',    sa.String(50),   nullable=False),
        sa.Column('agent_type',       sa.String(50),   nullable=False),
        sa.Column('agent_method',     sa.String(100),  nullable=False),
        sa.Column('store_id',         sa.String(36),   sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('ai_suggestion',    sa.JSON(),       nullable=False),
        sa.Column('ai_confidence',    sa.Float()),
        sa.Column('ai_reasoning',     sa.Text()),
        sa.Column('ai_alternatives',  sa.JSON()),
        sa.Column('manager_id',       sa.String(36),   sa.ForeignKey('users.id')),
        sa.Column('manager_decision', sa.JSON()),
        sa.Column('manager_feedback', sa.Text()),
        sa.Column('decision_status',  sa.String(20),   server_default='pending'),
        sa.Column('created_at',       sa.DateTime(),   nullable=False, server_default=sa.func.now()),
        sa.Column('approved_at',      sa.DateTime()),
        sa.Column('executed_at',      sa.DateTime()),
        sa.Column('outcome',          sa.String(20)),
        sa.Column('actual_result',    sa.JSON()),
        sa.Column('expected_result',  sa.JSON()),
        sa.Column('result_deviation', sa.Float()),
        sa.Column('business_impact',  sa.JSON()),
        sa.Column('cost_impact',      sa.Numeric(12, 2)),
        sa.Column('revenue_impact',   sa.Numeric(12, 2)),
        sa.Column('is_training_data', sa.Integer(),    server_default='0'),
        sa.Column('trust_score',      sa.Float()),
        sa.Column('context_data',     sa.JSON()),
        sa.Column('rag_context',      sa.JSON()),
        sa.Column('approval_chain',   sa.JSON()),
        sa.Column('notes',            sa.Text()),
    )
    op.create_index('idx_decision_logs_decision_type',   'decision_logs', ['decision_type'])
    op.create_index('idx_decision_logs_agent_type',      'decision_logs', ['agent_type'])
    op.create_index('idx_decision_logs_store_id',        'decision_logs', ['store_id'])
    op.create_index('idx_decision_logs_manager_id',      'decision_logs', ['manager_id'])
    op.create_index('idx_decision_logs_decision_status', 'decision_logs', ['decision_status'])

    # ── 9. compliance_licenses ────────────────────────────────────────────────
    op.create_table(
        'compliance_licenses',
        sa.Column('id',                  sa.String(36),  primary_key=True),
        sa.Column('store_id',            sa.String(36),  sa.ForeignKey('stores.id'),    nullable=False),
        sa.Column('license_type',        sa.String(30),  nullable=False),
        sa.Column('license_name',        sa.String(100), nullable=False),
        sa.Column('license_number',      sa.String(100)),
        sa.Column('holder_name',         sa.String(50)),
        sa.Column('holder_employee_id',  sa.String(36),  sa.ForeignKey('employees.id'), nullable=True),
        sa.Column('issue_date',          sa.Date()),
        sa.Column('expiry_date',         sa.Date(),      nullable=False),
        sa.Column('status',              sa.String(20),  server_default='valid'),
        sa.Column('remind_days_before',  sa.Integer(),   server_default='30'),
        sa.Column('last_reminded_at',    sa.DateTime()),
        sa.Column('notes',               sa.Text()),
        sa.Column('created_at',          sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',          sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_compliance_store_id',    'compliance_licenses', ['store_id'])
    op.create_index('idx_compliance_type',        'compliance_licenses', ['license_type'])
    op.create_index('idx_compliance_expiry_date', 'compliance_licenses', ['expiry_date'])
    op.create_index('idx_compliance_status',      'compliance_licenses', ['status'])

    # ── 10. external_systems ──────────────────────────────────────────────────
    op.create_table(
        'external_systems',
        sa.Column('id',               postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name',             sa.String(100), nullable=False),
        sa.Column('type',             sa.String(20),  nullable=False),
        sa.Column('provider',         sa.String(100)),
        sa.Column('version',          sa.String(50)),
        sa.Column('status',           sa.String(20),  server_default='inactive'),
        sa.Column('store_id',         sa.String(50)),
        sa.Column('api_endpoint',     sa.String(500)),
        sa.Column('api_key',          sa.String(500)),
        sa.Column('api_secret',       sa.String(500)),
        sa.Column('webhook_url',      sa.String(500)),
        sa.Column('webhook_secret',   sa.String(500)),
        sa.Column('config',           sa.JSON()),
        sa.Column('sync_enabled',     sa.Boolean(),   server_default='true'),
        sa.Column('sync_interval',    sa.Integer(),   server_default='300'),
        sa.Column('last_sync_at',     sa.DateTime()),
        sa.Column('last_sync_status', sa.String(20)),
        sa.Column('last_error',       sa.Text()),
        sa.Column('created_at',       sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',       sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('created_by',       sa.String(50)),
    )
    op.create_index('idx_external_systems_store_id', 'external_systems', ['store_id'])
    op.create_index('idx_external_systems_type',     'external_systems', ['type'])
    op.create_index('idx_external_systems_status',   'external_systems', ['status'])

    # ── 11. sync_logs ─────────────────────────────────────────────────────────
    op.create_table(
        'sync_logs',
        sa.Column('id',               postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('system_id',        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_type',        sa.String(50),  nullable=False),
        sa.Column('status',           sa.String(20),  nullable=False),
        sa.Column('records_total',    sa.Integer(),   server_default='0'),
        sa.Column('records_success',  sa.Integer(),   server_default='0'),
        sa.Column('records_failed',   sa.Integer(),   server_default='0'),
        sa.Column('started_at',       sa.DateTime(),  nullable=False),
        sa.Column('completed_at',     sa.DateTime()),
        sa.Column('duration_seconds', sa.Float()),
        sa.Column('error_message',    sa.Text()),
        sa.Column('error_details',    sa.JSON()),
        sa.Column('request_data',     sa.JSON()),
        sa.Column('response_data',    sa.JSON()),
        sa.Column('created_at',       sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index('idx_sync_logs_system_id', 'sync_logs', ['system_id'])
    op.create_index('idx_sync_logs_status',    'sync_logs', ['status'])
    op.create_index('idx_sync_logs_started_at','sync_logs', ['started_at'])

    # ── 12. pos_transactions ──────────────────────────────────────────────────
    op.create_table(
        'pos_transactions',
        sa.Column('id',                  postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('system_id',           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_id',            sa.String(50),   nullable=False),
        sa.Column('pos_transaction_id',  sa.String(100),  nullable=False, unique=True),
        sa.Column('pos_order_number',    sa.String(100)),
        sa.Column('transaction_type',    sa.String(50)),
        sa.Column('subtotal',            sa.Numeric(12, 2), server_default='0'),
        sa.Column('tax',                 sa.Numeric(12, 2), server_default='0'),
        sa.Column('discount',            sa.Numeric(12, 2), server_default='0'),
        sa.Column('total',               sa.Numeric(12, 2), server_default='0'),
        sa.Column('payment_method',      sa.String(50)),
        sa.Column('items',               sa.JSON()),
        sa.Column('customer_info',       sa.JSON()),
        sa.Column('sync_status',         sa.String(20),   server_default='pending'),
        sa.Column('synced_at',           sa.DateTime()),
        sa.Column('transaction_time',    sa.DateTime(),   nullable=False),
        sa.Column('created_at',          sa.DateTime(),   server_default=sa.func.now()),
        sa.Column('updated_at',          sa.DateTime(),   server_default=sa.func.now()),
        sa.Column('raw_data',            sa.JSON()),
    )
    op.create_index('idx_pos_txn_system_id',     'pos_transactions', ['system_id'])
    op.create_index('idx_pos_txn_store_id',      'pos_transactions', ['store_id'])
    op.create_index('idx_pos_txn_pos_id',        'pos_transactions', ['pos_transaction_id'], unique=True)
    op.create_index('idx_pos_txn_sync_status',   'pos_transactions', ['sync_status'])

    # ── 13. supplier_orders ───────────────────────────────────────────────────
    op.create_table(
        'supplier_orders',
        sa.Column('id',                postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('system_id',         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_id',          sa.String(50),   nullable=False),
        sa.Column('order_number',      sa.String(100),  nullable=False, unique=True),
        sa.Column('supplier_id',       sa.String(100)),
        sa.Column('supplier_name',     sa.String(200)),
        sa.Column('order_type',        sa.String(50)),
        sa.Column('status',            sa.String(50)),
        sa.Column('subtotal',          sa.Numeric(12, 2), server_default='0'),
        sa.Column('tax',               sa.Numeric(12, 2), server_default='0'),
        sa.Column('shipping',          sa.Numeric(12, 2), server_default='0'),
        sa.Column('total',             sa.Numeric(12, 2), server_default='0'),
        sa.Column('items',             sa.JSON()),
        sa.Column('delivery_info',     sa.JSON()),
        sa.Column('order_date',        sa.DateTime(),   nullable=False),
        sa.Column('expected_delivery', sa.DateTime()),
        sa.Column('actual_delivery',   sa.DateTime()),
        sa.Column('sync_status',       sa.String(20),   server_default='pending'),
        sa.Column('synced_at',         sa.DateTime()),
        sa.Column('created_at',        sa.DateTime(),   server_default=sa.func.now()),
        sa.Column('updated_at',        sa.DateTime(),   server_default=sa.func.now()),
        sa.Column('raw_data',          sa.JSON()),
    )
    op.create_index('idx_supplier_orders_system_id',    'supplier_orders', ['system_id'])
    op.create_index('idx_supplier_orders_store_id',     'supplier_orders', ['store_id'])
    op.create_index('idx_supplier_orders_order_number', 'supplier_orders', ['order_number'], unique=True)
    op.create_index('idx_supplier_orders_sync_status',  'supplier_orders', ['sync_status'])

    # ── 14. member_syncs ──────────────────────────────────────────────────────
    op.create_table(
        'member_syncs',
        sa.Column('id',                  postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('system_id',           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('member_id',           sa.String(100), nullable=False),
        sa.Column('external_member_id',  sa.String(100)),
        sa.Column('phone',               sa.String(20)),
        sa.Column('name',                sa.String(100)),
        sa.Column('email',               sa.String(200)),
        sa.Column('level',               sa.String(50)),
        sa.Column('points',              sa.Integer(),   server_default='0'),
        sa.Column('balance',             sa.Numeric(12, 2), server_default='0'),
        sa.Column('sync_status',         sa.String(20),  server_default='pending'),
        sa.Column('synced_at',           sa.DateTime()),
        sa.Column('last_activity',       sa.DateTime()),
        sa.Column('created_at',          sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',          sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('raw_data',            sa.JSON()),
    )
    op.create_index('idx_member_syncs_system_id',  'member_syncs', ['system_id'])
    op.create_index('idx_member_syncs_member_id',  'member_syncs', ['member_id'])
    op.create_index('idx_member_syncs_sync_status','member_syncs', ['sync_status'])

    # ── 15. reservation_syncs ─────────────────────────────────────────────────
    op.create_table(
        'reservation_syncs',
        sa.Column('id',                      postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('system_id',               postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_id',                sa.String(50),   nullable=False),
        sa.Column('reservation_id',          sa.String(100),  nullable=False),
        sa.Column('external_reservation_id', sa.String(100)),
        sa.Column('reservation_number',      sa.String(100)),
        sa.Column('customer_name',           sa.String(100),  nullable=False),
        sa.Column('customer_phone',          sa.String(20),   nullable=False),
        sa.Column('customer_count',          sa.Integer(),    nullable=False),
        sa.Column('reservation_date',        sa.DateTime(),   nullable=False),
        sa.Column('reservation_time',        sa.String(20),   nullable=False),
        sa.Column('arrival_time',            sa.DateTime()),
        sa.Column('table_type',              sa.String(50)),
        sa.Column('table_number',            sa.String(20)),
        sa.Column('area',                    sa.String(50)),
        sa.Column('status',                  sa.String(50),   nullable=False),
        sa.Column('special_requirements',    sa.Text()),
        sa.Column('notes',                   sa.Text()),
        sa.Column('deposit_required',        sa.Boolean(),    server_default='false'),
        sa.Column('deposit_amount',          sa.Numeric(12, 2), server_default='0'),
        sa.Column('deposit_paid',            sa.Boolean(),    server_default='false'),
        sa.Column('source',                  sa.String(50)),
        sa.Column('channel',                 sa.String(50)),
        sa.Column('sync_status',             sa.String(20),   server_default='pending'),
        sa.Column('synced_at',               sa.DateTime()),
        sa.Column('created_at',              sa.DateTime(),   server_default=sa.func.now()),
        sa.Column('updated_at',              sa.DateTime(),   server_default=sa.func.now()),
        sa.Column('cancelled_at',            sa.DateTime()),
        sa.Column('raw_data',                sa.JSON()),
    )
    op.create_index('idx_res_syncs_system_id',   'reservation_syncs', ['system_id'])
    op.create_index('idx_res_syncs_store_id',    'reservation_syncs', ['store_id'])
    op.create_index('idx_res_syncs_sync_status', 'reservation_syncs', ['sync_status'])

    # ── 16. notifications ─────────────────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id',         postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('title',      sa.String(200), nullable=False),
        sa.Column('message',    sa.Text(),      nullable=False),
        sa.Column('type',       sa.String(20),  nullable=False, server_default='info'),
        sa.Column('priority',   sa.String(20),  nullable=False, server_default='normal'),
        sa.Column('user_id',    postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('role',       sa.String(50)),
        sa.Column('store_id',   sa.String(50)),
        sa.Column('is_read',    sa.Boolean(),   nullable=False, server_default='false'),
        sa.Column('read_at',    sa.String(50)),
        sa.Column('extra_data', sa.JSON()),
        sa.Column('source',     sa.String(50)),
        sa.Column('created_at', sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_notifications_store_id', 'notifications', ['store_id'])
    op.create_index('idx_notifications_user_id',  'notifications', ['user_id'])
    op.create_index('idx_notifications_is_read',  'notifications', ['is_read'])

    # ── 17. notification_preferences ─────────────────────────────────────────
    op.create_table(
        'notification_preferences',
        sa.Column('id',                 postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id',            postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('notification_type',  sa.String(20)),
        sa.Column('channels',           sa.JSON(),     nullable=False),
        sa.Column('is_enabled',         sa.Boolean(),  nullable=False, server_default='true'),
        sa.Column('quiet_hours_start',  sa.String(5)),
        sa.Column('quiet_hours_end',    sa.String(5)),
        sa.Column('created_at',         sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',         sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_notif_prefs_user_id', 'notification_preferences', ['user_id'])

    # ── 18. notification_rules ────────────────────────────────────────────────
    op.create_table(
        'notification_rules',
        sa.Column('id',                    postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id',               postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('notification_type',     sa.String(20)),
        sa.Column('max_count',             sa.Integer(), nullable=False, server_default='10'),
        sa.Column('time_window_minutes',   sa.Integer(), nullable=False, server_default='60'),
        sa.Column('is_active',             sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('description',           sa.String(200)),
        sa.Column('created_at',            sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',            sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_notif_rules_user_id', 'notification_rules', ['user_id'])

    # ── 19. export_jobs ───────────────────────────────────────────────────────
    op.create_table(
        'export_jobs',
        sa.Column('id',              postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id',         postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('job_type',        sa.String(50),  nullable=False),
        sa.Column('params',          sa.JSON(),      nullable=False),
        sa.Column('format',          sa.String(10),  nullable=False, server_default='csv'),
        sa.Column('status',          sa.String(20),  nullable=False, server_default='pending'),
        sa.Column('celery_task_id',  sa.String(100)),
        sa.Column('progress',        sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('total_rows',      sa.Integer()),
        sa.Column('processed_rows',  sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('file_path',       sa.String(500)),
        sa.Column('file_size_bytes', sa.Integer()),
        sa.Column('error_message',   sa.Text()),
        sa.Column('completed_at',    sa.String(30)),
        sa.Column('created_at',      sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',      sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_export_jobs_user_id', 'export_jobs', ['user_id'])
    op.create_index('idx_export_jobs_status',  'export_jobs', ['status'])

    # ── 20. report_templates ──────────────────────────────────────────────────
    op.create_table(
        'report_templates',
        sa.Column('id',             postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name',           sa.String(100), nullable=False),
        sa.Column('description',    sa.Text()),
        sa.Column('data_source',    sa.String(50),  nullable=False),
        sa.Column('columns',        sa.JSON(),      nullable=False),
        sa.Column('filters',        sa.JSON()),
        sa.Column('sort_by',        sa.JSON()),
        sa.Column('default_format', sa.String(10),  nullable=False, server_default='xlsx'),
        sa.Column('is_public',      sa.Boolean(),   nullable=False, server_default='false'),
        sa.Column('created_by',     postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('store_id',       sa.String(50)),
        sa.Column('created_at',     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',     sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_report_templates_created_by', 'report_templates', ['created_by'])
    op.create_index('idx_report_templates_store_id',   'report_templates', ['store_id'])
    op.create_index('idx_report_templates_is_public',  'report_templates', ['is_public'])

    # ── 21. scheduled_reports ─────────────────────────────────────────────────
    op.create_table(
        'scheduled_reports',
        sa.Column('id',            postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('template_id',   postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('report_templates.id'), nullable=False),
        sa.Column('user_id',       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('frequency',     sa.String(20),  nullable=False, server_default='daily'),
        sa.Column('run_at',        sa.String(5),   nullable=False, server_default='06:00'),
        sa.Column('day_of_week',   sa.Integer()),
        sa.Column('day_of_month',  sa.Integer()),
        sa.Column('channels',      sa.JSON(),      nullable=False),
        sa.Column('recipients',    sa.JSON()),
        sa.Column('format',        sa.String(10),  nullable=False, server_default='xlsx'),
        sa.Column('is_active',     sa.Boolean(),   nullable=False, server_default='true'),
        sa.Column('last_run_at',   sa.String(30)),
        sa.Column('next_run_at',   sa.String(30)),
        sa.Column('created_at',    sa.DateTime(),  nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',    sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_scheduled_reports_template_id', 'scheduled_reports', ['template_id'])
    op.create_index('idx_scheduled_reports_user_id',     'scheduled_reports', ['user_id'])
    op.create_index('idx_scheduled_reports_is_active',   'scheduled_reports', ['is_active'])


def downgrade() -> None:
    # 按创建顺序反向删除（先删有 FK 依赖的子表）
    op.drop_table('scheduled_reports')
    op.drop_table('report_templates')
    op.drop_table('export_jobs')
    op.drop_table('notification_rules')
    op.drop_table('notification_preferences')
    op.drop_table('notifications')
    op.drop_table('reservation_syncs')
    op.drop_table('member_syncs')
    op.drop_table('supplier_orders')
    op.drop_table('pos_transactions')
    op.drop_table('sync_logs')
    op.drop_table('external_systems')
    op.drop_table('compliance_licenses')
    op.drop_table('decision_logs')
    op.drop_table('quality_inspections')
    op.drop_table('financial_reports')
    op.drop_table('invoices')
    op.drop_table('budgets')
    op.drop_table('financial_transactions')
    op.drop_table('queues')
    op.drop_table('audit_logs')
