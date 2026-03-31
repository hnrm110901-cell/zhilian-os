"""支付网关 — 实时支付记录表（gateway_payment_records）

注意：payment_records 表已由 payment_reconciliation 模型占用（对账流水场景）。
      本迁移创建 gateway_payment_records 表，用于实时支付网关（微信V3/支付宝）。

Revision ID: z70
Revises: z69
Create Date: 2026-03-31
"""

revision = "z70"
down_revision = "z69"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        "gateway_payment_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # 支付方式：wechat_jsapi / wechat_native / alipay_h5 / alipay_native 等
        sa.Column("payment_method", sa.String(32), nullable=False),
        # 金额（分），与DB其他表一致
        sa.Column("amount_fen", sa.Integer(), nullable=False),
        # 状态：pending / paid / refunding / refunded / failed / closed
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("third_party_trade_no", sa.String(64), nullable=True),
        sa.Column("prepay_id", sa.String(128), nullable=True),
        sa.Column("wechat_openid", sa.String(64), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column(
            "refund_amount_fen",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        # 原始回调报文，用于对账和争议处理
        sa.Column("callback_raw", sa.Text(), nullable=True),
    )

    # 索引
    op.create_index(
        "ix_gateway_payment_records_store_id",
        "gateway_payment_records",
        ["store_id"],
    )
    op.create_index(
        "ix_gateway_payment_records_order_id",
        "gateway_payment_records",
        ["order_id"],
    )
    op.create_index(
        "ix_gateway_payment_records_store_created",
        "gateway_payment_records",
        ["store_id", "created_at"],
    )
    op.create_index(
        "ix_gateway_payment_records_third_party_trade_no",
        "gateway_payment_records",
        ["third_party_trade_no"],
        unique=True,
        postgresql_where=sa.text("third_party_trade_no IS NOT NULL"),
    )

    # RLS — 多租户行级安全
    op.execute("ALTER TABLE gateway_payment_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gateway_payment_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY gateway_payment_records_tenant_isolation
        ON gateway_payment_records
        USING (
            current_setting('app.current_tenant', TRUE) IS NOT NULL
            AND store_id::text = current_setting('app.current_tenant', TRUE)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS gateway_payment_records_tenant_isolation "
        "ON gateway_payment_records"
    )
    op.drop_index(
        "ix_gateway_payment_records_third_party_trade_no",
        table_name="gateway_payment_records",
    )
    op.drop_index(
        "ix_gateway_payment_records_store_created",
        table_name="gateway_payment_records",
    )
    op.drop_index(
        "ix_gateway_payment_records_order_id",
        table_name="gateway_payment_records",
    )
    op.drop_index(
        "ix_gateway_payment_records_store_id",
        table_name="gateway_payment_records",
    )
    op.drop_table("gateway_payment_records")
