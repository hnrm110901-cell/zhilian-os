"""
自助结账服务
生成结账二维码、验证支付、完成结账流程
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class CheckoutStatus(str, Enum):
    PENDING = "pending"        # 待支付
    PAID = "paid"              # 已支付
    COMPLETED = "completed"    # 已完成（出品确认）
    EXPIRED = "expired"        # 已过期
    CANCELLED = "cancelled"


@dataclass
class SelfCheckout:
    """自助结账记录"""
    checkout_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    table_no: str = ""
    order_id: str = ""
    amount_fen: int = 0
    qr_code: str = ""       # 二维码内容
    qr_expire_at: Optional[datetime] = None
    status: CheckoutStatus = CheckoutStatus.PENDING
    payment_method: str = ""
    payment_ref: str = ""    # 支付流水号
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    paid_at: Optional[datetime] = None

    @property
    def amount_yuan(self) -> float:
        return round(self.amount_fen / 100, 2)


class SelfCheckoutService:
    """自助结账服务"""

    def __init__(self, qr_expire_minutes: int = 15):
        self._checkouts: Dict[str, SelfCheckout] = {}
        self._qr_expire_minutes = qr_expire_minutes

    def generate_checkout_qr(
        self,
        store_id: str,
        table_no: str,
        order_id: str,
        amount_fen: int,
    ) -> SelfCheckout:
        """
        生成自助结账二维码
        二维码内容包含checkout_id和金额的签名
        """
        if amount_fen <= 0:
            raise ValueError("结账金额必须大于0")

        checkout = SelfCheckout(
            store_id=store_id,
            table_no=table_no,
            order_id=order_id,
            amount_fen=amount_fen,
            qr_expire_at=datetime.now(timezone.utc) + timedelta(minutes=self._qr_expire_minutes),
        )
        # 生成二维码内容（模拟：实际会调用微信/支付宝支付接口）
        raw = f"{checkout.checkout_id}:{amount_fen}:{store_id}"
        sign = hashlib.sha256(raw.encode()).hexdigest()[:16]
        checkout.qr_code = f"https://pay.tunxiang.cn/checkout/{checkout.checkout_id}?sign={sign}"

        self._checkouts[checkout.checkout_id] = checkout
        logger.info("生成自助结账二维码", checkout_id=checkout.checkout_id,
                     amount_yuan=checkout.amount_yuan, table=table_no)
        return checkout

    def verify_payment(
        self,
        checkout_id: str,
        payment_method: str,
        payment_ref: str,
        paid_amount_fen: int,
    ) -> Dict:
        """
        验证支付结果
        检查金额是否匹配、二维码是否过期
        """
        checkout = self._get_checkout(checkout_id)
        if checkout.status != CheckoutStatus.PENDING:
            return {"verified": False, "reason": f"结账状态异常: {checkout.status.value}"}

        # 检查过期
        if checkout.qr_expire_at and datetime.now(timezone.utc) > checkout.qr_expire_at:
            checkout.status = CheckoutStatus.EXPIRED
            return {"verified": False, "reason": "二维码已过期"}

        # 检查金额
        if paid_amount_fen != checkout.amount_fen:
            return {
                "verified": False,
                "reason": f"金额不匹配: 应付{checkout.amount_yuan}元，实付{round(paid_amount_fen/100,2)}元",
            }

        checkout.status = CheckoutStatus.PAID
        checkout.payment_method = payment_method
        checkout.payment_ref = payment_ref
        checkout.paid_at = datetime.now(timezone.utc)
        logger.info("自助结账支付验证通过", checkout_id=checkout_id, method=payment_method)
        return {
            "verified": True,
            "checkout_id": checkout_id,
            "amount_fen": checkout.amount_fen,
            "amount_yuan": checkout.amount_yuan,
            "payment_method": payment_method,
        }

    def complete_checkout(self, checkout_id: str) -> SelfCheckout:
        """完成结账（出品确认后调用）"""
        checkout = self._get_checkout(checkout_id)
        if checkout.status != CheckoutStatus.PAID:
            raise ValueError(f"只有已支付的订单才能完成: {checkout.status.value}")
        checkout.status = CheckoutStatus.COMPLETED
        logger.info("自助结账完成", checkout_id=checkout_id)
        return checkout

    def _get_checkout(self, checkout_id: str) -> SelfCheckout:
        if checkout_id not in self._checkouts:
            raise ValueError(f"结账记录不存在: {checkout_id}")
        return self._checkouts[checkout_id]
