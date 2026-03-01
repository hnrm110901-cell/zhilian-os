"""
宴会全生命周期 migration (r11)

变更：
  1. reservations 表新增 banquet_stage 字段（仅 BANQUET 类型预约使用）
  2. 新建 banquet_stage_history 表（阶段变更审计追踪）

宴会 7 阶段销售漏斗（参考 宴荟佳 / 宴专家 PPT）：
  lead        → 商机    初次接触，客户表达初步需求
  intent      → 意向    客户进入选台/报价阶段
  room_lock   → 锁台    日期+场地锁定（软预留，未签约）
  signed      → 签约    合同已签，定金已付
  preparation → 准备    宴会前准备（BEO执行，物料到位）
  service     → 服务    宴会当天服务进行中
  completed   → 完成    宴会圆满结束，尾款结清
  cancelled   → 取消    任何阶段均可取消（terminal state）

设计原则：
  - banquet_stage 非必填（NULL = 非宴会预约 / 尚未启动销售流程）
  - banquet_stage_history 仅追加，不删除（审计完整性）
  - locked_at：room_lock 阶段时间戳（用于销控超时检测：未签约超过 N 天自动释放）

revision:      r11_banquet_lifecycle
down_revision: r10_banquet_event_orders
"""

revision      = "r11_banquet_lifecycle"
down_revision = "r10_banquet_event_orders"
branch_labels = None
depends_on    = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade() -> None:
    # 1. reservations 表新增 banquet_stage 字段
    op.add_column(
        "reservations",
        sa.Column(
            "banquet_stage",
            sa.String(20),
            nullable=True,
            comment="宴会销售阶段（仅 BANQUET 类型）：lead/intent/room_lock/signed/preparation/service/completed/cancelled",
        ),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "banquet_stage_updated_at",
            sa.DateTime(),
            nullable=True,
            comment="banquet_stage 最后更新时间",
        ),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "room_locked_at",
            sa.DateTime(),
            nullable=True,
            comment="锁台时间（room_lock 阶段；用于销控超时检测）",
        ),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "signed_at",
            sa.DateTime(),
            nullable=True,
            comment="签约时间",
        ),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "deposit_paid",
            sa.Integer(),
            nullable=True,
            comment="已付定金（分）",
        ),
    )

    # 索引：按门店 + 宴会阶段快速查询漏斗
    op.create_index(
        "ix_reservation_banquet_stage",
        "reservations",
        ["store_id", "banquet_stage"],
    )

    # 2. 新建 banquet_stage_history 表
    op.create_table(
        "banquet_stage_history",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            primary_key=True,
            comment="主键（自增）",
        ),
        sa.Column(
            "reservation_id",
            sa.String(50),
            nullable=False,
            index=True,
            comment="预约 ID（软关联 reservations.id）",
        ),
        sa.Column("store_id",    sa.String(50), nullable=False, index=True),
        sa.Column("from_stage",  sa.String(20), nullable=True,  comment="变更前阶段（NULL=初始）"),
        sa.Column("to_stage",    sa.String(20), nullable=False,  comment="变更后阶段"),
        sa.Column(
            "changed_by",
            sa.String(100),
            nullable=True,
            comment="操作人（用户ID / system）",
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="变更时间",
        ),
        sa.Column(
            "reason",
            sa.String(500),
            nullable=True,
            comment="变更原因/备注",
        ),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=True,
            comment="额外元数据（如合同编号、支付流水等）",
        ),
    )

    op.create_index(
        "ix_stage_history_reservation",
        "banquet_stage_history",
        ["reservation_id", "changed_at"],
    )
    op.create_index(
        "ix_stage_history_store_date",
        "banquet_stage_history",
        ["store_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stage_history_store_date",    table_name="banquet_stage_history")
    op.drop_index("ix_stage_history_reservation",   table_name="banquet_stage_history")
    op.drop_table("banquet_stage_history")

    op.drop_index("ix_reservation_banquet_stage",   table_name="reservations")
    op.drop_column("reservations", "deposit_paid")
    op.drop_column("reservations", "signed_at")
    op.drop_column("reservations", "room_locked_at")
    op.drop_column("reservations", "banquet_stage_updated_at")
    op.drop_column("reservations", "banquet_stage")
