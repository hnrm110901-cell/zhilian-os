"""HR知识OS层 — 三位一体知识操作系统

创建以下表：
  hr_knowledge_rules — HR专属行业经验库（与现有knowledge_rules共存，不修改）
  skill_nodes        — 技能知识图谱骨架
  behavior_patterns  — 行为模式学习（元数据，向量存Qdrant）
  person_achievements — 技能认证记录
  retention_signals  — 离职风险预测信号
  knowledge_captures  — 对话式知识采集记录

Revision ID: z55_hr_knowledge_tables
Revises: z54_hr_core_tables
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "z55_hr_knowledge_tables"
down_revision = "z54_hr_core_tables"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "hr_knowledge_rules"):
        op.create_table(
            "hr_knowledge_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("rule_type", sa.String(30), nullable=False,
                      comment="sop / kpi_baseline / alert / best_practice"),
            sa.Column("category", sa.String(50), nullable=True,
                      comment="turnover / scheduling / standards / training"),
            sa.Column("condition", JSONB, nullable=False, server_default="{}"),
            sa.Column("action", JSONB, nullable=False, server_default="{}"),
            sa.Column("expected_impact", JSONB, nullable=True),
            sa.Column("confidence", sa.Float, nullable=False, server_default="0.8"),
            sa.Column("industry_source", sa.String(100), nullable=True),
            sa.Column("org_node_id", sa.String(64), nullable=True,
                      comment="NULL = 全行业通用"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_hr_knowledge_rules_category",
                        "hr_knowledge_rules", ["category", "rule_type"])
        op.create_index("idx_hr_knowledge_rules_org",
                        "hr_knowledge_rules", ["org_node_id"])

    if not _table_exists(conn, "skill_nodes"):
        op.create_table(
            "skill_nodes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("skill_name", sa.String(100), nullable=False),
            sa.Column("category", sa.String(50), nullable=True,
                      comment="service / kitchen / management / compliance"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("prerequisite_skill_ids", ARRAY(UUID(as_uuid=True)),
                      nullable=True, server_default="{}",
                      comment="前置技能UUID数组（无FK约束，PostgreSQL数组）"),
            sa.Column("related_training_ids", ARRAY(UUID(as_uuid=True)),
                      nullable=True, server_default="{}"),
            sa.Column("kpi_impact", JSONB, nullable=True),
            sa.Column("estimated_revenue_lift", sa.Numeric(10, 2), nullable=True,
                      comment="预计¥收入提升（元/月）"),
            sa.Column("org_node_id", sa.String(64), nullable=True,
                      comment="NULL = 行业通用技能"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_skill_nodes_category", "skill_nodes", ["category"])

    if not _table_exists(conn, "behavior_patterns"):
        op.create_table(
            "behavior_patterns",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("pattern_type", sa.String(50), nullable=True,
                      comment="turnover_risk / high_performance / schedule_optimal"),
            sa.Column("feature_vector", JSONB, nullable=False, server_default="{}",
                      comment="特征元数据（字段名+权重），实际向量存Qdrant"),
            sa.Column("qdrant_vector_id", sa.String(100), nullable=True,
                      comment="Qdrant collection hr_behavior_patterns 的向量ID"),
            sa.Column("outcome", sa.String(100), nullable=True),
            sa.Column("confidence", sa.Float, nullable=True),
            sa.Column("sample_size", sa.Integer, nullable=True),
            sa.Column("org_scope", sa.String(30), nullable=True,
                      comment="brand / region / network"),
            sa.Column("org_node_id", sa.String(64), nullable=True),
            sa.Column("last_trained", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "person_achievements"):
        op.create_table(
            "person_achievements",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("skill_node_id", UUID(as_uuid=True),
                      sa.ForeignKey("skill_nodes.id", ondelete="RESTRICT"),
                      nullable=False, index=True),
            sa.Column("achieved_at", sa.Date, nullable=False),
            sa.Column("evidence", sa.Text, nullable=True),
            sa.Column("verified_by", UUID(as_uuid=True), nullable=True,
                      comment="认证人的person_id"),
            sa.Column("trigger_type", sa.String(30), nullable=True,
                      server_default="'manual'",
                      comment="manual / legacy_import / ai_assessment"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_person_achievements_person_skill",
                        "person_achievements", ["person_id", "skill_node_id"],
                        unique=True)

    if not _table_exists(conn, "retention_signals"):
        op.create_table(
            "retention_signals",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("assignment_id", UUID(as_uuid=True),
                      sa.ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("risk_score", sa.Float, nullable=False,
                      comment="0.0-1.0"),
            sa.Column("risk_factors", JSONB, nullable=False, server_default="{}"),
            sa.Column("intervention_status", sa.String(30), nullable=False,
                      server_default="'pending'",
                      comment="pending / in_progress / resolved"),
            sa.Column("intervention_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("computed_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_retention_signals_scan",
                        "retention_signals", ["risk_score", "computed_at"])
        op.create_index("idx_retention_signals_assignment",
                        "retention_signals", ["assignment_id", "computed_at"])

    if not _table_exists(conn, "knowledge_captures"):
        op.create_table(
            "knowledge_captures",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("trigger_type", sa.String(30), nullable=True,
                      comment=("exit / monthly_review / incident / onboarding / "
                               "growth_review / talent_assessment / legacy_import")),
            sa.Column("raw_dialogue", sa.Text, nullable=True),
            sa.Column("context", sa.Text, nullable=True),
            sa.Column("action", sa.Text, nullable=True),
            sa.Column("result", sa.Text, nullable=True),
            sa.Column("structured_output", JSONB, nullable=True),
            sa.Column("knowledge_node_id", UUID(as_uuid=True), nullable=True,
                      comment="关联的skill_nodes.id（无强FK，可为空）"),
            sa.Column("quality_score", sa.Float, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table in [
        "knowledge_captures", "retention_signals", "person_achievements",
        "behavior_patterns", "skill_nodes", "hr_knowledge_rules",
    ]:
        if _table_exists(conn, table):
            op.drop_table(table)
