"""z70: 影子模式 + 灰度切换 — SaaS渐进替换安全网

5张表：影子会话/影子记录/一致性报告/切换状态/切换事件
5个ENUM：会话状态/记录类型/一致性等级/切换阶段/切换模块

Revision ID: z70_shadow_mode_cutover
Revises: z69_data_fusion_engine
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "z70_shadow_mode_cutover"
down_revision = "z69_data_fusion_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUMs ─────────────────────────────────────────────────────────────

    shadow_session_status = sa.Enum(
        "active", "paused", "validating", "ready", "completed", "terminated",
        name="shadow_session_status_enum",
    )
    shadow_session_status.create(op.get_bind(), checkfirst=True)

    shadow_record_type = sa.Enum(
        "order", "inventory", "payment", "member_points", "schedule", "purchase",
        name="shadow_record_type_enum",
    )
    shadow_record_type.create(op.get_bind(), checkfirst=True)

    consistency_level = sa.Enum(
        "perfect", "acceptable", "warning", "critical",
        name="consistency_level_enum",
    )
    consistency_level.create(op.get_bind(), checkfirst=True)

    cutover_phase = sa.Enum(
        "shadow", "canary", "primary", "sole",
        name="cutover_phase_enum",
    )
    cutover_phase.create(op.get_bind(), checkfirst=True)

    cutover_module = sa.Enum(
        "analytics", "management", "operations", "finance",
        name="cutover_module_enum",
    )
    cutover_module.create(op.get_bind(), checkfirst=True)

    # ── shadow_sessions ───────────────────────────────────────────────────

    op.create_table(
        "shadow_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("status", shadow_session_status, nullable=False, server_default="active"),
        sa.Column("modules", JSON, nullable=False, server_default='["order","inventory"]'),
        sa.Column("auto_validate", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consistent_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inconsistent_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consistency_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("consecutive_pass_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_pass_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_shadow_session_store", "shadow_sessions", ["store_id", "source_system"])
    op.create_index("idx_shadow_session_status", "shadow_sessions", ["status"])

    # ── shadow_records ────────────────────────────────────────────────────

    op.create_table(
        "shadow_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("record_type", shadow_record_type, nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("source_data", JSON, nullable=True),
        sa.Column("source_amount_fen", sa.Integer(), nullable=True),
        sa.Column("shadow_data", JSON, nullable=True),
        sa.Column("shadow_amount_fen", sa.Integer(), nullable=True),
        sa.Column("is_consistent", sa.Boolean(), nullable=True),
        sa.Column("diff_fields", JSON, nullable=True),
        sa.Column("diff_amount_fen", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("compared_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_shadow_record_session", "shadow_records", ["session_id"])
    op.create_index("idx_shadow_record_source", "shadow_records", ["source_system", "source_id"])
    op.create_index("idx_shadow_record_consistent", "shadow_records", ["is_consistent"])
    op.create_index("idx_shadow_record_created", "shadow_records", ["created_at"])

    # ── consistency_reports ────────────────────────────────────────────────

    op.create_table(
        "consistency_reports",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("report_date", sa.DateTime(), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False, server_default="daily"),
        sa.Column("level", consistency_level, nullable=False, server_default="warning"),
        sa.Column("total_compared", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consistent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inconsistent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consistency_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("order_consistency_rate", sa.Float(), nullable=True),
        sa.Column("inventory_consistency_rate", sa.Float(), nullable=True),
        sa.Column("payment_consistency_rate", sa.Float(), nullable=True),
        sa.Column("total_diff_amount_fen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_diffs", JSON, nullable=True),
        sa.Column("recommendations", JSON, nullable=True),
        sa.Column("is_pass", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_consistency_session_date", "consistency_reports", ["session_id", "report_date"])
    op.create_index("idx_consistency_level", "consistency_reports", ["level"])

    # ── cutover_states ────────────────────────────────────────────────────

    op.create_table(
        "cutover_states",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("module", cutover_module, nullable=False),
        sa.Column("phase", cutover_phase, nullable=False, server_default="shadow"),
        sa.Column("previous_phase", cutover_phase, nullable=True),
        sa.Column("shadow_pass_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required_pass_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("health_gate_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("canary_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_transition_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cutover_store_module", "cutover_states",
                    ["store_id", "module"], unique=True)
    op.create_index("idx_cutover_phase", "cutover_states", ["phase"])
    op.create_index("idx_cutover_brand", "cutover_states", ["brand_id"])

    # ── cutover_events ────────────────────────────────────────────────────

    op.create_table(
        "cutover_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("cutover_state_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("module", cutover_module, nullable=False),
        sa.Column("from_phase", cutover_phase, nullable=False),
        sa.Column("to_phase", cutover_phase, nullable=False),
        sa.Column("trigger", sa.String(50), nullable=False),
        sa.Column("operator", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("health_snapshot", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cutover_event_state", "cutover_events", ["cutover_state_id"])
    op.create_index("idx_cutover_event_store", "cutover_events", ["store_id"])
    op.create_index("idx_cutover_event_created", "cutover_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("cutover_events")
    op.drop_table("cutover_states")
    op.drop_table("consistency_reports")
    op.drop_table("shadow_records")
    op.drop_table("shadow_sessions")

    for enum_name in [
        "cutover_module_enum",
        "cutover_phase_enum",
        "consistency_level_enum",
        "shadow_record_type_enum",
        "shadow_session_status_enum",
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
