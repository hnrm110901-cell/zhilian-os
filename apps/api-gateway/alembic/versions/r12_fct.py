"""
r12_fct — 业财税资金一体化数据表

新增：
  fct_tax_records      — 月度税务测算记录
  fct_cash_flow_items  — 资金流逐日预测明细
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision  = "r12_fct"
down_revision = "r11_banquet_lifecycle"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── fct_tax_records ─────────────────────────────────────────────────────
    op.create_table(
        "fct_tax_records",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id",         sa.String(50),  nullable=False),
        sa.Column("year",             sa.Integer(),   nullable=False),
        sa.Column("month",            sa.Integer(),   nullable=False),
        sa.Column("period_label",     sa.String(20)),

        # 纳税人
        sa.Column("taxpayer_type",    sa.String(20),  server_default="general"),

        # 收入口径（分）
        sa.Column("gross_revenue",    sa.Integer(),   server_default="0"),
        sa.Column("banquet_revenue",  sa.Integer(),   server_default="0"),
        sa.Column("other_revenue",    sa.Integer(),   server_default="0"),
        sa.Column("total_taxable",    sa.Integer(),   server_default="0"),

        # 税额测算（分）
        sa.Column("vat_rate",         sa.Float(),     server_default="0.06"),
        sa.Column("vat_amount",       sa.Integer(),   server_default="0"),
        sa.Column("vat_surcharge",    sa.Integer(),   server_default="0"),
        sa.Column("deductible_input", sa.Integer(),   server_default="0"),
        sa.Column("net_vat",          sa.Integer(),   server_default="0"),

        sa.Column("cit_rate",         sa.Float(),     server_default="0.20"),
        sa.Column("estimated_profit", sa.Integer(),   server_default="0"),
        sa.Column("cit_amount",       sa.Integer(),   server_default="0"),

        sa.Column("total_tax",        sa.Integer(),   server_default="0"),
        sa.Column("is_finalized",     sa.Boolean(),   server_default="false"),
        sa.Column("notes",            sa.Text()),
        sa.Column("generated_by",     sa.String(100), server_default="system"),

        sa.Column("created_at",       sa.DateTime(),  server_default=sa.text("NOW()")),
        sa.Column("updated_at",       sa.DateTime(),  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_fct_tax_store_period", "fct_tax_records",
                    ["store_id", "year", "month"])

    # ── fct_cash_flow_items ──────────────────────────────────────────────────
    op.create_table(
        "fct_cash_flow_items",
        sa.Column("id",                  UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id",            sa.String(50),  nullable=False),
        sa.Column("forecast_date",       sa.Date(),      nullable=False),
        sa.Column("is_actual",           sa.Boolean(),   server_default="false"),

        # 进流
        sa.Column("pos_inflow",          sa.Integer(),   server_default="0"),
        sa.Column("prepaid_inflow",      sa.Integer(),   server_default="0"),
        sa.Column("other_inflow",        sa.Integer(),   server_default="0"),
        sa.Column("total_inflow",        sa.Integer(),   server_default="0"),

        # 出流
        sa.Column("food_cost_outflow",   sa.Integer(),   server_default="0"),
        sa.Column("labor_outflow",       sa.Integer(),   server_default="0"),
        sa.Column("rent_outflow",        sa.Integer(),   server_default="0"),
        sa.Column("utilities_outflow",   sa.Integer(),   server_default="0"),
        sa.Column("tax_outflow",         sa.Integer(),   server_default="0"),
        sa.Column("other_outflow",       sa.Integer(),   server_default="0"),
        sa.Column("total_outflow",       sa.Integer(),   server_default="0"),

        # 净流
        sa.Column("net_flow",            sa.Integer(),   server_default="0"),
        sa.Column("cumulative_balance",  sa.Integer(),   server_default="0"),

        # 预警
        sa.Column("is_alert",            sa.Boolean(),   server_default="false"),
        sa.Column("alert_message",       sa.String(200)),
        sa.Column("confidence",          sa.Float(),     server_default="0.8"),

        sa.Column("created_at",          sa.DateTime(),  server_default=sa.text("NOW()")),
        sa.Column("updated_at",          sa.DateTime(),  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_fct_cashflow_store_date", "fct_cash_flow_items",
                    ["store_id", "forecast_date"])


def downgrade() -> None:
    op.drop_index("ix_fct_cashflow_store_date", table_name="fct_cash_flow_items")
    op.drop_table("fct_cash_flow_items")
    op.drop_index("ix_fct_tax_store_period",    table_name="fct_tax_records")
    op.drop_table("fct_tax_records")
