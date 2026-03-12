"""z39_business_intel_agent_tables

BusinessIntelAgent — Phase 12 经营智能体
合并 DecisionAgent + KPIAgent + OrderAgent

Revision ID: z39_business_intel_agent_tables
Revises: z39_edge_hub_tables
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z39_business_intel_agent_tables'
down_revision = 'z39_edge_hub_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 创建枚举类型 ──────────────────────────────────────────────
    op.execute("CREATE TYPE anomaly_level_enum AS ENUM ('normal','warning','critical','severe')")
    op.execute("CREATE TYPE kpi_status_enum AS ENUM ('excellent','on_track','at_risk','off_track')")
    op.execute("CREATE TYPE decision_priority_enum AS ENUM ('p0','p1','p2','p3')")
    op.execute("CREATE TYPE scenario_type_enum AS ENUM ('peak_revenue','revenue_slump','cost_overrun','staff_shortage','inventory_crisis','normal_ops')")
    op.execute("CREATE TYPE biz_intel_agent_type_enum AS ENUM ('revenue_anomaly','kpi_scorecard','order_forecast','biz_insight','scenario_match')")
    op.execute("CREATE TYPE biz_decision_status_enum AS ENUM ('pending','accepted','rejected','executed')")

    # ── L1: biz_metric_snapshots ──────────────────────────────────
    op.create_table(
        "biz_metric_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("revenue_yuan", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("expected_revenue_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("revenue_deviation_pct", sa.Float, nullable=True),
        sa.Column("order_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_order_value_yuan", sa.Numeric(10, 2), nullable=True),
        sa.Column("table_turnover_rate", sa.Float, nullable=True),
        sa.Column("food_cost_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("food_cost_ratio", sa.Float, nullable=True),
        sa.Column("labor_cost_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("labor_cost_ratio", sa.Float, nullable=True),
        sa.Column("gross_profit_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("gross_profit_ratio", sa.Float, nullable=True),
        sa.Column("customer_count", sa.Integer, nullable=True),
        sa.Column("complaint_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("staff_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_biz_snapshot_brand_store_date", "biz_metric_snapshots", ["brand_id", "store_id", "snapshot_date"])

    # ── L2: revenue_alerts ────────────────────────────────────────
    op.create_table(
        "revenue_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("alert_date", sa.Date, nullable=False),
        sa.Column("anomaly_level", postgresql.ENUM(name="anomaly_level_enum", create_type=False), nullable=False),
        sa.Column("actual_revenue_yuan", sa.Numeric(14, 2), nullable=False),
        sa.Column("expected_revenue_yuan", sa.Numeric(14, 2), nullable=False),
        sa.Column("deviation_pct", sa.Float, nullable=False),
        sa.Column("impact_yuan", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("root_causes", postgresql.JSON, nullable=True),
        sa.Column("recommended_action", sa.Text, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.8"),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_revenue_alert_brand_store_date", "revenue_alerts", ["brand_id", "store_id", "alert_date"])

    # ── L3: kpi_scorecards ───────────────────────────────────────
    op.create_table(
        "kpi_scorecards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("overall_health_score", sa.Float, nullable=False),
        sa.Column("revenue_score", sa.Float, nullable=True),
        sa.Column("cost_score", sa.Float, nullable=True),
        sa.Column("efficiency_score", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("kpi_items", postgresql.JSON, nullable=True),
        sa.Column("at_risk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("off_track_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("improvement_priorities", postgresql.JSON, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.85"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_kpi_scorecard_brand_store_period", "kpi_scorecards", ["brand_id", "store_id", "period"])

    # ── L4: order_forecasts ──────────────────────────────────────
    op.create_table(
        "order_forecasts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("forecast_date", sa.Date, nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False, server_default="7"),
        sa.Column("predicted_orders", sa.Integer, nullable=False),
        sa.Column("predicted_revenue_yuan", sa.Numeric(14, 2), nullable=False),
        sa.Column("lower_bound_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("upper_bound_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("trend_slope", sa.Float, nullable=True),
        sa.Column("avg_daily_orders_7d", sa.Float, nullable=True),
        sa.Column("avg_daily_revenue_7d", sa.Numeric(14, 2), nullable=True),
        sa.Column("day_of_week_factors", postgresql.JSON, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.75"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_order_forecast_brand_store_date", "order_forecasts", ["brand_id", "store_id", "forecast_date"])

    # ── L5: biz_decisions ────────────────────────────────────────
    op.create_table(
        "biz_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("decision_date", sa.Date, nullable=False),
        sa.Column("recommendations", postgresql.JSON, nullable=False),
        sa.Column("total_saving_yuan", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("priority", postgresql.ENUM(name="decision_priority_enum", create_type=False), nullable=False, server_default="p1"),
        sa.Column("data_sources", postgresql.JSON, nullable=True),
        sa.Column("scenario_type", postgresql.ENUM(name="scenario_type_enum", create_type=False), nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("status", postgresql.ENUM(name="biz_decision_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("accepted_rank", sa.Integer, nullable=True),
        sa.Column("accepted_at", sa.DateTime, nullable=True),
        sa.Column("outcome_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.80"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_biz_decision_brand_store_date", "biz_decisions", ["brand_id", "store_id", "decision_date"])

    # ── scenario_records ──────────────────────────────────────────
    op.create_table(
        "scenario_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("record_date", sa.Date, nullable=False),
        sa.Column("scenario_type", postgresql.ENUM(name="scenario_type_enum", create_type=False), nullable=False),
        sa.Column("scenario_score", sa.Float, nullable=True),
        sa.Column("key_signals", postgresql.JSON, nullable=True),
        sa.Column("historical_matches", postgresql.JSON, nullable=True),
        sa.Column("recommended_playbook", postgresql.JSON, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.75"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_scenario_brand_store_date", "scenario_records", ["brand_id", "store_id", "record_date"])

    # ── biz_intel_logs ────────────────────────────────────────────
    op.create_table(
        "biz_intel_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("agent_type", postgresql.ENUM(name="biz_intel_agent_type_enum", create_type=False), nullable=False),
        sa.Column("input_params", postgresql.JSON, nullable=True),
        sa.Column("output_summary", postgresql.JSON, nullable=True),
        sa.Column("saving_yuan", sa.Numeric(14, 2), nullable=True, server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_biz_intel_log_brand_created", "biz_intel_logs", ["brand_id", "created_at"])


def downgrade() -> None:
    op.drop_table("biz_intel_logs")
    op.drop_table("scenario_records")
    op.drop_table("biz_decisions")
    op.drop_table("order_forecasts")
    op.drop_table("kpi_scorecards")
    op.drop_table("revenue_alerts")
    op.drop_table("biz_metric_snapshots")

    op.execute("DROP TYPE IF EXISTS biz_decision_status_enum")
    op.execute("DROP TYPE IF EXISTS biz_intel_agent_type_enum")
    op.execute("DROP TYPE IF EXISTS scenario_type_enum")
    op.execute("DROP TYPE IF EXISTS decision_priority_enum")
    op.execute("DROP TYPE IF EXISTS kpi_status_enum")
    op.execute("DROP TYPE IF EXISTS anomaly_level_enum")
