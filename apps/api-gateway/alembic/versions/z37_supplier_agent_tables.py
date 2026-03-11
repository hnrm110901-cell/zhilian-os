"""z37 — Phase 11 供应商管理 Agent 数据模型

Supplier Intelligence System：
  supplier_profiles             供应商档案（智能分级+综合评分）
  material_catalogs             物料目录（标准化+多供应商价格）
  supplier_quotes               供应商报价单
  supplier_contracts            供应商合同
  supplier_deliveries           收货记录（质量+准时率）
  price_comparisons             比价记录（PriceComparisonAgent输出）
  supplier_evaluations          供应商评估（SupplierRatingAgent输出）
  sourcing_recommendations      自动寻源推荐（AutoSourcingAgent输出）
  contract_alerts               合同预警（ContractRiskAgent输出）
  supply_risk_events            供应链风险事件（SupplyChainRiskAgent输出）
  supplier_agent_logs           Agent执行日志
"""
from alembic import op
import sqlalchemy as sa

revision      = 'z37'
down_revision = 'z36'
branch_labels = None
depends_on    = None

# PG Enum 类型名
_SUPPLIER_TIER  = 'suppliertier_p11'
_QUOTE_STATUS   = 'quotestatus_p11'
_CONTRACT_STATUS = 'contractstatus_p11'
_DELIVERY_STATUS = 'deliverystatus_p11'
_RISK_LEVEL     = 'risklevel_p11'
_ALERT_TYPE     = 'alerttype_p11'
_AGENT_TYPE     = 'supplieragenttype_p11'


def upgrade() -> None:
    # ── PG Enums ─────────────────────────────────────────────────────
    op.execute(f"CREATE TYPE {_SUPPLIER_TIER} AS ENUM ('strategic','preferred','approved','probation','suspended')")
    op.execute(f"CREATE TYPE {_QUOTE_STATUS} AS ENUM ('draft','submitted','accepted','rejected','expired')")
    op.execute(f"CREATE TYPE {_CONTRACT_STATUS} AS ENUM ('draft','active','expiring','expired','terminated')")
    op.execute(f"CREATE TYPE {_DELIVERY_STATUS} AS ENUM ('pending','in_transit','delivered','rejected','partial')")
    op.execute(f"CREATE TYPE {_RISK_LEVEL} AS ENUM ('low','medium','high','critical')")
    op.execute(f"CREATE TYPE {_ALERT_TYPE} AS ENUM ('contract_expiring','price_spike','delivery_delay','quality_issue','supply_shortage','single_source_risk')")
    op.execute(f"CREATE TYPE {_AGENT_TYPE} AS ENUM ('price_comparison','supplier_rating','auto_sourcing','contract_risk','supply_chain_risk')")

    # ── supplier_profiles ─────────────────────────────────────────────
    op.create_table(
        "supplier_profiles",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("supplier_id",     sa.String(36), nullable=False),
        sa.Column("brand_id",        sa.String(36), nullable=False),
        sa.Column("tier",            sa.Text, nullable=False, server_default="approved"),
        sa.Column("certified",       sa.Boolean, server_default="false"),
        sa.Column("cert_expiry",     sa.Date),
        sa.Column("category_tags",   sa.JSON, server_default="[]"),
        sa.Column("region_coverage", sa.JSON, server_default="[]"),
        sa.Column("min_order_yuan",  sa.Numeric(10, 2), server_default="0"),
        sa.Column("composite_score", sa.Float, server_default="0"),
        sa.Column("price_score",     sa.Float, server_default="0"),
        sa.Column("quality_score",   sa.Float, server_default="0"),
        sa.Column("delivery_score",  sa.Float, server_default="0"),
        sa.Column("service_score",   sa.Float, server_default="0"),
        sa.Column("last_rated_at",   sa.DateTime),
        sa.Column("risk_flags",      sa.JSON, server_default="[]"),
        sa.Column("internal_notes",  sa.Text),
        sa.Column("created_at",      sa.DateTime),
        sa.Column("updated_at",      sa.DateTime),
    )
    op.create_index("ix_supplier_profiles_supplier", "supplier_profiles", ["supplier_id"], unique=True)
    op.create_index("ix_supplier_profiles_brand_tier", "supplier_profiles", ["brand_id", "tier"])

    # ── material_catalogs ─────────────────────────────────────────────
    op.create_table(
        "material_catalogs",
        sa.Column("id",                   sa.String(36), primary_key=True),
        sa.Column("brand_id",             sa.String(36), nullable=False),
        sa.Column("material_code",        sa.String(50), nullable=False),
        sa.Column("material_name",        sa.String(200), nullable=False),
        sa.Column("spec",                 sa.String(100)),
        sa.Column("base_unit",            sa.String(20), server_default="kg"),
        sa.Column("category",             sa.String(50)),
        sa.Column("benchmark_price_yuan", sa.Numeric(10, 4), server_default="0"),
        sa.Column("latest_price_yuan",    sa.Numeric(10, 4), server_default="0"),
        sa.Column("price_updated_at",     sa.DateTime),
        sa.Column("preferred_supplier_id",sa.String(36)),
        sa.Column("backup_supplier_ids",  sa.JSON, server_default="[]"),
        sa.Column("safety_stock_days",    sa.Integer, server_default="3"),
        sa.Column("reorder_point_kg",     sa.Float, server_default="0"),
        sa.Column("is_active",            sa.Boolean, server_default="true"),
        sa.Column("created_at",           sa.DateTime),
        sa.Column("updated_at",           sa.DateTime),
    )
    op.create_index("ix_material_catalogs_brand_code", "material_catalogs", ["brand_id", "material_code"])

    # ── supplier_quotes ───────────────────────────────────────────────
    op.create_table(
        "supplier_quotes",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("brand_id",         sa.String(36), nullable=False),
        sa.Column("store_id",         sa.String(36)),
        sa.Column("supplier_id",      sa.String(36), nullable=False),
        sa.Column("material_id",      sa.String(36)),
        sa.Column("material_name",    sa.String(200), nullable=False),
        sa.Column("spec",             sa.String(100)),
        sa.Column("unit",             sa.String(20), server_default="kg"),
        sa.Column("quantity",         sa.Float, nullable=False),
        sa.Column("unit_price_yuan",  sa.Numeric(10, 4), nullable=False),
        sa.Column("total_yuan",       sa.Numeric(10, 2)),
        sa.Column("valid_until",      sa.Date),
        sa.Column("status",           sa.Text, server_default="submitted"),
        sa.Column("delivery_days",    sa.Integer, server_default="3"),
        sa.Column("min_order_qty",    sa.Float, server_default="0"),
        sa.Column("notes",            sa.Text),
        sa.Column("rank_in_comparison", sa.Integer),
        sa.Column("price_delta_pct",  sa.Float),
        sa.Column("created_at",       sa.DateTime),
        sa.Column("updated_at",       sa.DateTime),
    )
    op.create_index("ix_supplier_quotes_brand_supplier", "supplier_quotes", ["brand_id", "supplier_id"])
    op.create_index("ix_supplier_quotes_material", "supplier_quotes", ["material_id"])

    # ── supplier_contracts ────────────────────────────────────────────
    op.create_table(
        "supplier_contracts",
        sa.Column("id",                   sa.String(36), primary_key=True),
        sa.Column("brand_id",             sa.String(36), nullable=False),
        sa.Column("supplier_id",          sa.String(36), nullable=False),
        sa.Column("contract_no",          sa.String(100), nullable=False),
        sa.Column("contract_name",        sa.String(200)),
        sa.Column("start_date",           sa.Date, nullable=False),
        sa.Column("end_date",             sa.Date, nullable=False),
        sa.Column("auto_renew",           sa.Boolean, server_default="false"),
        sa.Column("renewal_notice_days",  sa.Integer, server_default="30"),
        sa.Column("status",               sa.Text, server_default="draft"),
        sa.Column("annual_value_yuan",    sa.Numeric(12, 2), server_default="0"),
        sa.Column("payment_terms",        sa.String(50), server_default="net30"),
        sa.Column("delivery_guarantee",   sa.Boolean, server_default="false"),
        sa.Column("price_lock_months",    sa.Integer, server_default="0"),
        sa.Column("penalty_clause",       sa.Boolean, server_default="false"),
        sa.Column("exclusive_clause",     sa.Boolean, server_default="false"),
        sa.Column("covered_categories",   sa.JSON, server_default="[]"),
        sa.Column("covered_material_ids", sa.JSON, server_default="[]"),
        sa.Column("file_url",             sa.String(500)),
        sa.Column("signed_by",            sa.String(100)),
        sa.Column("signed_at",            sa.DateTime),
        sa.Column("notes",                sa.Text),
        sa.Column("created_at",           sa.DateTime),
        sa.Column("updated_at",           sa.DateTime),
    )
    op.create_index("ix_supplier_contracts_brand_status", "supplier_contracts", ["brand_id", "status"])
    op.create_index("ix_supplier_contracts_end_date", "supplier_contracts", ["end_date"])
    op.create_unique_constraint("uq_supplier_contracts_no", "supplier_contracts", ["contract_no"])

    # ── supplier_deliveries ───────────────────────────────────────────
    op.create_table(
        "supplier_deliveries",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("brand_id",         sa.String(36), nullable=False),
        sa.Column("store_id",         sa.String(36), nullable=False),
        sa.Column("supplier_id",      sa.String(36), nullable=False),
        sa.Column("purchase_order_id",sa.String(36)),
        sa.Column("promised_date",    sa.Date, nullable=False),
        sa.Column("actual_date",      sa.Date),
        sa.Column("delay_days",       sa.Integer, server_default="0"),
        sa.Column("status",           sa.Text, server_default="pending"),
        sa.Column("ordered_qty",      sa.Float, nullable=False),
        sa.Column("received_qty",     sa.Float, server_default="0"),
        sa.Column("rejected_qty",     sa.Float, server_default="0"),
        sa.Column("reject_reason",    sa.String(200)),
        sa.Column("quality_score",    sa.Float),
        sa.Column("freshness_ok",     sa.Boolean),
        sa.Column("packaging_ok",     sa.Boolean),
        sa.Column("temp_ok",          sa.Boolean),
        sa.Column("inspector_id",     sa.String(36)),
        sa.Column("notes",            sa.Text),
        sa.Column("created_at",       sa.DateTime),
        sa.Column("updated_at",       sa.DateTime),
    )
    op.create_index("ix_supplier_deliveries_supplier_date", "supplier_deliveries", ["supplier_id", "promised_date"])

    # ── price_comparisons ─────────────────────────────────────────────
    op.create_table(
        "price_comparisons",
        sa.Column("id",                      sa.String(36), primary_key=True),
        sa.Column("brand_id",                sa.String(36), nullable=False),
        sa.Column("store_id",                sa.String(36)),
        sa.Column("material_id",             sa.String(36)),
        sa.Column("material_name",           sa.String(200), nullable=False),
        sa.Column("comparison_date",         sa.Date, nullable=False),
        sa.Column("quote_count",             sa.Integer, server_default="0"),
        sa.Column("best_price_yuan",         sa.Numeric(10, 4)),
        sa.Column("best_supplier_id",        sa.String(36)),
        sa.Column("avg_price_yuan",          sa.Numeric(10, 4)),
        sa.Column("price_spread_pct",        sa.Float),
        sa.Column("recommended_supplier_id", sa.String(36)),
        sa.Column("recommendation_reason",   sa.Text),
        sa.Column("estimated_saving_yuan",   sa.Numeric(10, 2)),
        sa.Column("confidence",              sa.Float, server_default="0.8"),
        sa.Column("quote_snapshot",          sa.JSON, server_default="[]"),
        sa.Column("created_at",              sa.DateTime),
        sa.Column("updated_at",              sa.DateTime),
    )
    op.create_index("ix_price_comparisons_brand_material", "price_comparisons", ["brand_id", "material_id"])

    # ── supplier_evaluations ──────────────────────────────────────────
    op.create_table(
        "supplier_evaluations",
        sa.Column("id",                   sa.String(36), primary_key=True),
        sa.Column("brand_id",             sa.String(36), nullable=False),
        sa.Column("supplier_id",          sa.String(36), nullable=False),
        sa.Column("eval_period",          sa.String(10), nullable=False),
        sa.Column("price_score",          sa.Float, server_default="0"),
        sa.Column("quality_score",        sa.Float, server_default="0"),
        sa.Column("delivery_score",       sa.Float, server_default="0"),
        sa.Column("service_score",        sa.Float, server_default="0"),
        sa.Column("composite_score",      sa.Float, server_default="0"),
        sa.Column("tier_suggestion",      sa.Text),
        sa.Column("delivery_count",       sa.Integer, server_default="0"),
        sa.Column("on_time_count",        sa.Integer, server_default="0"),
        sa.Column("reject_rate",          sa.Float, server_default="0"),
        sa.Column("avg_price_delta_pct",  sa.Float, server_default="0"),
        sa.Column("action_required",      sa.Boolean, server_default="false"),
        sa.Column("action_text",          sa.Text),
        sa.Column("created_at",           sa.DateTime),
        sa.Column("updated_at",           sa.DateTime),
    )
    op.create_index("ix_supplier_evaluations_supplier_period", "supplier_evaluations", ["supplier_id", "eval_period"])

    # ── sourcing_recommendations ──────────────────────────────────────
    op.create_table(
        "sourcing_recommendations",
        sa.Column("id",                       sa.String(36), primary_key=True),
        sa.Column("brand_id",                 sa.String(36), nullable=False),
        sa.Column("store_id",                 sa.String(36)),
        sa.Column("trigger",                  sa.String(50), server_default="bom_gap"),
        sa.Column("material_id",              sa.String(36)),
        sa.Column("material_name",            sa.String(200)),
        sa.Column("required_qty",             sa.Float, server_default="0"),
        sa.Column("required_unit",            sa.String(20), server_default="kg"),
        sa.Column("needed_by_date",           sa.Date),
        sa.Column("recommended_supplier_id",  sa.String(36)),
        sa.Column("recommended_price_yuan",   sa.Numeric(10, 4)),
        sa.Column("alternative_supplier_ids", sa.JSON, server_default="[]"),
        sa.Column("sourcing_strategy",        sa.String(50)),
        sa.Column("split_plan",               sa.JSON),
        sa.Column("estimated_total_yuan",     sa.Numeric(10, 2)),
        sa.Column("estimated_saving_yuan",    sa.Numeric(10, 2)),
        sa.Column("reasoning",                sa.Text),
        sa.Column("confidence",               sa.Float, server_default="0.8"),
        sa.Column("status",                   sa.String(20), server_default="pending"),
        sa.Column("accepted_by",              sa.String(36)),
        sa.Column("accepted_at",              sa.DateTime),
        sa.Column("created_at",               sa.DateTime),
        sa.Column("updated_at",               sa.DateTime),
    )
    op.create_index("ix_sourcing_recommendations_brand", "sourcing_recommendations", ["brand_id", "trigger"])

    # ── contract_alerts ───────────────────────────────────────────────
    op.create_table(
        "contract_alerts",
        sa.Column("id",                     sa.String(36), primary_key=True),
        sa.Column("brand_id",               sa.String(36), nullable=False),
        sa.Column("contract_id",            sa.String(36), nullable=False),
        sa.Column("supplier_id",            sa.String(36), nullable=False),
        sa.Column("alert_type",             sa.Text, nullable=False),
        sa.Column("risk_level",             sa.Text, nullable=False, server_default="medium"),
        sa.Column("title",                  sa.String(200), nullable=False),
        sa.Column("description",            sa.Text),
        sa.Column("recommended_action",     sa.Text),
        sa.Column("financial_impact_yuan",  sa.Numeric(10, 2)),
        sa.Column("days_to_expiry",         sa.Integer),
        sa.Column("is_resolved",            sa.Boolean, server_default="false"),
        sa.Column("resolved_at",            sa.DateTime),
        sa.Column("resolved_by",            sa.String(36)),
        sa.Column("wechat_sent",            sa.Boolean, server_default="false"),
        sa.Column("wechat_sent_at",         sa.DateTime),
        sa.Column("created_at",             sa.DateTime),
        sa.Column("updated_at",             sa.DateTime),
    )
    op.create_index("ix_contract_alerts_brand_resolved", "contract_alerts", ["brand_id", "is_resolved"])

    # ── supply_risk_events ────────────────────────────────────────────
    op.create_table(
        "supply_risk_events",
        sa.Column("id",                     sa.String(36), primary_key=True),
        sa.Column("brand_id",               sa.String(36), nullable=False),
        sa.Column("store_id",               sa.String(36)),
        sa.Column("supplier_id",            sa.String(36)),
        sa.Column("material_id",            sa.String(36)),
        sa.Column("alert_type",             sa.Text, nullable=False),
        sa.Column("risk_level",             sa.Text, nullable=False),
        sa.Column("title",                  sa.String(200), nullable=False),
        sa.Column("description",            sa.Text),
        sa.Column("probability",            sa.Float, server_default="0.5"),
        sa.Column("impact_days",            sa.Integer, server_default="0"),
        sa.Column("financial_impact_yuan",  sa.Numeric(10, 2)),
        sa.Column("mitigation_plan",        sa.Text),
        sa.Column("backup_supplier_ids",    sa.JSON, server_default="[]"),
        sa.Column("is_resolved",            sa.Boolean, server_default="false"),
        sa.Column("resolved_at",            sa.DateTime),
        sa.Column("wechat_sent",            sa.Boolean, server_default="false"),
        sa.Column("created_at",             sa.DateTime),
        sa.Column("updated_at",             sa.DateTime),
    )
    op.create_index("ix_supply_risk_events_brand_level", "supply_risk_events", ["brand_id", "risk_level"])

    # ── supplier_agent_logs ───────────────────────────────────────────
    op.create_table(
        "supplier_agent_logs",
        sa.Column("id",                   sa.String(36), primary_key=True),
        sa.Column("brand_id",             sa.String(36), nullable=False),
        sa.Column("agent_type",           sa.Text, nullable=False),
        sa.Column("triggered_by",         sa.String(50), server_default="scheduled"),
        sa.Column("input_params",         sa.JSON, server_default="{}"),
        sa.Column("output_summary",       sa.JSON, server_default="{}"),
        sa.Column("recommendation_count", sa.Integer, server_default="0"),
        sa.Column("alert_count",          sa.Integer, server_default="0"),
        sa.Column("saving_yuan",          sa.Numeric(10, 2), server_default="0"),
        sa.Column("duration_ms",          sa.Integer, server_default="0"),
        sa.Column("success",              sa.Boolean, server_default="true"),
        sa.Column("error_message",        sa.Text),
        sa.Column("created_at",           sa.DateTime),
        sa.Column("updated_at",           sa.DateTime),
    )
    op.create_index("ix_supplier_agent_logs_brand_type", "supplier_agent_logs", ["brand_id", "agent_type"])


def downgrade() -> None:
    op.drop_table("supplier_agent_logs")
    op.drop_table("supply_risk_events")
    op.drop_table("contract_alerts")
    op.drop_table("sourcing_recommendations")
    op.drop_table("supplier_evaluations")
    op.drop_table("price_comparisons")
    op.drop_table("supplier_deliveries")
    op.drop_table("supplier_contracts")
    op.drop_table("supplier_quotes")
    op.drop_table("material_catalogs")
    op.drop_table("supplier_profiles")

    for t in [_AGENT_TYPE, _ALERT_TYPE, _RISK_LEVEL, _DELIVERY_STATUS,
              _CONTRACT_STATUS, _QUOTE_STATUS, _SUPPLIER_TIER]:
        op.execute(f"DROP TYPE IF EXISTS {t}")
