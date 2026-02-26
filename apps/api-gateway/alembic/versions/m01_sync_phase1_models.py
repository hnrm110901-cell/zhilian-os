"""
同步 Phase 1 模型与数据库 Schema

重建 employees/inventory_items/inventory_transactions/schedules/shifts/reservations 表
以匹配当前 SQLAlchemy 模型，并新增 kpis/kpi_records 表。

Revision ID: m01_sync_phase1_models
Revises: l15i2kk28m3k
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = 'm01_sync_phase1_models'
down_revision = 'l15i2kk28m3k'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. 删除旧表（按依赖顺序：子表先删）──────────────────────────────
    op.drop_table('shifts')
    op.drop_table('schedules')
    op.drop_table('inventory_transactions')
    # dish_ingredients 外键依赖 inventory_items，先删
    conn = op.get_bind()
    di_exists = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='dish_ingredients')")
    ).scalar()
    if di_exists:
        op.drop_table('dish_ingredients')
    op.drop_table('inventory_items')
    op.drop_table('employees')
    op.drop_table('reservations')

    # ── 2. 重建 employees ────────────────────────────────────────────────
    op.create_table(
        'employees',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('email', sa.String(100)),
        sa.Column('position', sa.String(50)),
        sa.Column('skills', postgresql.ARRAY(sa.String), default=list),
        sa.Column('hire_date', sa.Date),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('preferences', sa.JSON, default=dict),
        sa.Column('performance_score', sa.String(10)),
        sa.Column('training_completed', postgresql.ARRAY(sa.String), default=list),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_employees_store_id', 'employees', ['store_id'])
    op.create_index('idx_employees_is_active', 'employees', ['is_active'])

    # ── 3. 重建 inventory_items ──────────────────────────────────────────
    op.create_table(
        'inventory_items',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('category', sa.String(50)),
        sa.Column('unit', sa.String(20)),
        sa.Column('current_quantity', sa.Float, nullable=False, default=0),
        sa.Column('min_quantity', sa.Float, nullable=False),
        sa.Column('max_quantity', sa.Float),
        sa.Column('unit_cost', sa.Integer),
        sa.Column('status', sa.String(20), nullable=False, default='normal'),
        sa.Column('supplier_name', sa.String(100)),
        sa.Column('supplier_contact', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_inventory_items_store_id', 'inventory_items', ['store_id'])
    op.create_index('idx_inventory_items_status', 'inventory_items', ['status'])

    # ── 4. 重建 inventory_transactions ──────────────────────────────────
    op.create_table(
        'inventory_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('item_id', sa.String(50), sa.ForeignKey('inventory_items.id'), nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('transaction_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('unit_cost', sa.Integer),
        sa.Column('total_cost', sa.Integer),
        sa.Column('quantity_before', sa.Float, nullable=False),
        sa.Column('quantity_after', sa.Float, nullable=False),
        sa.Column('reference_id', sa.String(100)),
        sa.Column('notes', sa.String(500)),
        sa.Column('performed_by', sa.String(100)),
        sa.Column('transaction_time', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_inv_trans_item_id', 'inventory_transactions', ['item_id'])
    op.create_index('idx_inv_trans_store_id', 'inventory_transactions', ['store_id'])
    op.create_index('idx_inv_trans_type', 'inventory_transactions', ['transaction_type'])

    # ── 5. 重建 schedules ────────────────────────────────────────────────
    op.create_table(
        'schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('schedule_date', sa.Date, nullable=False),
        sa.Column('total_employees', sa.String(10)),
        sa.Column('total_hours', sa.String(10)),
        sa.Column('is_published', sa.Boolean, default=False),
        sa.Column('published_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_schedules_store_id', 'schedules', ['store_id'])
    op.create_index('idx_schedules_date', 'schedules', ['schedule_date'])
    op.create_index('idx_schedules_store_date', 'schedules', ['store_id', 'schedule_date'], unique=True)

    # ── 6. 重建 shifts ───────────────────────────────────────────────────
    op.create_table(
        'shifts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('schedules.id'), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('shift_type', sa.String(20), nullable=False),
        sa.Column('start_time', sa.Time, nullable=False),
        sa.Column('end_time', sa.Time, nullable=False),
        sa.Column('position', sa.String(50)),
        sa.Column('is_confirmed', sa.Boolean, default=False),
        sa.Column('is_completed', sa.Boolean, default=False),
        sa.Column('notes', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_shifts_schedule_id', 'shifts', ['schedule_id'])
    op.create_index('idx_shifts_employee_id', 'shifts', ['employee_id'])

    # ── 7. 重建 reservations ─────────────────────────────────────────────
    op.create_table(
        'reservations',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('customer_name', sa.String(100), nullable=False),
        sa.Column('customer_phone', sa.String(20), nullable=False),
        sa.Column('customer_email', sa.String(100)),
        sa.Column('reservation_type', sa.String(20), nullable=False, default='regular'),
        sa.Column('reservation_date', sa.Date, nullable=False),
        sa.Column('reservation_time', sa.Time, nullable=False),
        sa.Column('party_size', sa.Integer, nullable=False),
        sa.Column('table_number', sa.String(20)),
        sa.Column('room_name', sa.String(50)),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('special_requests', sa.String(500)),
        sa.Column('dietary_restrictions', sa.String(255)),
        sa.Column('banquet_details', sa.JSON, default=dict),
        sa.Column('estimated_budget', sa.Integer),
        sa.Column('notes', sa.String(500)),
        sa.Column('arrival_time', sa.DateTime(timezone=True)),
        sa.Column('cancelled_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_reservations_store_id', 'reservations', ['store_id'])
    op.create_index('idx_reservations_date', 'reservations', ['reservation_date'])
    op.create_index('idx_reservations_store_date', 'reservations', ['store_id', 'reservation_date'])
    op.create_index('idx_reservations_store_status', 'reservations', ['store_id', 'status'])
    op.create_index('idx_reservations_phone', 'reservations', ['customer_phone'])

    # ── 8. 新建 kpis ─────────────────────────────────────────────────────
    op.create_table(
        'kpis',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('description', sa.String(255)),
        sa.Column('unit', sa.String(20)),
        sa.Column('target_value', sa.Float),
        sa.Column('warning_threshold', sa.Float),
        sa.Column('critical_threshold', sa.Float),
        sa.Column('calculation_method', sa.String(50)),
        sa.Column('is_active', sa.String(10), default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_kpis_category', 'kpis', ['category'])
    op.create_index('idx_kpis_is_active', 'kpis', ['is_active'])

    # ── 9. 新建 kpi_records ──────────────────────────────────────────────
    op.create_table(
        'kpi_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('kpi_id', sa.String(50), sa.ForeignKey('kpis.id'), nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('record_date', sa.Date, nullable=False),
        sa.Column('value', sa.Float, nullable=False),
        sa.Column('target_value', sa.Float),
        sa.Column('achievement_rate', sa.Float),
        sa.Column('previous_value', sa.Float),
        sa.Column('change_rate', sa.Float),
        sa.Column('status', sa.String(20)),
        sa.Column('trend', sa.String(20)),
        sa.Column('kpi_metadata', sa.JSON, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_kpi_record_kpi_store_date', 'kpi_records', ['kpi_id', 'store_id', 'record_date'])
    op.create_index('idx_kpi_record_store_date', 'kpi_records', ['store_id', 'record_date'])


def downgrade():
    op.drop_table('kpi_records')
    op.drop_table('kpis')
    op.drop_table('reservations')
    op.drop_table('shifts')
    op.drop_table('schedules')
    op.drop_table('inventory_transactions')
    op.drop_table('inventory_items')
    op.drop_table('employees')
