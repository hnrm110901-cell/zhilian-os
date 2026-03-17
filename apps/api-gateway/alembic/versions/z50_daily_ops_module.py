"""日清日结 + 周复盘模块 — 8张新表

创建以下表：
  store_daily_metrics       — 门店日经营指标
  store_daily_settlements   — 门店日结单
  warning_rules             — 预警规则
  warning_records           — 预警记录
  action_tasks              — 异常整改任务
  weekly_reviews            — 周复盘单
  weekly_review_items       — 周复盘问题项
  data_quality_check_records — 数据质量校验记录

Revision ID: z50_daily_ops_module
Revises: z49_pos_daily_summaries
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z50_daily_ops_module"
down_revision = "z49_pos_daily_summaries"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # ─────────────────────────────────────────────────────────────
    # 1. store_daily_metrics
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "store_daily_metrics"):
        op.create_table(
            "store_daily_metrics",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            # 基础信息
            sa.Column("store_id", sa.String(64), nullable=False),
            sa.Column("store_code", sa.String(64)),
            sa.Column("store_name", sa.String(128), nullable=False),
            sa.Column("region_id", sa.String(64)),
            sa.Column("region_name", sa.String(128)),
            sa.Column("biz_date", sa.Date, nullable=False),
            sa.Column("day_of_week", sa.SmallInteger),
            sa.Column("weather_code", sa.String(32)),
            sa.Column("weather_text", sa.String(64)),
            sa.Column("is_holiday", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("holiday_name", sa.String(64)),
            sa.Column("business_status", sa.String(32), nullable=False, server_default="open"),
            # 销售类（分）
            sa.Column("total_sales_amount", sa.Integer, server_default="0"),
            sa.Column("actual_receipts_amount", sa.Integer, server_default="0"),
            sa.Column("dine_in_sales_amount", sa.Integer, server_default="0"),
            sa.Column("delivery_sales_amount", sa.Integer, server_default="0"),
            sa.Column("food_sales_amount", sa.Integer, server_default="0"),
            sa.Column("beverage_sales_amount", sa.Integer, server_default="0"),
            sa.Column("other_sales_amount", sa.Integer, server_default="0"),
            sa.Column("order_count", sa.Integer, server_default="0"),
            sa.Column("table_count", sa.Integer, server_default="0"),
            sa.Column("guest_count", sa.Integer, server_default="0"),
            sa.Column("avg_order_price", sa.Integer, server_default="0"),
            sa.Column("table_turnover_rate", sa.Integer, server_default="0"),
            # 成本类（分）
            sa.Column("total_cost_amount", sa.Integer, server_default="0"),
            sa.Column("food_cost_amount", sa.Integer, server_default="0"),
            sa.Column("beverage_cost_amount", sa.Integer, server_default="0"),
            sa.Column("other_cost_amount", sa.Integer, server_default="0"),
            sa.Column("loss_cost_amount", sa.Integer, server_default="0"),
            sa.Column("staff_meal_cost_amount", sa.Integer, server_default="0"),
            sa.Column("gift_cost_amount", sa.Integer, server_default="0"),
            sa.Column("tasting_cost_amount", sa.Integer, server_default="0"),
            sa.Column("inbound_amount", sa.Integer, server_default="0"),
            sa.Column("issue_amount", sa.Integer, server_default="0"),
            sa.Column("consumed_cost_amount", sa.Integer, server_default="0"),
            # 费用类（分）
            sa.Column("labor_cost_amount", sa.Integer, server_default="0"),
            sa.Column("rent_cost_amount", sa.Integer, server_default="0"),
            sa.Column("water_cost_amount", sa.Integer, server_default="0"),
            sa.Column("electricity_cost_amount", sa.Integer, server_default="0"),
            sa.Column("gas_cost_amount", sa.Integer, server_default="0"),
            sa.Column("platform_service_fee_amount", sa.Integer, server_default="0"),
            sa.Column("material_cost_amount", sa.Integer, server_default="0"),
            sa.Column("marketing_cost_amount", sa.Integer, server_default="0"),
            sa.Column("repair_cost_amount", sa.Integer, server_default="0"),
            sa.Column("management_fee_amount", sa.Integer, server_default="0"),
            sa.Column("other_expense_amount", sa.Integer, server_default="0"),
            # 优惠类（分）
            sa.Column("total_discount_amount", sa.Integer, server_default="0"),
            sa.Column("platform_discount_amount", sa.Integer, server_default="0"),
            sa.Column("member_discount_amount", sa.Integer, server_default="0"),
            sa.Column("manager_authorized_discount_amount", sa.Integer, server_default="0"),
            sa.Column("complaint_compensation_amount", sa.Integer, server_default="0"),
            sa.Column("rounding_discount_amount", sa.Integer, server_default="0"),
            # 派生结果（分 or ×10000）
            sa.Column("gross_profit_amount", sa.Integer, server_default="0"),
            sa.Column("gross_profit_rate", sa.Integer, server_default="0"),
            sa.Column("net_profit_amount", sa.Integer, server_default="0"),
            sa.Column("net_profit_rate", sa.Integer, server_default="0"),
            sa.Column("food_cost_rate", sa.Integer, server_default="0"),
            sa.Column("labor_cost_rate", sa.Integer, server_default="0"),
            sa.Column("discount_rate", sa.Integer, server_default="0"),
            sa.Column("dine_in_sales_rate", sa.Integer, server_default="0"),
            sa.Column("delivery_sales_rate", sa.Integer, server_default="0"),
            # 人效
            sa.Column("front_staff_count", sa.Integer, server_default="0"),
            sa.Column("kitchen_staff_count", sa.Integer, server_default="0"),
            sa.Column("total_staff_count", sa.Integer, server_default="0"),
            sa.Column("labor_hours", sa.Integer, server_default="0"),
            sa.Column("sales_per_staff", sa.Integer, server_default="0"),
            sa.Column("sales_per_labor_hour", sa.Integer, server_default="0"),
            # 数据来源状态
            sa.Column("pos_source_status", sa.String(32)),
            sa.Column("inventory_source_status", sa.String(32)),
            sa.Column("attendance_source_status", sa.String(32)),
            sa.Column("delivery_source_status", sa.String(32)),
            sa.Column("data_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("is_manual_adjusted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("adjusted_by", sa.String(64)),
            sa.Column("adjusted_at", sa.String(50)),
            sa.Column("warning_level", sa.String(16), server_default="green"),
            # 时间戳（TimestampMixin）
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        )
        op.create_index("ix_store_daily_metrics_store_id", "store_daily_metrics", ["store_id"])
        op.create_index("ix_store_daily_metrics_biz_date", "store_daily_metrics", ["biz_date"])
        op.create_index(
            "ix_store_daily_metrics_store_date",
            "store_daily_metrics",
            ["store_id", "biz_date"],
            unique=True,
        )

    # ─────────────────────────────────────────────────────────────
    # 2. store_daily_settlements
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "store_daily_settlements"):
        op.create_table(
            "store_daily_settlements",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("store_id", sa.String(64), nullable=False),
            sa.Column("biz_date", sa.String(10), nullable=False),
            sa.Column("settlement_no", sa.String(64), nullable=False, unique=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending_collect"),
            sa.Column("warning_level", sa.String(16), nullable=False, server_default="green"),
            sa.Column("warning_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("major_issue_types", JSONB),
            sa.Column("auto_summary", sa.Text),
            sa.Column("manager_comment", sa.Text),
            sa.Column("chef_comment", sa.Text),
            sa.Column("finance_comment", sa.Text),
            sa.Column("next_day_action_plan", sa.Text),
            sa.Column("next_day_focus_targets", JSONB),
            sa.Column("submitted_by", sa.String(64)),
            sa.Column("submitted_at", sa.DateTime),
            sa.Column("reviewed_by", sa.String(64)),
            sa.Column("reviewed_at", sa.DateTime),
            sa.Column("review_comment", sa.Text),
            sa.Column("returned_reason", sa.Text),
            sa.Column("closed_at", sa.DateTime),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_store_daily_settlements_store_id", "store_daily_settlements", ["store_id"])
        op.create_index("ix_store_daily_settlements_biz_date", "store_daily_settlements", ["biz_date"])
        op.create_index("ix_store_daily_settlements_status", "store_daily_settlements", ["status"])

    # ─────────────────────────────────────────────────────────────
    # 3. warning_rules
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "warning_rules"):
        op.create_table(
            "warning_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("rule_code", sa.String(64), nullable=False, unique=True),
            sa.Column("rule_name", sa.String(128), nullable=False),
            sa.Column("business_scope", sa.String(32), nullable=False),
            sa.Column("metric_code", sa.String(64), nullable=False),
            sa.Column("compare_operator", sa.String(16), nullable=False),
            sa.Column("yellow_threshold", sa.String(64)),
            sa.Column("red_threshold", sa.String(64)),
            sa.Column("baseline_type", sa.String(32)),
            sa.Column("rule_expression", sa.Text),
            sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_mandatory_comment", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("is_auto_task", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("effective_start_date", sa.Date),
            sa.Column("effective_end_date", sa.Date),
            sa.Column("created_by", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_warning_rules_rule_code", "warning_rules", ["rule_code"], unique=True)

    # ─────────────────────────────────────────────────────────────
    # 4. warning_records
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "warning_records"):
        op.create_table(
            "warning_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("store_id", sa.String(64), nullable=False),
            sa.Column("biz_date", sa.String(10), nullable=False),
            sa.Column("settlement_id", UUID(as_uuid=True)),
            sa.Column("rule_id", UUID(as_uuid=True), nullable=False),
            sa.Column("rule_code", sa.String(64), nullable=False),
            sa.Column("rule_name", sa.String(128), nullable=False),
            sa.Column("warning_type", sa.String(64), nullable=False),
            sa.Column("metric_code", sa.String(64), nullable=False),
            sa.Column("actual_value", sa.Integer),
            sa.Column("baseline_value", sa.Integer),
            sa.Column("yellow_threshold_value", sa.String(64)),
            sa.Column("red_threshold_value", sa.String(64)),
            sa.Column("warning_level", sa.String(16), nullable=False),
            sa.Column("reason_code", sa.String(64)),
            sa.Column("reason_text", sa.String(256)),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("related_task_id", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_warning_records_store_id", "warning_records", ["store_id"])
        op.create_index("ix_warning_records_biz_date", "warning_records", ["biz_date"])
        op.create_index("ix_warning_records_status", "warning_records", ["status"])

    # ─────────────────────────────────────────────────────────────
    # 5. action_tasks
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "action_tasks"):
        op.create_table(
            "action_tasks",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("task_no", sa.String(64), nullable=False, unique=True),
            sa.Column("store_id", sa.String(64), nullable=False),
            sa.Column("biz_date", sa.String(10), nullable=False),
            sa.Column("source_type", sa.String(32), nullable=False),
            sa.Column("source_id", UUID(as_uuid=True), nullable=False),
            sa.Column("task_type", sa.String(64), nullable=False),
            sa.Column("task_title", sa.String(256), nullable=False),
            sa.Column("task_description", sa.Text),
            sa.Column("severity_level", sa.String(16), nullable=False),
            sa.Column("assignee_id", sa.String(64)),
            sa.Column("assignee_role", sa.String(32)),
            sa.Column("reviewer_id", sa.String(64)),
            sa.Column("due_at", sa.DateTime),
            sa.Column("status", sa.String(32), nullable=False, server_default="generated"),
            sa.Column("submit_comment", sa.Text),
            sa.Column("submit_attachments", JSONB),
            sa.Column("review_comment", sa.Text),
            sa.Column("closed_at", sa.DateTime),
            sa.Column("is_repeated_issue", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("repeat_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_action_tasks_task_no", "action_tasks", ["task_no"], unique=True)
        op.create_index("ix_action_tasks_store_id", "action_tasks", ["store_id"])
        op.create_index("ix_action_tasks_biz_date", "action_tasks", ["biz_date"])
        op.create_index("ix_action_tasks_status", "action_tasks", ["status"])

    # ─────────────────────────────────────────────────────────────
    # 6. weekly_reviews
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "weekly_reviews"):
        op.create_table(
            "weekly_reviews",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("review_no", sa.String(64), nullable=False, unique=True),
            sa.Column("review_scope", sa.String(32), nullable=False),
            sa.Column("scope_id", sa.String(64), nullable=False),
            sa.Column("week_start_date", sa.Date, nullable=False),
            sa.Column("week_end_date", sa.Date, nullable=False),
            sa.Column("sales_target_amount", sa.Integer, server_default="0"),
            sa.Column("actual_sales_amount", sa.Integer, server_default="0"),
            sa.Column("target_achievement_rate", sa.Integer, server_default="0"),
            sa.Column("gross_profit_rate", sa.Integer, server_default="0"),
            sa.Column("net_profit_rate", sa.Integer, server_default="0"),
            sa.Column("profit_day_count", sa.Integer, server_default="0"),
            sa.Column("loss_day_count", sa.Integer, server_default="0"),
            sa.Column("abnormal_day_count", sa.Integer, server_default="0"),
            sa.Column("cost_abnormal_day_count", sa.Integer, server_default="0"),
            sa.Column("discount_abnormal_day_count", sa.Integer, server_default="0"),
            sa.Column("labor_abnormal_day_count", sa.Integer, server_default="0"),
            sa.Column("submitted_task_count", sa.Integer, server_default="0"),
            sa.Column("closed_task_count", sa.Integer, server_default="0"),
            sa.Column("pending_task_count", sa.Integer, server_default="0"),
            sa.Column("repeated_issue_count", sa.Integer, server_default="0"),
            sa.Column("system_summary", sa.Text),
            sa.Column("manager_summary", sa.Text),
            sa.Column("next_week_plan", sa.Text),
            sa.Column("next_week_focus_targets", JSONB),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("submitted_by", sa.String(64)),
            sa.Column("submitted_at", sa.DateTime),
            sa.Column("reviewed_by", sa.String(64)),
            sa.Column("reviewed_at", sa.DateTime),
            sa.Column("review_comment", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_weekly_reviews_review_no", "weekly_reviews", ["review_no"], unique=True)
        op.create_index("ix_weekly_reviews_scope_id", "weekly_reviews", ["scope_id"])
        op.create_index("ix_weekly_reviews_week_start_date", "weekly_reviews", ["week_start_date"])
        op.create_index("ix_weekly_reviews_status", "weekly_reviews", ["status"])

    # ─────────────────────────────────────────────────────────────
    # 7. weekly_review_items
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "weekly_review_items"):
        op.create_table(
            "weekly_review_items",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "weekly_review_id",
                UUID(as_uuid=True),
                sa.ForeignKey("weekly_reviews.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("item_type", sa.String(64), nullable=False),
            sa.Column("title", sa.String(256), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("related_dates", JSONB),
            sa.Column("related_warning_ids", JSONB),
            sa.Column("root_cause", sa.Text),
            sa.Column("corrective_action", sa.Text),
            sa.Column("owner_id", sa.String(64)),
            sa.Column("owner_role", sa.String(32)),
            sa.Column("due_date", sa.Date),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_weekly_review_items_weekly_review_id",
            "weekly_review_items",
            ["weekly_review_id"],
        )

    # ─────────────────────────────────────────────────────────────
    # 8. data_quality_check_records
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "data_quality_check_records"):
        op.create_table(
            "data_quality_check_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("store_id", sa.String(64), nullable=False),
            sa.Column("biz_date", sa.String(10), nullable=False),
            sa.Column("check_type", sa.String(64), nullable=False),
            sa.Column("check_code", sa.String(64), nullable=False),
            sa.Column("check_name", sa.String(128), nullable=False),
            sa.Column("check_result", sa.String(16), nullable=False),
            sa.Column("expected_value", sa.String(128)),
            sa.Column("actual_value", sa.String(128)),
            sa.Column("error_message", sa.Text),
            sa.Column("source_system", sa.String(64)),
            sa.Column("resolved_status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("resolved_by", sa.String(64)),
            sa.Column("resolved_at", sa.DateTime),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_data_quality_check_records_store_id",
            "data_quality_check_records",
            ["store_id"],
        )
        op.create_index(
            "ix_data_quality_check_records_biz_date",
            "data_quality_check_records",
            ["biz_date"],
        )


def downgrade():
    conn = op.get_bind()
    for table in [
        "data_quality_check_records",
        "weekly_review_items",
        "weekly_reviews",
        "action_tasks",
        "warning_records",
        "warning_rules",
        "store_daily_settlements",
        "store_daily_metrics",
    ]:
        if _table_exists(conn, table):
            op.drop_table(table)
