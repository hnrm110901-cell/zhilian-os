"""
储值卡退卡+赠送规则服务
管理充值赠送规则（充200送30）、退卡退款计算
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class CardStatus(str, Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    REFUNDED = "refunded"
    EXPIRED = "expired"


@dataclass
class RechargeRule:
    """充值赠送规则：充X送Y"""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""  # 空表示全局规则
    name: str = ""
    recharge_fen: int = 0  # 充值金额（分）
    gift_fen: int = 0      # 赠送金额（分）
    enabled: bool = True

    @property
    def recharge_yuan(self) -> float:
        return round(self.recharge_fen / 100, 2)

    @property
    def gift_yuan(self) -> float:
        return round(self.gift_fen / 100, 2)


@dataclass
class StoredValueCard:
    """储值卡"""
    card_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    customer_id: str = ""
    customer_name: str = ""
    # 余额
    cash_balance_fen: int = 0    # 现金充值余额（分），可退
    gift_balance_fen: int = 0    # 赠送余额（分），不可退
    total_recharge_fen: int = 0  # 累计充值金额
    total_gift_fen: int = 0      # 累计赠送金额
    total_consumed_fen: int = 0  # 累计消费金额
    status: CardStatus = CardStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_balance_fen(self) -> int:
        return self.cash_balance_fen + self.gift_balance_fen

    @property
    def total_balance_yuan(self) -> float:
        return round(self.total_balance_fen / 100, 2)

    @property
    def cash_balance_yuan(self) -> float:
        return round(self.cash_balance_fen / 100, 2)

    @property
    def gift_balance_yuan(self) -> float:
        return round(self.gift_balance_fen / 100, 2)


class StoredValueService:
    """储值卡退卡+赠送规则服务"""

    def __init__(self):
        self._cards: Dict[str, StoredValueCard] = {}
        self._rules: Dict[str, RechargeRule] = {}

    # ---- 赠送规则管理 ----

    def add_rule(
        self,
        name: str,
        recharge_fen: int,
        gift_fen: int,
        store_id: str = "",
    ) -> RechargeRule:
        """添加充值赠送规则"""
        if recharge_fen <= 0 or gift_fen <= 0:
            raise ValueError("充值和赠送金额必须大于0")
        rule = RechargeRule(
            store_id=store_id,
            name=name,
            recharge_fen=recharge_fen,
            gift_fen=gift_fen,
        )
        self._rules[rule.rule_id] = rule
        logger.info("添加充值规则", name=name,
                     recharge_yuan=rule.recharge_yuan, gift_yuan=rule.gift_yuan)
        return rule

    def apply_rule(self, card_id: str, rule_id: str) -> StoredValueCard:
        """
        应用充值规则：充值+赠送
        """
        card = self._get_card(card_id)
        if card.status != CardStatus.ACTIVE:
            raise ValueError(f"储值卡状态不允许充值: {card.status.value}")
        rule = self._get_rule(rule_id)

        card.cash_balance_fen += rule.recharge_fen
        card.gift_balance_fen += rule.gift_fen
        card.total_recharge_fen += rule.recharge_fen
        card.total_gift_fen += rule.gift_fen

        logger.info("充值赠送完成", card_id=card_id,
                     recharge_yuan=rule.recharge_yuan, gift_yuan=rule.gift_yuan,
                     balance_yuan=card.total_balance_yuan)
        return card

    def recharge(self, card_id: str, amount_fen: int) -> StoredValueCard:
        """直接充值（不走规则，无赠送）"""
        card = self._get_card(card_id)
        if card.status != CardStatus.ACTIVE:
            raise ValueError("储值卡不可用")
        if amount_fen <= 0:
            raise ValueError("充值金额必须大于0")
        card.cash_balance_fen += amount_fen
        card.total_recharge_fen += amount_fen
        return card

    # ---- 储值卡管理 ----

    def create_card(
        self,
        store_id: str,
        customer_id: str,
        customer_name: str = "",
    ) -> StoredValueCard:
        """创建储值卡"""
        card = StoredValueCard(
            store_id=store_id,
            customer_id=customer_id,
            customer_name=customer_name,
        )
        self._cards[card.card_id] = card
        return card

    def consume(self, card_id: str, amount_fen: int) -> StoredValueCard:
        """消费扣款（先扣赠送余额，再扣现金余额）"""
        card = self._get_card(card_id)
        if card.status != CardStatus.ACTIVE:
            raise ValueError("储值卡不可用")
        if amount_fen > card.total_balance_fen:
            raise ValueError("余额不足")
        # 先扣赠送
        if card.gift_balance_fen >= amount_fen:
            card.gift_balance_fen -= amount_fen
        else:
            remaining = amount_fen - card.gift_balance_fen
            card.gift_balance_fen = 0
            card.cash_balance_fen -= remaining
        card.total_consumed_fen += amount_fen
        return card

    def refund_card(self, card_id: str) -> Dict:
        """
        退卡：仅退还现金充值余额，赠送余额不退
        """
        card = self._get_card(card_id)
        if card.status == CardStatus.REFUNDED:
            raise ValueError("储值卡已退款")
        refund_result = self.calculate_refund(card_id)
        card.status = CardStatus.REFUNDED
        # 清零
        refund_fen = card.cash_balance_fen
        card.cash_balance_fen = 0
        card.gift_balance_fen = 0
        logger.info("储值卡退卡", card_id=card_id, refund_yuan=round(refund_fen / 100, 2))
        return refund_result

    def calculate_refund(self, card_id: str) -> Dict:
        """
        计算退卡金额
        规则：仅退现金充值余额，赠送部分不退
        """
        card = self._get_card(card_id)
        return {
            "card_id": card_id,
            "customer_name": card.customer_name,
            "cash_balance_fen": card.cash_balance_fen,
            "cash_balance_yuan": card.cash_balance_yuan,
            "gift_balance_fen": card.gift_balance_fen,
            "gift_balance_yuan": card.gift_balance_yuan,
            "refundable_fen": card.cash_balance_fen,
            "refundable_yuan": card.cash_balance_yuan,
            "non_refundable_fen": card.gift_balance_fen,
            "non_refundable_yuan": card.gift_balance_yuan,
            "total_recharge_fen": card.total_recharge_fen,
            "total_consumed_fen": card.total_consumed_fen,
        }

    def get_rules(self, store_id: str = "") -> List[RechargeRule]:
        """获取充值规则列表"""
        return [
            r for r in self._rules.values()
            if r.enabled and (r.store_id == store_id or r.store_id == "")
        ]

    def _get_card(self, card_id: str) -> StoredValueCard:
        if card_id not in self._cards:
            raise ValueError(f"储值卡不存在: {card_id}")
        return self._cards[card_id]

    def _get_rule(self, rule_id: str) -> RechargeRule:
        if rule_id not in self._rules:
            raise ValueError(f"充值规则不存在: {rule_id}")
        return self._rules[rule_id]
