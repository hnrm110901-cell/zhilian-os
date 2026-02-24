"""
Add neural_event_logs table for event sourcing

Revision ID: o01_neural_event_log
Revises: n01_pos_webhook_secret
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'o01_neural_event_log'
down_revision = 'n01_pos_webhook_secret'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'neural_event_logs',
        sa.Column('event_id', sa.String(36), primary_key=True, comment='事件ID'),
        sa.Column('celery_task_id', sa.String(255), nullable=True, comment='Celery任务ID'),
        sa.Column('event_type', sa.String(100), nullable=False, comment='事件类型'),
        sa.Column('event_source', sa.String(100), nullable=False, comment='事件来源'),
        sa.Column('store_id', sa.String(36), nullable=False, comment='门店ID'),
        sa.Column('priority', sa.Integer(), nullable=True, default=0, comment='优先级'),
        sa.Column('data', sa.JSON(), nullable=True, comment='原始事件数据'),
        sa.Column(
            'processing_status',
            sa.Enum('queued', 'processing', 'completed', 'failed', 'retrying', name='eventprocessingstatus'),
            nullable=False,
            server_default='queued',
            comment='处理状态',
        ),
        sa.Column('vector_indexed', sa.Boolean(), nullable=True, default=False, comment='是否已写入向量DB'),
        sa.Column('wechat_sent', sa.Boolean(), nullable=True, default=False, comment='是否已触发企微推送'),
        sa.Column('downstream_tasks', sa.JSON(), nullable=True, comment='触发的下游任务列表'),
        sa.Column('actions_taken', sa.JSON(), nullable=True, comment='处理过程中执行的动作列表'),
        sa.Column('queued_at', sa.DateTime(), nullable=False, comment='入队时间'),
        sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始处理时间'),
        sa.Column('processed_at', sa.DateTime(), nullable=True, comment='处理完成时间'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='失败时的错误信息'),
        sa.Column('retry_count', sa.Integer(), nullable=True, default=0, comment='重试次数'),
    )
    op.create_index('ix_neural_event_logs_event_type', 'neural_event_logs', ['event_type'])
    op.create_index('ix_neural_event_logs_event_source', 'neural_event_logs', ['event_source'])
    op.create_index('ix_neural_event_logs_store_id', 'neural_event_logs', ['store_id'])
    op.create_index('ix_neural_event_logs_processing_status', 'neural_event_logs', ['processing_status'])
    op.create_index('ix_neural_event_logs_celery_task_id', 'neural_event_logs', ['celery_task_id'])


def downgrade():
    op.drop_index('ix_neural_event_logs_celery_task_id', 'neural_event_logs')
    op.drop_index('ix_neural_event_logs_processing_status', 'neural_event_logs')
    op.drop_index('ix_neural_event_logs_store_id', 'neural_event_logs')
    op.drop_index('ix_neural_event_logs_event_source', 'neural_event_logs')
    op.drop_index('ix_neural_event_logs_event_type', 'neural_event_logs')
    op.drop_table('neural_event_logs')
    op.execute("DROP TYPE IF EXISTS eventprocessingstatus")
