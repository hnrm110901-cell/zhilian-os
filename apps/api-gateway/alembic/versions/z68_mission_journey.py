"""z68: 使命旅程引擎 — 业人成长旅程管理

Revision ID: z68_mission_journey
Revises: z67_knowledge_base_three_libraries
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "z68_mission_journey"
down_revision = "z67_knowledge_base_three_libraries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. mj_journey_templates — 旅程模板
    op.create_table(
        "mj_journey_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.String(50), nullable=True, index=True),
        sa.Column("store_id", sa.String(50), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("journey_type", sa.String(20), nullable=False, server_default="career"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("applicable_positions", JSON, nullable=True),
        sa.Column("total_stages", sa.Integer, server_default="0"),
        sa.Column("estimated_months", sa.Integer, nullable=True),
        sa.Column("auto_advance", sa.Boolean, server_default="true"),
        sa.Column("completion_reward_fen", sa.Integer, server_default="0"),
        sa.Column("completion_badge", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 2. mj_stage_definitions — 阶段定义
    op.create_table(
        "mj_stage_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", UUID(as_uuid=True),
                  sa.ForeignKey("mj_journey_templates.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("min_days", sa.Integer, nullable=True),
        sa.Column("max_days", sa.Integer, nullable=True),
        sa.Column("target_days", sa.Integer, nullable=True),
        sa.Column("entry_conditions", JSON, nullable=True),
        sa.Column("completion_conditions", JSON, nullable=True),
        sa.Column("tasks", JSON, nullable=True),
        sa.Column("milestone_types", JSON, nullable=True),
        sa.Column("stage_reward_fen", sa.Integer, server_default="0"),
        sa.Column("stage_badge", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 3. mj_employee_journeys — 员工旅程实例
    op.create_table(
        "mj_employee_journeys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("template_id", UUID(as_uuid=True),
                  sa.ForeignKey("mj_journey_templates.id"),
                  nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("current_stage_seq", sa.Integer, server_default="0"),
        sa.Column("current_stage_name", sa.String(200), nullable=True),
        sa.Column("progress_pct", sa.Numeric(5, 1), server_default="0"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("paused_at", sa.DateTime, nullable=True),
        sa.Column("total_milestones", sa.Integer, server_default="0"),
        sa.Column("achieved_milestones", sa.Integer, server_default="0"),
        sa.Column("total_narratives", sa.Integer, server_default="0"),
        sa.Column("mentor_person_id", UUID(as_uuid=True), nullable=True),
        sa.Column("mentor_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("person_id", "template_id",
                            name="uq_person_journey_template"),
    )

    # 4. mj_stage_progress — 阶段进度
    op.create_table(
        "mj_stage_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("journey_id", UUID(as_uuid=True),
                  sa.ForeignKey("mj_employee_journeys.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("stage_def_id", UUID(as_uuid=True),
                  sa.ForeignKey("mj_stage_definitions.id"),
                  nullable=False),
        sa.Column("stage_seq", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="locked"),
        sa.Column("entered_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("days_spent", sa.Integer, nullable=True),
        sa.Column("task_progress", JSON, nullable=True),
        sa.Column("tasks_total", sa.Integer, server_default="0"),
        sa.Column("tasks_done", sa.Integer, server_default="0"),
        sa.Column("evaluator_name", sa.String(100), nullable=True),
        sa.Column("evaluation_score", sa.Integer, nullable=True),
        sa.Column("evaluation_comment", sa.Text, nullable=True),
        sa.Column("reward_issued", sa.Boolean, server_default="false"),
        sa.Column("reward_fen", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 5. mj_growth_narratives — 成长叙事
    op.create_table(
        "mj_growth_narratives",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("journey_id", UUID(as_uuid=True),
                  sa.ForeignKey("mj_employee_journeys.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("narrative_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("emoji", sa.String(10), nullable=True),
        sa.Column("related_entity_type", sa.String(50), nullable=True),
        sa.Column("related_entity_id", sa.String(100), nullable=True),
        sa.Column("value_fen", sa.Integer, nullable=True),
        sa.Column("is_public", sa.Boolean, server_default="true"),
        sa.Column("is_pushed", sa.Boolean, server_default="false"),
        sa.Column("pushed_at", sa.DateTime, nullable=True),
        sa.Column("likes_count", sa.Integer, server_default="0"),
        sa.Column("occurred_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 6. mj_journey_milestones — 旅程里程碑
    op.create_table(
        "mj_journey_milestones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("journey_id", UUID(as_uuid=True),
                  sa.ForeignKey("mj_employee_journeys.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("stage_seq", sa.Integer, nullable=True),
        sa.Column("person_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), nullable=False),
        sa.Column("milestone_code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("achieved", sa.Boolean, server_default="false"),
        sa.Column("achieved_at", sa.DateTime, nullable=True),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("reward_fen", sa.Integer, server_default="0"),
        sa.Column("badge_icon", sa.String(50), nullable=True),
        sa.Column("badge_name", sa.String(100), nullable=True),
        sa.Column("notified", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 7. mj_journey_stats — 旅程统计快照
    op.create_table(
        "mj_journey_stats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("brand_id", sa.String(50), nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False, index=True),
        sa.Column("total_employees", sa.Integer, server_default="0"),
        sa.Column("active_journeys", sa.Integer, server_default="0"),
        sa.Column("completed_journeys", sa.Integer, server_default="0"),
        sa.Column("milestones_achieved_mtd", sa.Integer, server_default="0"),
        sa.Column("narratives_created_mtd", sa.Integer, server_default="0"),
        sa.Column("avg_journey_progress_pct", sa.Numeric(5, 1), server_default="0"),
        sa.Column("avg_stage_days", sa.Numeric(6, 1), nullable=True),
        sa.Column("retention_rate_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("industry_avg_progress_pct", sa.Numeric(5, 1), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "snapshot_date",
                            name="uq_journey_stats_store_date"),
    )


def downgrade() -> None:
    tables = [
        "mj_journey_stats",
        "mj_journey_milestones",
        "mj_growth_narratives",
        "mj_stage_progress",
        "mj_employee_journeys",
        "mj_stage_definitions",
        "mj_journey_templates",
    ]
    for t in tables:
        op.drop_table(t)
