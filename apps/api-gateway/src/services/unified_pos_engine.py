"""
统一 POS 收银引擎 — 平替天财商龙的核心消费处理

覆盖场景：堂食 / 外卖 / 自提 / 外摆 / 宴会 / 套餐 / 海鲜称重
支持设备：小程序 / 手机 / 平板 / 电视 / 触摸屏 / POS终端

核心能力：
  1. 多场景开单（堂食/外卖/自提/外摆/宴会）
  2. 海鲜复杂下单（称重/时价/按只/做法选择）
  3. 套餐组合下单（含子菜品拆分）
  4. 会员识别 + 会员价 + 积分抵扣 + 余额支付
  5. 平台券核销（美团/抖音/大众点评）
  6. 混合支付结账
  7. 厨打分单（按工位自动路由到KDS/打印机）
  8. 影子模式双写（同步天财商龙）

金额规则：内部计算用分(fen)，API返回同时提供 fen 和 yuan
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class ConsumptionScene(str, Enum):
    """消费场景"""
    DINE_IN = "dine_in"          # 堂食
    TAKEAWAY = "takeaway"        # 外卖
    SELF_PICKUP = "self_pickup"  # 自提
    OUTDOOR = "outdoor"          # 外摆
    BANQUET = "banquet"          # 宴会
    SET_MEAL = "set_meal"        # 套餐消费
    DELIVERY = "delivery"        # 配送（自营）


class PricingMode(str, Enum):
    """计价模式"""
    FIXED = "fixed"            # 固定价（份/例）
    BY_WEIGHT = "by_weight"    # 按重量（斤/两/克）
    MARKET_PRICE = "market"    # 时价（海鲜活物，需现场输入）
    BY_COUNT = "by_count"      # 按个（海鲜按只/条/尾）
    PACKAGE = "package"        # 套餐（含多子菜品）


class DeviceType(str, Enum):
    """点单设备类型"""
    MINI_PROGRAM = "mini_program"
    MOBILE = "mobile"
    TABLET = "tablet"
    TV = "tv"
    TOUCH_SCREEN = "touch_screen"
    KDS_SCREEN = "kds_screen"
    POS_TERMINAL = "pos_terminal"


class PaymentMethod(str, Enum):
    """支付方式"""
    CASH = "cash"
    WECHAT = "wechat"
    ALIPAY = "alipay"
    MEMBER_BALANCE = "member_balance"
    MEMBER_POINTS = "member_points"
    BANK_CARD = "bank_card"
    COUPON = "coupon"
    CREDIT = "credit"  # 挂账


class OrderPhase(str, Enum):
    """订单阶段"""
    DRAFT = "draft"          # 草稿（多端暂存）
    PLACED = "placed"        # 已下单
    CONFIRMED = "confirmed"  # 已确认（厨房已接）
    PREPARING = "preparing"  # 制作中
    READY = "ready"          # 待上菜/待取
    SERVED = "served"        # 已上菜
    SETTLING = "settling"    # 结账中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消
    REFUNDED = "refunded"    # 已退款


class KitchenStation(str, Enum):
    """厨房工位"""
    HOT_WOK = "hot_wok"           # 炒锅
    STEAMER = "steamer"           # 蒸柜
    DEEP_FRY = "deep_fry"        # 油炸
    COLD_DISH = "cold_dish"       # 凉菜
    SEAFOOD = "seafood"           # 海鲜档口
    SOUP = "soup"                 # 汤/煲
    PASTRY = "pastry"             # 面点
    GRILL = "grill"               # 烧烤/铁板
    BEVERAGE = "beverage"         # 饮品
    PREP = "prep"                 # 打荷/备料


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class OrderItemSpec:
    """订单菜品明细"""
    def __init__(
        self,
        dish_id: str,
        dish_name: str,
        pricing_mode: PricingMode = PricingMode.FIXED,
        quantity: int = 1,
        unit_price_fen: int = 0,
        spec_id: Optional[str] = None,
        spec_name: Optional[str] = None,
        weight_g: Optional[float] = None,
        weight_unit: str = "g",
        market_price_fen: Optional[int] = None,
        cooking_method: Optional[str] = None,
        notes: Optional[str] = None,
        kitchen_station: Optional[KitchenStation] = None,
        package_items: Optional[List[Dict[str, Any]]] = None,
        is_gift: bool = False,
    ):
        self.item_id = str(uuid.uuid4())
        self.dish_id = dish_id
        self.dish_name = dish_name
        self.pricing_mode = pricing_mode
        self.quantity = quantity
        self.unit_price_fen = unit_price_fen
        self.spec_id = spec_id
        self.spec_name = spec_name
        self.weight_g = weight_g
        self.weight_unit = weight_unit
        self.market_price_fen = market_price_fen
        self.cooking_method = cooking_method
        self.notes = notes
        self.kitchen_station = kitchen_station
        self.package_items = package_items or []
        self.is_gift = is_gift

    def calculate_subtotal_fen(self) -> int:
        """计算菜品小计（分）"""
        if self.is_gift:
            return 0

        if self.pricing_mode == PricingMode.BY_WEIGHT and self.weight_g:
            # 按重量：单价(分/500g) × 实际重量(g) / 500g
            weight_jin = Decimal(str(self.weight_g)) / Decimal("500")
            return int(Decimal(str(self.unit_price_fen)) * weight_jin)

        if self.pricing_mode == PricingMode.MARKET_PRICE and self.market_price_fen:
            return self.market_price_fen * self.quantity

        if self.pricing_mode == PricingMode.PACKAGE:
            # 套餐价以整体价格为准
            return self.unit_price_fen * self.quantity

        return self.unit_price_fen * self.quantity

    def to_dict(self) -> Dict[str, Any]:
        subtotal_fen = self.calculate_subtotal_fen()
        return {
            "item_id": self.item_id,
            "dish_id": self.dish_id,
            "dish_name": self.dish_name,
            "pricing_mode": self.pricing_mode.value,
            "quantity": self.quantity,
            "unit_price_fen": self.unit_price_fen,
            "unit_price_yuan": str(Decimal(str(self.unit_price_fen)) / 100),
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "weight_g": self.weight_g,
            "weight_unit": self.weight_unit,
            "market_price_fen": self.market_price_fen,
            "cooking_method": self.cooking_method,
            "notes": self.notes,
            "kitchen_station": self.kitchen_station.value if self.kitchen_station else None,
            "subtotal_fen": subtotal_fen,
            "subtotal_yuan": str(Decimal(str(subtotal_fen)) / 100),
            "is_gift": self.is_gift,
            "package_items": self.package_items,
        }


class CouponApplication:
    """优惠券应用"""
    def __init__(
        self,
        coupon_code: str,
        platform: str,
        coupon_value_fen: int,
        coupon_type: str = "voucher",
        min_order_fen: int = 0,
    ):
        self.coupon_code = coupon_code
        self.platform = platform
        self.coupon_value_fen = coupon_value_fen
        self.coupon_type = coupon_type
        self.min_order_fen = min_order_fen


class PaymentEntry:
    """支付条目"""
    def __init__(self, method: PaymentMethod, amount_fen: int, reference: str = ""):
        self.method = method
        self.amount_fen = amount_fen
        self.reference = reference


# ── 统一 POS 引擎 ─────────────────────────────────────────────────────────────

class UnifiedPOSEngine:
    """
    统一 POS 收银引擎。

    作为天财商龙的影子替代，提供完整的POS收银能力。
    影子模式下，所有操作同时写入天财商龙和屯象OS；
    独立模式下，直接操作屯象OS数据库。
    """

    def __init__(
        self,
        store_id: str,
        brand_id: str,
        shadow_adapter=None,
        db_session=None,
    ):
        self.store_id = store_id
        self.brand_id = brand_id
        self.shadow_adapter = shadow_adapter  # 天财商龙适配器（影子模式时使用）
        self.db = db_session
        self._order_cache: Dict[str, Dict[str, Any]] = {}

    # 影子同步最大重试次数，超过后标记需人工同步
    SHADOW_MAX_RETRIES = 3

    def _record_shadow_failure(self, order: Dict[str, Any], error: str) -> None:
        """记录影子同步失败，累加重试计数，超过阈值标记需人工同步"""
        order["shadow_sync_status"] = "failed"
        order["shadow_sync_error"] = error
        retry_count = order.get("shadow_retry_count", 0) + 1
        order["shadow_retry_count"] = retry_count
        if retry_count >= self.SHADOW_MAX_RETRIES:
            order["shadow_requires_manual_sync"] = True
            logger.error(
                "影子同步多次失败，需人工介入",
                order_id=order.get("order_id"),
                retry_count=retry_count,
            )
        else:
            order["shadow_requires_manual_sync"] = order.get(
                "shadow_requires_manual_sync", False
            )

    # ── 开单 ──────────────────────────────────────────────────────────────────

    async def create_order(
        self,
        table_code: str,
        party_size: int,
        items: List[OrderItemSpec],
        scene: ConsumptionScene = ConsumptionScene.DINE_IN,
        device_type: DeviceType = DeviceType.POS_TERMINAL,
        waiter_id: Optional[str] = None,
        member_id: Optional[str] = None,
        reservation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建订单（支持所有消费场景 + 海鲜称重 + 套餐）。

        ¥影响：创建订单后预计收入 = sum(item.subtotal)
        """
        order_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # 计算金额
        subtotal_fen = sum(item.calculate_subtotal_fen() for item in items)

        # 会员折扣
        member_discount_fen = 0
        member_info = None
        if member_id:
            member_info = await self._get_member_info(member_id)
            if member_info:
                discount_rate = member_info.get("discount_rate", 100)
                if discount_rate < 100:
                    member_discount_fen = subtotal_fen - int(
                        Decimal(str(subtotal_fen)) * Decimal(str(discount_rate)) / 100
                    )

        total_fen = subtotal_fen - member_discount_fen

        order = {
            "order_id": order_id,
            "order_number": self._generate_order_number(scene),
            "store_id": self.store_id,
            "brand_id": self.brand_id,
            "table_code": table_code,
            "party_size": party_size,
            "scene": scene.value,
            "device_type": device_type.value,
            "waiter_id": waiter_id,
            "member_id": member_id,
            "member_info": member_info,
            "reservation_id": reservation_id,
            "phase": OrderPhase.PLACED.value,
            "items": [item.to_dict() for item in items],
            "item_count": len(items),
            "subtotal_fen": subtotal_fen,
            "subtotal_yuan": str(Decimal(str(subtotal_fen)) / 100),
            "member_discount_fen": member_discount_fen,
            "coupon_discount_fen": 0,
            "total_fen": total_fen,
            "total_yuan": str(Decimal(str(total_fen)) / 100),
            "payments": [],
            "coupons": [],
            "created_at": now.isoformat(),
            "created_device": device_type.value,
        }

        self._order_cache[order_id] = order

        # 影子模式：同步到天财商龙
        if self.shadow_adapter:
            try:
                shadow_items = [
                    {
                        "dish_id": item.dish_id,
                        "qty": item.quantity,
                        "spec_id": item.spec_id,
                        "weight_g": item.weight_g,
                        "market_price_fen": item.market_price_fen,
                        "notes": item.notes,
                        "cooking_method": item.cooking_method,
                    }
                    for item in items
                ]
                shadow_result = await self.shadow_adapter.create_order(
                    table_code=table_code,
                    party_size=party_size,
                    items=shadow_items,
                    scene=scene,
                    device_type=device_type,
                    waiter_code=waiter_id,
                    member_id=member_id,
                )
                order["shadow_order_id"] = shadow_result.get("order_id")
                order["shadow_sync_status"] = "synced"
            except Exception as e:
                logger.warning("影子同步创建订单失败", error=str(e), order_id=order_id)
                self._record_shadow_failure(order, str(e))

        logger.info(
            "订单已创建",
            order_id=order_id,
            scene=scene.value,
            total_yuan=order["total_yuan"],
            item_count=len(items),
        )
        return order

    # ── 加菜 ──────────────────────────────────────────────────────────────────

    async def add_items(
        self,
        order_id: str,
        items: List[OrderItemSpec],
        device_type: DeviceType = DeviceType.POS_TERMINAL,
    ) -> Dict[str, Any]:
        """追加点菜（加菜）"""
        order = self._order_cache.get(order_id)
        if not order:
            raise ValueError(f"订单不存在: {order_id}")

        new_items = [item.to_dict() for item in items]
        order["items"].extend(new_items)
        order["item_count"] = len(order["items"])

        # 重新计算金额
        add_fen = sum(item.calculate_subtotal_fen() for item in items)
        order["subtotal_fen"] += add_fen
        order["total_fen"] = (
            order["subtotal_fen"]
            - order["member_discount_fen"]
            - order["coupon_discount_fen"]
        )
        order["subtotal_yuan"] = str(Decimal(str(order["subtotal_fen"])) / 100)
        order["total_yuan"] = str(Decimal(str(order["total_fen"])) / 100)

        # 影子同步
        if self.shadow_adapter and order.get("shadow_order_id"):
            try:
                await self.shadow_adapter.add_dishes_to_order(
                    order["shadow_order_id"],
                    [{"dish_id": item.dish_id, "qty": item.quantity} for item in items],
                )
            except Exception as e:
                logger.warning("影子同步加菜失败", error=str(e))
                self._record_shadow_failure(order, str(e))

        return order

    # ── 退菜 ──────────────────────────────────────────────────────────────────

    async def void_item(
        self,
        order_id: str,
        item_id: str,
        reason: str,
        operator_id: str,
    ) -> Dict[str, Any]:
        """退菜"""
        order = self._order_cache.get(order_id)
        if not order:
            raise ValueError(f"订单不存在: {order_id}")

        removed = None
        remaining = []
        for item in order["items"]:
            if item["item_id"] == item_id and removed is None:
                removed = item
            else:
                remaining.append(item)

        if not removed:
            raise ValueError(f"菜品不存在: {item_id}")

        order["items"] = remaining
        order["item_count"] = len(remaining)

        # 重新计算
        order["subtotal_fen"] -= removed["subtotal_fen"]
        order["total_fen"] = (
            order["subtotal_fen"]
            - order["member_discount_fen"]
            - order["coupon_discount_fen"]
        )
        order["subtotal_yuan"] = str(Decimal(str(order["subtotal_fen"])) / 100)
        order["total_yuan"] = str(Decimal(str(order["total_fen"])) / 100)

        logger.info("退菜", order_id=order_id, item=removed["dish_name"], reason=reason)
        return order

    # ── 应用优惠券 ────────────────────────────────────────────────────────────

    async def apply_coupon(
        self,
        order_id: str,
        coupon: CouponApplication,
    ) -> Dict[str, Any]:
        """
        应用优惠券（美团/抖音/大众点评/自有券）。

        验证规则：
          1. 券码有效性（调用平台验证接口）
          2. 最低消费门槛
          3. 优惠券叠加规则（同平台不叠加）
        """
        order = self._order_cache.get(order_id)
        if not order:
            raise ValueError(f"订单不存在: {order_id}")

        # 检查最低消费
        if order["subtotal_fen"] < coupon.min_order_fen:
            raise ValueError(
                f"未达到最低消费: 当前 ¥{Decimal(str(order['subtotal_fen'])) / 100}，"
                f"要求 ¥{Decimal(str(coupon.min_order_fen)) / 100}"
            )

        # 检查同平台不叠加
        for existing in order["coupons"]:
            if existing["platform"] == coupon.platform:
                raise ValueError(f"同平台券不可叠加: {coupon.platform}")

        # 验证券码（通过影子适配器调用天财商龙）
        if self.shadow_adapter:
            try:
                from packages.api_adapters.tiancai_shanglong.src.full_business_adapter import CouponPlatform
                verify = await self.shadow_adapter.verify_coupon(
                    coupon.coupon_code,
                    CouponPlatform(coupon.platform),
                )
                if not verify.get("valid"):
                    raise ValueError(f"券码无效: {coupon.coupon_code}")
            except ImportError:
                pass
            except ValueError:
                raise
            except Exception as e:
                logger.warning("券码验证异常，降级通过", error=str(e))

        # 应用优惠
        order["coupons"].append({
            "coupon_code": coupon.coupon_code,
            "platform": coupon.platform,
            "coupon_value_fen": coupon.coupon_value_fen,
            "coupon_type": coupon.coupon_type,
        })
        order["coupon_discount_fen"] += coupon.coupon_value_fen
        order["total_fen"] = max(0, (
            order["subtotal_fen"]
            - order["member_discount_fen"]
            - order["coupon_discount_fen"]
        ))
        order["total_yuan"] = str(Decimal(str(order["total_fen"])) / 100)

        logger.info(
            "优惠券已应用",
            order_id=order_id,
            platform=coupon.platform,
            value_yuan=str(Decimal(str(coupon.coupon_value_fen)) / 100),
        )
        return order

    # ── 结账 ──────────────────────────────────────────────────────────────────

    async def settle(
        self,
        order_id: str,
        payments: List[PaymentEntry],
    ) -> Dict[str, Any]:
        """
        结账（支持混合支付：微信+会员余额+积分+优惠券+现金）。

        ¥影响：实收 = sum(payments) - 找零
        """
        order = self._order_cache.get(order_id)
        if not order:
            raise ValueError(f"订单不存在: {order_id}")

        # 影子同步多次失败的订单，记录警告但不阻断结账
        if order.get("shadow_requires_manual_sync"):
            logger.warning(
                "结账订单存在未同步的影子数据，需人工同步",
                order_id=order_id,
                shadow_retry_count=order.get("shadow_retry_count", 0),
            )

        total_paid_fen = sum(p.amount_fen for p in payments)
        total_due_fen = order["total_fen"]

        if total_paid_fen < total_due_fen:
            shortage = Decimal(str(total_due_fen - total_paid_fen)) / 100
            raise ValueError(f"支付不足: 还差 ¥{shortage}")

        change_fen = total_paid_fen - total_due_fen

        # 处理会员余额支付
        member_points_earned = 0
        for p in payments:
            if p.method == PaymentMethod.MEMBER_BALANCE and order.get("member_id"):
                if self.shadow_adapter:
                    try:
                        await self.shadow_adapter.member_consume(
                            order["member_id"],
                            order_id,
                            p.amount_fen,
                            pay_type="balance",
                        )
                    except Exception as e:
                        logger.warning("会员消费同步失败", error=str(e))
                # 消费1元=1积分
                member_points_earned += p.amount_fen // 100

            elif p.method == PaymentMethod.MEMBER_POINTS and order.get("member_id"):
                if self.shadow_adapter:
                    try:
                        await self.shadow_adapter.member_consume(
                            order["member_id"],
                            order_id,
                            p.amount_fen,
                            pay_type="points",
                        )
                    except Exception as e:
                        logger.warning("积分抵扣同步失败", error=str(e))

        # 核销优惠券
        for coupon_info in order.get("coupons", []):
            if self.shadow_adapter:
                try:
                    await self.shadow_adapter.consume_coupon(
                        coupon_info["coupon_code"],
                        order_id,
                    )
                except Exception as e:
                    logger.warning("券核销同步失败", error=str(e))

        # 影子模式结账同步
        if self.shadow_adapter and order.get("shadow_order_id"):
            try:
                await self.shadow_adapter.settle_order(
                    order["shadow_order_id"],
                    [{"method": p.method.value, "amount_fen": p.amount_fen} for p in payments],
                    member_id=order.get("member_id"),
                    coupon_codes=[c["coupon_code"] for c in order.get("coupons", [])],
                )
            except Exception as e:
                logger.warning("影子同步结账失败", error=str(e))
                self._record_shadow_failure(order, str(e))

        # 更新订单状态
        settle_time = datetime.utcnow()
        order["phase"] = OrderPhase.COMPLETED.value
        order["payments"] = [
            {
                "method": p.method.value,
                "amount_fen": p.amount_fen,
                "amount_yuan": str(Decimal(str(p.amount_fen)) / 100),
                "reference": p.reference,
            }
            for p in payments
        ]
        order["paid_fen"] = total_paid_fen
        order["paid_yuan"] = str(Decimal(str(total_paid_fen)) / 100)
        order["change_fen"] = change_fen
        order["change_yuan"] = str(Decimal(str(change_fen)) / 100)
        order["member_points_earned"] = member_points_earned
        order["settled_at"] = settle_time.isoformat()

        logger.info(
            "订单已结账",
            order_id=order_id,
            total_yuan=order["total_yuan"],
            paid_yuan=order["paid_yuan"],
            payments=[p.method.value for p in payments],
        )

        return {
            "order_id": order_id,
            "total_fen": total_due_fen,
            "total_yuan": str(Decimal(str(total_due_fen)) / 100),
            "paid_fen": total_paid_fen,
            "paid_yuan": str(Decimal(str(total_paid_fen)) / 100),
            "change_fen": change_fen,
            "change_yuan": str(Decimal(str(change_fen)) / 100),
            "member_points_earned": member_points_earned,
            "settled_at": settle_time.isoformat(),
            "payments": order["payments"],
            "coupons_consumed": order.get("coupons", []),
        }

    # ── 厨打分单 ──────────────────────────────────────────────────────────────

    async def dispatch_to_kitchen(
        self,
        order_id: str,
        priority: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        按工位拆分厨打单，路由到对应KDS/打印机。

        返回：按工位分组的厨打票列表
        """
        order = self._order_cache.get(order_id)
        if not order:
            raise ValueError(f"订单不存在: {order_id}")

        # 按工位分组
        station_groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in order["items"]:
            station = item.get("kitchen_station") or KitchenStation.HOT_WOK.value
            if station not in station_groups:
                station_groups[station] = []
            station_groups[station].append(item)

        tickets = []
        for station, items in station_groups.items():
            ticket = {
                "ticket_id": str(uuid.uuid4()),
                "order_id": order_id,
                "order_number": order["order_number"],
                "table_code": order["table_code"],
                "station": station,
                "priority": priority,
                "scene": order["scene"],
                "items": [
                    {
                        "dish_name": i["dish_name"],
                        "quantity": i["quantity"],
                        "spec_name": i.get("spec_name", ""),
                        "weight_g": i.get("weight_g"),
                        "cooking_method": i.get("cooking_method", ""),
                        "notes": i.get("notes", ""),
                    }
                    for i in items
                ],
                "item_count": len(items),
                "dispatched_at": datetime.utcnow().isoformat(),
                "status": "received",
            }
            tickets.append(ticket)

        # 影子同步
        if self.shadow_adapter and order.get("shadow_order_id"):
            try:
                await self.shadow_adapter.send_kitchen_order(
                    order["shadow_order_id"],
                    order["table_code"],
                    [
                        {
                            "dish_id": i["dish_id"],
                            "dish_name": i["dish_name"],
                            "qty": i["quantity"],
                            "station": i.get("kitchen_station", ""),
                            "notes": i.get("notes", ""),
                        }
                        for i in order["items"]
                    ],
                    priority=priority,
                )
            except Exception as e:
                logger.warning("影子同步厨打失败", error=str(e))
                self._record_shadow_failure(order, str(e))

        order["phase"] = OrderPhase.CONFIRMED.value
        order["kitchen_tickets"] = tickets

        logger.info(
            "厨打已下发",
            order_id=order_id,
            stations=list(station_groups.keys()),
            ticket_count=len(tickets),
        )
        return tickets

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """获取订单详情"""
        return self._order_cache.get(order_id)

    def get_active_orders(self) -> List[Dict[str, Any]]:
        """获取所有进行中的订单"""
        active_phases = {
            OrderPhase.PLACED.value,
            OrderPhase.CONFIRMED.value,
            OrderPhase.PREPARING.value,
            OrderPhase.READY.value,
            OrderPhase.SERVED.value,
            OrderPhase.SETTLING.value,
        }
        return [
            o for o in self._order_cache.values()
            if o.get("phase") in active_phases
        ]

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _get_member_info(self, member_id: str) -> Optional[Dict[str, Any]]:
        """获取会员信息"""
        if self.shadow_adapter:
            try:
                return await self.shadow_adapter.query_member(card_no=member_id)
            except Exception:
                pass
        return None

    def _generate_order_number(self, scene: ConsumptionScene) -> str:
        """生成订单号：场景前缀 + 日期 + 序号"""
        prefix_map = {
            ConsumptionScene.DINE_IN: "DI",
            ConsumptionScene.TAKEAWAY: "TA",
            ConsumptionScene.SELF_PICKUP: "SP",
            ConsumptionScene.OUTDOOR: "OD",
            ConsumptionScene.BANQUET: "BQ",
            ConsumptionScene.SET_MEAL: "SM",
            ConsumptionScene.DELIVERY: "DL",
        }
        prefix = prefix_map.get(scene, "XX")
        date_part = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        seq = str(uuid.uuid4().int)[:6]
        return f"{prefix}{date_part}{seq}"
