"""
添加联邦学习相关表

Revision ID: k04h1jj17l2j
Revises: j93g0ii06k1i
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa


revision = 'k04h1jj17l2j'
down_revision = 'j93g0ii06k1i'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fl_training_rounds',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('model_type', sa.String(50), nullable=False, index=True),
        sa.Column('status', sa.String(20), default='initialized', index=True),
        sa.Column('config', sa.JSON),
        sa.Column('global_model_parameters', sa.JSON),
        sa.Column('aggregation_method', sa.String(50)),
        sa.Column('num_participating_stores', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('completed_at', sa.DateTime),
    )

    op.create_table(
        'fl_model_uploads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('round_id', sa.String(36), sa.ForeignKey('fl_training_rounds.id'), nullable=False, index=True),
        sa.Column('store_id', sa.String(36), sa.ForeignKey('stores.id'), nullable=False, index=True),
        sa.Column('model_parameters', sa.JSON),
        sa.Column('training_metrics', sa.JSON),
        sa.Column('training_samples', sa.Integer, default=0),
        sa.Column('uploaded_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('fl_model_uploads')
    op.drop_table('fl_training_rounds')
