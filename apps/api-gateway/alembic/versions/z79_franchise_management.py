"""z79: 加盟商管理 — franchisees / franchise_contracts / franchise_royalties / franchisee_portal_access

Revision ID: z79
Revises: z78
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "z79"
down_revision = "z78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. franchisees — 加盟商（法人/个人）
    # ------------------------------------------------------------------ #
    op.create_table(
        "franchisees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.String(50), nullable=False),
        sa.Column("company_name", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(64), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("contact_email", sa.String(128), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        # bank_account 加密存储（AES-256-GCM，ENC: 前缀），预留 256 字节
        sa.Column("bank_account", sa.String(256), nullable=True),
        sa.Column("tax_no", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_franchisees_brand_id", "franchisees", ["brand_id"])
    op.create_index("ix_franchisees_status", "franchisees", ["status"])

    # RLS：品牌方可以看自己品牌的所有加盟商
    op.execute("ALTER TABLE franchisees ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY brand_isolation_franchisees
        ON franchisees
        FOR ALL
        USING (
            current_setting('app.current_tenant', TRUE) IS NOT NULL
            AND brand_id::text = current_setting('app.current_tenant', TRUE)
        );
    """)

    # ------------------------------------------------------------------ #
    # 2. franchise_contracts — 加盟合同
    # ------------------------------------------------------------------ #
    op.create_table(
        "franchise_contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "franchisee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("franchisees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("brand_id", sa.String(50), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=True),
        sa.Column("contract_no", sa.String(32), nullable=False),
        sa.Column("contract_type", sa.String(30), nullable=False),
        sa.Column("franchise_fee_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("royalty_rate", sa.Float, nullable=False, server_default="0.05"),
        sa.Column("marketing_fund_rate", sa.Float, nullable=False, server_default="0.02"),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("renewal_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("signed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fc_franchisee_id", "franchise_contracts", ["franchisee_id"])
    op.create_index("ix_fc_brand_id", "franchise_contracts", ["brand_id"])
    op.create_index("ix_fc_store_id", "franchise_contracts", ["store_id"])
    op.create_index("ix_fc_status", "franchise_contracts", ["status"])
    op.create_index("ix_fc_contract_no", "franchise_contracts", ["contract_no"], unique=True)
    op.create_index("ix_fc_end_date", "franchise_contracts", ["end_date"])

    # RLS：品牌方可以看自己品牌的所有合同
    op.execute("ALTER TABLE franchise_contracts ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY brand_isolation_franchise_contracts
        ON franchise_contracts
        FOR ALL
        USING (
            current_setting('app.current_tenant', TRUE) IS NOT NULL
            AND brand_id::text = current_setting('app.current_tenant', TRUE)
        );
    """)

    # ------------------------------------------------------------------ #
    # 3. franchise_royalties — 月度提成结算记录
    # ------------------------------------------------------------------ #
    op.create_table(
        "franchise_royalties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("franchise_contracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("franchisee_id", UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("period_year", sa.Integer, nullable=False),
        sa.Column("period_month", sa.Integer, nullable=False),
        sa.Column("gross_revenue_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("royalty_amount_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("marketing_fund_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_due_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("paid_at", sa.DateTime, nullable=True),
        sa.Column("payment_reference", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("contract_id", "period_year", "period_month", name="uq_royalty_contract_period"),
    )
    op.create_index("ix_fr_contract_id", "franchise_royalties", ["contract_id"])
    op.create_index("ix_fr_franchisee_id", "franchise_royalties", ["franchisee_id"])
    op.create_index("ix_fr_store_id", "franchise_royalties", ["store_id"])
    op.create_index("ix_fr_status", "franchise_royalties", ["status"])
    op.create_index("ix_fr_due_date", "franchise_royalties", ["due_date"])

    # RLS：按 store_id 隔离（加盟商通过门户只能看自己门店的提成）
    op.execute("ALTER TABLE franchise_royalties ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY store_isolation_franchise_royalties
        ON franchise_royalties
        FOR ALL
        USING (
            store_id::text = current_setting('app.current_tenant', TRUE)
        );
    """)

    # ------------------------------------------------------------------ #
    # 4. franchisee_portal_access — 加盟商门户访问权限
    # ------------------------------------------------------------------ #
    op.create_table(
        "franchisee_portal_access",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "franchisee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("franchisees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("store_ids", ARRAY(sa.String), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fpa_franchisee_id", "franchisee_portal_access", ["franchisee_id"])
    op.create_index("ix_fpa_user_id", "franchisee_portal_access", ["user_id"])


def downgrade() -> None:
    # 删除顺序与创建相反（先删依赖表）
    op.drop_index("ix_fpa_user_id", table_name="franchisee_portal_access")
    op.drop_index("ix_fpa_franchisee_id", table_name="franchisee_portal_access")
    op.drop_table("franchisee_portal_access")

    op.execute("DROP POLICY IF EXISTS store_isolation_franchise_royalties ON franchise_royalties;")
    op.drop_index("ix_fr_due_date", table_name="franchise_royalties")
    op.drop_index("ix_fr_status", table_name="franchise_royalties")
    op.drop_index("ix_fr_store_id", table_name="franchise_royalties")
    op.drop_index("ix_fr_franchisee_id", table_name="franchise_royalties")
    op.drop_index("ix_fr_contract_id", table_name="franchise_royalties")
    op.drop_table("franchise_royalties")

    op.execute("DROP POLICY IF EXISTS brand_isolation_franchise_contracts ON franchise_contracts;")
    op.drop_index("ix_fc_end_date", table_name="franchise_contracts")
    op.drop_index("ix_fc_contract_no", table_name="franchise_contracts")
    op.drop_index("ix_fc_status", table_name="franchise_contracts")
    op.drop_index("ix_fc_store_id", table_name="franchise_contracts")
    op.drop_index("ix_fc_brand_id", table_name="franchise_contracts")
    op.drop_index("ix_fc_franchisee_id", table_name="franchise_contracts")
    op.drop_table("franchise_contracts")

    op.execute("DROP POLICY IF EXISTS brand_isolation_franchisees ON franchisees;")
    op.drop_index("ix_franchisees_status", table_name="franchisees")
    op.drop_index("ix_franchisees_brand_id", table_name="franchisees")
    op.drop_table("franchisees")
