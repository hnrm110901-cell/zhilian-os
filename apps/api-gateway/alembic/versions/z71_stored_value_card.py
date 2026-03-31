"""z71: 储值卡体系 — stored_value_accounts / stored_value_transactions / recharge_promotions

每张表启用 RLS（app.current_tenant + IS NOT NULL 拒绝未授权访问）。

Revision ID: z71
Revises: z70
Create Date: 2026-03-31
"""

import re
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "z71"
down_revision = "z70"
branch_labels = None
depends_on = None

_SAFE_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _assert_safe_ident(name: str) -> None:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier in migration: {name!r}")


def upgrade() -> None:
    # ── stored_value_accounts ──────────────────────────────────────────────────
    op.create_table(
        "stored_value_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", sa.String(100), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("balance_fen", sa.Integer(), nullable=False, server_default="0",
                  comment="本金余额（分）"),
        sa.Column("gift_balance_fen", sa.Integer(), nullable=False, server_default="0",
                  comment="赠送金余额（分）"),
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0",
                  comment="乐观锁版本号"),
        sa.Column("last_recharge_at", sa.DateTime(), nullable=True),
        sa.Column("last_consume_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_sva_member_store", "stored_value_accounts",
                    ["member_id", "store_id"], unique=True)
    op.create_index("ix_sva_store_id", "stored_value_accounts", ["store_id"])

    # ── stored_value_transactions ──────────────────────────────────────────────
    op.create_table(
        "stored_value_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", sa.String(100), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("amount_fen", sa.Integer(), nullable=False,
                  comment="本金变动（分），正=增加，负=减少"),
        sa.Column("gift_amount_fen", sa.Integer(), nullable=False, server_default="0",
                  comment="赠送金变动（分）"),
        sa.Column("balance_after", sa.Integer(), nullable=False,
                  comment="操作后本金余额快照（分）"),
        sa.Column("gift_balance_after", sa.Integer(), nullable=False, server_default="0",
                  comment="操作后赠送金余额快照（分）"),
        sa.Column("order_id", sa.String(100), nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("operator_id", sa.String(100), nullable=True),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_svt_member_created", "stored_value_transactions",
                    ["member_id", "created_at"])
    op.create_index("ix_svt_store_created", "stored_value_transactions",
                    ["store_id", "created_at"])
    op.create_index("ix_svt_account_id", "stored_value_transactions", ["account_id"])
    op.create_index("ix_svt_order_id", "stored_value_transactions", ["order_id"])

    # ── recharge_promotions ────────────────────────────────────────────────────
    op.create_table(
        "recharge_promotions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("min_recharge_fen", sa.Integer(), nullable=False,
                  comment="触发门槛（分）"),
        sa.Column("gift_amount_fen", sa.Integer(), nullable=False, server_default="0",
                  comment="固定赠送额（分）"),
        sa.Column("gift_rate", sa.Float(), nullable=False, server_default="0.0",
                  comment="比例赠送率（0.0~1.0）"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_rp_store_active", "recharge_promotions", ["store_id", "is_active"])

    # ── RLS 策略（三张表）─────────────────────────────────────────────────────
    conn = op.get_bind()
    for tbl in ("stored_value_accounts", "stored_value_transactions", "recharge_promotions"):
        _assert_safe_ident(tbl)
        conn.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {tbl} "
            f"USING ("
            f"  current_setting('app.current_tenant', TRUE) IS NOT NULL"
            f"  AND store_id::text = current_setting('app.current_tenant', TRUE)"
            f")"
        ))
        conn.execute(sa.text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    conn = op.get_bind()
    for tbl in ("stored_value_accounts", "stored_value_transactions", "recharge_promotions"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}"))
        conn.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY"))

    op.drop_table("recharge_promotions")
    op.drop_table("stored_value_transactions")
    op.drop_table("stored_value_accounts")
