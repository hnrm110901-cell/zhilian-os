"""
初始数据库架构 - 创建所有核心表

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建所有核心表"""

    # 1. 创建stores表（门店表）
    op.create_table(
        'stores',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(20), unique=True, nullable=False),
        sa.Column('address', sa.String(200)),
        sa.Column('phone', sa.String(20)),
        sa.Column('manager_name', sa.String(50)),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('opening_hours', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_stores_code', 'stores', ['code'])
    op.create_index('idx_stores_status', 'stores', ['status'])

    # 2. 创建users表（用户表）
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('email', sa.String(100), unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(100)),
        sa.Column('phone', sa.String(20)),
        sa.Column('role', sa.String(50), default='user'),
        sa.Column('store_id', sa.String(50)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_superuser', sa.Boolean, default=False),
        sa.Column('last_login', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_users_username', 'users', ['username'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_store_id', 'users', ['store_id'])

    # 3. 创建employees表（员工表）
    op.create_table(
        'employees',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('employee_id', sa.String(50), unique=True, nullable=False),
        sa.Column('position', sa.String(50)),
        sa.Column('phone', sa.String(20)),
        sa.Column('email', sa.String(100)),
        sa.Column('hire_date', sa.Date),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('skills', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_employees_store_id', 'employees', ['store_id'])
    op.create_index('idx_employees_employee_id', 'employees', ['employee_id'])
    op.create_index('idx_employees_status', 'employees', ['status'])

    # 4. 创建orders表（订单表）
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('order_number', sa.String(50), unique=True, nullable=False),
        sa.Column('table_number', sa.String(20)),
        sa.Column('customer_name', sa.String(100)),
        sa.Column('customer_phone', sa.String(20)),
        sa.Column('order_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('total_amount', sa.Numeric(10, 2), default=0),
        sa.Column('payment_method', sa.String(50)),
        sa.Column('payment_status', sa.String(20), default='unpaid'),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_orders_store_id', 'orders', ['store_id'])
    op.create_index('idx_orders_order_number', 'orders', ['order_number'])
    op.create_index('idx_orders_store_status', 'orders', ['store_id', 'status'])
    op.create_index('idx_orders_store_time', 'orders', ['store_id', 'order_time'])

    # 5. 创建order_items表（订单项表）
    op.create_table(
        'order_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id'), nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('item_name', sa.String(100), nullable=False),
        sa.Column('item_id', sa.String(50)),
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_order_items_order_id', 'order_items', ['order_id'])
    op.create_index('idx_order_items_store_id', 'order_items', ['store_id'])

    # 6. 创建inventory_items表（库存项表）
    op.create_table(
        'inventory_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('category', sa.String(50)),
        sa.Column('unit', sa.String(20)),
        sa.Column('unit_price', sa.Numeric(10, 2)),
        sa.Column('current_quantity', sa.Numeric(10, 2), default=0),
        sa.Column('min_quantity', sa.Numeric(10, 2)),
        sa.Column('max_quantity', sa.Numeric(10, 2)),
        sa.Column('status', sa.String(20), default='normal'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_inventory_items_store_id', 'inventory_items', ['store_id'])
    op.create_index('idx_inventory_items_category', 'inventory_items', ['category'])

    # 7. 创建inventory_transactions表（库存交易表）
    op.create_table(
        'inventory_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_items.id'), nullable=False),
        sa.Column('transaction_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2)),
        sa.Column('total_amount', sa.Numeric(10, 2)),
        sa.Column('transaction_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_inventory_trans_store_id', 'inventory_transactions', ['store_id'])
    op.create_index('idx_inventory_trans_item_id', 'inventory_transactions', ['item_id'])

    # 8. 创建schedules表（排班表）
    op.create_table(
        'schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('shift_type', sa.String(20)),
        sa.Column('start_time', sa.Time),
        sa.Column('end_time', sa.Time),
        sa.Column('status', sa.String(20), default='scheduled'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_schedules_store_id', 'schedules', ['store_id'])
    op.create_index('idx_schedules_employee_id', 'schedules', ['employee_id'])
    op.create_index('idx_schedules_date', 'schedules', ['date'])

    # 9. 创建shifts表（班次表）
    op.create_table(
        'shifts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('start_time', sa.Time, nullable=False),
        sa.Column('end_time', sa.Time, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_shifts_store_id', 'shifts', ['store_id'])

    # 10. 创建reservations表（预订表）
    op.create_table(
        'reservations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('customer_name', sa.String(100), nullable=False),
        sa.Column('customer_phone', sa.String(20), nullable=False),
        sa.Column('reservation_date', sa.Date, nullable=False),
        sa.Column('reservation_time', sa.Time, nullable=False),
        sa.Column('party_size', sa.Integer, nullable=False),
        sa.Column('table_number', sa.String(20)),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_reservations_store_id', 'reservations', ['store_id'])
    op.create_index('idx_reservations_date', 'reservations', ['reservation_date'])
    op.create_index('idx_reservations_store_date', 'reservations', ['store_id', 'reservation_date'])
