"""
轻量POS收银服务

Phase 2.2 功能对等模块 — 提供基础收银功能，用于SaaS过渡期。
不是完整POS替代，而是覆盖开单、加菜、折扣、结账等核心操作。

设计原则：
- 所有金额以分(fen)为单位存储和计算，仅在API边界转换为元
- 纯函数 + dataclass，不依赖ORM
- 账单状态机: open → settled → voided
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ============================================================
# 枚举定义
# ============================================================

class BillStatus(str, Enum):
    """账单状态"""
    OPEN = "open"            # 开台中
    SETTLED = "settled"      # 已结账
    VOIDED = "voided"        # 已作废


class PaymentMethod(str, Enum):
    """支付方式"""
    CASH = "cash"            # 现金
    WECHAT = "wechat"        # 微信支付
    ALIPAY = "alipay"        # 支付宝
    CARD = "card"            # 银行卡
    MEMBER_CARD = "member_card"  # 会员卡


class DiscountType(str, Enum):
    """折扣类型"""
    PERCENTAGE = "percentage"      # 折扣（如85折 = 85）
    FIXED_AMOUNT = "fixed_amount"  # 固定减免（单位：分）
    COUPON = "coupon"              # 优惠券


# ============================================================
# 数据结构
# ============================================================

@dataclass
class BillItem:
    """账单明细项"""
    item_id: str
    dish_id: str
    dish_name: str
    quantity: int
    unit_price_fen: int          # 单价（分）
    subtotal_fen: int            # 小计（分）= 单价 × 数量
    specification: str = ""      # 规格（如：大份、小份）
    methods: str = ""            # 做法（如：微辣、去冰）
    added_at: str = ""           # 添加时间 ISO 格式


@dataclass
class Discount:
    """折扣信息"""
    discount_type: DiscountType
    discount_value: int          # percentage: 85表示85折; fixed_amount: 分; coupon: 分
    description: str = ""


@dataclass
class BillSummary:
    """账单汇总"""
    bill_id: str
    subtotal_fen: int            # 菜品合计（分）
    discount_fen: int            # 折扣金额（分，正数表示优惠）
    total_fen: int               # 应收金额（分）= subtotal - discount
    item_count: int              # 菜品数量


@dataclass
class Bill:
    """账单主体"""
    bill_id: str
    store_id: str
    table_number: str
    waiter_id: str
    status: BillStatus
    items: List[BillItem] = field(default_factory=list)
    discount: Optional[Discount] = None
    subtotal_fen: int = 0
    discount_fen: int = 0
    total_fen: int = 0
    created_at: str = ""
    settled_at: str = ""
    payment_method: Optional[PaymentMethod] = None
    void_reason: str = ""


@dataclass
class BillDetail:
    """账单详情（含完整信息）"""
    bill: Bill
    summary: BillSummary


@dataclass
class SettlementResult:
    """结账结果"""
    bill_id: str
    success: bool
    total_fen: int               # 应收（分）
    paid_fen: int                # 实收（分）
    change_fen: int              # 找零（分）
    payment_method: PaymentMethod
    settled_at: str
    message: str = ""


# ============================================================
# 服务层：内存存储（POC阶段，后续接数据库）
# ============================================================

class PosTerminalService:
    """
    轻量POS收银服务

    POC阶段使用内存字典存储账单数据，后续迁移到数据库时
    只需替换存储层，业务逻辑不变。
    """

    def __init__(self):
        # 内存存储：bill_id -> Bill
        self._bills: Dict[str, Bill] = {}

    def open_bill(
        self,
        store_id: str,
        table_number: str,
        waiter_id: str,
    ) -> Bill:
        """
        开台/开单

        为指定门店的桌号创建一张新账单，初始状态为 open。
        """
        bill_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        bill = Bill(
            bill_id=bill_id,
            store_id=store_id,
            table_number=table_number,
            waiter_id=waiter_id,
            status=BillStatus.OPEN,
            items=[],
            created_at=now,
        )
        self._bills[bill_id] = bill

        logger.info(
            "pos.bill_opened",
            bill_id=bill_id,
            store_id=store_id,
            table_number=table_number,
            waiter_id=waiter_id,
        )
        return bill

    def add_item(
        self,
        bill_id: str,
        dish_id: str,
        dish_name: str,
        quantity: int,
        unit_price_fen: int,
        specification: str = "",
        methods: str = "",
    ) -> BillItem:
        """
        加菜

        向已开台的账单中添加一道菜品。自动重算小计。
        """
        bill = self._get_open_bill(bill_id)

        item_id = str(uuid.uuid4())
        # 小计 = 单价 × 数量
        subtotal_fen = unit_price_fen * quantity

        item = BillItem(
            item_id=item_id,
            dish_id=dish_id,
            dish_name=dish_name,
            quantity=quantity,
            unit_price_fen=unit_price_fen,
            subtotal_fen=subtotal_fen,
            specification=specification,
            methods=methods,
            added_at=datetime.utcnow().isoformat(),
        )
        bill.items.append(item)
        self._recalculate(bill)

        logger.info(
            "pos.item_added",
            bill_id=bill_id,
            dish_id=dish_id,
            dish_name=dish_name,
            quantity=quantity,
            subtotal_fen=subtotal_fen,
        )
        return item

    def remove_item(self, bill_id: str, item_id: str) -> bool:
        """
        退菜/删除菜品

        从账单中移除指定菜品，自动重算合计。
        """
        bill = self._get_open_bill(bill_id)

        original_count = len(bill.items)
        bill.items = [i for i in bill.items if i.item_id != item_id]

        if len(bill.items) == original_count:
            raise ValueError(f"菜品不存在: item_id={item_id}")

        self._recalculate(bill)

        logger.info("pos.item_removed", bill_id=bill_id, item_id=item_id)
        return True

    def calculate_bill(self, bill_id: str) -> BillSummary:
        """
        计算账单合计

        返回当前账单的菜品合计、折扣金额、应收金额。
        """
        bill = self._get_bill(bill_id)
        return BillSummary(
            bill_id=bill_id,
            subtotal_fen=bill.subtotal_fen,
            discount_fen=bill.discount_fen,
            total_fen=bill.total_fen,
            item_count=sum(item.quantity for item in bill.items),
        )

    def apply_discount(
        self,
        bill_id: str,
        discount_type: DiscountType,
        discount_value: int,
        description: str = "",
    ) -> BillSummary:
        """
        应用折扣

        折扣类型：
        - percentage: discount_value=85 表示85折（即打8.5折）
        - fixed_amount: discount_value=500 表示减5元（500分）
        - coupon: discount_value=1000 表示优惠券抵扣10元（1000分）
        """
        bill = self._get_open_bill(bill_id)

        # 校验折扣值合法性
        if discount_type == DiscountType.PERCENTAGE:
            if discount_value < 1 or discount_value > 99:
                raise ValueError("折扣值必须在1~99之间（如85表示85折）")
        elif discount_value < 0:
            raise ValueError("折扣金额不能为负数")

        bill.discount = Discount(
            discount_type=discount_type,
            discount_value=discount_value,
            description=description,
        )
        self._recalculate(bill)

        logger.info(
            "pos.discount_applied",
            bill_id=bill_id,
            discount_type=discount_type.value,
            discount_value=discount_value,
        )
        return self.calculate_bill(bill_id)

    def settle_bill(
        self,
        bill_id: str,
        payment_method: PaymentMethod,
        amount_fen: int,
    ) -> SettlementResult:
        """
        结账

        校验实收金额是否足够，完成结账并记录支付方式。
        现金支付允许找零，电子支付必须精确匹配。
        """
        bill = self._get_open_bill(bill_id)

        if not bill.items:
            raise ValueError("空账单不能结账")

        # 电子支付不允许多付（无找零场景）
        if payment_method != PaymentMethod.CASH and amount_fen != bill.total_fen:
            raise ValueError(
                f"电子支付金额必须精确匹配: 应收{bill.total_fen}分, 实收{amount_fen}分"
            )

        # 现金支付允许多付（找零）
        if amount_fen < bill.total_fen:
            raise ValueError(
                f"支付金额不足: 应收{bill.total_fen}分, 实收{amount_fen}分"
            )

        change_fen = amount_fen - bill.total_fen
        now = datetime.utcnow().isoformat()

        bill.status = BillStatus.SETTLED
        bill.payment_method = payment_method
        bill.settled_at = now

        result = SettlementResult(
            bill_id=bill_id,
            success=True,
            total_fen=bill.total_fen,
            paid_fen=amount_fen,
            change_fen=change_fen,
            payment_method=payment_method,
            settled_at=now,
            message="结账成功",
        )

        logger.info(
            "pos.bill_settled",
            bill_id=bill_id,
            total_fen=bill.total_fen,
            paid_fen=amount_fen,
            change_fen=change_fen,
            payment_method=payment_method.value,
        )
        return result

    def void_bill(self, bill_id: str, reason: str) -> bool:
        """
        作废账单

        已结账的账单不能作废（需走退款流程）。
        """
        bill = self._get_bill(bill_id)

        if bill.status == BillStatus.VOIDED:
            raise ValueError("账单已作废，不能重复操作")
        if bill.status == BillStatus.SETTLED:
            raise ValueError("已结账账单不能作废，请走退款流程")

        bill.status = BillStatus.VOIDED
        bill.void_reason = reason

        logger.info("pos.bill_voided", bill_id=bill_id, reason=reason)
        return True

    def get_active_bills(self, store_id: str) -> List[Bill]:
        """
        获取门店所有未结账账单

        按创建时间正序排列，方便服务员查看最早开台的桌。
        """
        active = [
            b for b in self._bills.values()
            if b.store_id == store_id and b.status == BillStatus.OPEN
        ]
        active.sort(key=lambda b: b.created_at)
        return active

    def get_bill_detail(self, bill_id: str) -> BillDetail:
        """获取账单完整详情"""
        bill = self._get_bill(bill_id)
        summary = BillSummary(
            bill_id=bill_id,
            subtotal_fen=bill.subtotal_fen,
            discount_fen=bill.discount_fen,
            total_fen=bill.total_fen,
            item_count=sum(item.quantity for item in bill.items),
        )
        return BillDetail(bill=bill, summary=summary)

    # ============================================================
    # 内部方法
    # ============================================================

    def _get_bill(self, bill_id: str) -> Bill:
        """获取账单，不存在则抛异常"""
        bill = self._bills.get(bill_id)
        if not bill:
            raise ValueError(f"账单不存在: bill_id={bill_id}")
        return bill

    def _get_open_bill(self, bill_id: str) -> Bill:
        """获取处于open状态的账单"""
        bill = self._get_bill(bill_id)
        if bill.status != BillStatus.OPEN:
            raise ValueError(
                f"账单状态不允许此操作: bill_id={bill_id}, status={bill.status.value}"
            )
        return bill

    def _recalculate(self, bill: Bill) -> None:
        """
        重算账单合计

        计算逻辑：
        1. subtotal = 所有菜品小计之和
        2. discount = 根据折扣类型计算优惠金额
        3. total = subtotal - discount（最低为0，不会出现负数）
        """
        # 菜品合计
        bill.subtotal_fen = sum(item.subtotal_fen for item in bill.items)

        # 计算折扣金额
        bill.discount_fen = 0
        if bill.discount:
            if bill.discount.discount_type == DiscountType.PERCENTAGE:
                # 85折 = 原价 × (100 - 85) / 100
                bill.discount_fen = bill.subtotal_fen * (100 - bill.discount.discount_value) // 100
            elif bill.discount.discount_type == DiscountType.FIXED_AMOUNT:
                bill.discount_fen = bill.discount.discount_value
            elif bill.discount.discount_type == DiscountType.COUPON:
                bill.discount_fen = bill.discount.discount_value

        # 应收金额（不低于0）
        bill.total_fen = max(0, bill.subtotal_fen - bill.discount_fen)


# 模块级单例（POC阶段内存存储）
pos_terminal_service = PosTerminalService()
