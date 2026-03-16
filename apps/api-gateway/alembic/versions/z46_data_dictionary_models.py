"""Data Dictionary models — 15 new tables

Revision ID: z46_data_dictionary
Revises: z45
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "z46_data_dictionary"
down_revision = "z45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Organization hierarchy
    op.create_table(
        "groups",
        sa.Column("group_id", sa.String(50), primary_key=True),
        sa.Column("group_name", sa.String(200), nullable=False),
        sa.Column("legal_entity", sa.String(200), nullable=False),
        sa.Column("unified_social_credit_code", sa.String(18), nullable=False),
        sa.Column("industry_type", sa.String(30), nullable=False),
        sa.Column("contact_person", sa.String(50), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "brands",
        sa.Column("brand_id", sa.String(50), primary_key=True),
        sa.Column("group_id", sa.String(50), nullable=False),
        sa.Column("brand_name", sa.String(100), nullable=False),
        sa.Column("cuisine_type", sa.String(30), nullable=False),
        sa.Column("avg_ticket_yuan", sa.Numeric(10, 2)),
        sa.Column("target_food_cost_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("target_labor_cost_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("target_rent_cost_pct", sa.Numeric(5, 2)),
        sa.Column("target_waste_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("logo_url", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_brands_group_id", "brands", ["group_id"])

    op.create_table(
        "regions",
        sa.Column("region_id", sa.String(50), primary_key=True),
        sa.Column("brand_id", sa.String(50), nullable=False),
        sa.Column("region_name", sa.String(100), nullable=False),
        sa.Column("supervisor_id", sa.String(50)),
        sa.Column("store_ids", postgresql.ARRAY(sa.String(50))),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_regions_brand_id", "regions", ["brand_id"])

    # 2. Ingredient Master
    op.create_table(
        "ingredient_masters",
        sa.Column("ingredient_id", sa.String(50), primary_key=True),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String(100))),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("sub_category", sa.String(30)),
        sa.Column("base_unit", sa.String(10), nullable=False),
        sa.Column("spec_desc", sa.String(100)),
        sa.Column("shelf_life_days", sa.Integer()),
        sa.Column("storage_type", sa.String(20), nullable=False),
        sa.Column("storage_temp_min", sa.Numeric(5, 1)),
        sa.Column("storage_temp_max", sa.Numeric(5, 1)),
        sa.Column("is_traceable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("allergen_tags", postgresql.ARRAY(sa.String(30))),
        sa.Column("seasonality", postgresql.ARRAY(sa.String(2))),
        sa.Column("typical_waste_pct", sa.Numeric(5, 2)),
        sa.Column("typical_yield_rate", sa.Numeric(5, 4)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # 3. Inventory extensions
    op.create_table(
        "inventory_batches",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", sa.String(50), nullable=False),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("purchase_order_id", sa.String(50)),
        sa.Column("supplier_id", sa.String(50)),
        sa.Column("batch_no", sa.String(50)),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("production_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("received_qty", sa.Numeric(12, 4), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_cost_fen", sa.Integer(), nullable=False),
        sa.Column("quality_grade", sa.String(10)),
        sa.Column("inspection_result", sa.String(20)),
        sa.Column("inspection_notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_inv_batches_item", "inventory_batches", ["item_id"])
    op.create_index("ix_inv_batches_store", "inventory_batches", ["store_id"])

    op.create_table(
        "inventory_counts",
        sa.Column("count_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("count_date", sa.Date(), nullable=False),
        sa.Column("count_type", sa.String(20), nullable=False),
        sa.Column("item_id", sa.String(50), nullable=False),
        sa.Column("system_qty", sa.Numeric(12, 4), nullable=False),
        sa.Column("actual_qty", sa.Numeric(12, 4), nullable=False),
        sa.Column("variance_qty", sa.Numeric(12, 4), nullable=False),
        sa.Column("variance_cost_fen", sa.Integer()),
        sa.Column("variance_reason", sa.String(30)),
        sa.Column("counted_by", sa.String(50), nullable=False),
        sa.Column("verified_by", sa.String(50)),
        sa.Column("photo_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_inv_counts_store", "inventory_counts", ["store_id"])

    # 4. Purchase Order Items
    op.create_table(
        "purchase_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("po_id", sa.String(50), nullable=False),
        sa.Column("ingredient_id", sa.String(50), nullable=False),
        sa.Column("ordered_qty", sa.Numeric(12, 4), nullable=False),
        sa.Column("received_qty", sa.Numeric(12, 4)),
        sa.Column("rejected_qty", sa.Numeric(12, 4)),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("unit_price_fen", sa.Integer(), nullable=False),
        sa.Column("line_amount_fen", sa.Integer(), nullable=False),
        sa.Column("reject_reason", sa.String(50)),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_po_items_po_id", "purchase_order_items", ["po_id"])

    # 5. Daily Summaries
    op.create_table(
        "daily_revenue_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("biz_date", sa.Date(), nullable=False),
        sa.Column("order_count", sa.Integer(), nullable=False),
        sa.Column("guest_count", sa.Integer()),
        sa.Column("dine_in_count", sa.Integer()),
        sa.Column("takeout_count", sa.Integer()),
        sa.Column("gross_revenue_fen", sa.Integer(), nullable=False),
        sa.Column("discount_total_fen", sa.Integer()),
        sa.Column("net_revenue_fen", sa.Integer(), nullable=False),
        sa.Column("platform_commission_fen", sa.Integer()),
        sa.Column("avg_ticket_fen", sa.Integer()),
        sa.Column("table_turnover_rate", sa.Numeric(5, 2)),
        sa.Column("peak_hour_start", sa.Time()),
        sa.Column("peak_hour_end", sa.Time()),
        sa.Column("weather", sa.String(20)),
        sa.Column("is_holiday", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "biz_date"),
    )
    op.create_index("ix_daily_rev_store", "daily_revenue_summary", ["store_id"])

    op.create_table(
        "daily_waste_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("biz_date", sa.Date(), nullable=False),
        sa.Column("total_waste_cost_fen", sa.Integer(), nullable=False),
        sa.Column("total_waste_events", sa.Integer(), nullable=False),
        sa.Column("waste_rate_pct", sa.Numeric(5, 2)),
        sa.Column("top_waste_ingredient", sa.String(100)),
        sa.Column("top_waste_cost_fen", sa.Integer()),
        sa.Column("preventable_cost_fen", sa.Integer()),
        sa.Column("root_cause_dist", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "biz_date"),
    )
    op.create_index("ix_daily_waste_store", "daily_waste_summary", ["store_id"])

    op.create_table(
        "daily_pnl_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("biz_date", sa.Date(), nullable=False),
        sa.Column("gross_revenue_fen", sa.Integer(), nullable=False),
        sa.Column("discount_fen", sa.Integer()),
        sa.Column("net_revenue_fen", sa.Integer(), nullable=False),
        sa.Column("food_cost_fen", sa.Integer(), nullable=False),
        sa.Column("food_cost_pct", sa.Numeric(5, 2)),
        sa.Column("labor_cost_fen", sa.Integer(), nullable=False),
        sa.Column("labor_cost_pct", sa.Numeric(5, 2)),
        sa.Column("rent_cost_fen", sa.Integer()),
        sa.Column("utility_cost_fen", sa.Integer()),
        sa.Column("platform_fee_fen", sa.Integer()),
        sa.Column("packaging_cost_fen", sa.Integer()),
        sa.Column("waste_cost_fen", sa.Integer()),
        sa.Column("other_cost_fen", sa.Integer()),
        sa.Column("gross_profit_fen", sa.Integer()),
        sa.Column("gross_profit_pct", sa.Numeric(5, 2)),
        sa.Column("operating_profit_fen", sa.Integer()),
        sa.Column("operating_profit_pct", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "biz_date"),
    )
    op.create_index("ix_daily_pnl_store", "daily_pnl_summary", ["store_id"])

    # 6. Attendance
    op.create_table(
        "attendance_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("employee_id", sa.String(50), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("clock_in", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clock_out", sa.DateTime(timezone=True)),
        sa.Column("break_minutes", sa.Integer()),
        sa.Column("actual_hours", sa.Numeric(5, 2)),
        sa.Column("overtime_hours", sa.Numeric(5, 2)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("late_minutes", sa.Integer()),
        sa.Column("leave_type", sa.String(20)),
        sa.Column("source", sa.String(20)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("store_id", "employee_id", "work_date"),
    )
    op.create_index("ix_attendance_store", "attendance_logs", ["store_id"])
    op.create_index("ix_attendance_emp", "attendance_logs", ["employee_id"])

    # 7. Member RFM
    op.create_table(
        "member_rfm_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", sa.String(50), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("recency_days", sa.Integer(), nullable=False),
        sa.Column("frequency_30d", sa.Integer(), nullable=False),
        sa.Column("monetary_30d_fen", sa.Integer(), nullable=False),
        sa.Column("r_score", sa.Integer(), nullable=False),
        sa.Column("f_score", sa.Integer(), nullable=False),
        sa.Column("m_score", sa.Integer(), nullable=False),
        sa.Column("rfm_segment", sa.String(30), nullable=False),
        sa.Column("churn_risk_pct", sa.Numeric(5, 2)),
        sa.Column("ltv_yuan", sa.Numeric(12, 2)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_rfm_member", "member_rfm_snapshots", ["member_id"])

    # 8. Price Benchmark
    op.create_table(
        "price_benchmark_pool",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingredient_id", sa.String(50), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("city", sa.String(50), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("unit_cost_fen", sa.Integer(), nullable=False),
        sa.Column("quality_grade", sa.String(10), nullable=False, server_default="standard"),
        sa.Column("purchase_month", sa.String(7), nullable=False),
        sa.Column("contributor_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_pbp_ingredient", "price_benchmark_pool", ["ingredient_id"])

    op.create_table(
        "price_benchmark_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("report_month", sa.String(7), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("cheap_count", sa.Integer(), nullable=False),
        sa.Column("fair_count", sa.Integer(), nullable=False),
        sa.Column("expensive_count", sa.Integer(), nullable=False),
        sa.Column("very_expensive_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total_saving_potential_yuan", sa.Numeric(12, 2)),
        sa.Column("annual_saving_potential_yuan", sa.Numeric(12, 2)),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_pbr_store", "price_benchmark_reports", ["store_id"])

    # 9. Decision Lifecycle
    op.create_table(
        "decision_lifecycle",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("expected_saving_yuan", sa.Numeric(10, 2), nullable=False),
        sa.Column("confidence_pct", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("executor", sa.String(50)),
        sa.Column("deadline_hours", sa.Integer()),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
        sa.Column("pushed_at", sa.DateTime(timezone=True)),
        sa.Column("push_channel", sa.String(20)),
        sa.Column("viewed_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("reject_reason", sa.String(100)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("measured_at", sa.DateTime(timezone=True)),
        sa.Column("actual_saving_yuan", sa.Numeric(10, 2)),
        sa.Column("measurement_method", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_decision_store", "decision_lifecycle", ["store_id"])


def downgrade() -> None:
    tables = [
        "decision_lifecycle",
        "price_benchmark_reports", "price_benchmark_pool",
        "member_rfm_snapshots",
        "attendance_logs",
        "daily_pnl_summary", "daily_waste_summary", "daily_revenue_summary",
        "purchase_order_items",
        "inventory_counts", "inventory_batches",
        "ingredient_masters",
        "regions", "brands", "groups",
    ]
    for t in tables:
        op.drop_table(t)
