"""Merge q01_ops_tables and r12_fct into a single head

Revision ID: s00_merge_heads
Revises: q01_ops_tables, r12_fct
Create Date: 2026-02-28 00:00:00.000000

The migration chain split at rls_001_tenant_isolation into two parallel branches:
  Branch A: rls_001 → n01 → o01 → p01 → q01_ops_tables
  Branch B: rls_001 → r01 → r02 → ... → r12_fct

This empty merge migration reconciles both branches into a single linear head.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 's00_merge_heads'
down_revision: Union[str, Sequence[str], None] = ('q01_ops_tables', 'r12_fct')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
