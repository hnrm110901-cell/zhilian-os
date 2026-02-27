"""
Phase 3 — WasteEvent PostgreSQL 表迁移

Revision ID: r04_waste_event_table
Revises: r03_knowledge_rule_tables
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'r04_waste_event_table'
down_revision = 'r03_knowledge_rule_tables'
branch_labels = None
depends_on = None

_EVENT_TYPES = ('cooking_loss', 'spoilage', 'over_prep', 'drop_damage',
                'quality_reject', 'transfer_loss', 'unknown')
_EVENT_STATUSES = ('pending', 'analyzing', 'analyzed', 'verified', 'closed')


def upgrade() -> None:
    waste_type_enum = postgresql.ENUM(*_EVENT_TYPES, name='wasteeventtype')
    waste_type_enum.create(op.get_bind(), checkfirst=True)
    waste_status_enum = postgresql.ENUM(*_EVENT_STATUSES, name='wasteeventstatus')
    waste_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'waste_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', sa.String(50), unique=True, nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('event_type', waste_type_enum, nullable=False, server_default='unknown'),
        sa.Column('status', waste_status_enum, nullable=False, server_default='pending'),
        sa.Column('dish_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('dishes.id'), nullable=True),
        sa.Column('ingredient_id', sa.String(50),
                  sa.ForeignKey('inventory_items.id'), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 4), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('theoretical_qty', sa.Numeric(10, 4), nullable=True),
        sa.Column('variance_qty', sa.Numeric(10, 4), nullable=True),
        sa.Column('variance_pct', sa.Float(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('reported_by', sa.String(100), nullable=True),
        sa.Column('assigned_staff_id', sa.String(100), nullable=True),
        sa.Column('root_cause', sa.String(50), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('evidence', postgresql.JSON(), nullable=True),
        sa.Column('scores', postgresql.JSON(), nullable=True),
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('wechat_action_id', sa.String(50), nullable=True),
        sa.Column('photo_urls', postgresql.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_waste_store_date', 'waste_events', ['store_id', 'occurred_at'])
    op.create_index('idx_waste_type_status', 'waste_events', ['event_type', 'status'])
    op.create_index('idx_waste_dish', 'waste_events', ['dish_id'])
    op.create_index('idx_waste_ingredient', 'waste_events', ['ingredient_id'])

    # RLS
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE waste_events ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text(
        "CREATE POLICY tenant_isolation ON waste_events "
        "USING (store_id = current_setting('app.current_store_id', TRUE))"
    ))


def downgrade() -> None:
    op.drop_table('waste_events')
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS wasteeventstatus"))
    op.get_bind().execute(sa.text("DROP TYPE IF EXISTS wasteeventtype"))
