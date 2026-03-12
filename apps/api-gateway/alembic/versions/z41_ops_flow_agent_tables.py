"""z41_ops_flow_agent_tables

OpsFlowAgent — Phase 13 运营流程体
订单异常 / 库存预警 / 菜品质检 / 出品链联动告警 / 综合优化

Revision ID: z41
Revises: z40
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z41'
down_revision = 'z40'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 枚举类型 ──────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE ops_flow_agent_type_enum AS ENUM ('chain_alert','order_anomaly','inventory_intel','quality_inspection','ops_optimize')")
    op.execute("CREATE TYPE ops_chain_event_type_enum AS ENUM ('order_anomaly','inventory_low','quality_fail','order_spike','inventory_expiry','quality_pattern')")
    op.execute("CREATE TYPE ops_chain_event_severity_enum AS ENUM ('info','warning','critical')")
    op.execute("CREATE TYPE ops_order_anomaly_type_enum AS ENUM ('refund_spike','complaint_rate','delivery_timeout','revenue_drop','cancel_surge','avg_order_drop')")
    op.execute("CREATE TYPE ops_inventory_alert_type_enum AS ENUM ('low_stock','expiry_risk','stockout_predicted','overstock','restock_overdue')")
    op.execute("CREATE TYPE ops_quality_status_enum AS ENUM ('pass','warning','fail')")
    op.execute("CREATE TYPE ops_decision_status_enum AS ENUM ('pending','accepted','rejected','auto_executed')")

    # ── L1: ops_flow_chain_events ─────────────────────────────────────────────
    op.create_table(
        "ops_flow_chain_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("event_type", postgresql.ENUM(name="ops_chain_event_type_enum", create_type=False), nullable=False),
        sa.Column("severity", postgresql.ENUM(name="ops_chain_event_severity_enum", create_type=False), nullable=False, server_default="warning"),
        sa.Column("source_layer", sa.String(20), nullable=False),
        sa.Column("source_record_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("impact_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("event_data", postgresql.JSON, nullable=True),
        sa.Column("linkage_triggered", sa.Boolean, server_default="false"),
        sa.Column("linkage_count", sa.Integer, server_default="0"),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_chain_event_store_type", "ops_flow_chain_events", ["store_id", "event_type"])
    op.create_index("idx_ops_chain_event_created", "ops_flow_chain_events", ["created_at"])

    # ── L2: ops_flow_chain_linkages ────────────────────────────────────────────
    op.create_table(
        "ops_flow_chain_linkages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trigger_event_id", sa.String(36), nullable=False),
        sa.Column("trigger_layer", sa.String(20), nullable=False),
        sa.Column("target_layer", sa.String(20), nullable=False),
        sa.Column("target_action", sa.String(100), nullable=False),
        sa.Column("target_record_id", sa.String(36), nullable=True),
        sa.Column("result_summary", sa.Text, nullable=True),
        sa.Column("impact_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("executed_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_linkage_event", "ops_flow_chain_linkages", ["trigger_event_id"])

    # ── L3: ops_flow_order_anomalies ───────────────────────────────────────────
    op.create_table(
        "ops_flow_order_anomalies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("anomaly_type", postgresql.ENUM(name="ops_order_anomaly_type_enum", create_type=False), nullable=False),
        sa.Column("time_period", sa.String(20), nullable=False, server_default="today"),
        sa.Column("current_value", sa.Float, nullable=True),
        sa.Column("baseline_value", sa.Float, nullable=True),
        sa.Column("deviation_pct", sa.Float, nullable=True),
        sa.Column("estimated_revenue_loss_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("recommendations", postgresql.JSON, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.80"),
        sa.Column("chain_event_id", sa.String(36), nullable=True),
        sa.Column("order_count", sa.Integer, nullable=True),
        sa.Column("affected_dish_ids", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_order_anomaly_store", "ops_flow_order_anomalies", ["store_id", "created_at"])

    # ── L4: ops_flow_inventory_alerts ──────────────────────────────────────────
    op.create_table(
        "ops_flow_inventory_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("alert_type", postgresql.ENUM(name="ops_inventory_alert_type_enum", create_type=False), nullable=False),
        sa.Column("dish_id", sa.String(36), nullable=True),
        sa.Column("dish_name", sa.String(100), nullable=True),
        sa.Column("current_qty", sa.Integer, nullable=True),
        sa.Column("safety_qty", sa.Integer, nullable=True),
        sa.Column("predicted_stockout_hours", sa.Float, nullable=True),
        sa.Column("restock_qty_recommended", sa.Integer, nullable=True),
        sa.Column("estimated_loss_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("recommendations", postgresql.JSON, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.85"),
        sa.Column("chain_event_id", sa.String(36), nullable=True),
        sa.Column("resolved", sa.Boolean, server_default="false"),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_inv_alert_store_dish", "ops_flow_inventory_alerts", ["store_id", "dish_id"])
    op.create_index("idx_ops_inv_alert_unresolved", "ops_flow_inventory_alerts", ["store_id", "resolved"])

    # ── L5: ops_flow_quality_records ───────────────────────────────────────────
    op.create_table(
        "ops_flow_quality_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("dish_id", sa.String(36), nullable=True),
        sa.Column("dish_name", sa.String(100), nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("status", postgresql.ENUM(name="ops_quality_status_enum", create_type=False), nullable=False),
        sa.Column("issues", postgresql.JSON, nullable=True),
        sa.Column("suggestions", postgresql.JSON, nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("chain_event_id", sa.String(36), nullable=True),
        sa.Column("alert_sent", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_quality_store_date", "ops_flow_quality_records", ["store_id", "created_at"])
    op.create_index("idx_ops_quality_status", "ops_flow_quality_records", ["store_id", "status"])

    # ── L6: ops_flow_decisions ─────────────────────────────────────────────────
    op.create_table(
        "ops_flow_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("decision_title", sa.String(200), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="P2"),
        sa.Column("involves_order", sa.Boolean, server_default="false"),
        sa.Column("involves_inventory", sa.Boolean, server_default="false"),
        sa.Column("involves_quality", sa.Boolean, server_default="false"),
        sa.Column("estimated_revenue_impact_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("estimated_cost_saving_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("recommendations", postgresql.JSON, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.80"),
        sa.Column("status", postgresql.ENUM(name="ops_decision_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("accepted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_decision_store_priority", "ops_flow_decisions", ["store_id", "priority"])

    # ── L7: ops_flow_agent_logs ────────────────────────────────────────────────
    op.create_table(
        "ops_flow_agent_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("agent_type", postgresql.ENUM(name="ops_flow_agent_type_enum", create_type=False), nullable=False),
        sa.Column("input_params", postgresql.JSON, nullable=True),
        sa.Column("output_summary", postgresql.JSON, nullable=True),
        sa.Column("impact_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ops_log_agent_type", "ops_flow_agent_logs", ["agent_type", "created_at"])


def downgrade() -> None:
    op.drop_table("ops_flow_agent_logs")
    op.drop_table("ops_flow_decisions")
    op.drop_table("ops_flow_quality_records")
    op.drop_table("ops_flow_inventory_alerts")
    op.drop_table("ops_flow_order_anomalies")
    op.drop_table("ops_flow_chain_linkages")
    op.drop_table("ops_flow_chain_events")

    op.execute("DROP TYPE IF EXISTS ops_decision_status_enum")
    op.execute("DROP TYPE IF EXISTS ops_quality_status_enum")
    op.execute("DROP TYPE IF EXISTS ops_inventory_alert_type_enum")
    op.execute("DROP TYPE IF EXISTS ops_order_anomaly_type_enum")
    op.execute("DROP TYPE IF EXISTS ops_chain_event_severity_enum")
    op.execute("DROP TYPE IF EXISTS ops_chain_event_type_enum")
    op.execute("DROP TYPE IF EXISTS ops_flow_agent_type_enum")
