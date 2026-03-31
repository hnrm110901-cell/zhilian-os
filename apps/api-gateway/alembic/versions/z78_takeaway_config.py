"""z78: 外卖平台配置表 — takeaway_platform_configs

Revision ID: z78_takeaway_config
Revises: z77_receiving_inspection
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z78"
down_revision = "z77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 创建外卖平台配置表
    # 每个门店对每个外卖平台有一行独立配置
    # ------------------------------------------------------------------ #
    op.create_table(
        "takeaway_platform_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False),
        # 平台标识: meituan / eleme / douyin
        sa.Column("platform", sa.String(30), nullable=False),
        # 自动接单开关
        sa.Column(
            "auto_accept_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        # 最大并发订单数（超过后暂停自动接单）
        sa.Column(
            "max_concurrent_orders",
            sa.Integer,
            nullable=False,
            server_default=sa.text("10"),
        ),
        # 该平台是否营业中（配合沽清/下线使用）
        sa.Column(
            "is_online",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        # 平台佣金率（0.0~1.0，用于利润核算）
        sa.Column(
            "commission_rate",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        # 审计字段
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        # 每个门店对每个平台只有一行配置
        sa.UniqueConstraint("store_id", "platform", name="uq_takeaway_config_store_platform"),
    )

    # ── 索引 ──────────────────────────────────────────────────────────
    op.create_index(
        "ix_takeaway_platform_configs_store_id",
        "takeaway_platform_configs",
        ["store_id"],
    )

    # ── RLS 行级安全（使用 app.current_tenant，与项目其他表一致） ──────
    op.execute("ALTER TABLE takeaway_platform_configs ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY takeaway_platform_configs_tenant_isolation
        ON takeaway_platform_configs
        USING (
            store_id::text = current_setting('app.current_tenant', true)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS takeaway_platform_configs_tenant_isolation ON takeaway_platform_configs"
    )
    op.drop_index("ix_takeaway_platform_configs_store_id", table_name="takeaway_platform_configs")
    op.drop_table("takeaway_platform_configs")
