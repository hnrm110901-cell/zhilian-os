"""z80: 财务日快照缓存表 — finance_daily_snapshots

加速财务聚合查询，避免每次 API 请求都扫全表。
快照由后台 Celery 任务在每日凌晨 02:30 生成。

Revision ID: z80
Revises: z77
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z80"
down_revision = "z79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_daily_snapshots",
        # ── 主键 ──
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # ── 门店 + 日期（联合唯一，确保每店每日只有一条快照） ──
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        # ── 营收（分） ──
        sa.Column("gross_revenue_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("discount_amount_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("net_revenue_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("order_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_order_fen", sa.Integer, nullable=False, server_default="0"),
        # ── 成本（分） ──
        sa.Column("ingredient_cost_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("labor_cost_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("waste_cost_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_cost_fen", sa.BigInteger, nullable=False, server_default="0"),
        # ── 利润（分） ──
        sa.Column("gross_profit_fen", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("net_profit_fen", sa.BigInteger, nullable=False, server_default="0"),
        # ── 利润率（float，百分比值，如 32.5 表示 32.5%） ──
        sa.Column("gross_margin_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("net_margin_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("food_cost_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("labor_cost_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("waste_rate", sa.Float, nullable=False, server_default="0"),
        # ── 元数据 ──
        sa.Column(
            "generated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # ── 约束 ──
        sa.UniqueConstraint("store_id", "snapshot_date", name="uq_finance_snapshot_store_date"),
    )

    # RLS：只能读写本租户的快照（与项目其他表保持一致，使用 app.current_tenant）
    op.execute("ALTER TABLE finance_daily_snapshots ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE finance_daily_snapshots FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY finance_daily_snapshots_tenant_isolation
            ON finance_daily_snapshots
            USING (
                current_setting('app.current_tenant', TRUE) IS NOT NULL
                AND store_id::text = current_setting('app.current_tenant', TRUE)
            );
        """
    )

    # 索引：按门店+日期范围查询（最常用）
    op.create_index(
        "idx_finance_snapshot_store_date",
        "finance_daily_snapshots",
        ["store_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS finance_daily_snapshots_tenant_isolation
            ON finance_daily_snapshots;
        """
    )
    op.drop_index("idx_finance_snapshot_store_date", table_name="finance_daily_snapshots")
    op.drop_table("finance_daily_snapshots")
