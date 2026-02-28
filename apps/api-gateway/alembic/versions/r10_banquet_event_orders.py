"""
r10 宴会执行协调单（BEO）数据库迁移

新建：
  banquet_event_orders — 宴会 BEO 单（版本化，支持变更追踪）

架构背景：
  BEO（Banquet Event Order）是宴会执行的核心协调文档，
  覆盖采购清单、排班方案、财务摘要、菜单快照和变更日志。

  版本策略：
    - 同一 (store_id, reservation_id) 下允许多版本（每次变更产生新版本）
    - is_latest=True 标记当前有效版本（原子性更新旧版本 is_latest→False）
    - 版本号从 1 开始递增，旧版本永久保留（审计追踪）

  状态机：
    draft → confirmed → executed → archived
                      ↘ cancelled

  与宴会熔断引擎的关系：
    - BanquetPlanningEngine.check_circuit_breaker() 在内存生成 BEO
    - DailyHubService._get_banquet_variables() 调用熔断引擎后写入此表
    - WorkflowEngine procurement 阶段 DecisionVersion.content 可引用 BEO ID

revision:      r10_banquet_event_orders
down_revision: r09_workflow_engine
"""

revision      = "r10_banquet_event_orders"
down_revision = "r09_workflow_engine"
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade() -> None:
    op.create_table(
        "banquet_event_orders",

        # ── 主键
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"),
                  comment="BEO 主键（UUID）"),

        # ── 关联字段
        sa.Column("store_id",       sa.String(50),  nullable=False, comment="门店 ID"),
        sa.Column("reservation_id", sa.String(100), nullable=False, comment="预约 ID（软关联）"),
        sa.Column("event_date",     sa.Date(),       nullable=False, comment="宴会日期"),

        # ── 版本控制
        sa.Column("version",   sa.Integer(),  nullable=False, server_default="1",
                  comment="BEO 版本号（从1开始递增）"),
        sa.Column("is_latest", sa.Boolean(),  nullable=False, server_default="true",
                  comment="是否为当前最新版本"),

        # ── 状态
        sa.Column("status", sa.String(20), nullable=False, server_default="draft",
                  comment="BEO 状态（draft/confirmed/executed/archived/cancelled）"),

        # ── BEO 内容（完整快照）
        sa.Column("content", JSONB(), nullable=False, server_default="'{}'::jsonb",
                  comment="BEO 完整内容快照（JSON）"),

        # ── 宴会关键信息（冗余存储，支持快速查询）
        sa.Column("party_size",        sa.Integer(), nullable=True, comment="宴会人数"),
        sa.Column("estimated_budget",  sa.Integer(), nullable=True, comment="预算（分）"),
        sa.Column("circuit_triggered", sa.Boolean(), nullable=False, server_default="false",
                  comment="是否触发宴会熔断"),

        # ── 操作人信息
        sa.Column("generated_by", sa.String(100), nullable=True, comment="生成人"),
        sa.Column("approved_by",  sa.String(100), nullable=True, comment="审批人"),
        sa.Column("approved_at",  sa.DateTime(),  nullable=True, comment="审批时间"),

        # ── 变更摘要
        sa.Column("change_summary", sa.String(500), nullable=True, comment="本次变更摘要"),

        # ── 时间戳
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("NOW()"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("NOW()"), comment="更新时间"),
    )

    # ── 唯一约束：同一预约在同一门店下，版本号唯一
    op.create_unique_constraint(
        "uq_beo_store_reservation_version",
        "banquet_event_orders",
        ["store_id", "reservation_id", "version"],
    )

    # ── 索引：快速查询某预约的最新 BEO
    op.create_index(
        "ix_beo_reservation_latest",
        "banquet_event_orders",
        ["reservation_id", "is_latest"],
    )
    # ── 索引：按日期查询当天所有宴会 BEO
    op.create_index(
        "ix_beo_store_event_date",
        "banquet_event_orders",
        ["store_id", "event_date"],
    )
    # ── 索引：按状态查询
    op.create_index(
        "ix_beo_status",
        "banquet_event_orders",
        ["store_id", "status"],
    )
    # ── 基础 B-tree 索引
    op.create_index(
        "ix_beo_store_id",
        "banquet_event_orders",
        ["store_id"],
    )
    op.create_index(
        "ix_beo_reservation_id",
        "banquet_event_orders",
        ["reservation_id"],
    )
    op.create_index(
        "ix_beo_event_date",
        "banquet_event_orders",
        ["event_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_beo_event_date",         table_name="banquet_event_orders")
    op.drop_index("ix_beo_reservation_id",     table_name="banquet_event_orders")
    op.drop_index("ix_beo_store_id",           table_name="banquet_event_orders")
    op.drop_index("ix_beo_status",             table_name="banquet_event_orders")
    op.drop_index("ix_beo_store_event_date",   table_name="banquet_event_orders")
    op.drop_index("ix_beo_reservation_latest", table_name="banquet_event_orders")
    op.drop_constraint("uq_beo_store_reservation_version", "banquet_event_orders")
    op.drop_table("banquet_event_orders")
