"""z67: 屯象OS 连锁餐饮行业知识库 — 三库 + 菜品知识库 + 行业字典

创建 17 张表:
  BOM配方与工艺库(7): kb_bom_recipes, kb_bom_recipe_items,
    kb_bom_recipe_process_steps, kb_bom_recipe_serving_standards,
    kb_bom_recipe_storage_rules, kb_bom_recipe_versions, kb_bom_recipe_cost_calcs
  成本结构基准库(6): kb_cost_benchmarks, kb_cost_benchmark_items,
    kb_cost_benchmark_versions, kb_cost_store_daily_facts,
    kb_cost_dish_daily_facts, kb_cost_warning_records
  定价策略与折扣规则库(6): kb_pricing_strategies, kb_pricing_dish_rules,
    kb_pricing_strategy_versions, kb_promotion_rules,
    kb_coupon_templates, kb_pricing_execution_snapshots
  菜品知识库(7): kb_dish_knowledge, kb_dish_recipe_versions,
    kb_dish_recipe_ingredients, kb_industry_ingredient_masters,
    kb_dish_knowledge_nutrition, kb_dish_knowledge_operation_profiles,
    kb_dish_knowledge_taxonomy_tags
  行业字典(1): kb_industry_dictionaries

Revision ID: z67_knowledge_base_three_libraries
Revises: z66_fix_org_permissions_uuid
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY


revision = "z67_knowledge_base_three_libraries"
down_revision = "z66_fix_org_permissions_uuid"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """幂等检查：表是否已存在。"""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    # ── 1. BOM 配方与工艺库 ──

    if not _table_exists("kb_bom_recipes"):
        op.create_table(
            "kb_bom_recipes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("recipe_code", sa.String(64), nullable=False),
            sa.Column("recipe_name", sa.String(128), nullable=False),
            sa.Column("recipe_alias", sa.String(128)),
            sa.Column("recipe_type", sa.String(32), nullable=False),
            sa.Column("recipe_level", sa.String(32), nullable=False),
            sa.Column("brand_id", UUID(as_uuid=True)),
            sa.Column("org_id", UUID(as_uuid=True)),
            sa.Column("category_id", UUID(as_uuid=True)),
            sa.Column("cuisine_type", sa.String(64)),
            sa.Column("dish_type", sa.String(64)),
            sa.Column("channel_scope", sa.String(32), nullable=False, server_default="all"),
            sa.Column("applicable_store_type", sa.String(32)),
            sa.Column("output_qty", sa.Numeric(12, 3), nullable=False, server_default="1"),
            sa.Column("output_unit", sa.String(32), nullable=False),
            sa.Column("portion_qty", sa.Numeric(12, 3)),
            sa.Column("portion_unit", sa.String(32)),
            sa.Column("standard_cost", sa.Numeric(12, 2)),
            sa.Column("estimated_cost", sa.Numeric(12, 2)),
            sa.Column("version_no", sa.Integer, nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("effective_from", sa.DateTime),
            sa.Column("effective_to", sa.DateTime),
            sa.Column("owner_dept_id", UUID(as_uuid=True)),
            sa.Column("owner_user_id", UUID(as_uuid=True)),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "recipe_code", name="uq_kb_bom_recipe_code"),
        )
        op.create_index("ix_kb_bom_recipe_status", "kb_bom_recipes", ["tenant_id", "status"])
        op.create_index("ix_kb_bom_recipe_brand", "kb_bom_recipes", ["tenant_id", "brand_id"])

    if not _table_exists("kb_bom_recipe_items"):
        op.create_table(
            "kb_bom_recipe_items",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("kb_bom_recipes.id"), nullable=False),
            sa.Column("line_no", sa.Integer, nullable=False),
            sa.Column("material_id", UUID(as_uuid=True)),
            sa.Column("material_code", sa.String(64), nullable=False),
            sa.Column("material_name", sa.String(128), nullable=False),
            sa.Column("material_type", sa.String(32), nullable=False),
            sa.Column("usage_stage", sa.String(32)),
            sa.Column("qty_ap", sa.Numeric(12, 3)),
            sa.Column("qty_ep", sa.Numeric(12, 3)),
            sa.Column("base_unit", sa.String(32), nullable=False),
            sa.Column("loss_rate_trim", sa.Numeric(8, 4)),
            sa.Column("loss_rate_cook", sa.Numeric(8, 4)),
            sa.Column("net_qty", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit_cost", sa.Numeric(12, 4)),
            sa.Column("line_cost", sa.Numeric(12, 2)),
            sa.Column("substitute_group_code", sa.String(64)),
            sa.Column("is_optional", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("is_key_material", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("allergen_tags", sa.String(255)),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_bom_item_recipe", "kb_bom_recipe_items", ["recipe_id", "sort_order"])

    if not _table_exists("kb_bom_recipe_process_steps"):
        op.create_table(
            "kb_bom_recipe_process_steps",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("kb_bom_recipes.id"), nullable=False),
            sa.Column("line_no", sa.Integer, nullable=False),
            sa.Column("process_stage", sa.String(32), nullable=False),
            sa.Column("step_name", sa.String(128), nullable=False),
            sa.Column("step_desc", sa.Text),
            sa.Column("action_standard", sa.Text),
            sa.Column("equipment_id", UUID(as_uuid=True)),
            sa.Column("equipment_name", sa.String(128)),
            sa.Column("tool_name", sa.String(128)),
            sa.Column("target_temp", sa.Numeric(8, 2)),
            sa.Column("temp_unit", sa.String(16)),
            sa.Column("target_time_sec", sa.Integer),
            sa.Column("fire_level", sa.String(32)),
            sa.Column("speed_level", sa.String(32)),
            sa.Column("qc_point", sa.Text),
            sa.Column("is_ccp", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("ccp_limit", sa.String(255)),
            sa.Column("deviation_action", sa.Text),
            sa.Column("media_url", sa.String(500)),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_bom_process_recipe", "kb_bom_recipe_process_steps", ["recipe_id", "sort_order"])

    if not _table_exists("kb_bom_recipe_serving_standards"):
        op.create_table(
            "kb_bom_recipe_serving_standards",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("kb_bom_recipes.id"), nullable=False, unique=True),
            sa.Column("portion_weight", sa.Numeric(12, 3)),
            sa.Column("portion_count", sa.Numeric(12, 3)),
            sa.Column("serving_temp", sa.Numeric(8, 2)),
            sa.Column("plating_desc", sa.Text),
            sa.Column("garnish_rule", sa.Text),
            sa.Column("container_type", sa.String(64)),
            sa.Column("sensory_color", sa.String(255)),
            sa.Column("sensory_aroma", sa.String(255)),
            sa.Column("sensory_texture", sa.String(255)),
            sa.Column("standard_image_url", sa.String(500)),
            sa.Column("remark", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("kb_bom_recipe_storage_rules"):
        op.create_table(
            "kb_bom_recipe_storage_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("kb_bom_recipes.id"), nullable=False, unique=True),
            sa.Column("storage_temp_min", sa.Numeric(8, 2)),
            sa.Column("storage_temp_max", sa.Numeric(8, 2)),
            sa.Column("shelf_life_hours", sa.Integer),
            sa.Column("hold_time_minutes", sa.Integer),
            sa.Column("thaw_rule", sa.Text),
            sa.Column("reheat_rule", sa.Text),
            sa.Column("discard_rule", sa.Text),
            sa.Column("batch_size", sa.Numeric(12, 3)),
            sa.Column("prep_window", sa.String(128)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("kb_bom_recipe_versions"):
        op.create_table(
            "kb_bom_recipe_versions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("kb_bom_recipes.id"), nullable=False, index=True),
            sa.Column("version_no", sa.Integer, nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("snapshot_json", sa.JSON, nullable=False),
            sa.Column("change_summary", sa.Text),
            sa.Column("submitted_by", UUID(as_uuid=True)),
            sa.Column("submitted_at", sa.DateTime),
            sa.Column("reviewed_by", UUID(as_uuid=True)),
            sa.Column("reviewed_at", sa.DateTime),
            sa.Column("published_by", UUID(as_uuid=True)),
            sa.Column("published_at", sa.DateTime),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("recipe_id", "version_no", name="uq_kb_bom_version"),
        )

    if not _table_exists("kb_bom_recipe_cost_calcs"):
        op.create_table(
            "kb_bom_recipe_cost_calcs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True), sa.ForeignKey("kb_bom_recipes.id"), nullable=False, index=True),
            sa.Column("version_no", sa.Integer, nullable=False),
            sa.Column("material_cost", sa.Numeric(12, 2)),
            sa.Column("seasoning_cost", sa.Numeric(12, 2)),
            sa.Column("packaging_cost", sa.Numeric(12, 2)),
            sa.Column("process_cost", sa.Numeric(12, 2)),
            sa.Column("total_std_cost", sa.Numeric(12, 2)),
            sa.Column("output_qty", sa.Numeric(12, 3)),
            sa.Column("cost_per_portion", sa.Numeric(12, 2)),
            sa.Column("calc_time", sa.DateTime),
            sa.Column("calc_snapshot", sa.JSON),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )

    # ── 2. 成本结构基准库 ──

    if not _table_exists("kb_cost_benchmarks"):
        op.create_table(
            "kb_cost_benchmarks",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("benchmark_code", sa.String(64), nullable=False),
            sa.Column("benchmark_name", sa.String(128), nullable=False),
            sa.Column("benchmark_scope", sa.String(32), nullable=False),
            sa.Column("business_type", sa.String(64)),
            sa.Column("brand_id", UUID(as_uuid=True)),
            sa.Column("store_id", UUID(as_uuid=True)),
            sa.Column("channel_type", sa.String(32)),
            sa.Column("version_no", sa.Integer, nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("effective_from", sa.DateTime),
            sa.Column("effective_to", sa.DateTime),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "benchmark_code", name="uq_kb_cost_benchmark_code"),
        )
        op.create_index("ix_kb_cost_bm_scope", "kb_cost_benchmarks", ["tenant_id", "benchmark_scope"])

    if not _table_exists("kb_cost_benchmark_items"):
        op.create_table(
            "kb_cost_benchmark_items",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("benchmark_id", UUID(as_uuid=True), sa.ForeignKey("kb_cost_benchmarks.id"), nullable=False),
            sa.Column("line_no", sa.Integer, nullable=False),
            sa.Column("cost_category_lv1", sa.String(64), nullable=False),
            sa.Column("cost_category_lv2", sa.String(64)),
            sa.Column("basis_type", sa.String(32), nullable=False, server_default="ratio"),
            sa.Column("target_ratio", sa.Numeric(8, 4)),
            sa.Column("target_amount", sa.Numeric(14, 2)),
            sa.Column("warning_ratio_yellow", sa.Numeric(8, 4)),
            sa.Column("warning_ratio_red", sa.Numeric(8, 4)),
            sa.Column("industry_p25", sa.Numeric(8, 4)),
            sa.Column("industry_p50", sa.Numeric(8, 4)),
            sa.Column("industry_p75", sa.Numeric(8, 4)),
            sa.Column("industry_p90", sa.Numeric(8, 4)),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_cost_bm_item_bm", "kb_cost_benchmark_items", ["benchmark_id", "line_no"])

    if not _table_exists("kb_cost_benchmark_versions"):
        op.create_table(
            "kb_cost_benchmark_versions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("benchmark_id", UUID(as_uuid=True), sa.ForeignKey("kb_cost_benchmarks.id"), nullable=False, index=True),
            sa.Column("version_no", sa.Integer, nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("snapshot_json", sa.JSON, nullable=False),
            sa.Column("change_summary", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("benchmark_id", "version_no", name="uq_kb_cost_bm_version"),
        )

    if not _table_exists("kb_cost_store_daily_facts"):
        op.create_table(
            "kb_cost_store_daily_facts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("store_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("biz_date", sa.Date, nullable=False),
            sa.Column("revenue_total", sa.Numeric(14, 2)),
            sa.Column("cogs_food", sa.Numeric(14, 2)),
            sa.Column("cogs_packaging", sa.Numeric(14, 2)),
            sa.Column("cogs_beverage", sa.Numeric(14, 2)),
            sa.Column("cogs_seasoning", sa.Numeric(14, 2)),
            sa.Column("labor_cost", sa.Numeric(14, 2)),
            sa.Column("rent_cost", sa.Numeric(14, 2)),
            sa.Column("utility_cost", sa.Numeric(14, 2)),
            sa.Column("platform_commission", sa.Numeric(14, 2)),
            sa.Column("payment_fee", sa.Numeric(14, 2)),
            sa.Column("marketing_cost", sa.Numeric(14, 2)),
            sa.Column("waste_cost", sa.Numeric(14, 2)),
            sa.Column("prime_cost", sa.Numeric(14, 2)),
            sa.Column("prime_cost_ratio", sa.Numeric(8, 4)),
            sa.Column("food_cost_ratio", sa.Numeric(8, 4)),
            sa.Column("labor_cost_ratio", sa.Numeric(8, 4)),
            sa.Column("op_profit", sa.Numeric(14, 2)),
            sa.Column("op_profit_ratio", sa.Numeric(8, 4)),
            sa.Column("calc_status", sa.String(32), server_default="calculated"),
            sa.Column("detail_json", sa.JSON),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("store_id", "biz_date", name="uq_kb_cost_store_daily"),
        )
        op.create_index("ix_kb_cost_store_daily_date", "kb_cost_store_daily_facts", ["tenant_id", "biz_date"])

    if not _table_exists("kb_cost_dish_daily_facts"):
        op.create_table(
            "kb_cost_dish_daily_facts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("store_id", UUID(as_uuid=True), nullable=False),
            sa.Column("biz_date", sa.Date, nullable=False),
            sa.Column("dish_id", UUID(as_uuid=True), nullable=False),
            sa.Column("recipe_id", UUID(as_uuid=True)),
            sa.Column("sold_qty", sa.Numeric(12, 2)),
            sa.Column("revenue_amount", sa.Numeric(14, 2)),
            sa.Column("std_cost_amount", sa.Numeric(14, 2)),
            sa.Column("actual_cost_amount", sa.Numeric(14, 2)),
            sa.Column("contribution_margin", sa.Numeric(14, 2)),
            sa.Column("contribution_margin_ratio", sa.Numeric(8, 4)),
            sa.Column("food_cost_ratio", sa.Numeric(8, 4)),
            sa.Column("menu_class", sa.String(32)),
            sa.Column("detail_json", sa.JSON),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("store_id", "biz_date", "dish_id", name="uq_kb_cost_dish_daily"),
        )
        op.create_index("ix_kb_cost_dish_daily_date", "kb_cost_dish_daily_facts", ["tenant_id", "biz_date"])

    if not _table_exists("kb_cost_warning_records"):
        op.create_table(
            "kb_cost_warning_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("warning_code", sa.String(64), nullable=False),
            sa.Column("warning_type", sa.String(32), nullable=False),
            sa.Column("scope_type", sa.String(32), nullable=False),
            sa.Column("scope_id", UUID(as_uuid=True), nullable=False),
            sa.Column("biz_date", sa.Date, nullable=False),
            sa.Column("target_value", sa.Numeric(8, 4)),
            sa.Column("actual_value", sa.Numeric(8, 4)),
            sa.Column("deviation", sa.Numeric(8, 4)),
            sa.Column("warning_level", sa.String(16), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="open"),
            sa.Column("resolved_by", UUID(as_uuid=True)),
            sa.Column("resolved_at", sa.DateTime),
            sa.Column("resolution_note", sa.Text),
            sa.Column("detail_json", sa.JSON),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_cost_warning_date", "kb_cost_warning_records", ["tenant_id", "biz_date"])
        op.create_index("ix_kb_cost_warning_status", "kb_cost_warning_records", ["tenant_id", "status"])

    # ── 3. 定价策略与折扣规则库 ──

    if not _table_exists("kb_pricing_strategies"):
        op.create_table(
            "kb_pricing_strategies",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("strategy_code", sa.String(64), nullable=False),
            sa.Column("strategy_name", sa.String(128), nullable=False),
            sa.Column("strategy_type", sa.String(32), nullable=False),
            sa.Column("target_scope", sa.String(32), nullable=False),
            sa.Column("brand_id", UUID(as_uuid=True)),
            sa.Column("store_id", UUID(as_uuid=True)),
            sa.Column("channel_scope", sa.String(32), server_default="all"),
            sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
            sa.Column("version_no", sa.Integer, nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("effective_from", sa.DateTime),
            sa.Column("effective_to", sa.DateTime),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "strategy_code", name="uq_kb_pricing_strategy_code"),
        )
        op.create_index("ix_kb_pricing_strategy_status", "kb_pricing_strategies", ["tenant_id", "status"])

    if not _table_exists("kb_pricing_dish_rules"):
        op.create_table(
            "kb_pricing_dish_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("strategy_id", UUID(as_uuid=True), sa.ForeignKey("kb_pricing_strategies.id"), nullable=False),
            sa.Column("dish_id", UUID(as_uuid=True)),
            sa.Column("recipe_id", UUID(as_uuid=True)),
            sa.Column("price_type", sa.String(32), nullable=False, server_default="standard"),
            sa.Column("base_cost", sa.Numeric(12, 2)),
            sa.Column("target_food_cost_ratio", sa.Numeric(8, 4)),
            sa.Column("target_contribution_margin", sa.Numeric(12, 2)),
            sa.Column("suggested_price", sa.Numeric(12, 2)),
            sa.Column("final_price", sa.Numeric(12, 2)),
            sa.Column("floor_price", sa.Numeric(12, 2)),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_pricing_dish_rule_strategy", "kb_pricing_dish_rules", ["strategy_id"])

    if not _table_exists("kb_pricing_strategy_versions"):
        op.create_table(
            "kb_pricing_strategy_versions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("strategy_id", UUID(as_uuid=True), sa.ForeignKey("kb_pricing_strategies.id"), nullable=False, index=True),
            sa.Column("version_no", sa.Integer, nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("snapshot_json", sa.JSON, nullable=False),
            sa.Column("change_summary", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("strategy_id", "version_no", name="uq_kb_pricing_version"),
        )

    if not _table_exists("kb_promotion_rules"):
        op.create_table(
            "kb_promotion_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("promo_code", sa.String(64), nullable=False),
            sa.Column("promo_name", sa.String(128), nullable=False),
            sa.Column("promo_type", sa.String(32), nullable=False),
            sa.Column("target_scope", sa.String(32)),
            sa.Column("trigger_condition_json", sa.JSON),
            sa.Column("benefit_rule_json", sa.JSON),
            sa.Column("stackable_flag", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("exclusive_group_code", sa.String(64)),
            sa.Column("gross_margin_floor", sa.Numeric(8, 4)),
            sa.Column("contribution_floor", sa.Numeric(12, 2)),
            sa.Column("budget_limit", sa.Numeric(14, 2)),
            sa.Column("used_budget", sa.Numeric(14, 2), server_default="0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("effective_from", sa.DateTime),
            sa.Column("effective_to", sa.DateTime),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "promo_code", name="uq_kb_promo_code"),
        )
        op.create_index("ix_kb_promo_status", "kb_promotion_rules", ["tenant_id", "status"])

    if not _table_exists("kb_coupon_templates"):
        op.create_table(
            "kb_coupon_templates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("coupon_code", sa.String(64), nullable=False),
            sa.Column("coupon_name", sa.String(128), nullable=False),
            sa.Column("coupon_type", sa.String(32), nullable=False),
            sa.Column("threshold_amount", sa.Numeric(12, 2)),
            sa.Column("discount_amount", sa.Numeric(12, 2)),
            sa.Column("discount_ratio", sa.Numeric(8, 4)),
            sa.Column("max_discount", sa.Numeric(12, 2)),
            sa.Column("new_customer_only", sa.Boolean, server_default="false"),
            sa.Column("total_quota", sa.Integer),
            sa.Column("issued_count", sa.Integer, server_default="0"),
            sa.Column("valid_days", sa.Integer),
            sa.Column("valid_from", sa.DateTime),
            sa.Column("valid_to", sa.DateTime),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("remark", sa.Text),
            sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_by", UUID(as_uuid=True)),
            sa.Column("updated_by", UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "coupon_code", name="uq_kb_coupon_code"),
        )

    if not _table_exists("kb_pricing_execution_snapshots"):
        op.create_table(
            "kb_pricing_execution_snapshots",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
            sa.Column("store_id", UUID(as_uuid=True), nullable=False),
            sa.Column("biz_date", sa.Date, nullable=False),
            sa.Column("dish_id", UUID(as_uuid=True), nullable=False),
            sa.Column("order_id", UUID(as_uuid=True)),
            sa.Column("channel_type", sa.String(32)),
            sa.Column("base_price", sa.Numeric(12, 2)),
            sa.Column("strategy_price", sa.Numeric(12, 2)),
            sa.Column("promo_price", sa.Numeric(12, 2)),
            sa.Column("coupon_deduction", sa.Numeric(12, 2)),
            sa.Column("final_settlement_price", sa.Numeric(12, 2)),
            sa.Column("matched_strategy_id", UUID(as_uuid=True)),
            sa.Column("matched_promo_id", UUID(as_uuid=True)),
            sa.Column("matched_coupon_id", UUID(as_uuid=True)),
            sa.Column("margin_check_result", sa.String(32)),
            sa.Column("snapshot_json", sa.JSON),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_pricing_exec_date", "kb_pricing_execution_snapshots", ["tenant_id", "biz_date"])
        op.create_index("ix_kb_pricing_exec_store", "kb_pricing_execution_snapshots", ["store_id", "biz_date"])

    # ── 4. 菜品知识库 ──

    if not _table_exists("kb_dish_knowledge"):
        op.create_table(
            "kb_dish_knowledge",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("dish_code", sa.String(64), nullable=False, unique=True),
            sa.Column("dish_name_zh", sa.String(128), nullable=False),
            sa.Column("dish_name_en", sa.String(200)),
            sa.Column("alias_names", ARRAY(sa.String)),
            sa.Column("dish_status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("launch_type", sa.String(32), server_default="listed"),
            sa.Column("cuisine_country", sa.String(64), server_default="中国"),
            sa.Column("cuisine_region", sa.String(64), nullable=False),
            sa.Column("category_l1", sa.String(64), nullable=False),
            sa.Column("category_l2", sa.String(64)),
            sa.Column("category_l3", sa.String(64)),
            sa.Column("main_ingredient_group", sa.String(64)),
            sa.Column("dish_type", sa.String(32), server_default="a_la_carte"),
            sa.Column("serving_temp", sa.String(16)),
            sa.Column("serving_size_type", sa.String(16)),
            sa.Column("cooking_method", sa.String(64)),
            sa.Column("taste_profile_primary", sa.String(64)),
            sa.Column("taste_profile_secondary", ARRAY(sa.String)),
            sa.Column("color_profile", sa.String(64)),
            sa.Column("texture_profile", ARRAY(sa.String)),
            sa.Column("spicy_level", sa.Integer),
            sa.Column("plating_style", sa.String(32)),
            sa.Column("is_signature", sa.Boolean, server_default="false"),
            sa.Column("is_classic", sa.Boolean, server_default="false"),
            sa.Column("is_chain_friendly", sa.Boolean, server_default="true"),
            sa.Column("standardization_level", sa.String(1)),
            sa.Column("prep_complexity", sa.String(1)),
            sa.Column("dine_in_fit", sa.Integer),
            sa.Column("takeaway_fit", sa.Integer),
            sa.Column("catering_fit", sa.Integer),
            sa.Column("breakfast_fit", sa.Integer),
            sa.Column("lunch_fit", sa.Integer),
            sa.Column("dinner_fit", sa.Integer),
            sa.Column("supper_fit", sa.Integer),
            sa.Column("seasonality", sa.String(16), server_default="all_year"),
            sa.Column("allergen_flags", ARRAY(sa.String)),
            sa.Column("dietary_flags", ARRAY(sa.String)),
            sa.Column("culture_story", sa.Text),
            sa.Column("search_keywords", ARRAY(sa.String)),
            sa.Column("embedding_text", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_dish_knowledge_cuisine", "kb_dish_knowledge", ["cuisine_region"])
        op.create_index("ix_kb_dish_knowledge_category", "kb_dish_knowledge", ["category_l1", "category_l2"])

    if not _table_exists("kb_dish_recipe_versions"):
        op.create_table(
            "kb_dish_recipe_versions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("dish_knowledge_id", UUID(as_uuid=True), sa.ForeignKey("kb_dish_knowledge.id"), nullable=False, index=True),
            sa.Column("version_no", sa.String(16), nullable=False),
            sa.Column("version_status", sa.String(32), nullable=False, server_default="current"),
            sa.Column("serving_count", sa.Numeric(8, 2), server_default="1"),
            sa.Column("net_weight_g", sa.Numeric(12, 2)),
            sa.Column("gross_weight_g", sa.Numeric(12, 2)),
            sa.Column("yield_rate", sa.Numeric(8, 4)),
            sa.Column("prep_time_min", sa.Integer),
            sa.Column("cook_time_min", sa.Integer),
            sa.Column("total_time_min", sa.Integer),
            sa.Column("wok_station_type", sa.String(64)),
            sa.Column("equipment_required", ARRAY(sa.String)),
            sa.Column("step_text", sa.Text),
            sa.Column("critical_control_points", ARRAY(sa.String)),
            sa.Column("plating_standard", sa.Text),
            sa.Column("garnish_standard", sa.Text),
            sa.Column("taste_target", sa.Text),
            sa.Column("photo_ref", sa.String(500)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("dish_knowledge_id", "version_no", name="uq_kb_dish_recipe_version"),
        )

    if not _table_exists("kb_dish_recipe_ingredients"):
        op.create_table(
            "kb_dish_recipe_ingredients",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("recipe_version_id", UUID(as_uuid=True), sa.ForeignKey("kb_dish_recipe_versions.id"), nullable=False),
            sa.Column("ingredient_id", UUID(as_uuid=True)),
            sa.Column("ingredient_canonical_name", sa.String(128), nullable=False),
            sa.Column("ingredient_variant_name", sa.String(128)),
            sa.Column("ingredient_role", sa.String(32), nullable=False),
            sa.Column("part_used", sa.String(64)),
            sa.Column("cut_style", sa.String(32)),
            sa.Column("pre_process", sa.String(64)),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit", sa.String(16), nullable=False),
            sa.Column("loss_rate", sa.Numeric(8, 4)),
            sa.Column("substitution_group", sa.String(64)),
            sa.Column("is_optional", sa.Boolean, server_default="false"),
            sa.Column("sort_no", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_dish_recipe_ing_recipe", "kb_dish_recipe_ingredients", ["recipe_version_id", "sort_no"])

    if not _table_exists("kb_industry_ingredient_masters"):
        op.create_table(
            "kb_industry_ingredient_masters",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("ingredient_code", sa.String(64), nullable=False, unique=True),
            sa.Column("ingredient_name_zh", sa.String(128), nullable=False),
            sa.Column("ingredient_name_en", sa.String(128)),
            sa.Column("aliases", ARRAY(sa.String)),
            sa.Column("category_l1", sa.String(64), nullable=False),
            sa.Column("category_l2", sa.String(64)),
            sa.Column("species_source", sa.String(128)),
            sa.Column("default_unit", sa.String(16), nullable=False, server_default="g"),
            sa.Column("storage_type", sa.String(16)),
            sa.Column("shelf_life_rule", sa.String(200)),
            sa.Column("allergen_flag", sa.Boolean, server_default="false"),
            sa.Column("allergen_type", ARRAY(sa.String)),
            sa.Column("dietary_flags", ARRAY(sa.String)),
            sa.Column("cost_grade", sa.String(1)),
            sa.Column("standard_sku_code", sa.String(64)),
            sa.Column("is_active", sa.Boolean, server_default="true"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_industry_ing_category", "kb_industry_ingredient_masters", ["category_l1", "category_l2"])

    if not _table_exists("kb_dish_knowledge_nutrition"):
        op.create_table(
            "kb_dish_knowledge_nutrition",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("dish_knowledge_id", UUID(as_uuid=True), sa.ForeignKey("kb_dish_knowledge.id"), nullable=False, unique=True),
            sa.Column("kcal", sa.Numeric(8, 1)),
            sa.Column("protein_g", sa.Numeric(8, 1)),
            sa.Column("fat_g", sa.Numeric(8, 1)),
            sa.Column("carbs_g", sa.Numeric(8, 1)),
            sa.Column("sodium_mg", sa.Numeric(8, 1)),
            sa.Column("sugar_g", sa.Numeric(8, 1)),
            sa.Column("fiber_g", sa.Numeric(8, 1)),
            sa.Column("nutrition_note", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("kb_dish_knowledge_operation_profiles"):
        op.create_table(
            "kb_dish_knowledge_operation_profiles",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("dish_knowledge_id", UUID(as_uuid=True), sa.ForeignKey("kb_dish_knowledge.id"), nullable=False, unique=True),
            sa.Column("price_band", sa.String(16)),
            sa.Column("food_cost_rate", sa.Numeric(8, 4)),
            sa.Column("gross_margin_rate", sa.Numeric(8, 4)),
            sa.Column("sales_volume_potential", sa.Integer),
            sa.Column("standardization_score", sa.Integer),
            sa.Column("training_difficulty", sa.Integer),
            sa.Column("peak_hour_pressure", sa.Integer),
            sa.Column("pre_make_fit", sa.Integer),
            sa.Column("central_kitchen_fit", sa.Integer),
            sa.Column("menu_role", sa.String(32)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("kb_dish_knowledge_taxonomy_tags"):
        op.create_table(
            "kb_dish_knowledge_taxonomy_tags",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("dish_knowledge_id", UUID(as_uuid=True), sa.ForeignKey("kb_dish_knowledge.id"), nullable=False, index=True),
            sa.Column("tag_type", sa.String(32), nullable=False),
            sa.Column("tag_value", sa.String(128), nullable=False),
            sa.Column("tag_source", sa.String(16), server_default="system"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_kb_dish_tag_type", "kb_dish_knowledge_taxonomy_tags", ["tag_type", "tag_value"])

    # ── 5. 行业字典 ──

    if not _table_exists("kb_industry_dictionaries"):
        op.create_table(
            "kb_industry_dictionaries",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("dict_type", sa.String(32), nullable=False),
            sa.Column("dict_code", sa.String(64), nullable=False),
            sa.Column("dict_name_zh", sa.String(128), nullable=False),
            sa.Column("dict_name_en", sa.String(128)),
            sa.Column("parent_code", sa.String(64)),
            sa.Column("level", sa.Integer, nullable=False, server_default="1"),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("description", sa.Text),
            sa.Column("icon", sa.String(128)),
            sa.Column("extra_json", sa.Text),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("is_system", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("dict_type", "dict_code", name="uq_kb_industry_dict"),
        )
        op.create_index("ix_kb_industry_dict_type", "kb_industry_dictionaries", ["dict_type"])
        op.create_index("ix_kb_industry_dict_parent", "kb_industry_dictionaries", ["dict_type", "parent_code"])


def downgrade() -> None:
    tables = [
        "kb_dish_knowledge_taxonomy_tags",
        "kb_dish_knowledge_operation_profiles",
        "kb_dish_knowledge_nutrition",
        "kb_dish_recipe_ingredients",
        "kb_dish_recipe_versions",
        "kb_industry_ingredient_masters",
        "kb_dish_knowledge",
        "kb_pricing_execution_snapshots",
        "kb_coupon_templates",
        "kb_promotion_rules",
        "kb_pricing_strategy_versions",
        "kb_pricing_dish_rules",
        "kb_pricing_strategies",
        "kb_cost_warning_records",
        "kb_cost_dish_daily_facts",
        "kb_cost_store_daily_facts",
        "kb_cost_benchmark_versions",
        "kb_cost_benchmark_items",
        "kb_cost_benchmarks",
        "kb_bom_recipe_cost_calcs",
        "kb_bom_recipe_versions",
        "kb_bom_recipe_storage_rules",
        "kb_bom_recipe_serving_standards",
        "kb_bom_recipe_process_steps",
        "kb_bom_recipe_items",
        "kb_bom_recipes",
        "kb_industry_dictionaries",
    ]
    for t in tables:
        op.drop_table(t)
