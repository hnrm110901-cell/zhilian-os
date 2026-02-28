"""
Phase 3-M3.1 — AES-256-GCM 密钥管理表

Revision ID: r02_security_tables
Revises: r01_bom_tables
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'r02_security_tables'
down_revision = 'r01_bom_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    key_status_enum = postgresql.ENUM(
        'active', 'rotating', 'retired', 'revoked',
        name='keystatus'
    )
    key_status_enum.create(op.get_bind(), checkfirst=True)

    key_algo_enum = postgresql.ENUM(
        'AES-256-GCM', 'AES-256-CBC',
        name='keyalgorithm'
    )
    key_algo_enum.create(op.get_bind(), checkfirst=True)

    # ── customer_keys ──────────────────────────────────────────────────────────
    op.create_table(
        'customer_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('key_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('key_alias', sa.String(100), nullable=True),
        sa.Column('algorithm', postgresql.ENUM(name='keyalgorithm', create_type=False), nullable=False, server_default='AES-256-GCM'),
        sa.Column('encrypted_dek', sa.Text(), nullable=False),
        sa.Column('status', postgresql.ENUM(name='keystatus', create_type=False), nullable=False, server_default='active'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('rotated_at', sa.DateTime(), nullable=True),
        sa.Column('rotated_by', sa.String(100), nullable=True),
        sa.Column('purpose', sa.String(50), nullable=False, server_default='data_encryption'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_customer_key_store_active', 'customer_keys', ['store_id', 'is_active'])
    op.create_index('idx_customer_key_store_version', 'customer_keys', ['store_id', 'key_version'])

    # ── encrypted_field_audit ──────────────────────────────────────────────────
    op.create_table(
        'encrypted_field_audit',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('key_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('record_id', sa.String(100), nullable=False),
        sa.Column('encrypted_at', sa.DateTime(), nullable=True),
        sa.Column('algorithm', sa.String(20), nullable=True, server_default='AES-256-GCM'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_enc_audit_store_table', 'encrypted_field_audit', ['store_id', 'table_name'])
    op.create_index('idx_enc_audit_key_id', 'encrypted_field_audit', ['key_id'])


def downgrade() -> None:
    op.drop_table('encrypted_field_audit')
    op.drop_table('customer_keys')
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS keyalgorithm"))
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS keystatus"))
