"""z69: 数据融合引擎 — 历史数据智能融合 + SaaS渐进替换基础

5张表：融合项目/融合任务/实体映射/数据血缘/冲突记录
5个ENUM：项目状态/任务状态/采集通道/实体类型/冲突仲裁

Revision ID: z69_data_fusion_engine
Revises: z68_mission_journey
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "z69_data_fusion_engine"
down_revision = "z68_mission_journey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUMs ─────────────────────────────────────────────────────────────

    fusion_project_status = sa.Enum(
        "created", "scanning", "importing", "resolving",
        "generating", "completed", "failed", "paused",
        name="fusion_project_status_enum",
    )
    fusion_project_status.create(op.get_bind(), checkfirst=True)

    fusion_task_status = sa.Enum(
        "pending", "running", "completed", "failed", "paused", "cancelled",
        name="fusion_task_status_enum",
    )
    fusion_task_status.create(op.get_bind(), checkfirst=True)

    fusion_task_channel = sa.Enum(
        "api", "file", "db_mirror", "webhook",
        name="fusion_task_channel_enum",
    )
    fusion_task_channel.create(op.get_bind(), checkfirst=True)

    fusion_entity_type = sa.Enum(
        "dish", "ingredient", "customer", "supplier",
        "employee", "order", "store",
        name="fusion_entity_type_enum",
    )
    fusion_entity_type.create(op.get_bind(), checkfirst=True)

    fusion_conflict_resolution = sa.Enum(
        "auto_latest", "auto_primary", "auto_highest", "manual", "pending",
        name="fusion_conflict_resolution_enum",
    )
    fusion_conflict_resolution.create(op.get_bind(), checkfirst=True)

    # ── fusion_projects ───────────────────────────────────────────────────

    op.create_table(
        "fusion_projects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", fusion_project_status, nullable=False, server_default="created"),
        sa.Column("source_systems", JSON, nullable=False, server_default="[]"),
        sa.Column("data_start_date", sa.DateTime(), nullable=True),
        sa.Column("data_end_date", sa.DateTime(), nullable=True),
        sa.Column("entity_types", JSON, nullable=False,
                  server_default='["order","dish","customer","ingredient"]'),
        sa.Column("total_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_records_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_entities_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_conflicts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("knowledge_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("health_report_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fusion_project_brand", "fusion_projects", ["brand_id"])
    op.create_index("idx_fusion_project_status", "fusion_projects", ["status"])

    # ── fusion_tasks ──────────────────────────────────────────────────────

    op.create_table(
        "fusion_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=True),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_category", sa.String(50), nullable=False),
        sa.Column("channel", fusion_task_channel, nullable=False, server_default="api"),
        sa.Column("entity_type", fusion_entity_type, nullable=False),
        sa.Column("status", fusion_task_status, nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_range_start", sa.DateTime(), nullable=True),
        sa.Column("date_range_end", sa.DateTime(), nullable=True),
        sa.Column("last_cursor", sa.String(500), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("total_estimated", sa.Integer(), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("error_details", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fusion_task_project", "fusion_tasks", ["project_id"])
    op.create_index("idx_fusion_task_status", "fusion_tasks", ["status"])
    op.create_index("idx_fusion_task_store_system", "fusion_tasks", ["store_id", "source_system"])

    # ── fusion_entity_maps ────────────────────────────────────────────────

    op.create_table(
        "fusion_entity_maps",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=True),
        sa.Column("entity_type", fusion_entity_type, nullable=False),
        sa.Column("canonical_id", sa.String(36), nullable=False),
        sa.Column("canonical_name", sa.String(200), nullable=True),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("external_name", sa.String(200), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("match_method", sa.String(50), nullable=True),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("external_metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fusion_entity_canonical", "fusion_entity_maps",
                    ["entity_type", "canonical_id"])
    op.create_index("idx_fusion_entity_external", "fusion_entity_maps",
                    ["source_system", "external_id"])
    op.create_index("idx_fusion_entity_brand_type", "fusion_entity_maps",
                    ["brand_id", "entity_type"])
    op.create_index("idx_fusion_entity_confidence", "fusion_entity_maps", ["confidence"])

    # ── fusion_provenances ────────────────────────────────────────────────

    op.create_table(
        "fusion_provenances",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("target_table", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("target_field", sa.String(100), nullable=True),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_table", sa.String(200), nullable=True),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("source_field", sa.String(100), nullable=True),
        sa.Column("fusion_task_id", sa.String(36), nullable=True),
        sa.Column("imported_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fusion_prov_target", "fusion_provenances",
                    ["target_table", "target_id"])
    op.create_index("idx_fusion_prov_source", "fusion_provenances",
                    ["source_system", "source_id"])
    op.create_index("idx_fusion_prov_task", "fusion_provenances", ["fusion_task_id"])

    # ── fusion_conflicts ──────────────────────────────────────────────────

    op.create_table(
        "fusion_conflicts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=True),
        sa.Column("entity_type", fusion_entity_type, nullable=False),
        sa.Column("canonical_id", sa.String(36), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("source_a_system", sa.String(50), nullable=False),
        sa.Column("source_a_value", sa.Text(), nullable=True),
        sa.Column("source_a_timestamp", sa.DateTime(), nullable=True),
        sa.Column("source_b_system", sa.String(50), nullable=False),
        sa.Column("source_b_value", sa.Text(), nullable=True),
        sa.Column("source_b_timestamp", sa.DateTime(), nullable=True),
        sa.Column("resolution", fusion_conflict_resolution, nullable=False,
                  server_default="pending"),
        sa.Column("resolved_value", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("impact_amount_fen", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fusion_conflict_entity", "fusion_conflicts",
                    ["entity_type", "canonical_id"])
    op.create_index("idx_fusion_conflict_resolution", "fusion_conflicts", ["resolution"])
    op.create_index("idx_fusion_conflict_brand", "fusion_conflicts", ["brand_id"])


def downgrade() -> None:
    op.drop_table("fusion_conflicts")
    op.drop_table("fusion_provenances")
    op.drop_table("fusion_entity_maps")
    op.drop_table("fusion_tasks")
    op.drop_table("fusion_projects")

    for enum_name in [
        "fusion_conflict_resolution_enum",
        "fusion_entity_type_enum",
        "fusion_task_channel_enum",
        "fusion_task_status_enum",
        "fusion_project_status_enum",
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
