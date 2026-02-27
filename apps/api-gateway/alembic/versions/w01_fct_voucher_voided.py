"""FCT 凭证状态增加 voided（作废）

Revision ID: w01_fct_voucher_voided
Revises: v01_fct_phase4_tables
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op

revision = 'w01_fct_voucher_voided'
down_revision = 'v01_fct_phase4_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE fctvoucherstatus ADD VALUE 'voided';
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)


def downgrade() -> None:
    # PostgreSQL enum 无法简单删除值，且可能已有数据使用 voided，故 downgrade 仅注释
    pass
