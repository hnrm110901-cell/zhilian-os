"""z75: 多渠道独立定价 — DishChannelPrice / TimePeriodPrice

Revision ID: z75
Revises: z74
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "z75"
down_revision = "z74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. dish_channel_prices — 渠道定价
    op.create_table(
        "dish_channel_prices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("dish_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "channel",
            sa.Enum(
                "dine_in",
                "meituan",
                "eleme",
                "douyin",
                "miniprogram",
                "corporate",
                name="dish_channel_enum",
            ),
            nullable=False,
        ),
        sa.Column("price_fen", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "dish_id", "channel", name="uq_dish_channel_price"),
    )
    op.create_index("idx_dish_channel_price_store_id", "dish_channel_prices", ["store_id"])
    op.create_index("idx_dish_channel_price_dish_id", "dish_channel_prices", ["dish_id"])
    op.create_index("idx_dish_channel_price_channel", "dish_channel_prices", ["channel"])

    # 2. time_period_prices — 时段定价规则
    op.create_table(
        "time_period_prices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "period_type",
            sa.Enum(
                "lunch",
                "dinner",
                "breakfast",
                "late_night",
                "holiday",
                "weekend",
                name="time_period_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column("weekdays", ARRAY(sa.Integer), nullable=False),
        sa.Column("apply_to_dishes", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("discount_rate", sa.Float, nullable=True),
        sa.Column("fixed_price_json", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_time_period_price_store_id", "time_period_prices", ["store_id"])
    op.create_index("idx_time_period_price_period_type", "time_period_prices", ["period_type"])
    op.create_index("idx_time_period_price_is_active", "time_period_prices", ["is_active"])

    # RLS 策略（两张表都含 store_id，按门店隔离）
    for tbl in ("dish_channel_prices", "time_period_prices"):
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

    for tbl in ("dish_channel_prices", "time_period_prices"):
        conn.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}"))

    op.drop_table("time_period_prices")
    op.drop_table("dish_channel_prices")

    # 删除 enum 类型
    op.execute("DROP TYPE IF EXISTS dish_channel_enum")
    op.execute("DROP TYPE IF EXISTS time_period_type_enum")
