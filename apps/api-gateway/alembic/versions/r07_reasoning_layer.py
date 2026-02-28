"""
r07 L4 推理层数据库迁移

新建：
  reasoning_reports — 维度化推理报告物化表
    （每日 × 门店 × 维度 唯一，支持 P1/P2/P3/OK 严重程度 + 证据链 + 行动追踪）

revision:      r07_reasoning_layer
down_revision: r06_cross_store_metrics
"""

revision     = "r07_reasoning_layer"
down_revision = "r06_cross_store_metrics"
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade():
    op.create_table(
        "reasoning_reports",

        sa.Column("id",          UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id",    sa.String(50),  nullable=False),
        sa.Column("report_date", sa.Date(),       nullable=False),

        # 维度（waste / efficiency / quality / cost / inventory / cross_store）
        sa.Column("dimension",   sa.String(30), nullable=False),

        # 严重程度（P1 = 立即处理, P2 = 本日内, P3 = 本周内, OK = 正常）
        sa.Column("severity", sa.String(10), nullable=False, server_default="OK"),

        # 推理结论
        sa.Column("root_cause",           sa.String(100)),
        sa.Column("confidence",           sa.Float()),
        sa.Column("evidence_chain",       JSONB()),      # List[str]
        sa.Column("triggered_rule_codes", JSONB()),      # List[str]
        sa.Column("recommended_actions",  JSONB()),      # List[str]

        # 同伴组上下文（来自 L3）
        sa.Column("peer_group",      sa.String(100)),
        sa.Column("peer_context",    JSONB()),           # {"peer.p25": 0.05, ...}
        sa.Column("peer_percentile", sa.Float()),        # 本店在同伴组的百分位（0-100）

        # KPI 快照（推理时刻的实际值）
        sa.Column("kpi_snapshot", JSONB()),              # {"waste_rate": 0.15, ...}

        # 行动追踪
        sa.Column("is_actioned", sa.Boolean(), server_default="false"),
        sa.Column("actioned_by", sa.String(100)),
        sa.Column("actioned_at", sa.DateTime()),

        # 时间戳
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 唯一约束：同一门店同日同维度只保留一份报告（upsert on conflict）
    op.create_unique_constraint(
        "uq_reasoning_report_store_date_dim",
        "reasoning_reports",
        ["store_id", "report_date", "dimension"],
    )

    # 查询索引
    op.create_index("idx_rr_store_date",  "reasoning_reports", ["store_id", "report_date"])
    op.create_index("idx_rr_severity",    "reasoning_reports", ["severity"])
    op.create_index("idx_rr_dimension",   "reasoning_reports", ["dimension"])
    op.create_index("idx_rr_report_date", "reasoning_reports", ["report_date"])


def downgrade():
    op.drop_index("idx_rr_report_date", table_name="reasoning_reports")
    op.drop_index("idx_rr_dimension",   table_name="reasoning_reports")
    op.drop_index("idx_rr_severity",    table_name="reasoning_reports")
    op.drop_index("idx_rr_store_date",  table_name="reasoning_reports")
    op.drop_table("reasoning_reports")
