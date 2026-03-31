"""
支付记录模型（支付网关）
金额单位：分（fen），与DB其他模型一致

注意：payment_reconciliation.py 中已有 PaymentRecord（__tablename__ = "payment_records"）
      用于对账流水导入场景。本模型面向实时支付网关，使用 gateway_payment_records 表。
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.models.base import Base


class PaymentMethod(str, PyEnum):
    WECHAT_JSAPI = "wechat_jsapi"    # 微信小程序/H5内支付
    WECHAT_NATIVE = "wechat_native"  # 微信扫码支付
    ALIPAY_H5 = "alipay_h5"          # 支付宝H5跳转
    ALIPAY_NATIVE = "alipay_native"  # 支付宝扫码支付
    CASH = "cash"
    BANK_CARD = "bank_card"


class PaymentStatus(str, PyEnum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDING = "refunding"
    REFUNDED = "refunded"
    FAILED = "failed"
    CLOSED = "closed"


class GatewayPaymentRecord(Base):
    """支付网关记录（实时支付下单/回调/退款）"""

    __tablename__ = "gateway_payment_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # 支付方式：见 PaymentMethod 枚举
    payment_method = Column(String(32), nullable=False)
    # 支付金额（分），与DB其他模型保持一致
    amount_fen = Column(Integer, nullable=False, comment="支付金额（分）")
    # 支付状态：见 PaymentStatus 枚举
    status = Column(String(16), nullable=False, default=PaymentStatus.PENDING.value)

    # 第三方支付信息
    third_party_trade_no = Column(String(64), unique=True, nullable=True,
                                  comment="微信/支付宝流水号")
    prepay_id = Column(String(128), nullable=True, comment="微信预支付ID")
    wechat_openid = Column(String(64), nullable=True,
                           comment="微信用户openid（JSAPI支付必需）")

    # 时间戳
    paid_at = Column(DateTime, nullable=True)
    refund_amount_fen = Column(Integer, default=0, nullable=False,
                               comment="已退款金额（分）")
    refunded_at = Column(DateTime, nullable=True)

    # 审计
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                        nullable=True)
    # 原始回调报文，加密存储，用于对账和争议处理
    callback_raw = Column(Text, nullable=True, comment="原始回调报文（用于对账）")

    __table_args__ = (
        Index("ix_gateway_payment_records_store_created", "store_id", "created_at"),
    )
