"""
r05 L2 融合层（Fusion Layer）

新建表：
  - ingredient_mappings   规范ID注册中心（canonical entity registry）
  - fusion_audit_log      融合决策不可变审计日志

扩展列：
  - inventory_items  ← external_ids, canonical_ingredient_id,
                        fusion_confidence, source_system
  - dishes           ← external_ids
  - stores           ← external_ids
  - waste_events     ← source_system, ingredient_fusion_confidence

Neo4j 约束（注释形式，运维手动执行）：
  CREATE CONSTRAINT ON (m:IngredientMapping) ASSERT m.canonical_id IS UNIQUE;
  CREATE CONSTRAINT ON (s:ExternalSource) ASSERT s.source_key IS UNIQUE;
  CREATE INDEX ON :IngredientMapping(category);
  CREATE INDEX ON :IngredientMapping(fusion_confidence);
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "r05_fusion_layer"
down_revision = "r04_waste_event_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ingredient_mappings（规范ID注册中心）────────────────────────────────
    op.create_table(
        "ingredient_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # 规范标识
        sa.Column("canonical_id", sa.String(50), nullable=False, unique=True),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text), nullable=False,
                  server_default="{}"),
        # 语义属性
        sa.Column("category", sa.String(50)),        # meat / seafood / vegetable / ...
        sa.Column("unit", sa.String(20)),             # kg / piece / bottle / ...
        # 多源映射：{"pinzhi": "123", "meituan": "F789", "tiancai": "M456", "supplier_sku": "SKU-001"}
        sa.Column("external_ids", postgresql.JSONB, nullable=False,
                  server_default="{}"),
        # 多源成本快照：{"pinzhi": {"cost_fen": 3500, "confidence": 0.85, "updated_at": "..."}, ...}
        sa.Column("source_costs", postgresql.JSONB, nullable=False,
                  server_default="{}"),
        # 加权规范成本（分）
        sa.Column("canonical_cost_fen", sa.Integer),
        # 融合元数据
        sa.Column("fusion_confidence", sa.Float, nullable=False,
                  server_default="1.0"),
        sa.Column("fusion_method", sa.String(50)),   # exact_match / fuzzy_name / manual_merge
        # 冲突标记：多源成本或名称严重分歧时置 true
        sa.Column("conflict_flag", sa.Boolean, nullable=False,
                  server_default="false"),
        # 若本记录是从 merge_of 列表中的多个 canonical_id 合并而来
        sa.Column("merge_of", postgresql.ARRAY(sa.String(50)), nullable=False,
                  server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_ingredient_mappings_canonical_id",
                    "ingredient_mappings", ["canonical_id"])
    op.create_index("ix_ingredient_mappings_category",
                    "ingredient_mappings", ["category"])
    op.create_index("ix_ingredient_mappings_conflict",
                    "ingredient_mappings", ["conflict_flag"])
    # GIN 索引加速 external_ids JSONB 查询
    op.execute("""
        CREATE INDEX ix_ingredient_mappings_external_ids
        ON ingredient_mappings USING GIN (external_ids);
    """)

    # ── fusion_audit_log（不可变融合审计日志）──────────────────────────────
    op.create_table(
        "fusion_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type", sa.String(50), nullable=False),   # ingredient / dish / store
        sa.Column("canonical_id", sa.String(50)),
        sa.Column("action", sa.String(50), nullable=False),
        # create_canonical / alias_to_existing / merge / conflict_detected /
        # manual_override / cost_update / split
        sa.Column("source_system", sa.String(50)),
        sa.Column("raw_external_id", sa.String(200)),
        sa.Column("raw_name", sa.String(200)),
        sa.Column("matched_canonical_id", sa.String(50)),  # 命中的规范 ID（alias 时）
        sa.Column("confidence", sa.Float),
        sa.Column("fusion_method", sa.String(50)),
        sa.Column("evidence", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(100)),
    )
    op.create_index("ix_fusion_audit_canonical_id",
                    "fusion_audit_log", ["canonical_id"])
    op.create_index("ix_fusion_audit_source_system",
                    "fusion_audit_log", ["source_system"])
    op.create_index("ix_fusion_audit_created_at",
                    "fusion_audit_log", ["created_at"])

    # ── 扩展 inventory_items ───────────────────────────────────────────────
    op.add_column(
        "inventory_items",
        sa.Column("external_ids", postgresql.JSONB,
                  nullable=False, server_default="{}"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("canonical_ingredient_id", sa.String(50)),
    )
    op.add_column(
        "inventory_items",
        sa.Column("fusion_confidence", sa.Float,
                  nullable=False, server_default="1.0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("source_system", sa.String(50),
                  nullable=False, server_default="manual"),
    )
    op.execute("""
        CREATE INDEX ix_inventory_items_external_ids
        ON inventory_items USING GIN (external_ids);
    """)
    op.create_index("ix_inventory_items_canonical_id",
                    "inventory_items", ["canonical_ingredient_id"])

    # ── 扩展 dishes ───────────────────────────────────────────────────────
    op.add_column(
        "dishes",
        sa.Column("external_ids", postgresql.JSONB,
                  nullable=False, server_default="{}"),
    )
    op.execute("""
        CREATE INDEX ix_dishes_external_ids
        ON dishes USING GIN (external_ids);
    """)

    # ── 扩展 stores ───────────────────────────────────────────────────────
    op.add_column(
        "stores",
        sa.Column("external_ids", postgresql.JSONB,
                  nullable=False, server_default="{}"),
    )
    op.execute("""
        CREATE INDEX ix_stores_external_ids
        ON stores USING GIN (external_ids);
    """)

    # ── 扩展 waste_events ─────────────────────────────────────────────────
    op.add_column(
        "waste_events",
        sa.Column("source_system", sa.String(50),
                  nullable=False, server_default="manual"),
    )
    op.add_column(
        "waste_events",
        sa.Column("ingredient_fusion_confidence", sa.Float,
                  nullable=False, server_default="1.0"),
    )


def downgrade() -> None:
    # waste_events
    op.drop_column("waste_events", "ingredient_fusion_confidence")
    op.drop_column("waste_events", "source_system")

    # stores
    op.execute("DROP INDEX IF EXISTS ix_stores_external_ids;")
    op.drop_column("stores", "external_ids")

    # dishes
    op.execute("DROP INDEX IF EXISTS ix_dishes_external_ids;")
    op.drop_column("dishes", "external_ids")

    # inventory_items
    op.execute("DROP INDEX IF EXISTS ix_inventory_items_external_ids;")
    op.drop_index("ix_inventory_items_canonical_id", "inventory_items")
    op.drop_column("inventory_items", "source_system")
    op.drop_column("inventory_items", "fusion_confidence")
    op.drop_column("inventory_items", "canonical_ingredient_id")
    op.drop_column("inventory_items", "external_ids")

    # fusion_audit_log
    op.drop_index("ix_fusion_audit_created_at", "fusion_audit_log")
    op.drop_index("ix_fusion_audit_source_system", "fusion_audit_log")
    op.drop_index("ix_fusion_audit_canonical_id", "fusion_audit_log")
    op.drop_table("fusion_audit_log")

    # ingredient_mappings
    op.execute("DROP INDEX IF EXISTS ix_ingredient_mappings_external_ids;")
    op.drop_index("ix_ingredient_mappings_conflict", "ingredient_mappings")
    op.drop_index("ix_ingredient_mappings_category", "ingredient_mappings")
    op.drop_index("ix_ingredient_mappings_canonical_id", "ingredient_mappings")
    op.drop_table("ingredient_mappings")
