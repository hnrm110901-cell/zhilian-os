"""
r08 L5 行动层数据库迁移

新建：
  action_plans — L5 行动计划物化表
    （每条 reasoning_report P1/P2/P3 对应一个行动计划，追踪派发与结果）

revision:      r08_action_plans
down_revision: r07_reasoning_layer
"""

revision     = "r08_action_plans"
down_revision = "r07_reasoning_layer"
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade():
    op.create_table(
        "action_plans",

        sa.Column("id", UUID(as_uuid=True), primary_key=True),

        # 关联 L4 推理报告
        sa.Column("reasoning_report_id", UUID(as_uuid=True), nullable=False),

        # 冗余字段（避免频繁 JOIN）
        sa.Column("store_id",    sa.String(50),  nullable=False),
        sa.Column("report_date", sa.Date(),       nullable=False),
        sa.Column("dimension",   sa.String(30),   nullable=False),
        sa.Column("severity",    sa.String(10),   nullable=False),  # P1/P2/P3
        sa.Column("root_cause",  sa.String(200)),
        sa.Column("confidence",  sa.Float()),

        # 派发结果（关联各子系统 ID）
        sa.Column("wechat_action_id", sa.String(100)),           # WeChatActionFSM action_id
        sa.Column("task_id",          UUID(as_uuid=True)),        # tasks.id
        sa.Column("decision_log_id",  UUID(as_uuid=True)),        # decision_logs.id（审批流）
        sa.Column("notification_ids", JSONB()),                    # List[str] 通知 ID

        # 派发状态
        # pending → dispatched / partial / failed / skipped
        sa.Column("dispatch_status",   sa.String(20), nullable=False, server_default="pending"),
        sa.Column("dispatched_at",     sa.DateTime()),
        sa.Column("dispatched_actions", JSONB()),                  # List[str] 实际派发的行动类型

        # 结果追踪（Human-in-the-Loop 反馈闭环）
        # pending → resolved / escalated / expired / no_effect / cancelled
        sa.Column("outcome",      sa.String(20), nullable=False, server_default="pending"),
        sa.Column("outcome_note", sa.Text()),
        sa.Column("resolved_at",  sa.DateTime()),
        sa.Column("resolved_by",  sa.String(100)),

        # 跟进诊断（行动后下一次 L4 扫描的报告 ID）
        sa.Column("followup_report_id", UUID(as_uuid=True)),

        # KPI 变化量（行动前后对比：{waste_rate: {before: 0.15, after: 0.11, delta: -0.04}}）
        sa.Column("kpi_delta", JSONB()),

        # 时间戳
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 唯一约束：每份推理报告最多对应一个行动计划
    op.create_unique_constraint(
        "uq_action_plan_report_id",
        "action_plans",
        ["reasoning_report_id"],
    )

    # 查询索引
    op.create_index("idx_ap_store_date",       "action_plans", ["store_id", "report_date"])
    op.create_index("idx_ap_severity",         "action_plans", ["severity"])
    op.create_index("idx_ap_dispatch_status",  "action_plans", ["dispatch_status"])
    op.create_index("idx_ap_outcome",          "action_plans", ["outcome"])
    op.create_index("idx_ap_dimension",        "action_plans", ["dimension"])


def downgrade():
    op.drop_index("idx_ap_dimension",       table_name="action_plans")
    op.drop_index("idx_ap_outcome",         table_name="action_plans")
    op.drop_index("idx_ap_dispatch_status", table_name="action_plans")
    op.drop_index("idx_ap_severity",        table_name="action_plans")
    op.drop_index("idx_ap_store_date",      table_name="action_plans")
    op.drop_table("action_plans")
