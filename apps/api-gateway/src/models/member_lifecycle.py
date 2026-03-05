"""
会员生命周期状态历史模型

MemberLifecycleHistory — 状态变更审计追踪（只追加，不删改）

与 banquet_lifecycle.py 设计一致：
- 每次 LifecycleStateMachine.apply_trigger() 追加一条记录
- PrivateDomainMember.lifecycle_state 字段通过 migration c01 添加
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from src.models.base import Base


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class LifecycleState(str, enum.Enum):
    """会员生命周期状态（9个）"""
    LEAD                = "lead"                   # 初始接触（未注册）
    REGISTERED          = "registered"             # 已注册，尚无订单（同 first_order_pending）
    FIRST_ORDER_PENDING = "first_order_pending"    # 已注册，等待首单
    REPEAT              = "repeat"                 # 回头客（1+单，活跃）
    HIGH_FREQUENCY      = "high_frequency"         # 高频会员（30天内5+单）
    VIP                 = "vip"                    # VIP会员（高频+高消费）
    AT_RISK             = "at_risk"                # 流失风险（45天无订单）
    DORMANT             = "dormant"                # 沉睡（90天无订单）
    LOST                = "lost"                   # 已流失（terminal）


class StateTransitionTrigger(str, enum.Enum):
    """状态转移触发器（7个）"""
    REGISTER                 = "register"
    FIRST_ORDER              = "first_order"
    REPEAT_ORDER             = "repeat_order"
    HIGH_FREQUENCY_MILESTONE = "high_frequency_milestone"  # 30天内≥5单
    VIP_UPGRADE              = "vip_upgrade"
    CHURN_WARNING            = "churn_warning"             # 45天无订单
    INACTIVITY_LONG          = "inactivity_long"           # 90天无订单


# ── ORM 模型 ──────────────────────────────────────────────────────────────────

class MemberLifecycleHistory(Base):
    """
    会员生命周期状态变更审计追踪（只追加，不删改）。

    每次调用 LifecycleStateMachine.apply_trigger() 追加一条记录，
    保留完整的状态变更历史，供私域运营分析和漏斗追踪。
    """

    __tablename__ = "member_lifecycle_histories"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键",
    )

    store_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="门店ID（软关联 stores.id）",
    )
    customer_id = Column(
        String(100),
        nullable=False,
        index=True,
        comment="客户ID（软关联 private_domain_members.customer_id）",
    )

    from_state = Column(
        String(30),
        nullable=True,
        comment="变更前状态（NULL=初始化）",
    )
    to_state = Column(
        String(30),
        nullable=False,
        comment="变更后状态",
    )
    trigger = Column(
        String(50),
        nullable=True,
        comment="触发转移的事件（StateTransitionTrigger）",
    )

    changed_by = Column(
        String(100),
        nullable=True,
        comment="操作人（用户ID / system / auto）",
    )
    changed_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="变更时间（UTC）",
    )
    reason = Column(
        String(500),
        nullable=True,
        comment="变更原因/备注",
    )

    __table_args__ = (
        Index("ix_mlh_store_customer", "store_id", "customer_id"),
        Index("ix_mlh_store_changed_at", "store_id", "changed_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<MemberLifecycleHistory "
            f"cid={self.customer_id} "
            f"{self.from_state}→{self.to_state} "
            f"trigger={self.trigger} "
            f"at={self.changed_at}>"
        )
