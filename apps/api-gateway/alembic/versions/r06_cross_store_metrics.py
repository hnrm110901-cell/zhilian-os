"""
r06 L3 跨店知识聚合（Cross-Store Knowledge Aggregation）

变更：
  1. rulecategory 枚举追加 cross_store 值
  2. stores 表追加 tier 列（门店层级：premium / standard / fastfood）
  3. 新建 cross_store_metrics  — 日维度物化指标（物化层）
  4. 新建 store_similarity_cache — 门店两两相似度缓存
  5. 新建 store_peer_groups      — 同伴组（tier + region 分组）

Neo4j 约束建议（运维在 Neo4j Browser 执行一次）：
  CREATE CONSTRAINT ON (s:Store) ASSERT s.store_id IS UNIQUE;
  CREATE INDEX ON :Store(region);
  CREATE INDEX ON :Store(tier);
  CREATE INDEX ON :Store(city);
  CREATE INDEX FOR ()-[r:SIMILAR_TO]-() ON (r.similarity_score);
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "r06_cross_store_metrics"
down_revision = "r05_fusion_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. rulecategory 枚举追加 cross_store ─────────────────────────────────
    # PostgreSQL 枚举追加值（不可回滚！）
    op.execute("ALTER TYPE rulecategory ADD VALUE IF NOT EXISTS 'cross_store';")

    # ── 2. stores 追加 tier ───────────────────────────────────────────────────
    op.add_column(
        "stores",
        sa.Column(
            "tier",
            sa.String(30),
            nullable=False,
            server_default="standard",
            comment="门店层级：premium / standard / fastfood",
        ),
    )
    op.create_index("ix_stores_tier", "stores", ["tier"])

    # ── 3. cross_store_metrics（日维度物化指标）───────────────────────────────
    op.create_table(
        "cross_store_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # 主键维度：门店 × 日期 × 指标名
        sa.Column("store_id",     sa.String(50),  nullable=False),
        sa.Column("metric_date",  sa.Date,         nullable=False),
        sa.Column("metric_name",  sa.String(50),   nullable=False),
        # waste_rate / cost_ratio / bom_compliance /
        # revenue_per_seat / labor_ratio / menu_coverage

        sa.Column("value",        sa.Float,         nullable=False),
        # 同伴组信息
        sa.Column("peer_group",   sa.String(100)),   # e.g. "standard_华东"
        sa.Column("peer_count",   sa.Integer),
        sa.Column("peer_p25",     sa.Float),
        sa.Column("peer_p50",     sa.Float),
        sa.Column("peer_p75",     sa.Float),
        sa.Column("peer_p90",     sa.Float),
        # 本店在同伴组中的百分位（0-100）
        sa.Column("percentile_in_peer", sa.Float),
        sa.Column("created_at",   sa.DateTime, server_default=sa.text("now()")),
        # 唯一约束：同一门店同一日期同一指标只保留一条
        sa.UniqueConstraint("store_id", "metric_date", "metric_name",
                            name="uq_cross_store_metric"),
    )
    op.create_index("ix_csm_store_date",
                    "cross_store_metrics", ["store_id", "metric_date"])
    op.create_index("ix_csm_metric_date",
                    "cross_store_metrics", ["metric_name", "metric_date"])
    op.create_index("ix_csm_peer_group",
                    "cross_store_metrics", ["peer_group"])

    # ── 4. store_similarity_cache（门店两两相似度缓存）──────────────────────
    op.create_table(
        "store_similarity_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("store_a_id",       sa.String(50),  nullable=False),
        sa.Column("store_b_id",       sa.String(50),  nullable=False),
        sa.Column("similarity_score", sa.Float,        nullable=False),
        # 各维度分量
        sa.Column("menu_overlap",     sa.Float),   # 菜单 Jaccard
        sa.Column("region_match",     sa.Boolean),  # 同区域
        sa.Column("tier_match",       sa.Boolean),  # 同层级
        sa.Column("capacity_ratio",   sa.Float),   # 座位数比率
        sa.Column("computed_at",      sa.DateTime, server_default=sa.text("now()")),
        sa.UniqueConstraint("store_a_id", "store_b_id",
                            name="uq_store_similarity"),
    )
    op.create_index("ix_ssc_store_a",   "store_similarity_cache", ["store_a_id"])
    op.create_index("ix_ssc_store_b",   "store_similarity_cache", ["store_b_id"])
    op.create_index("ix_ssc_score",     "store_similarity_cache", ["similarity_score"])

    # ── 5. store_peer_groups（同伴组）───────────────────────────────────────
    op.create_table(
        "store_peer_groups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("group_key",   sa.String(100), nullable=False, unique=True),
        # e.g.  "standard_华东" | "premium_上海" | "fastfood_全国"
        sa.Column("tier",        sa.String(30)),
        sa.Column("region",      sa.String(50)),
        sa.Column("store_ids",   postgresql.ARRAY(sa.String(50)), nullable=False,
                  server_default="{}"),
        sa.Column("store_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at",  sa.DateTime, server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_spg_tier_region",
                    "store_peer_groups", ["tier", "region"])


def downgrade() -> None:
    op.drop_index("ix_spg_tier_region",  "store_peer_groups")
    op.drop_table("store_peer_groups")

    op.drop_index("ix_ssc_score",  "store_similarity_cache")
    op.drop_index("ix_ssc_store_b", "store_similarity_cache")
    op.drop_index("ix_ssc_store_a", "store_similarity_cache")
    op.drop_table("store_similarity_cache")

    op.drop_index("ix_csm_peer_group",  "cross_store_metrics")
    op.drop_index("ix_csm_metric_date", "cross_store_metrics")
    op.drop_index("ix_csm_store_date",  "cross_store_metrics")
    op.drop_table("cross_store_metrics")

    op.drop_index("ix_stores_tier", "stores")
    op.drop_column("stores", "tier")

    # 注：PostgreSQL 不支持 DROP VALUE from enum，downgrade 不回滚 cross_store 值
