"""z77: 收货验收 — purchase_receivings + purchase_receiving_items + receiving_disputes

Revision ID: z77_receiving_inspection
Revises: z76_inter_store_transfer
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z77"
down_revision = "z76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. 创建收货主表
    # ------------------------------------------------------------------ #
    op.create_table(
        "purchase_receivings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("receiving_no", sa.String(30), nullable=False),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_name", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("received_by", UUID(as_uuid=True), nullable=False),
        sa.Column("received_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("invoice_no", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("total_amount_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "ix_pr_receiving_no",
        "purchase_receivings",
        ["receiving_no"],
        unique=True,
    )
    op.create_index("ix_pr_store_id", "purchase_receivings", ["store_id"])
    op.create_index("ix_pr_purchase_order_id", "purchase_receivings", ["purchase_order_id"])
    op.create_index("ix_pr_status", "purchase_receivings", ["status"])

    # ------------------------------------------------------------------ #
    # 2. 创建收货明细表
    # ------------------------------------------------------------------ #
    op.create_table(
        "purchase_receiving_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "receiving_id",
            UUID(as_uuid=True),
            sa.ForeignKey("purchase_receivings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ingredient_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("ordered_qty", sa.Float, nullable=True),
        sa.Column("received_qty", sa.Float, nullable=False),
        sa.Column("rejected_qty", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit_price_fen", sa.Integer, nullable=True),
        sa.Column(
            "quality_status",
            sa.String(20),
            nullable=False,
            server_default="pass",
        ),
        sa.Column("quality_notes", sa.String(500), nullable=True),
        sa.Column("temperature", sa.Float, nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("batch_no", sa.String(100), nullable=True),
        sa.Column(
            "has_shortage", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column(
            "has_quality_issue", sa.Boolean, nullable=False, server_default="false"
        ),
    )

    op.create_index(
        "ix_pri_receiving_id", "purchase_receiving_items", ["receiving_id"]
    )
    op.create_index(
        "ix_pri_ingredient_id", "purchase_receiving_items", ["ingredient_id"]
    )

    # ------------------------------------------------------------------ #
    # 3. 创建争议记录表
    # ------------------------------------------------------------------ #
    op.create_table(
        "receiving_disputes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "receiving_id",
            UUID(as_uuid=True),
            sa.ForeignKey("purchase_receivings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("purchase_receiving_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dispute_type", sa.String(20), nullable=False),
        sa.Column("claimed_amount_fen", sa.Integer, nullable=True),
        sa.Column(
            "resolution",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "ix_rd_receiving_id", "receiving_disputes", ["receiving_id"]
    )
    op.create_index("ix_rd_item_id", "receiving_disputes", ["item_id"])

    # ------------------------------------------------------------------ #
    # 4. RLS 策略（按 store_id）
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE purchase_receivings ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE purchase_receivings FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE purchase_receiving_items ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE purchase_receiving_items FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE receiving_disputes ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE receiving_disputes FORCE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY pr_store_policy
        ON purchase_receivings
        FOR ALL
        USING (
            current_setting('app.current_tenant', TRUE) IS NOT NULL
            AND store_id::text = current_setting('app.current_tenant', TRUE)
        );
    """)

    op.execute("""
        CREATE POLICY pri_store_policy
        ON purchase_receiving_items
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM purchase_receivings pr
                WHERE pr.id = receiving_id
                AND pr.store_id::text = current_setting('app.current_tenant', TRUE)
            )
        );
    """)

    op.execute("""
        CREATE POLICY rd_store_policy
        ON receiving_disputes
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM purchase_receivings pr
                WHERE pr.id = receiving_id
                AND pr.store_id::text = current_setting('app.current_tenant', TRUE)
            )
        );
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rd_store_policy ON receiving_disputes;")
    op.execute("DROP POLICY IF EXISTS pri_store_policy ON purchase_receiving_items;")
    op.execute("DROP POLICY IF EXISTS pr_store_policy ON purchase_receivings;")

    op.drop_index("ix_rd_item_id", table_name="receiving_disputes")
    op.drop_index("ix_rd_receiving_id", table_name="receiving_disputes")
    op.drop_table("receiving_disputes")

    op.drop_index("ix_pri_ingredient_id", table_name="purchase_receiving_items")
    op.drop_index("ix_pri_receiving_id", table_name="purchase_receiving_items")
    op.drop_table("purchase_receiving_items")

    op.drop_index("ix_pr_status", table_name="purchase_receivings")
    op.drop_index("ix_pr_purchase_order_id", table_name="purchase_receivings")
    op.drop_index("ix_pr_store_id", table_name="purchase_receivings")
    op.drop_index("ix_pr_receiving_no", table_name="purchase_receivings")
    op.drop_table("purchase_receivings")
