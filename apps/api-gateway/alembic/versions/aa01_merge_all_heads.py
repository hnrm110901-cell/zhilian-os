"""合并所有迁移头（merge all heads）

将三条并行迁移链合并为单一 HEAD：
  - t01_all_missing_tables  （模型补全链）
  - z02_dish_bom_version    （FCT / 本体论链）
  - z03_execution_audit     （RLS 品牌隔离 + 可信执行层链）

Revision ID: aa01_merge_all_heads
Revises: t01_all_missing_tables, z02_dish_bom_version, z03_execution_audit
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'aa01_merge_all_heads'
down_revision: Union[str, Sequence[str], None] = (
    't01_all_missing_tables',
    'z02_dish_bom_version',
    'z03_execution_audit',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """合并迁移，无 DDL 变更。"""
    pass


def downgrade() -> None:
    """合并迁移，降级无操作。"""
    pass
