"""
HR04: 员工成长旅程 — 技能矩阵·职业路径·里程碑·成长计划·幸福指数

新建表:
  - skill_definitions        技能定义（岗位技能标准）
  - employee_skills          员工技能评估记录
  - career_paths             职业发展路径
  - employee_milestones      员工里程碑
  - employee_growth_plans    成长计划
  - employee_wellbeing       幸福指数

Revision ID: hr04
Revises: hr03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY, ENUM as PG_ENUM

revision = 'hr04'
down_revision = 'hr03'
branch_labels = None
depends_on = None


def _create_enum_safe(name, values):
    """安全创建 PostgreSQL ENUM（已存在则跳过，兼容 offline SQL 生成模式）"""
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(
        f"DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({vals}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; "
        f"END $$"
    ))


def upgrade():
    # ── ENUM 类型 ──
    _create_enum_safe("skill_level_enum", [
        "novice", "apprentice", "journeyman", "expert", "master",
    ])
    _create_enum_safe("milestone_type_enum", [
        "onboard", "trial_pass", "probation_pass", "first_praise",
        "skill_up", "zero_waste_month", "sales_champion", "anniversary",
        "promotion", "mentor_first", "culture_star", "training_complete",
        "perfect_attendance", "custom",
    ])
    _create_enum_safe("growth_plan_status_enum", [
        "active", "completed", "paused", "cancelled",
    ])

    # ── 1. skill_definitions ──
    op.create_table(
        "skill_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=True, index=True),
        sa.Column("brand_id", sa.String(50), nullable=True),
        sa.Column("skill_name", sa.String(100), nullable=False),
        sa.Column("skill_category", sa.String(50), nullable=False),
        sa.Column("applicable_positions", JSON, nullable=True),
        sa.Column("required_level", PG_ENUM(
            "novice", "apprentice", "journeyman", "expert", "master",
            name="skill_level_enum", create_type=False,
        ), nullable=False, server_default="journeyman"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("promotion_weight", sa.Integer, default=50),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 2. employee_skills ──
    op.create_table(
        "employee_skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("skill_id", UUID(as_uuid=True), sa.ForeignKey("skill_definitions.id"), nullable=False),
        sa.Column("current_level", PG_ENUM(
            "novice", "apprentice", "journeyman", "expert", "master",
            name="skill_level_enum", create_type=False,
        ), nullable=False, server_default="novice"),
        sa.Column("score", sa.Integer, default=0),
        sa.Column("assessed_by", sa.String(100), nullable=True),
        sa.Column("assessed_at", sa.Date, nullable=True),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("next_target_level", PG_ENUM(
            "novice", "apprentice", "journeyman", "expert", "master",
            name="skill_level_enum", create_type=False,
        ), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 3. career_paths ──
    op.create_table(
        "career_paths",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=True, index=True),
        sa.Column("brand_id", sa.String(50), nullable=True),
        sa.Column("path_name", sa.String(100), nullable=False),
        sa.Column("from_position", sa.String(50), nullable=False),
        sa.Column("to_position", sa.String(50), nullable=False),
        sa.Column("sequence", sa.Integer, default=0),
        sa.Column("min_tenure_months", sa.Integer, default=6),
        sa.Column("required_skills", JSON, nullable=True),
        sa.Column("required_training", JSON, nullable=True),
        sa.Column("min_performance_level", sa.String(10), server_default="B"),
        sa.Column("min_performance_score", sa.Integer, server_default="70"),
        sa.Column("salary_increase_pct", sa.Numeric(5, 1), server_default="15.0"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 4. employee_milestones ──
    op.create_table(
        "employee_milestones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("milestone_type", PG_ENUM(
            "onboard", "trial_pass", "probation_pass", "first_praise",
            "skill_up", "zero_waste_month", "sales_champion", "anniversary",
            "promotion", "mentor_first", "culture_star", "training_complete",
            "perfect_attendance", "custom",
            name="milestone_type_enum", create_type=False,
        ), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("achieved_at", sa.Date, nullable=False),
        sa.Column("related_entity_type", sa.String(50), nullable=True),
        sa.Column("related_entity_id", sa.String(100), nullable=True),
        sa.Column("reward_fen", sa.Integer, default=0),
        sa.Column("badge_icon", sa.String(50), nullable=True),
        sa.Column("notified", sa.Boolean, default=False),
        sa.Column("notified_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 5. employee_growth_plans ──
    op.create_table(
        "employee_growth_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("plan_name", sa.String(200), nullable=False),
        sa.Column("status", PG_ENUM(
            "active", "completed", "paused", "cancelled",
            name="growth_plan_status_enum", create_type=False,
        ), nullable=False, server_default="active"),
        sa.Column("target_position", sa.String(50), nullable=True),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("tasks", JSON, nullable=True),
        sa.Column("total_tasks", sa.Integer, default=0),
        sa.Column("completed_tasks", sa.Integer, default=0),
        sa.Column("progress_pct", sa.Numeric(5, 1), default=0),
        sa.Column("mentor_id", sa.String(50), nullable=True),
        sa.Column("mentor_name", sa.String(100), nullable=True),
        sa.Column("ai_generated", sa.Boolean, default=False),
        sa.Column("ai_reasoning", sa.Text, nullable=True),
        sa.Column("started_at", sa.Date, nullable=True),
        sa.Column("completed_at", sa.Date, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 6. employee_wellbeing ──
    op.create_table(
        "employee_wellbeing",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("period", sa.String(7), nullable=False, index=True),
        sa.Column("achievement_score", sa.Integer, default=0),
        sa.Column("belonging_score", sa.Integer, default=0),
        sa.Column("growth_score", sa.Integer, default=0),
        sa.Column("balance_score", sa.Integer, default=0),
        sa.Column("culture_score", sa.Integer, default=0),
        sa.Column("overall_score", sa.Numeric(4, 1), default=0),
        sa.Column("highlights", sa.Text, nullable=True),
        sa.Column("concerns", sa.Text, nullable=True),
        sa.Column("suggestions", sa.Text, nullable=True),
        sa.Column("is_anonymous", sa.Boolean, default=False),
        sa.Column("submitted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("employee_id", "period", name="uq_wellbeing_period"),
    )


def downgrade():
    op.drop_table("employee_wellbeing")
    op.drop_table("employee_growth_plans")
    op.drop_table("employee_milestones")
    op.drop_table("career_paths")
    op.drop_table("employee_skills")
    op.drop_table("skill_definitions")
