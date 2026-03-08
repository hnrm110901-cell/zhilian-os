"""z35 — Phase 9 宴会管理 Agent 数据模型

Banquet Intelligence System：
  banquet_halls                  宴会厅主数据
  banquet_customers              宴会CRM客户
  banquet_leads                  宴会线索
  lead_followup_records          跟进记录
  banquet_quotes                 报价单
  banquet_menu_packages          套餐
  banquet_menu_package_items     套餐菜品
  banquet_orders                 宴会订单
  banquet_hall_bookings          厅房档期占用
  banquet_execution_templates    执行任务模板
  banquet_execution_tasks        执行任务
  banquet_execution_exceptions   执行异常
  banquet_payment_records        收款记录
  banquet_contracts              合同
  banquet_profit_snapshots       利润快照
  banquet_kpi_daily              KPI日报
  banquet_agent_rules            Agent规则
  banquet_agent_action_logs      Agent执行日志
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = 'z35'
down_revision = 'z34'
branch_labels = None
depends_on    = None


def upgrade():
    # ── Enums ──────────────────────────────────────────────────────────
    op.execute("CREATE TYPE banquethalltype AS ENUM ('main_hall','vip_room','garden','outdoor')")
    op.execute("CREATE TYPE banquettypeenum AS ENUM ('wedding','birthday','business','full_moon','graduation','anniversary','other')")
    op.execute("CREATE TYPE leadstatusenum AS ENUM ('new','contacted','visit_scheduled','quoted','waiting_decision','deposit_pending','won','lost')")
    op.execute("CREATE TYPE orderstatusenum AS ENUM ('draft','confirmed','preparing','in_progress','completed','settled','closed','cancelled')")
    op.execute("CREATE TYPE depositstatusenum AS ENUM ('unpaid','partial','paid')")
    op.execute("CREATE TYPE taskstatusenum AS ENUM ('pending','in_progress','done','verified','overdue','closed')")
    op.execute("CREATE TYPE taskownerroleenum AS ENUM ('kitchen','service','decor','purchase','manager')")
    op.execute("CREATE TYPE paymenttypeenum AS ENUM ('deposit','balance','extra')")
    op.execute("CREATE TYPE banquetagenttypeenum AS ENUM ('followup','quotation','scheduling','execution','review')")

    # ── banquet_halls ───────────────────────────────────────────────────
    op.create_table(
        "banquet_halls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("hall_type", postgresql.ENUM("main_hall","vip_room","garden","outdoor", name="banquethalltype", create_type=False), nullable=False),
        sa.Column("max_tables", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_people", sa.Integer, nullable=False),
        sa.Column("min_spend_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("floor_area_m2", sa.Float, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_banquet_halls_store_active", "banquet_halls", ["store_id", "is_active"])

    # ── banquet_customers ───────────────────────────────────────────────
    op.create_table(
        "banquet_customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("wechat_id", sa.String(100), nullable=True),
        sa.Column("customer_type", sa.String(50), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("tags", postgresql.JSON, nullable=True),
        sa.Column("vip_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_banquet_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_banquet_amount_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_banquet_customers_brand_phone", "banquet_customers", ["brand_id", "phone"])

    # ── banquet_leads ───────────────────────────────────────────────────
    op.create_table(
        "banquet_leads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("banquet_customers.id"), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("banquet_type", postgresql.ENUM("wedding","birthday","business","full_moon","graduation","anniversary","other", name="banquettypeenum", create_type=False), nullable=False),
        sa.Column("expected_date", sa.Date, nullable=True),
        sa.Column("expected_people_count", sa.Integer, nullable=True),
        sa.Column("expected_budget_fen", sa.Integer, nullable=True),
        sa.Column("preferred_hall_type", postgresql.ENUM("main_hall","vip_room","garden","outdoor", name="banquethalltype", create_type=False), nullable=True),
        sa.Column("source_channel", sa.String(50), nullable=True),
        sa.Column("current_stage", postgresql.ENUM("new","contacted","visit_scheduled","quoted","waiting_decision","deposit_pending","won","lost", name="leadstatusenum", create_type=False), nullable=False, server_default="new"),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("last_followup_at", sa.DateTime, nullable=True),
        sa.Column("next_followup_at", sa.DateTime, nullable=True),
        sa.Column("lost_reason", sa.String(200), nullable=True),
        sa.Column("converted_order_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_banquet_leads_store_stage", "banquet_leads", ["store_id", "current_stage"])
    op.create_index("ix_banquet_leads_owner", "banquet_leads", ["owner_user_id"])

    # ── lead_followup_records ───────────────────────────────────────────
    op.create_table(
        "lead_followup_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("banquet_leads.id"), nullable=False),
        sa.Column("followup_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("stage_before", postgresql.ENUM("new","contacted","visit_scheduled","quoted","waiting_decision","deposit_pending","won","lost", name="leadstatusenum", create_type=False), nullable=True),
        sa.Column("stage_after", postgresql.ENUM("new","contacted","visit_scheduled","quoted","waiting_decision","deposit_pending","won","lost", name="leadstatusenum", create_type=False), nullable=True),
        sa.Column("next_followup_at", sa.DateTime, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_quotes ──────────────────────────────────────────────────
    op.create_table(
        "banquet_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("banquet_leads.id"), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("package_id", sa.String(36), nullable=True),
        sa.Column("people_count", sa.Integer, nullable=False),
        sa.Column("table_count", sa.Integer, nullable=False),
        sa.Column("quoted_amount_fen", sa.Integer, nullable=False),
        sa.Column("menu_snapshot", postgresql.JSON, nullable=True),
        sa.Column("valid_until", sa.Date, nullable=True),
        sa.Column("is_accepted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_menu_packages ───────────────────────────────────────────
    op.create_table(
        "banquet_menu_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("banquet_type", postgresql.ENUM("wedding","birthday","business","full_moon","graduation","anniversary","other", name="banquettypeenum", create_type=False), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("suggested_price_fen", sa.Integer, nullable=False),
        sa.Column("cost_fen", sa.Integer, nullable=True),
        sa.Column("target_people_min", sa.Integer, nullable=False, server_default="1"),
        sa.Column("target_people_max", sa.Integer, nullable=False, server_default="999"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_menu_package_items ──────────────────────────────────────
    op.create_table(
        "banquet_menu_package_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("package_id", sa.String(36), sa.ForeignKey("banquet_menu_packages.id"), nullable=False),
        sa.Column("dish_id", sa.String(36), nullable=True),
        sa.Column("dish_name", sa.String(200), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False, server_default="standard"),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("replace_group", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_orders ──────────────────────────────────────────────────
    op.create_table(
        "banquet_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("banquet_leads.id"), nullable=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("banquet_customers.id"), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("banquet_type", postgresql.ENUM("wedding","birthday","business","full_moon","graduation","anniversary","other", name="banquettypeenum", create_type=False), nullable=False),
        sa.Column("banquet_date", sa.Date, nullable=False),
        sa.Column("people_count", sa.Integer, nullable=False),
        sa.Column("table_count", sa.Integer, nullable=False),
        sa.Column("package_id", sa.String(36), sa.ForeignKey("banquet_menu_packages.id"), nullable=True),
        sa.Column("menu_snapshot", postgresql.JSON, nullable=True),
        sa.Column("order_status", postgresql.ENUM("draft","confirmed","preparing","in_progress","completed","settled","closed","cancelled", name="orderstatusenum", create_type=False), nullable=False, server_default="draft"),
        sa.Column("deposit_status", postgresql.ENUM("unpaid","partial","paid", name="depositstatusenum", create_type=False), nullable=False, server_default="unpaid"),
        sa.Column("total_amount_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deposit_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("paid_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("contact_name", sa.String(100), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_banquet_orders_store_date", "banquet_orders", ["store_id", "banquet_date"])
    op.create_index("ix_banquet_orders_store_status", "banquet_orders", ["store_id", "order_status"])

    # ── banquet_hall_bookings ───────────────────────────────────────────
    op.create_table(
        "banquet_hall_bookings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hall_id", sa.String(36), sa.ForeignKey("banquet_halls.id"), nullable=False),
        sa.Column("banquet_order_id", sa.String(36), sa.ForeignKey("banquet_orders.id"), nullable=False),
        sa.Column("slot_date", sa.Date, nullable=False),
        sa.Column("slot_name", sa.String(50), nullable=False),
        sa.Column("start_time", sa.String(10), nullable=True),
        sa.Column("end_time", sa.String(10), nullable=True),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("hall_id", "slot_date", "slot_name", name="uq_hall_booking_slot"),
    )
    op.create_index("ix_hall_bookings_date", "banquet_hall_bookings", ["slot_date"])

    # ── banquet_execution_templates ─────────────────────────────────────
    op.create_table(
        "banquet_execution_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("template_name", sa.String(200), nullable=False),
        sa.Column("banquet_type", postgresql.ENUM("wedding","birthday","business","full_moon","graduation","anniversary","other", name="banquettypeenum", create_type=False), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("task_defs", postgresql.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_execution_tasks ─────────────────────────────────────────
    op.create_table(
        "banquet_execution_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("banquet_order_id", sa.String(36), sa.ForeignKey("banquet_orders.id"), nullable=False),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("banquet_execution_templates.id"), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("task_name", sa.String(200), nullable=False),
        sa.Column("owner_role", postgresql.ENUM("kitchen","service","decor","purchase","manager", name="taskownerroleenum", create_type=False), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("due_time", sa.DateTime, nullable=False),
        sa.Column("task_status", postgresql.ENUM("pending","in_progress","done","verified","overdue","closed", name="taskstatusenum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_exec_tasks_order", "banquet_execution_tasks", ["banquet_order_id"])
    op.create_index("ix_exec_tasks_status_due", "banquet_execution_tasks", ["task_status", "due_time"])

    # ── banquet_execution_exceptions ────────────────────────────────────
    op.create_table(
        "banquet_execution_exceptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("banquet_order_id", sa.String(36), sa.ForeignKey("banquet_orders.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("banquet_execution_tasks.id"), nullable=True),
        sa.Column("exception_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_payment_records ─────────────────────────────────────────
    op.create_table(
        "banquet_payment_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("banquet_order_id", sa.String(36), sa.ForeignKey("banquet_orders.id"), nullable=False),
        sa.Column("payment_type", postgresql.ENUM("deposit","balance","extra", name="paymenttypeenum", create_type=False), nullable=False),
        sa.Column("amount_fen", sa.Integer, nullable=False),
        sa.Column("paid_at", sa.DateTime, nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("receipt_no", sa.String(100), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_contracts ───────────────────────────────────────────────
    op.create_table(
        "banquet_contracts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("banquet_order_id", sa.String(36), sa.ForeignKey("banquet_orders.id"), nullable=False, unique=True),
        sa.Column("contract_no", sa.String(100), nullable=False, unique=True),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("contract_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("signed_at", sa.DateTime, nullable=True),
        sa.Column("signed_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_profit_snapshots ────────────────────────────────────────
    op.create_table(
        "banquet_profit_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("banquet_order_id", sa.String(36), sa.ForeignKey("banquet_orders.id"), nullable=False, unique=True),
        sa.Column("revenue_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ingredient_cost_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("labor_cost_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("material_cost_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("other_cost_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gross_profit_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gross_margin_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_kpi_daily ───────────────────────────────────────────────
    op.create_table(
        "banquet_kpi_daily",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("stat_date", sa.Date, nullable=False),
        sa.Column("lead_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("order_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("revenue_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gross_profit_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hall_utilization_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("conversion_rate_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("store_id", "stat_date", name="uq_banquet_kpi_store_date"),
    )

    # ── banquet_agent_rules ─────────────────────────────────────────────
    op.create_table(
        "banquet_agent_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_id", sa.String(36), nullable=True),
        sa.Column("agent_type", postgresql.ENUM("followup","quotation","scheduling","execution","review", name="banquetagenttypeenum", create_type=False), nullable=False),
        sa.Column("rule_name", sa.String(200), nullable=False),
        sa.Column("trigger_event", sa.String(100), nullable=False),
        sa.Column("rule_expression", postgresql.JSON, nullable=False),
        sa.Column("action_template", postgresql.JSON, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )

    # ── banquet_agent_action_logs ───────────────────────────────────────
    op.create_table(
        "banquet_agent_action_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_type", postgresql.ENUM("followup","quotation","scheduling","execution","review", name="banquetagenttypeenum", create_type=False), nullable=False),
        sa.Column("related_object_type", sa.String(50), nullable=False),
        sa.Column("related_object_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=True),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_result", postgresql.JSON, nullable=True),
        sa.Column("suggestion_text", sa.Text, nullable=True),
        sa.Column("is_human_approved", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_banquet_agent_log_obj", "banquet_agent_action_logs", ["related_object_type", "related_object_id"])


def downgrade():
    # tables
    for tbl in [
        "banquet_agent_action_logs", "banquet_agent_rules",
        "banquet_kpi_daily", "banquet_profit_snapshots",
        "banquet_contracts", "banquet_payment_records",
        "banquet_execution_exceptions", "banquet_execution_tasks",
        "banquet_execution_templates", "banquet_hall_bookings",
        "banquet_orders", "banquet_menu_package_items",
        "banquet_menu_packages", "banquet_quotes",
        "lead_followup_records", "banquet_leads",
        "banquet_customers", "banquet_halls",
    ]:
        op.drop_table(tbl)
    # enums
    for e in [
        "banquetagenttypeenum", "paymenttypeenum", "taskownerroleenum",
        "taskstatusenum", "depositstatusenum", "orderstatusenum",
        "leadstatusenum", "banquettypeenum", "banquethalltype",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {e}")
