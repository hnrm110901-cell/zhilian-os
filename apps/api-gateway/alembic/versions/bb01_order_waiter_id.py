"""add waiter_id to orders table

服务员ID字段，用于门店记忆层的员工绩效基线计算（ARCH-003）。
可为空，向后兼容；历史订单保持 NULL。

Revision ID: bb01_order_waiter_id
Revises: aa01_merge_all_heads
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'bb01_order_waiter_id'
down_revision: Union[str, Sequence[str], None] = 'aa01_merge_all_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('waiter_id', sa.String(50), nullable=True),
    )
    op.create_index(
        'idx_order_store_waiter',
        'orders',
        ['store_id', 'waiter_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_order_store_waiter', table_name='orders')
    op.drop_column('orders', 'waiter_id')
