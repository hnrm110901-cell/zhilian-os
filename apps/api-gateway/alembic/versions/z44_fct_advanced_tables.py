"""FCT Advanced: bank-treasury direct connect, multi-entity consolidation, tax auto-extract

Revision ID: z44
Revises: z43
Create Date: 2026-03-12

Tables:
  - fct_bank_accounts
  - fct_bank_transactions
  - fct_bank_match_rules
  - fct_entities
  - fct_consolidation_runs
  - fct_intercompany_items
  - fct_tax_declarations
  - fct_tax_extract_rules
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z44"
down_revision = "z43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 银企直连
    op.create_table(
        "fct_bank_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", sa.String(50), nullable=False, index=True),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("account_no", sa.String(40), nullable=False),
        sa.Column("account_name", sa.String(100), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("balance_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("last_synced_at", sa.DateTime),
        sa.Column("api_config", sa.JSON),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("entity_id", "account_no", name="uq_bank_entity_account"),
    )

    op.create_table(
        "fct_bank_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("bank_account_id", UUID(as_uuid=True), sa.ForeignKey("fct_bank_accounts.id"), nullable=False),
        sa.Column("tx_date", sa.Date, nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("amount_yuan", sa.Numeric(15, 2), nullable=False),
        sa.Column("counterparty", sa.String(200)),
        sa.Column("memo", sa.String(500)),
        sa.Column("bank_ref", sa.String(100)),
        sa.Column("match_status", sa.String(20), nullable=False, server_default="unmatched"),
        sa.Column("matched_voucher_id", UUID(as_uuid=True)),
        sa.Column("matched_at", sa.DateTime),
        sa.Column("raw_data", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_bank_tx_date", "fct_bank_transactions", ["bank_account_id", "tx_date"])

    op.create_table(
        "fct_bank_match_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", sa.String(50), nullable=False, index=True),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("match_field", sa.String(50), nullable=False, server_default="counterparty"),
        sa.Column("match_pattern", sa.String(200), nullable=False),
        sa.Column("target_account_code", sa.String(20)),
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 2. 多实体合并
    op.create_table(
        "fct_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_code", sa.String(50), nullable=False, unique=True),
        sa.Column("entity_name", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("fct_entities.id")),
        sa.Column("currency", sa.String(3), server_default="CNY"),
        sa.Column("tax_id", sa.String(30)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "fct_consolidation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("entity_count", sa.Integer, server_default="0"),
        sa.Column("total_revenue_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("total_cost_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("total_profit_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("elimination_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("consolidated_at", sa.DateTime),
        sa.Column("run_log", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "fct_intercompany_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("fct_consolidation_runs.id"), nullable=False),
        sa.Column("from_entity_id", UUID(as_uuid=True), sa.ForeignKey("fct_entities.id"), nullable=False),
        sa.Column("to_entity_id", UUID(as_uuid=True), sa.ForeignKey("fct_entities.id"), nullable=False),
        sa.Column("amount_yuan", sa.Numeric(15, 2), nullable=False),
        sa.Column("description", sa.String(200)),
        sa.Column("voucher_ref", sa.String(50)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 3. 税务申报自动提取
    op.create_table(
        "fct_tax_declarations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", sa.String(50), nullable=False, index=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("declaration_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("taxable_revenue_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("tax_deductible_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("tax_payable_yuan", sa.Numeric(15, 2), server_default="0"),
        sa.Column("line_items", sa.JSON),
        sa.Column("extraction_log", sa.JSON),
        sa.Column("reviewer_notes", sa.Text),
        sa.Column("submitted_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("entity_id", "period", "declaration_type", name="uq_tax_decl_entity_period_type"),
    )

    op.create_table(
        "fct_tax_extract_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("declaration_type", sa.String(30), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("field_label", sa.String(200)),
        sa.Column("extract_sql", sa.Text),
        sa.Column("account_codes", sa.JSON),
        sa.Column("direction", sa.String(10)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("fct_tax_extract_rules")
    op.drop_table("fct_tax_declarations")
    op.drop_table("fct_intercompany_items")
    op.drop_table("fct_consolidation_runs")
    op.drop_table("fct_entities")
    op.drop_table("fct_bank_match_rules")
    op.drop_index("ix_bank_tx_date", "fct_bank_transactions")
    op.drop_table("fct_bank_transactions")
    op.drop_table("fct_bank_accounts")
