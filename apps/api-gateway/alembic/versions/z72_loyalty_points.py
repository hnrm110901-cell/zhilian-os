"""z72: 积分+会员等级体系 — loyalty_accounts / points_transactions / member_level_configs

Revision ID: z72
Revises: z71
Create Date: 2026-03-31
"""

import re
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "z72"
down_revision = "z71"
branch_labels = None
depends_on = None

_SAFE_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _assert_safe_ident(name: str) -> None:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier in migration: {name!r}")


def upgrade() -> None:
    # ── loyalty_accounts ───────────────────────────────────────────────────────
    op.create_table(
        "loyalty_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", sa.String(100), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0",
                  comment="当前可用积分"),
        sa.Column("lifetime_points", sa.Integer(), nullable=False, server_default="0",
                  comment="历史累计积分（只增不减，用于定级）"),
        sa.Column("member_level", sa.String(20), nullable=False, server_default="bronze",
                  comment="当前会员等级"),
        sa.Column("last_earn_at", sa.DateTime(), nullable=True),
        sa.Column("last_redeem_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_la_member_store", "loyalty_accounts",
                    ["member_id", "store_id"], unique=True)
    op.create_index("ix_la_store_id", "loyalty_accounts", ["store_id"])

    # ── points_transactions ────────────────────────────────────────────────────
    op.create_table(
        "points_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", sa.String(100), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("points_change", sa.Integer(), nullable=False,
                  comment="积分变动（正=获得，负=消耗）"),
        sa.Column("points_after", sa.Integer(), nullable=False,
                  comment="操作后积分余额快照"),
        sa.Column("change_reason", sa.String(30), nullable=False),
        sa.Column("order_id", sa.String(100), nullable=True),
        sa.Column("order_amount_fen", sa.Integer(), nullable=True,
                  comment="关联订单金额（分）"),
        sa.Column("operator_id", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_pt_member_created", "points_transactions",
                    ["member_id", "created_at"])
    op.create_index("ix_pt_store_created", "points_transactions",
                    ["store_id", "created_at"])
    op.create_index("ix_pt_account_id", "points_transactions", ["account_id"])
    op.create_index("ix_pt_order_id", "points_transactions", ["order_id"])

    # ── member_level_configs ───────────────────────────────────────────────────
    op.create_table(
        "member_level_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("level_name", sa.String(50), nullable=False, server_default=""),
        sa.Column("min_lifetime_points", sa.Integer(), nullable=False, server_default="0",
                  comment="升级所需历史累计积分"),
        sa.Column("points_rate", sa.Float(), nullable=False, server_default="1.0",
                  comment="积分倍率"),
        sa.Column("discount_rate", sa.Float(), nullable=False, server_default="1.0",
                  comment="消费折扣率（1.0=无折扣，0.9=九折）"),
        sa.Column("birthday_bonus", sa.Integer(), nullable=False, server_default="0",
                  comment="生日赠分（积分数）"),
        sa.Column("priority_reservation", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_mlc_store_level", "member_level_configs",
                    ["store_id", "level"], unique=True)

    # ── RLS 策略（三张表）─────────────────────────────────────────────────────
    conn = op.get_bind()
    for tbl in ("loyalty_accounts", "points_transactions", "member_level_configs"):
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
    for tbl in ("loyalty_accounts", "points_transactions", "member_level_configs"):
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}"))
        conn.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY"))

    op.drop_table("member_level_configs")
    op.drop_table("points_transactions")
    op.drop_table("loyalty_accounts")
