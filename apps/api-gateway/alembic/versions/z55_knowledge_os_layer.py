"""z55 — HR架构重构M1：新建知识OS层 behavior_patterns / retention_signals / knowledge_captures

三位一体知识OS层 + 职业发展留人层：
- BehaviorPattern: 行为模型（越用越准），从员工行为数据挖掘高绩效/离职风险模式
- RetentionSignal: 离职风险预测信号，HRAgent v2 产出
- KnowledgeCapture: 对话式知识采集，"人走知识留"核心机制

同时扩展已有 knowledge_rules 表：增加 org_node_id / action 字段。

Revision ID: z55
Revises: z54
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "z55"
down_revision = "z54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 扩展已有 knowledge_rules 表 ─────────────────────────────
    # 新增 org_node_id（可为null=全行业规则）
    op.add_column("knowledge_rules", sa.Column(
        "org_node_id", UUID(as_uuid=True), nullable=True,
        comment="组织节点ID（null=全行业通用规则）",
    ))
    op.create_index("ix_knowledge_rules_org_node", "knowledge_rules", ["org_node_id"])

    # 新增 action JSON（区别于已有的 conclusion，action 是可执行动作）
    op.add_column("knowledge_rules", sa.Column(
        "action", JSON, nullable=True, server_default="{}",
        comment="可执行动作 {type, params, expected_effect}",
    ))

    # 新增 industry_source（行业经验来源）
    op.add_column("knowledge_rules", sa.Column(
        "industry_source", sa.String(100), nullable=True,
        comment="行业经验来源: tunxiang_pack/expert/crowdsource",
    ))

    # ── behavior_patterns 表 ─────────────────────────────────────
    op.create_table(
        "behavior_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # 模式类型
        sa.Column("pattern_type", sa.String(50), nullable=False, index=True,
                  comment="high_performer/churn_risk/service_quality/efficiency/safety"),
        sa.Column("name", sa.String(200)),
        sa.Column("description", sa.Text),
        # 特征向量
        sa.Column("feature_vector", JSON, nullable=False, server_default="{}"),
        sa.Column("feature_names", JSON, server_default="[]"),
        # 模型效果
        sa.Column("outcome", sa.String(100)),
        sa.Column("confidence", sa.Float, server_default="0"),
        sa.Column("precision_score", sa.Float),
        sa.Column("recall_score", sa.Float),
        # 训练数据
        sa.Column("sample_size", sa.Integer, server_default="0"),
        sa.Column("training_period_days", sa.Integer),
        sa.Column("last_trained_at", sa.DateTime),
        # 适用范围
        sa.Column("org_scope", sa.String(20), server_default="brand", index=True,
                  comment="brand(品牌级)/global(全网)"),
        sa.Column("brand_id", sa.String(50), nullable=True, index=True),
        sa.Column("applicable_positions", JSON, server_default="[]"),
        # 版本
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("is_active", sa.Boolean, server_default="true", index=True),
        sa.Column("superseded_by", UUID(as_uuid=True), nullable=True),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_behavior_patterns_type_scope", "behavior_patterns", ["pattern_type", "org_scope"])

    # ── retention_signals 表 ─────────────────────────────────────
    op.create_table(
        "retention_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True), sa.ForeignKey("assignments.id"),
                  nullable=False, index=True),
        # 风险评估
        sa.Column("risk_score", sa.Integer, nullable=False, comment="0-100"),
        sa.Column("risk_level", sa.String(20), comment="low/medium/high/critical"),
        sa.Column("risk_factors", JSON, server_default="{}"),
        # 干预跟踪
        sa.Column("intervention_status", sa.String(20), server_default="none",
                  comment="none/planned/in_progress/completed/ignored"),
        sa.Column("intervention_plan", JSON, nullable=True),
        sa.Column("intervened_by", UUID(as_uuid=True), nullable=True),
        sa.Column("intervened_at", sa.DateTime),
        # 预测模型
        sa.Column("model_version", sa.String(50)),
        sa.Column("computed_at", sa.DateTime, nullable=False),
        sa.Column("valid_until", sa.DateTime),
        # 结果追踪
        sa.Column("actual_outcome", sa.String(20), comment="stayed/resigned/terminated"),
        sa.Column("outcome_date", sa.DateTime),
        sa.Column("prediction_accuracy", sa.Float),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_retention_signals_risk", "retention_signals", ["risk_level", "intervention_status"])

    # ── knowledge_captures 表 ────────────────────────────────────
    op.create_table(
        "knowledge_captures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("persons.id"),
                  nullable=False, index=True),
        # 触发场景
        sa.Column("trigger_type", sa.String(30), nullable=False, index=True,
                  comment="exit/review/project_end/spontaneous"),
        sa.Column("trigger_context", JSON, server_default="{}"),
        # 采集内容（CAR: Context-Action-Result）
        sa.Column("context", sa.Text, comment="情境"),
        sa.Column("action", sa.Text, comment="行动"),
        sa.Column("result", sa.Text, comment="结果"),
        # 结构化输出
        sa.Column("structured_output", JSON, server_default="{}"),
        # 关联知识体系
        sa.Column("knowledge_node_id", UUID(as_uuid=True), nullable=True),
        sa.Column("linked_skill_ids", JSON, server_default="[]"),
        # 质量
        sa.Column("quality_score", sa.String(10), comment="A/B/C/D"),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime),
        # 状态
        sa.Column("status", sa.String(20), server_default="draft",
                  comment="draft/reviewed/published/archived"),
        # 采集方式
        sa.Column("capture_method", sa.String(20), server_default="dialogue"),
        sa.Column("session_transcript", JSON, nullable=True, comment="对话记录(加密)"),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("knowledge_captures")
    op.drop_table("retention_signals")
    op.drop_table("behavior_patterns")
    # 回退 knowledge_rules 扩展
    op.drop_index("ix_knowledge_rules_org_node", table_name="knowledge_rules")
    op.drop_column("knowledge_rules", "industry_source")
    op.drop_column("knowledge_rules", "action")
    op.drop_column("knowledge_rules", "org_node_id")
