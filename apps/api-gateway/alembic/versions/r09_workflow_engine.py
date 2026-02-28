"""
r09 多阶段工作流引擎数据库迁移

新建：
  daily_workflows   — 每家门店每日一条规划工作流（Day N 晚上规划 Day N+1）
  workflow_phases   — 工作流的 6 个阶段（各有硬 deadline + 自动锁定）
  decision_versions — 阶段内决策的版本快照（版本链，记录每次修改原因）

架构背景：
  餐饮经营的 Day N+1 规划必须在 Day N 当天（17:00-22:00）分阶段完成：
    Phase 1 initial_plan  17:00-17:30  初版规划（快速模式，数据不完整也要出结果）
    Phase 2 procurement   17:30-18:00  采购确认 + LOCK（供应商次日 07:00 送货）
    Phase 3 scheduling    18:00-19:00  排班确认 + LOCK（员工需要提前准备）
    Phase 4 menu          19:00-20:00  菜单确认 + LOCK（外卖平台同步需 1-2h）
    Phase 5 menu_sync     20:00-21:00  菜单同步执行（自动，无人工介入）
    Phase 6 marketing     21:00-22:00  营销推送 + LOCK

revision:      r09_workflow_engine
down_revision: r08_action_plans
"""

revision     = "r09_workflow_engine"
down_revision = "r08_action_plans"
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade():
    # ── 1. daily_workflows ────────────────────────────────────────────────────
    op.create_table(
        "daily_workflows",

        sa.Column("id",           UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id",     sa.String(50),  nullable=False),

        # plan_date    = 正在规划的日期（Day N+1）
        # trigger_date = 触发规划的日期（Day N，实际执行规划的那天）
        sa.Column("plan_date",    sa.Date(), nullable=False),
        sa.Column("trigger_date", sa.Date(), nullable=False),

        # 工作流状态
        # pending → running → partial_locked → fully_locked → completed
        sa.Column("status",         sa.String(20), nullable=False, server_default="pending"),
        sa.Column("current_phase",  sa.String(30)),   # 当前正在执行的阶段名

        # 执行时间
        sa.Column("started_at",   sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),

        # 门店个性化配置（可覆盖默认 deadline）
        # e.g. {"procurement_deadline": "17:45", "supplier_cutoff": "17:30"}
        sa.Column("store_config", JSONB()),

        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_daily_workflow_store_plan_date",
        "daily_workflows",
        ["store_id", "plan_date"],
    )
    op.create_index("idx_wf_store_date",    "daily_workflows", ["store_id", "plan_date"])
    op.create_index("idx_wf_status",        "daily_workflows", ["status"])
    op.create_index("idx_wf_trigger_date",  "daily_workflows", ["trigger_date"])

    # ── 2. workflow_phases ────────────────────────────────────────────────────
    op.create_table(
        "workflow_phases",

        sa.Column("id",          UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),

        # 阶段标识
        # initial_plan / procurement / scheduling / menu / menu_sync / marketing
        sa.Column("phase_name",  sa.String(30), nullable=False),
        sa.Column("phase_order", sa.Integer(),  nullable=False),

        # 硬 deadline（超过后自动 lock）
        sa.Column("deadline", sa.DateTime(), nullable=False),

        # 阶段状态
        # pending → running → reviewing → locked → completed / skipped
        sa.Column("status",    sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("locked_at",  sa.DateTime()),
        sa.Column("locked_by",  sa.String(50)),   # 'auto' 或 user_id

        # 当前最终决策版本 ID（锁定后指向最终版本）
        sa.Column("current_version_id", UUID(as_uuid=True)),

        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_workflow_phase_name",
        "workflow_phases",
        ["workflow_id", "phase_name"],
    )
    op.create_index("idx_wp_workflow_id",  "workflow_phases", ["workflow_id"])
    op.create_index("idx_wp_status",       "workflow_phases", ["status"])
    op.create_index("idx_wp_deadline",     "workflow_phases", ["deadline"])

    # ── 3. decision_versions ─────────────────────────────────────────────────
    op.create_table(
        "decision_versions",

        sa.Column("id",             UUID(as_uuid=True), primary_key=True),
        sa.Column("phase_id",       UUID(as_uuid=True), nullable=False),

        # 冗余字段（快速查询）
        sa.Column("store_id",       sa.String(50),  nullable=False),
        sa.Column("phase_name",     sa.String(30),  nullable=False),
        sa.Column("plan_date",      sa.Date(),      nullable=False),
        sa.Column("version_number", sa.Integer(),   nullable=False),   # 1, 2, 3 ...

        # 决策内容快照（各阶段格式不同）
        # initial_plan:  {forecast_footfall, top_dishes, risk_flags}
        # procurement:   {items: [{ingredient, qty, unit, cost}], total_cost}
        # scheduling:    {shifts: [{role, count, start, end}], total_hours}
        # menu:          {featured, stop_sell, price_adjustments}
        # marketing:     {push_messages, target_segments, promo_items}
        sa.Column("content", JSONB(), nullable=False),

        # 生成元数据
        # generation_mode: fast（<30秒，历史规律） / precise（精确算法）/ manual（人工）
        sa.Column("generation_mode",    sa.String(20)),
        sa.Column("generation_seconds", sa.Float()),      # 实际生成耗时
        sa.Column("data_completeness",  sa.Float()),      # 输入数据完整度 (0-1)
        sa.Column("confidence",         sa.Float()),      # 系统置信度 (0-1)

        # 版本差异（与上一版本相比的变化）
        sa.Column("changes_from_prev", JSONB()),  # {added: [], removed: [], modified: []}
        sa.Column("change_reason",     sa.Text()),

        # 操作人
        sa.Column("submitted_by", sa.String(50)),   # 'system' 或 user_id

        # 是否为最终版本（phase lock 时标记）
        sa.Column("is_final", sa.Boolean(), server_default="false"),

        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_decision_version_phase_ver",
        "decision_versions",
        ["phase_id", "version_number"],
    )
    op.create_index("idx_dv_phase_id",    "decision_versions", ["phase_id"])
    op.create_index("idx_dv_store_date",  "decision_versions", ["store_id", "plan_date"])
    op.create_index("idx_dv_is_final",    "decision_versions", ["is_final"])


def downgrade():
    op.drop_index("idx_dv_is_final",      table_name="decision_versions")
    op.drop_index("idx_dv_store_date",    table_name="decision_versions")
    op.drop_index("idx_dv_phase_id",      table_name="decision_versions")
    op.drop_table("decision_versions")

    op.drop_index("idx_wp_deadline",      table_name="workflow_phases")
    op.drop_index("idx_wp_status",        table_name="workflow_phases")
    op.drop_index("idx_wp_workflow_id",   table_name="workflow_phases")
    op.drop_table("workflow_phases")

    op.drop_index("idx_wf_trigger_date",  table_name="daily_workflows")
    op.drop_index("idx_wf_status",        table_name="daily_workflows")
    op.drop_index("idx_wf_store_date",    table_name="daily_workflows")
    op.drop_table("daily_workflows")
