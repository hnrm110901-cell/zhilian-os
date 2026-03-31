"""z76: 门店间调拨 — inter_store_transfer_requests + inter_store_transfer_items

注意：本迁移的 down_revision 暂时设为 z68_mission_journey，
实际部署时请按照 git log 确认最新的 head 并调整 down_revision。
如果数据库已跑过 z69_fix_rls_session_variables，请将 down_revision 改为
"z69_fix_rls_session_variables"。

Revision ID: z76_inter_store_transfer
Revises: z68_mission_journey
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z76"
# TODO: 部署前确认实际最新 head，临时使用 z68
down_revision = "z75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. 创建调拨申请主表
    # ------------------------------------------------------------------ #
    op.create_table(
        "inter_store_transfer_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transfer_no", sa.String(30), nullable=False),
        sa.Column("from_store_id", UUID(as_uuid=True), nullable=False),
        sa.Column("to_store_id", UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("dispatched_at", sa.DateTime, nullable=True),
        sa.Column("received_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # 索引
    op.create_index(
        "ix_ist_requests_transfer_no",
        "inter_store_transfer_requests",
        ["transfer_no"],
        unique=True,
    )
    op.create_index(
        "ix_ist_requests_from_store_id",
        "inter_store_transfer_requests",
        ["from_store_id"],
    )
    op.create_index(
        "ix_ist_requests_to_store_id",
        "inter_store_transfer_requests",
        ["to_store_id"],
    )
    op.create_index(
        "ix_ist_requests_brand_id",
        "inter_store_transfer_requests",
        ["brand_id"],
    )
    op.create_index(
        "ix_ist_requests_status",
        "inter_store_transfer_requests",
        ["status"],
    )

    # ------------------------------------------------------------------ #
    # 2. 创建调拨明细表
    # ------------------------------------------------------------------ #
    op.create_table(
        "inter_store_transfer_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "transfer_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "inter_store_transfer_requests.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("ingredient_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("requested_qty", sa.Float, nullable=False),
        sa.Column("dispatched_qty", sa.Float, nullable=True),
        sa.Column("received_qty", sa.Float, nullable=True),
        sa.Column("unit_cost_fen", sa.Integer, nullable=True),
        sa.Column("qty_variance", sa.Float, nullable=True),
        sa.Column("variance_reason", sa.String(500), nullable=True),
    )

    op.create_index(
        "ix_ist_items_transfer_id",
        "inter_store_transfer_items",
        ["transfer_id"],
    )
    op.create_index(
        "ix_ist_items_ingredient_id",
        "inter_store_transfer_items",
        ["ingredient_id"],
    )

    # ------------------------------------------------------------------ #
    # 3. RLS 策略（允许调拨双方门店访问）
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE inter_store_transfer_requests ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE inter_store_transfer_items ENABLE ROW LEVEL SECURITY;")

    # 调拨申请：from_store 或 to_store 均可访问
    op.execute("""
        CREATE POLICY ist_requests_store_policy
        ON inter_store_transfer_requests
        FOR ALL
        USING (
            current_setting('app.current_tenant', TRUE) IS NOT NULL
            AND (
                from_store_id::text = current_setting('app.current_tenant', TRUE)
                OR to_store_id::text = current_setting('app.current_tenant', TRUE)
            )
        );
    """)

    # 调拨明细：通过主表 join 校验（使用 EXISTS 子查询）
    op.execute("""
        CREATE POLICY ist_items_store_policy
        ON inter_store_transfer_items
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM inter_store_transfer_requests r
                WHERE r.id = transfer_id
                AND current_setting('app.current_tenant', TRUE) IS NOT NULL
                AND (
                    r.from_store_id::text = current_setting('app.current_tenant', TRUE)
                    OR r.to_store_id::text = current_setting('app.current_tenant', TRUE)
                )
            )
        );
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ist_items_store_policy ON inter_store_transfer_items;")
    op.execute("DROP POLICY IF EXISTS ist_requests_store_policy ON inter_store_transfer_requests;")

    op.drop_index("ix_ist_items_ingredient_id", table_name="inter_store_transfer_items")
    op.drop_index("ix_ist_items_transfer_id", table_name="inter_store_transfer_items")
    op.drop_table("inter_store_transfer_items")

    op.drop_index("ix_ist_requests_status", table_name="inter_store_transfer_requests")
    op.drop_index("ix_ist_requests_brand_id", table_name="inter_store_transfer_requests")
    op.drop_index("ix_ist_requests_to_store_id", table_name="inter_store_transfer_requests")
    op.drop_index("ix_ist_requests_from_store_id", table_name="inter_store_transfer_requests")
    op.drop_index("ix_ist_requests_transfer_no", table_name="inter_store_transfer_requests")
    op.drop_table("inter_store_transfer_requests")
