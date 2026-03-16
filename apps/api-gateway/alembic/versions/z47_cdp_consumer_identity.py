"""CDP Consumer Identity — 统一消费者身份 + ID映射 + 三表加 consumer_id

Sprint 1 地基层：
- consumer_identities 表（统一消费者身份）
- consumer_id_mappings 表（外部ID映射）
- orders/reservations/queues 加 consumer_id 字段

Revision ID: z47_cdp_consumer
Revises: z46_data_dictionary
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "z47_cdp_consumer"
down_revision = "z46_data_dictionary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # 1. consumer_identities 表
    # ============================================================
    op.create_table(
        "consumer_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("primary_phone", sa.String(20), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("gender", sa.String(10), nullable=True),
        sa.Column("birth_date", sa.Date, nullable=True),
        # 微信
        sa.Column("wechat_openid", sa.String(128), nullable=True),
        sa.Column("wechat_unionid", sa.String(128), nullable=True),
        sa.Column("wechat_nickname", sa.String(100), nullable=True),
        sa.Column("wechat_avatar_url", sa.String(500), nullable=True),
        # 聚合统计
        sa.Column("total_order_count", sa.Integer, default=0),
        sa.Column("total_order_amount_fen", sa.Integer, default=0),
        sa.Column("total_reservation_count", sa.Integer, default=0),
        sa.Column("first_order_at", sa.DateTime, nullable=True),
        sa.Column("last_order_at", sa.DateTime, nullable=True),
        sa.Column("first_store_id", sa.String(50), nullable=True),
        # RFM
        sa.Column("rfm_recency_days", sa.Integer, nullable=True),
        sa.Column("rfm_frequency", sa.Integer, nullable=True),
        sa.Column("rfm_monetary_fen", sa.Integer, nullable=True),
        # 标签
        sa.Column("tags", postgresql.JSON, server_default="[]"),
        # merge
        sa.Column("is_merged", sa.Boolean, server_default="false"),
        sa.Column("merged_into", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merged_at", sa.DateTime, nullable=True),
        # 来源
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("confidence_score", sa.Float, server_default="1.0"),
        sa.Column("extra", postgresql.JSON, server_default="{}"),
        # timestamps
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ci_phone_active", "consumer_identities", ["primary_phone", "is_merged"])
    op.create_index("idx_ci_wechat_openid", "consumer_identities", ["wechat_openid"])
    op.create_index("idx_ci_wechat_unionid", "consumer_identities", ["wechat_unionid"])
    op.create_index("idx_ci_merged_into", "consumer_identities", ["merged_into"])
    op.create_index("idx_ci_last_order", "consumer_identities", ["last_order_at"])

    # ============================================================
    # 2. consumer_id_mappings 表
    # ============================================================
    op.create_table(
        "consumer_id_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consumer_identities.id"), nullable=False),
        sa.Column("id_type", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=True),
        sa.Column("source_system", sa.String(50), nullable=True),
        sa.Column("confidence", sa.Integer, server_default="100"),
        sa.Column("is_verified", sa.Boolean, server_default="false"),
        sa.Column("verified_at", sa.DateTime, nullable=True),
        sa.Column("verified_by", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("deactivated_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id_type", "external_id", name="uq_id_type_external_id"),
    )
    op.create_index("idx_cim_consumer", "consumer_id_mappings", ["consumer_id"])
    op.create_index("idx_cim_type_ext", "consumer_id_mappings", ["id_type", "external_id"])
    op.create_index("idx_cim_consumer_active", "consumer_id_mappings", ["consumer_id", "is_active"])
    op.create_index("idx_cim_store", "consumer_id_mappings", ["store_id"])

    # ============================================================
    # 3. 三表加 consumer_id 字段
    # ============================================================
    op.add_column("orders", sa.Column("consumer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("idx_order_consumer_id", "orders", ["consumer_id"])

    op.add_column("reservations", sa.Column("consumer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("idx_reservation_consumer_id", "reservations", ["consumer_id"])

    # queues 表可能尚未创建（模型存在但无迁移），安全跳过
    op.execute(sa.text("""
        DO $$ BEGIN
            ALTER TABLE queues ADD COLUMN IF NOT EXISTS consumer_id UUID;
        EXCEPTION WHEN undefined_table THEN NULL;
        END $$
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE INDEX IF NOT EXISTS idx_queue_consumer_id ON queues (consumer_id);
        EXCEPTION WHEN undefined_table THEN NULL;
        END $$
    """))


def downgrade() -> None:
    # 三表移除 consumer_id
    op.execute(sa.text("""
        DO $$ BEGIN
            DROP INDEX IF EXISTS idx_queue_consumer_id;
            ALTER TABLE queues DROP COLUMN IF EXISTS consumer_id;
        EXCEPTION WHEN undefined_table THEN NULL;
        END $$
    """))

    op.drop_index("idx_reservation_consumer_id", "reservations")
    op.drop_column("reservations", "consumer_id")

    op.drop_index("idx_order_consumer_id", "orders")
    op.drop_column("orders", "consumer_id")

    # 移除 consumer_id_mappings
    op.drop_table("consumer_id_mappings")

    # 移除 consumer_identities
    op.drop_table("consumer_identities")
