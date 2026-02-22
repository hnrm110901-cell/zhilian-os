"""
添加 AI 模型市场相关表

Revision ID: j93g0ii06k1i
Revises: i82f9hh95j0h
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa


revision = 'j93g0ii06k1i'
down_revision = 'i82f9hh95j0h'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_models',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('model_name', sa.String(200), nullable=False),
        sa.Column('model_type', sa.String(50), nullable=False, index=True),
        sa.Column('model_level', sa.String(50), nullable=False, index=True),
        sa.Column('industry_category', sa.String(50), index=True),
        sa.Column('description', sa.Text),
        sa.Column('price', sa.Float, default=0.0),
        sa.Column('training_stores_count', sa.Integer, default=0),
        sa.Column('training_data_points', sa.Integer, default=0),
        sa.Column('accuracy', sa.Float, default=0.0),
        sa.Column('status', sa.String(20), default='active', index=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
    )

    op.create_table(
        'model_purchases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id'), nullable=False, index=True),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('ai_models.id'), nullable=False, index=True),
        sa.Column('purchase_date', sa.DateTime, nullable=False),
        sa.Column('expiry_date', sa.DateTime, nullable=False),
        sa.Column('price_paid', sa.Float, default=0.0),
        sa.Column('status', sa.String(20), default='active', index=True),
    )

    op.create_table(
        'data_contributions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id'), nullable=False, index=True),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('ai_models.id'), nullable=False, index=True),
        sa.Column('data_points_contributed', sa.Integer, default=0),
        sa.Column('quality_score', sa.Float, default=0.0),
        sa.Column('contribution_date', sa.DateTime, nullable=False),
        sa.Column('revenue_share', sa.Float, default=0.0),
    )


def downgrade() -> None:
    op.drop_table('data_contributions')
    op.drop_table('model_purchases')
    op.drop_table('ai_models')
