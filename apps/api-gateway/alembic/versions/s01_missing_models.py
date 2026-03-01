"""Add missing model tables: suppliers, purchase_orders, backup_jobs,
competitor_stores, competitor_prices

Revision ID: s01_missing_models
Revises: s00_merge_heads
Create Date: 2026-02-28 00:01:00.000000

Covers ORM models that had no migration:
  - src/models/supply_chain.py  → suppliers, purchase_orders
  - src/models/backup_job.py    → backup_jobs
  - src/models/competitor.py    → competitor_stores, competitor_prices
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 's01_missing_models'
down_revision: Union[str, None] = 's00_merge_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── suppliers ─────────────────────────────────────────────────────────────
    op.create_table(
        'suppliers',
        sa.Column('id',             sa.String(),    primary_key=True),
        sa.Column('name',           sa.String(200), nullable=False),
        sa.Column('code',           sa.String(50),  unique=True),
        sa.Column('category',       sa.String(50),  nullable=False, server_default='food'),
        sa.Column('contact_person', sa.String(100)),
        sa.Column('phone',          sa.String(20)),
        sa.Column('email',          sa.String(100)),
        sa.Column('address',        sa.Text()),
        sa.Column('status',         sa.String(20),  nullable=False, server_default='active'),
        sa.Column('rating',         sa.Float(),     server_default='5.0'),
        sa.Column('payment_terms',  sa.String(50),  server_default='net30'),
        sa.Column('delivery_time',  sa.Integer(),   server_default='3'),
        sa.Column('notes',          sa.Text()),
        sa.Column('created_at',     sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',     sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index('ix_suppliers_name', 'suppliers', ['name'])
    op.create_index('ix_suppliers_code', 'suppliers', ['code'], unique=True)

    # ── purchase_orders ───────────────────────────────────────────────────────
    op.create_table(
        'purchase_orders',
        sa.Column('id',                sa.String(),    primary_key=True),
        sa.Column('order_number',      sa.String(50),  unique=True, nullable=False),
        sa.Column('supplier_id',       sa.String(),    sa.ForeignKey('suppliers.id'), nullable=False),
        sa.Column('store_id',          sa.String(),    sa.ForeignKey('stores.id'),    nullable=False),
        sa.Column('status',            sa.String(30),  nullable=False, server_default='pending'),
        sa.Column('total_amount',      sa.Integer(),   server_default='0'),
        sa.Column('items',             sa.JSON()),
        sa.Column('expected_delivery', sa.DateTime()),
        sa.Column('actual_delivery',   sa.DateTime()),
        sa.Column('notes',             sa.Text()),
        sa.Column('created_at',        sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',        sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index('ix_purchase_orders_number',     'purchase_orders', ['order_number'],  unique=True)
    op.create_index('ix_purchase_orders_store',      'purchase_orders', ['store_id'])
    op.create_index('ix_purchase_orders_supplier',   'purchase_orders', ['supplier_id'])

    # ── backup_jobs ───────────────────────────────────────────────────────────
    op.create_table(
        'backup_jobs',
        sa.Column('id',               postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('backup_type',      sa.String(20),  nullable=False, server_default='full'),
        sa.Column('since_timestamp',  sa.String(30)),
        sa.Column('tables',           sa.JSON(),      nullable=False,
                  server_default=sa.text("'[]'::json")),
        sa.Column('status',           sa.String(20),  nullable=False, server_default='pending'),
        sa.Column('celery_task_id',   sa.String(100)),
        sa.Column('progress',         sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('file_path',        sa.String(500)),
        sa.Column('file_size_bytes',  sa.Integer()),
        sa.Column('checksum',         sa.String(64)),
        sa.Column('row_counts',       sa.JSON()),
        sa.Column('error_message',    sa.Text()),
        sa.Column('completed_at',     sa.String(30)),
        sa.Column('created_at',       sa.DateTime(),  server_default=sa.func.now()),
        sa.Column('updated_at',       sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index('ix_backup_jobs_status', 'backup_jobs', ['status'])

    # ── competitor_stores ─────────────────────────────────────────────────────
    op.create_table(
        'competitor_stores',
        sa.Column('id',                  postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('our_store_id',        sa.String(50), sa.ForeignKey('stores.id'),
                  nullable=False),
        sa.Column('name',                sa.String(100), nullable=False),
        sa.Column('brand',               sa.String(100)),
        sa.Column('cuisine_type',        sa.String(50)),
        sa.Column('address',             sa.String(200)),
        sa.Column('distance_meters',     sa.Integer()),
        sa.Column('avg_price_per_person',sa.Numeric(10, 2)),
        sa.Column('rating',              sa.Numeric(3, 1)),
        sa.Column('monthly_customers',   sa.Integer()),
        sa.Column('is_active',           sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notes',               sa.Text()),
        sa.Column('created_at',          sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at',          sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_competitor_stores_our_store', 'competitor_stores', ['our_store_id'])

    # ── competitor_prices ─────────────────────────────────────────────────────
    op.create_table(
        'competitor_prices',
        sa.Column('id',            postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('competitor_stores.id'), nullable=False),
        sa.Column('dish_name',     sa.String(100), nullable=False),
        sa.Column('category',      sa.String(50)),
        sa.Column('price',         sa.Numeric(10, 2), nullable=False),
        sa.Column('record_date',   sa.Date(), nullable=False),
        sa.Column('our_dish_id',   postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('dishes.id'), nullable=True),
        sa.Column('created_at',    sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at',    sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_competitor_prices_competitor', 'competitor_prices', ['competitor_id'])
    op.create_index('ix_competitor_prices_date',       'competitor_prices', ['record_date'])


def downgrade() -> None:
    op.drop_table('competitor_prices')
    op.drop_table('competitor_stores')
    op.drop_table('backup_jobs')
    op.drop_table('purchase_orders')
    op.drop_table('suppliers')
