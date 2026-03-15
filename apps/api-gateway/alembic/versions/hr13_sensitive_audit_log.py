"""HR W1-2 — 敏感数据审计日志表 + 员工表字段扩容

1. 新建 sensitive_data_audit_logs 表（PII 访问审计）
2. 扩大 employees.id_card_no String(20) → String(200)（容纳加密后密文）
3. 扩大 employees.bank_account String(50) → String(200)

Revision ID: hr13
Revises: hr12
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "hr13"
down_revision = "hr12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. 创建敏感数据审计日志表 ──
    op.create_table(
        "sensitive_data_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("operator_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), nullable=False, index=True),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("store_id", sa.String(50), nullable=True, index=True),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # 复合索引
    op.create_index(
        "idx_sensitive_audit_operator_time",
        "sensitive_data_audit_logs",
        ["operator_id", "created_at"],
    )
    op.create_index(
        "idx_sensitive_audit_employee_time",
        "sensitive_data_audit_logs",
        ["employee_id", "created_at"],
    )
    op.create_index(
        "idx_sensitive_audit_action",
        "sensitive_data_audit_logs",
        ["action"],
    )

    # ── 2. 扩大 employees 敏感字段长度（容纳 AES-256-GCM 密文） ──
    op.alter_column(
        "employees",
        "id_card_no",
        existing_type=sa.String(20),
        type_=sa.String(200),
        existing_nullable=True,
    )
    op.alter_column(
        "employees",
        "bank_account",
        existing_type=sa.String(50),
        type_=sa.String(200),
        existing_nullable=True,
    )


def downgrade() -> None:
    # 缩回字段长度（注意：已有加密数据会被截断，不可逆操作需谨慎）
    op.alter_column(
        "employees",
        "bank_account",
        existing_type=sa.String(200),
        type_=sa.String(50),
        existing_nullable=True,
    )
    op.alter_column(
        "employees",
        "id_card_no",
        existing_type=sa.String(200),
        type_=sa.String(20),
        existing_nullable=True,
    )

    op.drop_index("idx_sensitive_audit_action", table_name="sensitive_data_audit_logs")
    op.drop_index("idx_sensitive_audit_employee_time", table_name="sensitive_data_audit_logs")
    op.drop_index("idx_sensitive_audit_operator_time", table_name="sensitive_data_audit_logs")
    op.drop_table("sensitive_data_audit_logs")
