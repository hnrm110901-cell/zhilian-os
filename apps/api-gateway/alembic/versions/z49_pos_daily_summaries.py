"""POS 日营业汇总表 + orders 补充列

创建 daily_summaries 表，供品智/天财等 POS 适配器写入每日营业汇总数据。
同时补充 orders.sales_channel / orders.customer_phone / orders.customer_name
字段（若不存在）。

Revision ID: z49_pos_daily_summaries
Revises: z48_cdp_pdm_link
Create Date: 2026-03-14
"""
from alembic import op, context
import sqlalchemy as sa

revision = "z49_pos_daily_summaries"
down_revision = "z48_cdp_pdm_link"
branch_labels = None
depends_on = None


def _col_exists(conn, table: str, col: str) -> bool:
    if conn is None:
        return False
    r = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": col},
    )
    return bool(r.scalar())


def _table_exists(conn, table: str) -> bool:
    if conn is None:
        return False
    r = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :t)"
        ),
        {"t": table},
    )
    return bool(r.scalar())


def upgrade() -> None:
    conn = None if context.is_offline_mode() else op.get_bind()

    # ── daily_summaries ─────────────────────────────────────────────────────
    if not _table_exists(conn, "daily_summaries"):
        op.create_table(
            "daily_summaries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("store_id", sa.String(50), nullable=False, comment="门店ID"),
            sa.Column("business_date", sa.Date(), nullable=False, comment="营业日期"),
            # 营收（分，int）
            sa.Column("revenue_cents", sa.BigInteger(), nullable=False, default=0,
                      comment="营收金额（分）"),
            sa.Column("order_count", sa.Integer(), nullable=False, default=0,
                      comment="订单数"),
            sa.Column("customer_count", sa.Integer(), nullable=False, default=0,
                      comment="客流数"),
            sa.Column("avg_ticket_cents", sa.Integer(), nullable=False, default=0,
                      comment="客单价（分）"),
            # 数据来源
            sa.Column("source", sa.String(50), nullable=False, default="pos",
                      comment="数据来源：pinzhi/tiancai/aoqiwei 等"),
            sa.Column("raw_data", sa.Text(), nullable=True, comment="原始JSON备份"),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("store_id", "business_date", "source",
                                name="uq_daily_summaries_store_date_source"),
        )
        op.create_index("idx_daily_summaries_store_date",
                        "daily_summaries", ["store_id", "business_date"])
        op.create_index("idx_daily_summaries_date",
                        "daily_summaries", ["business_date"])

    # ── orders 补充列 ────────────────────────────────────────────────────────
    # sales_channel（POS来源渠道，如 pinzhi/tiancai/meituan）
    if not _col_exists(conn, "orders", "sales_channel"):
        op.execute(sa.text(
            "ALTER TABLE orders ADD COLUMN sales_channel VARCHAR(50)"
        ))

    # customer_phone / customer_name（已在初始 schema 存在，但部分部署可能缺少）
    if not _col_exists(conn, "orders", "customer_phone"):
        op.execute(sa.text(
            "ALTER TABLE orders ADD COLUMN customer_phone VARCHAR(20)"
        ))
    if not _col_exists(conn, "orders", "customer_name"):
        op.execute(sa.text(
            "ALTER TABLE orders ADD COLUMN customer_name VARCHAR(100)"
        ))


def downgrade() -> None:
    conn = None if context.is_offline_mode() else op.get_bind()
    if _table_exists(conn, "daily_summaries"):
        op.drop_table("daily_summaries")
