"""hr20 — HR操作审计日志表

新建 operation_audit_logs 表，自动记录所有HR模块写操作（POST/PUT/DELETE），
用于合规审计和操作追溯。

Revision ID: hr20
Revises: hr19
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "hr20"
down_revision = "hr19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # 操作人
        sa.Column("operator_id", sa.String(50), nullable=False, index=True),
        sa.Column("operator_name", sa.String(100), nullable=True),
        sa.Column("operator_role", sa.String(30), nullable=True),
        # 操作信息
        sa.Column("action", sa.String(20), nullable=False, index=True),
        sa.Column("module", sa.String(50), nullable=False, index=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        # 请求信息
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        # 变更详情
        sa.Column("request_body", JSON, nullable=True),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("changes", JSON, nullable=True),
        # 结果
        sa.Column("success", sa.String(10), server_default="true"),
        sa.Column("error_message", sa.Text, nullable=True),
        # 门店/品牌
        sa.Column("store_id", sa.String(50), nullable=True, index=True),
        sa.Column("brand_id", sa.String(50), nullable=True),
        # 时间戳
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # 复合索引：按模块+时间查询（审计报告常用）
    op.create_index(
        "idx_op_audit_module_time",
        "operation_audit_logs",
        ["module", "created_at"],
    )
    # 复合索引：按操作人+时间查询（追溯某人操作）
    op.create_index(
        "idx_op_audit_operator_time",
        "operation_audit_logs",
        ["operator_id", "created_at"],
    )
    # 复合索引：按资源类型+资源ID查询（追溯某资源变更历史）
    op.create_index(
        "idx_op_audit_resource",
        "operation_audit_logs",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_op_audit_resource", table_name="operation_audit_logs")
    op.drop_index("idx_op_audit_operator_time", table_name="operation_audit_logs")
    op.drop_index("idx_op_audit_module_time", table_name="operation_audit_logs")
    op.drop_table("operation_audit_logs")
