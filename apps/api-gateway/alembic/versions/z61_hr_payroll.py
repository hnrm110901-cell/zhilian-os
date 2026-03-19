"""z61: HR payroll tables — batches, items, cost allocations

Revision ID: z61_hr_payroll
Revises: z60_hr_attendance_leave
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z61_hr_payroll"
down_revision = "z60_hr_attendance_leave"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. payroll_batches
    op.create_table(
        "payroll_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_node_id", sa.String(64),
                  sa.ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="'draft'",
                  comment="draft/calculating/review/approved/paid/locked"),
        sa.Column("total_gross_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="税前总额（分）"),
        sa.Column("total_net_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="税后总额（分）"),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_payroll_batches_org_node_id", "payroll_batches",
                    ["org_node_id"])
    op.create_unique_constraint("uq_payroll_batch_org_period",
                                "payroll_batches",
                                ["org_node_id", "period_year", "period_month"])

    # 2. payroll_items
    op.create_table(
        "payroll_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True),
                  sa.ForeignKey("payroll_batches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("assignment_id", UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id",
                                ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("base_salary_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="基本工资（分）"),
        sa.Column("performance_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="绩效奖金（分）"),
        sa.Column("overtime_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="加班费（分）"),
        sa.Column("deduction_absent_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="缺勤扣款（分）"),
        sa.Column("deduction_late_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="迟到扣款（分）"),
        sa.Column("allowances", JSONB, nullable=True, comment="其他津贴"),
        sa.Column("gross_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="税前合计（分）"),
        sa.Column("social_insurance_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="社保个人部分（分）"),
        sa.Column("tax_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="个税（分）"),
        sa.Column("net_fen", sa.Integer(), nullable=False,
                  server_default="0", comment="实发工资（分）"),
        sa.Column("viewed_at", sa.TIMESTAMP(timezone=True), nullable=True,
                  comment="工资条查看时间"),
        sa.Column("view_expires_at", sa.TIMESTAMP(timezone=True),
                  nullable=True, comment="查看有效期（阅后即焚）"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_payroll_items_batch_id", "payroll_items", ["batch_id"])
    op.create_index("ix_payroll_items_assignment_id", "payroll_items",
                    ["assignment_id"])

    # 3. cost_allocations
    op.create_table(
        "cost_allocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id",
                                ondelete="CASCADE"),
                  nullable=False),
        sa.Column("org_node_id", sa.String(64),
                  sa.ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("ratio", sa.Numeric(4, 3), nullable=False,
                  comment="分摊比例0.000-1.000"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_cost_allocations_assignment_id", "cost_allocations",
                    ["assignment_id"])
    op.create_index("ix_cost_allocations_org_node_id", "cost_allocations",
                    ["org_node_id"])
    op.create_unique_constraint("uq_cost_allocation_assignment_org",
                                "cost_allocations",
                                ["assignment_id", "org_node_id"])


def downgrade() -> None:
    op.drop_constraint("uq_cost_allocation_assignment_org",
                       "cost_allocations", type_="unique")
    op.drop_index("ix_cost_allocations_org_node_id",
                  table_name="cost_allocations")
    op.drop_index("ix_cost_allocations_assignment_id",
                  table_name="cost_allocations")
    op.drop_table("cost_allocations")

    op.drop_index("ix_payroll_items_assignment_id",
                  table_name="payroll_items")
    op.drop_index("ix_payroll_items_batch_id", table_name="payroll_items")
    op.drop_table("payroll_items")

    op.drop_constraint("uq_payroll_batch_org_period", "payroll_batches",
                       type_="unique")
    op.drop_index("ix_payroll_batches_org_node_id",
                  table_name="payroll_batches")
    op.drop_table("payroll_batches")
