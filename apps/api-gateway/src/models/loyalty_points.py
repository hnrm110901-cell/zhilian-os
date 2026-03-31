"""
积分与会员等级模型

LoyaltyAccount      — 积分账户（当前积分 + 历史累计积分用于定级）
PointsTransaction   — 积分流水（只追加，不修改）
MemberLevelConfig   — 等级配置（升级门槛/积分倍率/折扣率等权益）

金额字段（birthday_bonus）使用 Integer（分）。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from src.models.base import Base, TimestampMixin


# ── 枚举 ─────────────────────────────────────────────────────────────────────


class MemberLevel(str, enum.Enum):
    """会员等级（按消费积累升级）"""

    BRONZE = "bronze"        # 铜牌
    SILVER = "silver"        # 银牌
    GOLD = "gold"            # 金牌
    PLATINUM = "platinum"    # 铂金
    DIAMOND = "diamond"      # 钻石


class PointsChangeReason(str, enum.Enum):
    """积分变动原因"""

    CONSUME_EARN = "consume_earn"      # 消费得积分
    REDEEM = "redeem"                  # 积分兑换抵扣
    BIRTHDAY_BONUS = "birthday_bonus"  # 生日赠分
    MANUAL_ADJUST = "manual_adjust"    # 人工调整
    EXPIRE = "expire"                  # 过期清零
    REFUND_DEDUCT = "refund_deduct"    # 退款扣回积分
    REGISTER_BONUS = "register_bonus"  # 注册奖励


# ── ORM 模型 ──────────────────────────────────────────────────────────────────


class LoyaltyAccount(Base, TimestampMixin):
    """
    积分账户

    total_points      — 当前可用积分
    lifetime_points   — 历史累计积分（只增不减，用于计算会员等级）
    member_level      — 当前等级（由 check_and_upgrade_level 自动维护）
    """

    __tablename__ = "loyalty_accounts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键",
    )
    member_id = Column(
        String(100),
        nullable=False,
        index=True,
        comment="会员ID（软关联 private_domain_members.id）",
    )
    store_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="门店ID（软关联 stores.id）",
    )
    total_points = Column(
        Integer,
        nullable=False,
        default=0,
        comment="当前可用积分",
    )
    lifetime_points = Column(
        Integer,
        nullable=False,
        default=0,
        comment="历史累计积分（只增不减，用于定级）",
    )
    member_level = Column(
        String(20),
        nullable=False,
        default=MemberLevel.BRONZE.value,
        comment="当前会员等级（MemberLevel 枚举值）",
    )
    last_earn_at = Column(
        DateTime,
        nullable=True,
        comment="最后一次获得积分时间（UTC）",
    )
    last_redeem_at = Column(
        DateTime,
        nullable=True,
        comment="最后一次兑换时间（UTC）",
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="乐观锁版本号",
    )

    __table_args__ = (
        Index("ix_la_member_store", "member_id", "store_id", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<LoyaltyAccount member={self.member_id} "
            f"points={self.total_points} level={self.member_level}>"
        )


class PointsTransaction(Base):
    """
    积分流水（只追加，不修改）

    points_change  — 本次积分变动（正=获得，负=消耗/过期）
    points_after   — 操作后积分余额快照（时点快照，用于对账）
    """

    __tablename__ = "points_transactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键",
    )
    account_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="积分账户ID（软关联 loyalty_accounts.id）",
    )
    member_id = Column(
        String(100),
        nullable=False,
        index=True,
        comment="会员ID（冗余，方便查询）",
    )
    store_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="门店ID",
    )
    points_change = Column(
        Integer,
        nullable=False,
        comment="积分变动（正=获得，负=消耗）",
    )
    points_after = Column(
        Integer,
        nullable=False,
        comment="操作后积分余额快照",
    )
    change_reason = Column(
        String(30),
        nullable=False,
        comment="变动原因（PointsChangeReason 枚举值）",
    )
    order_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="关联订单ID（消费/兑换时填写）",
    )
    order_amount_fen = Column(
        Integer,
        nullable=True,
        comment="关联订单金额（分），用于积分计算审计",
    )
    operator_id = Column(
        String(100),
        nullable=True,
        comment="操作人ID（人工调整时填写）",
    )
    note = Column(
        Text,
        nullable=True,
        comment="备注",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="创建时间（UTC）",
    )

    __table_args__ = (
        Index("ix_pt_member_created", "member_id", "created_at"),
        Index("ix_pt_store_created", "store_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PointsTransaction reason={self.change_reason} "
            f"change={self.points_change} after={self.points_after}>"
        )


class MemberLevelConfig(Base, TimestampMixin):
    """
    会员等级配置（各门店可自定义）

    min_lifetime_points  — 达到该等级所需历史累计积分
    points_rate          — 积分倍率（1.0=1倍，2.0=双倍，门店可为高等级配置更高倍率）
    discount_rate        — 折扣率（1.0=无折扣，0.9=九折，用于消费折扣权益）
    birthday_bonus       — 生日赠分（分数）
    priority_reservation — 是否享有优先订台权益
    """

    __tablename__ = "member_level_configs"

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
    level = Column(
        String(20),
        nullable=False,
        comment="等级（MemberLevel 枚举值）",
    )
    level_name = Column(
        String(50),
        nullable=False,
        default="",
        comment="等级显示名称，如 '铜牌会员'",
    )
    min_lifetime_points = Column(
        Integer,
        nullable=False,
        default=0,
        comment="升级所需历史累计积分（达到即升级）",
    )
    points_rate = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="积分倍率（1.0=1倍，2.0=双倍）",
    )
    discount_rate = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="消费折扣率（1.0=无折扣，0.9=九折）",
    )
    birthday_bonus = Column(
        Integer,
        nullable=False,
        default=0,
        comment="生日赠分（积分数）",
    )
    priority_reservation = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否享有优先订台权益",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用此等级配置",
    )

    __table_args__ = (
        Index("ix_mlc_store_level", "store_id", "level", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<MemberLevelConfig store={self.store_id} level={self.level} "
            f"min_pts={self.min_lifetime_points} rate={self.points_rate}>"
        )
