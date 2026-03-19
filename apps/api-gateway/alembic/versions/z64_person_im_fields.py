"""z64 — 为 persons 和 employment_assignments 补充 M8 考勤迁移所需字段

M8 考勤迁移前置：im_attendance_sync 需要按微信/钉钉 ID 查找人员；
smart_schedule_service 需要按岗位排序和过滤员工。

新增字段：
  persons.wechat_userid         — 企业微信 userid（条件唯一索引）
  persons.dingtalk_userid       — 钉钉 userid（条件唯一索引）
  persons.store_id              — 主门店ID（兼容过渡）
  persons.is_active             — 是否在职（兼容过渡）
  employment_assignments.position   — 岗位名称（来自 Chain-B assignments 表，补回 Chain-A）
  employment_assignments.department — 部门名称

注意：is_active/store_id 为过渡期兼容字段，M5 完整迁移后可由 EmploymentAssignment 替代。

Revision ID: z64_person_im_fields
Revises: z63_merge_all_current_heads
Create Date: 2026-03-19
"""
import sqlalchemy as sa
from alembic import op

revision = "z64_person_im_fields"
down_revision = "z63_merge_all_current_heads"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ")"
        ),
        {"t": table, "c": column},
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "persons", "wechat_userid"):
        op.add_column("persons", sa.Column(
            "wechat_userid", sa.String(100), nullable=True,
            comment="企业微信 userid，用于消息推送和考勤同步",
        ))
        op.create_index("ix_persons_wechat_userid", "persons", ["wechat_userid"],
                        unique=True, postgresql_where=sa.text("wechat_userid IS NOT NULL"))

    if not _column_exists(conn, "persons", "dingtalk_userid"):
        op.add_column("persons", sa.Column(
            "dingtalk_userid", sa.String(100), nullable=True,
            comment="钉钉 userid，用于消息推送和考勤同步",
        ))
        op.create_index("ix_persons_dingtalk_userid", "persons", ["dingtalk_userid"],
                        unique=True, postgresql_where=sa.text("dingtalk_userid IS NOT NULL"))

    if not _column_exists(conn, "persons", "store_id"):
        op.add_column("persons", sa.Column(
            "store_id", sa.String(50), nullable=True,
            comment="主门店ID（过渡期兼容，最终由 EmploymentAssignment.org_node_id 替代）",
        ))
        op.create_index("ix_persons_store_id", "persons", ["store_id"])

    if not _column_exists(conn, "persons", "is_active"):
        op.add_column("persons", sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default="true",
            comment="是否在职（过渡期兼容，最终由 EmploymentAssignment.status 替代）",
        ))

    # ── employment_assignments 补字段 ─────────────────────────────────────────
    if not _column_exists(conn, "employment_assignments", "position"):
        op.add_column("employment_assignments", sa.Column(
            "position", sa.String(50), nullable=True,
            comment="岗位名称（厨师/服务员/收银等），Chain-B 补回字段",
        ))
        op.create_index("ix_employment_assignments_position",
                        "employment_assignments", ["position"])

    if not _column_exists(conn, "employment_assignments", "department"):
        op.add_column("employment_assignments", sa.Column(
            "department", sa.String(50), nullable=True,
            comment="部门（前厅/后厨/管理）",
        ))


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "employment_assignments", "department"):
        op.drop_column("employment_assignments", "department")
    if _column_exists(conn, "employment_assignments", "position"):
        op.drop_index("ix_employment_assignments_position",
                      table_name="employment_assignments")
        op.drop_column("employment_assignments", "position")
    if _column_exists(conn, "persons", "is_active"):
        op.drop_column("persons", "is_active")
    if _column_exists(conn, "persons", "store_id"):
        op.drop_index("ix_persons_store_id", table_name="persons")
        op.drop_column("persons", "store_id")
    if _column_exists(conn, "persons", "dingtalk_userid"):
        op.drop_index("ix_persons_dingtalk_userid", table_name="persons")
        op.drop_column("persons", "dingtalk_userid")
    if _column_exists(conn, "persons", "wechat_userid"):
        op.drop_index("ix_persons_wechat_userid", table_name="persons")
        op.drop_column("persons", "wechat_userid")
