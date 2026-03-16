"""hr21 — 决策飞轮记录表

新建 decision_records 表，记录每个AI决策建议的完整生命周期：
建议 → 用户响应 → 执行 → 效果追踪 → 模型校准。
Palantir闭环控制的核心数据表。

Revision ID: hr21
Revises: hr20
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "hr21"
down_revision = "hr20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # 归属
        sa.Column("brand_id", sa.String(50), nullable=False, index=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        # 决策来源
        sa.Column("decision_type", sa.String(50), nullable=False, index=True),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="ai"),
        # 决策目标
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("target_name", sa.String(100), nullable=True),
        # AI建议内容
        sa.Column("recommendation", sa.Text, nullable=False),
        sa.Column("risk_score", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("predicted_impact_fen", sa.Integer, nullable=True),
        sa.Column("ai_analysis", sa.Text, nullable=True),
        sa.Column("context_snapshot", JSON, nullable=True),
        # 用户响应
        sa.Column("user_action", sa.String(20), nullable=True),
        sa.Column("user_id", sa.String(50), nullable=True),
        sa.Column("user_action_at", sa.DateTime, nullable=True),
        sa.Column("user_note", sa.Text, nullable=True),
        sa.Column("modified_action", sa.Text, nullable=True),
        # 执行追踪
        sa.Column("executed", sa.Boolean, server_default="false"),
        sa.Column("executed_at", sa.DateTime, nullable=True),
        sa.Column("execution_detail", JSON, nullable=True),
        # 效果追踪（30/60/90天）
        sa.Column("review_30d_at", sa.DateTime, nullable=True),
        sa.Column("review_30d_result", JSON, nullable=True),
        sa.Column("review_60d_at", sa.DateTime, nullable=True),
        sa.Column("review_60d_result", JSON, nullable=True),
        sa.Column("review_90d_at", sa.DateTime, nullable=True),
        sa.Column("review_90d_result", JSON, nullable=True),
        # 校准
        sa.Column("actual_impact_fen", sa.Integer, nullable=True),
        sa.Column("deviation_pct", sa.Float, nullable=True),
        sa.Column("calibration_note", sa.Text, nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        # 状态
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # 时间戳
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # 复合索引：按门店+类型+状态查询（仪表盘常用）
    op.create_index(
        "idx_dr_store_type_status",
        "decision_records",
        ["store_id", "decision_type", "status"],
    )
    # 复合索引：按目标类型+目标ID查询（追溯某员工/门店的决策历史）
    op.create_index(
        "idx_dr_target",
        "decision_records",
        ["target_type", "target_id"],
    )
    # 索引：按创建时间排序（列表查询）
    op.create_index(
        "idx_dr_created",
        "decision_records",
        ["created_at"],
    )
    # 复合索引：按状态+执行时间查询（定位到期需要Review的记录）
    op.create_index(
        "idx_dr_review_due",
        "decision_records",
        ["status", "executed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_dr_review_due", table_name="decision_records")
    op.drop_index("idx_dr_created", table_name="decision_records")
    op.drop_index("idx_dr_target", table_name="decision_records")
    op.drop_index("idx_dr_store_type_status", table_name="decision_records")
    op.drop_table("decision_records")
