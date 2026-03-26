"""z71: 活海鲜养殖 + 菜品做法变体 + 菜品规格

新增表：
  - aquarium_tanks          — 鱼缸/水族箱主数据
  - aquarium_water_metrics  — 水质指标记录
  - live_seafood_batches    — 活海鲜入缸批次
  - seafood_mortality_logs  — 死亡/损耗记录
  - aquarium_inspections    — 每日巡检记录
  - dish_method_variants    — 菜品做法变体（做法→工位→BOM）
  - dish_specifications     — 菜品多规格定价

Revision ID: z71_aquarium_dish_variants
Revises: z70_shadow_mode_cutover
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z71_aquarium_dish_variants"
down_revision = "z70_shadow_mode_cutover"


def upgrade() -> None:
    # ── aquarium_tanks ────────────────────────────────────────────────────
    op.create_table(
        "aquarium_tanks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tank_type", sa.String(20), nullable=False, server_default="saltwater"),
        sa.Column("capacity_liters", sa.Float, nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column("current_species", sa.String(200)),
        sa.Column("equipment_info", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── aquarium_water_metrics ────────────────────────────────────────────
    op.create_table(
        "aquarium_water_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tank_id", UUID(as_uuid=True), sa.ForeignKey("aquarium_tanks.id"), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("temperature", sa.Float),
        sa.Column("ph", sa.Float),
        sa.Column("dissolved_oxygen", sa.Float),
        sa.Column("salinity", sa.Float),
        sa.Column("ammonia", sa.Float),
        sa.Column("nitrite", sa.Float),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("recorded_by", sa.String(100)),
        sa.Column("recorded_at", sa.DateTime, nullable=False, index=True),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── live_seafood_batches ──────────────────────────────────────────────
    op.create_table(
        "live_seafood_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tank_id", UUID(as_uuid=True), sa.ForeignKey("aquarium_tanks.id"), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("species", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50)),
        sa.Column("entry_date", sa.DateTime, nullable=False, index=True),
        sa.Column("initial_quantity", sa.Integer, nullable=False),
        sa.Column("initial_weight_g", sa.Integer),
        sa.Column("unit", sa.String(20), server_default="只"),
        sa.Column("current_quantity", sa.Integer, nullable=False),
        sa.Column("current_weight_g", sa.Integer),
        sa.Column("unit_cost_fen", sa.Integer, nullable=False),
        sa.Column("total_cost_fen", sa.Integer, nullable=False),
        sa.Column("cost_unit", sa.String(20), server_default="只"),
        sa.Column("supplier_name", sa.String(100)),
        sa.Column("supplier_contact", sa.String(100)),
        sa.Column("purchase_order_id", sa.String(100)),
        sa.Column("is_active", sa.String(10), nullable=False, server_default="true"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── seafood_mortality_logs ────────────────────────────────────────────
    op.create_table(
        "seafood_mortality_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True), sa.ForeignKey("live_seafood_batches.id"), nullable=False, index=True),
        sa.Column("tank_id", UUID(as_uuid=True), sa.ForeignKey("aquarium_tanks.id"), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("dead_quantity", sa.Integer, nullable=False),
        sa.Column("dead_weight_g", sa.Integer),
        sa.Column("reason", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("disposal", sa.String(20), nullable=False, server_default="discard"),
        sa.Column("loss_amount_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("recorded_by", sa.String(100)),
        sa.Column("recorded_at", sa.DateTime, nullable=False, index=True),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── aquarium_inspections ──────────────────────────────────────────────
    op.create_table(
        "aquarium_inspections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tank_id", UUID(as_uuid=True), sa.ForeignKey("aquarium_tanks.id"), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("inspector", sa.String(100), nullable=False),
        sa.Column("inspection_date", sa.Date, nullable=False, index=True),
        sa.Column("inspection_time", sa.DateTime, nullable=False),
        sa.Column("result", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("tank_cleanliness", sa.Integer),
        sa.Column("fish_activity", sa.Integer),
        sa.Column("equipment_status", sa.Integer),
        sa.Column("abnormal_description", sa.Text),
        sa.Column("action_taken", sa.Text),
        sa.Column("image_urls", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── dish_method_variants ──────────────────────────────────────────────
    op.create_table(
        "dish_method_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dish_id", UUID(as_uuid=True), sa.ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("method_name", sa.String(50), nullable=False),
        sa.Column("kitchen_station", sa.String(50), nullable=False),
        sa.Column("prep_time_minutes", sa.Integer, nullable=False, server_default="10"),
        sa.Column("bom_template_id", UUID(as_uuid=True), sa.ForeignKey("bom_templates.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("extra_cost_fen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("dish_id", "method_name", name="uq_dish_method_variant"),
    )
    op.create_index("idx_dmv_dish_available", "dish_method_variants", ["dish_id", "is_available"])
    op.create_index("idx_dmv_kitchen_station", "dish_method_variants", ["kitchen_station"])

    # ── dish_specifications ───────────────────────────────────────────────
    op.create_table(
        "dish_specifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dish_id", UUID(as_uuid=True), sa.ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("spec_name", sa.String(50), nullable=False),
        sa.Column("price_fen", sa.Integer, nullable=False),
        sa.Column("cost_fen", sa.Integer, nullable=True),
        sa.Column("bom_multiplier", sa.Numeric(5, 2), nullable=False, server_default="1.00"),
        sa.Column("unit", sa.String(20), nullable=False, server_default="份"),
        sa.Column("min_order_qty", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("dish_id", "spec_name", name="uq_dish_specification"),
    )
    op.create_index("idx_dspec_dish_available", "dish_specifications", ["dish_id", "is_available"])


def downgrade() -> None:
    op.drop_table("dish_specifications")
    op.drop_table("dish_method_variants")
    op.drop_table("aquarium_inspections")
    op.drop_table("seafood_mortality_logs")
    op.drop_table("live_seafood_batches")
    op.drop_table("aquarium_water_metrics")
    op.drop_table("aquarium_tanks")
