"""
宴会全生命周期 ORM 模型

BanquetStage  — 7 阶段枚举
BanquetStageHistory — 阶段变更审计追踪（只追加，不删改）

Reservation 模型已有 banquet_stage / banquet_stage_updated_at /
room_locked_at / signed_at / deposit_paid 字段（见 r11 migration）。
本文件仅定义 BanquetStageHistory 模型和 BanquetStage 枚举。

阶段状态机（合法转换）：
  None → lead → intent → room_lock → signed → preparation → service → completed
  任意 → cancelled（终态，不可回退）

注意：
  BanquetLifecycleService 在推进阶段时：
  1. 校验转换合法性
  2. 更新 Reservation.banquet_stage + banquet_stage_updated_at
  3. 在 room_lock 阶段同时写入 room_locked_at
  4. 在 signed 阶段同时写入 signed_at
  5. 追加一条 BanquetStageHistory 记录
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class BanquetStage(str, enum.Enum):
    """宴会销售漏斗 7 阶段（参考 宴荟佳 / 宴专家 PPT）。"""
    LEAD        = "lead"         # 商机：初次接触，客户表达初步需求
    INTENT      = "intent"       # 意向：进入选台/报价阶段
    ROOM_LOCK   = "room_lock"    # 锁台：日期+场地软预留（未签约）
    SIGNED      = "signed"       # 签约：合同已签，定金已付
    PREPARATION = "preparation"  # 准备：BEO 执行，物料/排班就位
    SERVICE     = "service"      # 服务：宴会当天进行中
    COMPLETED   = "completed"    # 完成：宴会圆满结束，尾款结清
    CANCELLED   = "cancelled"    # 取消（任何阶段均可，terminal）


# 合法阶段转换表（from → allowed_to_list）
STAGE_TRANSITIONS: dict[str, list[str]] = {
    BanquetStage.LEAD:        [BanquetStage.INTENT,   BanquetStage.CANCELLED],
    BanquetStage.INTENT:      [BanquetStage.ROOM_LOCK, BanquetStage.CANCELLED],
    BanquetStage.ROOM_LOCK:   [BanquetStage.SIGNED,   BanquetStage.LEAD, BanquetStage.CANCELLED],
    BanquetStage.SIGNED:      [BanquetStage.PREPARATION, BanquetStage.CANCELLED],
    BanquetStage.PREPARATION: [BanquetStage.SERVICE,  BanquetStage.CANCELLED],
    BanquetStage.SERVICE:     [BanquetStage.COMPLETED, BanquetStage.CANCELLED],
    BanquetStage.COMPLETED:   [],  # terminal，不可再转换
    BanquetStage.CANCELLED:   [],  # terminal，不可再转换
}

# 初始阶段（新建宴会预约时的默认起点）
INITIAL_STAGE = BanquetStage.LEAD

# 锁台超时阈值（天）：room_lock 超过此天数未签约，视为超时
ROOM_LOCK_TIMEOUT_DAYS = int(__import__("os").getenv("ROOM_LOCK_TIMEOUT_DAYS", "7"))


# ── ORM 模型 ──────────────────────────────────────────────────────────────────

class BanquetStageHistory(Base):
    """
    宴会阶段变更审计追踪（只追加，不删改）。

    每次调用 BanquetLifecycleService.advance_stage() 都追加一条记录，
    保留完整的阶段变更历史，供运营追溯和漏斗分析。
    """

    __tablename__ = "banquet_stage_history"

    id = Column(
        Integer,
        autoincrement=True,
        primary_key=True,
        comment="主键（自增）",
    )

    reservation_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="预约 ID（软关联 reservations.id）",
    )
    store_id = Column(String(50), nullable=False, index=True)

    from_stage = Column(
        String(20),
        nullable=True,
        comment="变更前阶段（NULL=初始创建）",
    )
    to_stage = Column(
        String(20),
        nullable=False,
        comment="变更后阶段",
    )

    changed_by = Column(
        String(100),
        nullable=True,
        comment="操作人（用户ID / system）",
    )
    changed_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="变更时间",
    )

    reason = Column(
        String(500),
        nullable=True,
        comment="变更原因/备注",
    )
    metadata_ = Column(
        "metadata",
        JSONB,
        nullable=True,
        comment="额外元数据（合同编号、支付流水等）",
    )

    __table_args__ = (
        Index("ix_stage_history_reservation", "reservation_id", "changed_at"),
        Index("ix_stage_history_store_date",  "store_id",       "changed_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<BanquetStageHistory "
            f"rid={self.reservation_id} "
            f"{self.from_stage}→{self.to_stage} "
            f"at={self.changed_at}>"
        )
