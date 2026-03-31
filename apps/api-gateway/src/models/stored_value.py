"""
储值卡相关模型

StoredValueAccount       — 储值账户（本金 + 赠送金）
StoredValueTransaction   — 储值流水（充值/消费/退款/赠送/调整/过期）
RechargePromotion        — 充值赠送规则（门槛/固定赠送/比例赠送）

金额字段统一使用 Integer（分），避免浮点精度问题。
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


class TransactionType(str, enum.Enum):
    """储值流水类型"""

    RECHARGE = "recharge"    # 充值（本金）
    CONSUME = "consume"      # 消费扣款
    REFUND = "refund"        # 退款回卡
    GIFT = "gift"            # 赠送金（充值活动赠送）
    ADJUST = "adjust"        # 人工调整
    EXPIRE = "expire"        # 过期清零


# ── ORM 模型 ──────────────────────────────────────────────────────────────────


class StoredValueAccount(Base, TimestampMixin):
    """
    储值账户

    每位会员（member_id）在每个门店（store_id）下各有一个账户。
    balance_fen       — 本金余额（分），充值/退款增加，消费减少
    gift_balance_fen  — 赠送金余额（分），充值活动赠送，消费时优先扣减
    """

    __tablename__ = "stored_value_accounts"

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
    balance_fen = Column(
        Integer,
        nullable=False,
        default=0,
        comment="本金余额（分）",
    )
    gift_balance_fen = Column(
        Integer,
        nullable=False,
        default=0,
        comment="赠送金余额（分），充值活动赠送",
    )
    is_frozen = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否冻结（冻结时不允许消费）",
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="乐观锁版本号，每次写操作 +1",
    )
    last_recharge_at = Column(
        DateTime,
        nullable=True,
        comment="最后充值时间（UTC）",
    )
    last_consume_at = Column(
        DateTime,
        nullable=True,
        comment="最后消费时间（UTC）",
    )

    __table_args__ = (
        Index("ix_sva_member_store", "member_id", "store_id", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<StoredValueAccount member={self.member_id} "
            f"balance={self.balance_fen}fen gift={self.gift_balance_fen}fen>"
        )


class StoredValueTransaction(Base):
    """
    储值流水（只追加，不修改）

    balance_after      — 本金余额快照（分），写入时点余额，用于对账
    gift_balance_after — 赠送金余额快照（分）
    """

    __tablename__ = "stored_value_transactions"

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
        comment="储值账户ID（软关联 stored_value_accounts.id）",
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
    transaction_type = Column(
        String(20),
        nullable=False,
        comment="流水类型（TransactionType 枚举值）",
    )
    amount_fen = Column(
        Integer,
        nullable=False,
        comment="本次变动金额（分），正=增加，负=减少",
    )
    gift_amount_fen = Column(
        Integer,
        nullable=False,
        default=0,
        comment="赠送金变动（分），正=增加，负=减少",
    )
    balance_after = Column(
        Integer,
        nullable=False,
        comment="操作后本金余额快照（分）",
    )
    gift_balance_after = Column(
        Integer,
        nullable=False,
        default=0,
        comment="操作后赠送金余额快照（分）",
    )
    order_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="关联订单ID（消费/退款时填写）",
    )
    payment_method = Column(
        String(50),
        nullable=True,
        comment="支付方式（充值时：wechat/alipay/cash/card 等）",
    )
    operator_id = Column(
        String(100),
        nullable=True,
        comment="操作人ID（staff_id 或 system）",
    )
    promotion_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="关联充值活动ID（有赠送时填写）",
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
        Index("ix_svt_member_created", "member_id", "created_at"),
        Index("ix_svt_store_created", "store_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<StoredValueTransaction type={self.transaction_type} "
            f"amount={self.amount_fen}fen balance_after={self.balance_after}fen>"
        )


class RechargePromotion(Base, TimestampMixin):
    """
    充值赠送规则

    支持两种赠送方式（可同时生效，叠加计算）：
      gift_amount_fen — 固定赠送额（分），如充100送20
      gift_rate       — 比例赠送，如充值金额 * 0.1 = 赠送额

    is_active=True 且在 valid_from～valid_until 范围内方生效。
    """

    __tablename__ = "recharge_promotions"

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
    name = Column(
        String(100),
        nullable=False,
        comment="活动名称，如 '充100送20'",
    )
    min_recharge_fen = Column(
        Integer,
        nullable=False,
        comment="触发门槛（分），充值金额 >= 此值才赠送",
    )
    gift_amount_fen = Column(
        Integer,
        nullable=False,
        default=0,
        comment="固定赠送额（分），0=不赠固定金额",
    )
    gift_rate = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="比例赠送率（0.0~1.0），0=不按比例赠送",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    valid_from = Column(
        DateTime,
        nullable=True,
        comment="有效期开始（UTC），NULL=无限制",
    )
    valid_until = Column(
        DateTime,
        nullable=True,
        comment="有效期结束（UTC），NULL=无限制",
    )
    sort_order = Column(
        Integer,
        nullable=False,
        default=0,
        comment="排序权重（越大越优先展示）",
    )

    __table_args__ = (
        Index("ix_rp_store_active", "store_id", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<RechargePromotion name={self.name} "
            f"min={self.min_recharge_fen}fen gift={self.gift_amount_fen}fen "
            f"rate={self.gift_rate}>"
        )
