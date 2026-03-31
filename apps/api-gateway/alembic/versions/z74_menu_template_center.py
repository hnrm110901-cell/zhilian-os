"""z74: 集团菜单模板中心 — MenuTemplate/MenuTemplateItem/StoreMenuDeployment/StoreDishOverride

NOTE: down_revision 设为 z72（由 linter 自动校正），部署时需要按
      z72->z73->z74 顺序执行，或使用 alembic merge 解决多头问题。

Revision ID: z74
Revises: z72
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "z74"
down_revision = "z72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. menu_templates — 集团菜单模板
    op.create_table(
        "menu_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", name="menu_template_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "apply_scope",
            sa.Enum("all_stores", "selected_stores", name="menu_template_apply_scope"),
            nullable=False,
            server_default="all_stores",
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_menu_template_brand_id", "menu_templates", ["brand_id"])
    op.create_index("idx_menu_template_status", "menu_templates", ["status"])

    # 2. menu_template_items — 模板菜品条目
    op.create_table(
        "menu_template_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("menu_templates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("dish_master_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("category", sa.String(100), nullable=False, server_default=""),
        sa.Column("base_price_fen", sa.Integer, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("allow_store_adjust", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_adjust_rate", sa.Float, nullable=False, server_default="0.2"),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_menu_template_item_template_id", "menu_template_items", ["template_id"])
    op.create_index("idx_menu_template_item_dish_master_id", "menu_template_items", ["dish_master_id"])

    # 3. store_menu_deployments — 门店部署记录
    op.create_table(
        "store_menu_deployments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("menu_templates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("deployed_at", sa.DateTime, nullable=False),
        sa.Column("deployed_by", UUID(as_uuid=True), nullable=False),
        sa.Column("override_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "template_id", name="uq_store_menu_deployment"),
    )
    op.create_index("idx_store_menu_deployment_store_id", "store_menu_deployments", ["store_id"])
    op.create_index("idx_store_menu_deployment_template_id", "store_menu_deployments", ["template_id"])

    # 4. store_dish_overrides — 门店菜品个性化
    op.create_table(
        "store_dish_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "template_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("menu_template_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("custom_price_fen", sa.Integer, nullable=True),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("custom_name", sa.String(200), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "template_item_id", name="uq_store_dish_override"),
    )
    op.create_index("idx_store_dish_override_store_id", "store_dish_overrides", ["store_id"])
    op.create_index("idx_store_dish_override_template_item_id", "store_dish_overrides", ["template_item_id"])

    # RLS 策略（store_id 字段适用门店级别隔离）
    for tbl in ("store_menu_deployments", "store_dish_overrides"):
        conn.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {tbl} "
            f"USING ("
            f"  current_setting('app.current_tenant', TRUE) IS NOT NULL"
            f"  AND store_id::text = current_setting('app.current_tenant', TRUE)"
            f")"
        ))
        conn.execute(sa.text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    conn = op.get_bind()

    for tbl in ("store_menu_deployments", "store_dish_overrides"):
        conn.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}"))

    op.drop_table("store_dish_overrides")
    op.drop_table("store_menu_deployments")
    op.drop_table("menu_template_items")
    op.drop_table("menu_templates")

    # 删除 enum 类型
    op.execute("DROP TYPE IF EXISTS menu_template_status")
    op.execute("DROP TYPE IF EXISTS menu_template_apply_scope")
