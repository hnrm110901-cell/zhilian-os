"""
BanquetEventOrder (BEO) ORM 模型

职责：
  - 持久化宴会执行协调单（BEO），支持版本追踪和变更审计
  - 关联 reservations.id（via reservation_id 字符串，软关联）
  - 每次 BEO 变更产生新版本（版本链），旧版本保留用于 diff 回溯

BEO 状态机：
  draft → confirmed → executed → archived
                    ↘ cancelled

BEO 版本原则：
  - 同一 reservation_id + store_id 下允许多条记录（不同 version）
  - is_latest=True 标记当前最新版本（原子性更新）
  - 每次菜单/采购/排班变更创建新版本，不可原地修改

与其他服务的集成：
  - BanquetPlanningEngine.generate_beo() → 通过 BEORepository.save() 持久化
  - DailyHubService._get_banquet_variables() → 查询 is_latest BEO 注入备战板
  - WorkflowEngine procurement 阶段 → DecisionVersion.content 可引用 BEO ID
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Index,
    Integer, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.models.base import Base, TimestampMixin


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class BEOStatus(str, enum.Enum):
    DRAFT     = "draft"      # 自动生成，待店长确认
    CONFIRMED = "confirmed"  # 店长已确认，下发执行
    EXECUTED  = "executed"   # 宴会已举办完成
    ARCHIVED  = "archived"   # 归档（超过 90 天自动归档）
    CANCELLED = "cancelled"  # 宴会取消


# ── ORM 模型 ──────────────────────────────────────────────────────────────────

class BanquetEventOrder(Base, TimestampMixin):
    """
    宴会执行协调单（BEO）数据库模型。

    一个预约可以对应多个 BEO 版本（每次变更产生新版本）。
    `is_latest=True` 标记当前有效版本，查询时按此字段过滤。
    """

    __tablename__ = "banquet_event_orders"

    # ── 主键
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="BEO 主键（UUID）",
    )

    # ── 关联字段
    store_id       = Column(String(50),  nullable=False, index=True, comment="门店 ID")
    reservation_id = Column(String(100), nullable=False, index=True, comment="预约 ID（软关联）")
    event_date     = Column(Date,        nullable=False, index=True, comment="宴会日期")

    # ── 版本控制
    version    = Column(Integer, nullable=False, default=1, comment="BEO 版本号（从1开始递增）")
    is_latest  = Column(Boolean, nullable=False, default=True, comment="是否为当前最新版本")

    # ── 状态
    status = Column(
        String(20),
        nullable=False,
        default=BEOStatus.DRAFT.value,
        index=True,
        comment="BEO 状态（draft/confirmed/executed/archived/cancelled）",
    )

    # ── BEO 内容（完整快照，含采购/排班/财务/菜单）
    content = Column(
        JSONB,
        nullable=False,
        default=dict,
        comment="BEO 完整内容快照（JSON）",
    )

    # ── 宴会关键信息（冗余存储，支持快速查询无需反序列化 content）
    party_size        = Column(Integer, nullable=True, comment="宴会人数")
    estimated_budget  = Column(Integer, nullable=True, comment="预算（分，避免浮点精度问题）")
    circuit_triggered = Column(Boolean, nullable=False, default=False, comment="是否触发宴会熔断")

    # ── 操作人信息
    generated_by = Column(String(100), nullable=True, comment="生成人（system / 用户ID）")
    approved_by  = Column(String(100), nullable=True, comment="审批人（店长ID）")
    approved_at  = Column(DateTime,    nullable=True, comment="审批时间")

    # ── 变更日志（轻量级，完整变更见 content["change_log"]）
    change_summary = Column(String(500), nullable=True, comment="本次变更摘要（一句话）")

    # ── 约束 & 索引
    __table_args__ = (
        # 同一预约在同一门店下，版本号唯一
        UniqueConstraint(
            "store_id", "reservation_id", "version",
            name="uq_beo_store_reservation_version",
        ),
        # 快速查询某预约的最新 BEO
        Index("ix_beo_reservation_latest", "reservation_id", "is_latest"),
        # 按日期查询当天所有宴会 BEO
        Index("ix_beo_store_event_date", "store_id", "event_date"),
        # 按状态查询（待确认的 draft BEO 列表）
        Index("ix_beo_status", "store_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<BanquetEventOrder "
            f"id={self.id!s:.8} "
            f"reservation={self.reservation_id} "
            f"v{self.version} "
            f"status={self.status}>"
        )
