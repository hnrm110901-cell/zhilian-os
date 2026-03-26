"""
天财商龙全业务适配器 — 预定/会员/厨打/KDS/券核销/结账

扩展基础 adapter.py，覆盖天财商龙开放平台全部业务接口：
  - 预定管理（预定/排队/宴会）
  - 会员体系（查询/充值/积分/等级）
  - 厨打 & KDS（下单后厨打分单/KDS状态同步）
  - 平台券核销（美团/抖音/大众点评券码验证）
  - 收银结账（多支付方式/会员余额/挂账）
  - 菜品同步（含海鲜称重/套餐/时价菜）
  - 桌台管理（开台/换台/并台/清台）

官方文档：http://doc.wuuxiang.com/showdoc/web/#/46
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

from .adapter import TiancaiShanglongAdapter

logger = structlog.get_logger()

# ── API 路径常量 ──────────────────────────────────────────────────────────────

_DISH_LIST_PATH = "/api/datatransfer/getdishdata"
_DISH_CATEGORY_PATH = "/api/datatransfer/getdishcategorydata"
_TABLE_LIST_PATH = "/api/datatransfer/gettabledata"
_TABLE_STATUS_PATH = "/api/datatransfer/gettablestatusdata"
_MEMBER_QUERY_PATH = "/api/member/query"
_MEMBER_CONSUME_PATH = "/api/member/consume"
_MEMBER_RECHARGE_PATH = "/api/member/recharge"
_MEMBER_POINTS_PATH = "/api/member/points"
_RESERVATION_LIST_PATH = "/api/reservation/list"
_RESERVATION_CREATE_PATH = "/api/reservation/create"
_RESERVATION_CANCEL_PATH = "/api/reservation/cancel"
_QUEUE_STATUS_PATH = "/api/queue/status"
_QUEUE_ADD_PATH = "/api/queue/add"
_COUPON_VERIFY_PATH = "/api/coupon/verify"
_COUPON_CONSUME_PATH = "/api/coupon/consume"
_KITCHEN_ORDER_PATH = "/api/kitchen/sendorder"
_KITCHEN_STATUS_PATH = "/api/kitchen/status"
_PAYMENT_SETTLE_PATH = "/api/payment/settle"
_PAYMENT_METHODS_PATH = "/api/payment/methods"
_ORDER_CREATE_PATH = "/api/order/create"
_ORDER_ADD_DISH_PATH = "/api/order/adddish"
_ORDER_VOID_PATH = "/api/order/void"


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class DishPricingMode(str, Enum):
    """菜品计价模式"""
    FIXED = "fixed"            # 固定价格（份/例）
    BY_WEIGHT = "by_weight"    # 按重量（斤/两/克）
    MARKET_PRICE = "market"    # 时价（海鲜活物）
    BY_COUNT = "by_count"      # 按个（如海鲜按只）
    PACKAGE = "package"        # 套餐


class TableAction(str, Enum):
    """桌台操作"""
    OPEN = "open"         # 开台
    TRANSFER = "transfer" # 换台
    MERGE = "merge"       # 并台
    CLEAR = "clear"       # 清台
    SPLIT = "split"       # 拆台


class KDSOrderStatus(str, Enum):
    """KDS 出餐状态"""
    RECEIVED = "received"    # 已接单
    COOKING = "cooking"      # 制作中
    PLATING = "plating"      # 装盘中
    READY = "ready"          # 出餐就绪
    SERVED = "served"        # 已上菜
    RETURNED = "returned"    # 退菜


class CouponPlatform(str, Enum):
    """券平台来源"""
    MEITUAN = "meituan"          # 美团
    DOUYIN = "douyin"            # 抖音
    DIANPING = "dianping"        # 大众点评
    WEISHENGHUO = "weishenghuo"  # 微生活
    SELF = "self"                # 自有优惠券


class ConsumptionScene(str, Enum):
    """消费场景"""
    DINE_IN = "dine_in"          # 堂食
    TAKEAWAY = "takeaway"        # 外卖
    SELF_PICKUP = "self_pickup"  # 自提
    OUTDOOR = "outdoor"          # 外摆
    BANQUET = "banquet"          # 宴会
    SET_MEAL = "set_meal"        # 套餐
    DELIVERY = "delivery"        # 配送


class DeviceType(str, Enum):
    """点单设备类型"""
    MINI_PROGRAM = "mini_program"  # 小程序
    MOBILE = "mobile"              # 手机
    TABLET = "tablet"              # 平板
    TV = "tv"                      # 电视
    TOUCH_SCREEN = "touch_screen"  # 触摸屏（前台收银机）
    KDS_SCREEN = "kds_screen"      # 厨房显示屏
    POS_TERMINAL = "pos_terminal"  # POS 收银终端


# ── 全业务适配器 ──────────────────────────────────────────────────────────────

class TiancaiFullBusinessAdapter(TiancaiShanglongAdapter):
    """
    天财商龙全业务适配器。

    继承基础适配器的认证和请求机制，扩展全部业务接口。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        # KDS 回调 URL（屯象OS 接收厨房状态变更）
        self.kds_callback_url = config.get("kds_callback_url", "")
        logger.info("天财商龙全业务适配器已初始化")

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. 菜品同步（含海鲜称重/套餐/时价菜）
    # ═══════════════════════════════════════════════════════════════════════════

    async def sync_dishes(
        self,
        update_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        同步菜品主数据（含海鲜称重菜、套餐、时价菜）。

        Args:
            update_time: 增量同步时间点 yyyy-MM-dd HH:mm:ss

        Returns:
            标准化菜品列表，每个菜品包含 pricing_mode 字段
        """
        params: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
        }
        if update_time:
            params["updateTime"] = update_time

        raw = await self._request(_DISH_LIST_PATH, params)
        dishes = raw if isinstance(raw, list) else raw.get("dishList", [])

        result = []
        for d in dishes:
            pricing_mode = self._detect_pricing_mode(d)
            result.append({
                "dish_id": str(d.get("item_code", d.get("item_id", ""))),
                "name": d.get("item_name", ""),
                "category_id": d.get("big_class_code", ""),
                "category_name": d.get("big_class_name", ""),
                "sub_category": d.get("small_class_name", ""),
                "price_fen": int(d.get("item_price", 0)),
                "price_yuan": Decimal(str(d.get("item_price", 0))) / 100,
                "unit": d.get("item_unit", "份"),
                "pricing_mode": pricing_mode.value,
                "is_package": bool(d.get("is_pkg", 0)),
                "package_items": d.get("pkg_items", []),
                "is_weighable": pricing_mode in (
                    DishPricingMode.BY_WEIGHT,
                    DishPricingMode.MARKET_PRICE,
                ),
                "is_market_price": pricing_mode == DishPricingMode.MARKET_PRICE,
                "min_order_qty": d.get("min_qty", 1),
                "step_qty": d.get("step_qty", 1),
                "weight_unit": d.get("weight_unit", "斤") if pricing_mode == DishPricingMode.BY_WEIGHT else None,
                "kitchen_station": d.get("cook_station", d.get("print_scheme", "")),
                "prep_time_min": d.get("cook_time", 0),
                "image_url": d.get("item_img", ""),
                "is_available": d.get("item_status", 1) == 1,
                "spicy_level": d.get("spicy_level", 0),
                "allergens": d.get("allergens", []),
                "specs": self._parse_dish_specs(d),
                "raw": d,
            })

        logger.info("菜品同步完成", count=len(result))
        return result

    def _detect_pricing_mode(self, dish: Dict[str, Any]) -> DishPricingMode:
        """根据菜品属性检测计价模式"""
        if dish.get("is_pkg", 0):
            return DishPricingMode.PACKAGE
        unit = str(dish.get("item_unit", "")).lower()
        if unit in ("斤", "两", "克", "kg", "g"):
            return DishPricingMode.BY_WEIGHT
        if dish.get("is_market_price", 0) or dish.get("item_price", 0) == 0:
            return DishPricingMode.MARKET_PRICE
        if unit in ("只", "条", "尾", "个"):
            return DishPricingMode.BY_COUNT
        return DishPricingMode.FIXED

    def _parse_dish_specs(self, dish: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析菜品多规格（大/中/小份, 海鲜不同做法等）"""
        specs = dish.get("specs", dish.get("item_specs", []))
        if not specs:
            return []
        return [
            {
                "spec_id": str(s.get("spec_id", "")),
                "spec_name": s.get("spec_name", ""),
                "price_fen": int(s.get("spec_price", 0)),
                "price_yuan": Decimal(str(s.get("spec_price", 0))) / 100,
            }
            for s in (specs if isinstance(specs, list) else [])
        ]

    async def sync_dish_categories(self) -> List[Dict[str, Any]]:
        """同步菜品分类"""
        params = {"centerId": self.center_id, "shopId": self.shop_id}
        raw = await self._request(_DISH_CATEGORY_PATH, params)
        categories = raw if isinstance(raw, list) else raw.get("categoryList", [])
        return [
            {
                "category_id": str(c.get("big_class_code", "")),
                "name": c.get("big_class_name", ""),
                "sort_order": c.get("sort_no", 0),
            }
            for c in categories
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. 桌台管理（开台/换台/并台/清台）
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_tables(self) -> List[Dict[str, Any]]:
        """获取全部桌台及当前状态"""
        params = {"centerId": self.center_id, "shopId": self.shop_id}
        raw = await self._request(_TABLE_LIST_PATH, params)
        tables = raw if isinstance(raw, list) else raw.get("tableList", [])
        return [
            {
                "table_id": str(t.get("point_id", "")),
                "table_code": t.get("point_code", ""),
                "table_name": t.get("point_name", ""),
                "area": t.get("area_name", ""),
                "capacity": int(t.get("max_people", 0)),
                "min_people": int(t.get("min_people", 0)),
                "status": self._map_table_status(t.get("point_status", 0)),
                "current_order_id": t.get("bs_id"),
                "open_time": t.get("open_time"),
            }
            for t in tables
        ]

    def _map_table_status(self, status_code: int) -> str:
        """天财商龙桌台状态码映射"""
        mapping = {0: "free", 1: "occupied", 2: "reserved", 3: "cleaning", 4: "disabled"}
        return mapping.get(status_code, "unknown")

    async def get_table_realtime_status(self) -> List[Dict[str, Any]]:
        """获取桌台实时状态（含就餐人数、已点菜品数等）"""
        params = {"centerId": self.center_id, "shopId": self.shop_id}
        raw = await self._request(_TABLE_STATUS_PATH, params)
        return raw if isinstance(raw, list) else raw.get("statusList", [])

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. 预定 & 排队
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_reservations(
        self,
        date: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询预定列表"""
        params: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "reserveDate": date,
        }
        if status:
            params["status"] = status
        raw = await self._request(_RESERVATION_LIST_PATH, params)
        reservations = raw if isinstance(raw, list) else raw.get("reserveList", [])
        return [
            {
                "reservation_id": str(r.get("reserve_id", "")),
                "customer_name": r.get("customer_name", ""),
                "customer_phone": r.get("customer_phone", ""),
                "party_size": int(r.get("people_num", 0)),
                "reservation_date": r.get("reserve_date", ""),
                "reservation_time": r.get("reserve_time", ""),
                "table_code": r.get("point_code", ""),
                "status": r.get("status", "pending"),
                "meal_type": r.get("meal_type", "lunch"),
                "special_requests": r.get("remark", ""),
                "source": r.get("source", "direct"),
            }
            for r in reservations
        ]

    async def create_reservation(
        self,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        reserve_date: str,
        reserve_time: str,
        table_code: Optional[str] = None,
        meal_type: str = "lunch",
        remark: str = "",
    ) -> Dict[str, Any]:
        """创建预定"""
        params = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "customerName": customer_name,
            "customerPhone": customer_phone,
            "peopleNum": party_size,
            "reserveDate": reserve_date,
            "reserveTime": reserve_time,
            "mealType": meal_type,
            "remark": remark,
        }
        if table_code:
            params["pointCode"] = table_code
        return await self._request(_RESERVATION_CREATE_PATH, params)

    async def cancel_reservation(self, reservation_id: str, reason: str = "") -> Dict[str, Any]:
        """取消预定"""
        return await self._request(_RESERVATION_CANCEL_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "reserveId": reservation_id,
            "reason": reason,
        })

    async def get_queue_status(self) -> Dict[str, Any]:
        """获取当前排队状态"""
        params = {"centerId": self.center_id, "shopId": self.shop_id}
        raw = await self._request(_QUEUE_STATUS_PATH, params)
        return {
            "total_waiting": int(raw.get("waitingCount", 0)),
            "queue_groups": raw.get("queueGroups", []),
            "avg_wait_minutes": int(raw.get("avgWaitMin", 0)),
            "called_number": raw.get("calledNumber", ""),
        }

    async def add_to_queue(
        self,
        customer_name: str,
        customer_phone: str,
        party_size: int,
    ) -> Dict[str, Any]:
        """排队取号"""
        return await self._request(_QUEUE_ADD_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "customerName": customer_name,
            "customerPhone": customer_phone,
            "peopleNum": party_size,
        })

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. 会员体系
    # ═══════════════════════════════════════════════════════════════════════════

    async def query_member(
        self,
        card_no: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """查询会员信息"""
        params: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
        }
        if card_no:
            params["cardNo"] = card_no
        if phone:
            params["mobile"] = phone

        try:
            raw = await self._request(_MEMBER_QUERY_PATH, params)
        except Exception:
            return None

        if not raw:
            return None

        member = raw if isinstance(raw, dict) else (raw[0] if isinstance(raw, list) and raw else {})
        if not member:
            return None

        return {
            "member_id": str(member.get("member_id", "")),
            "card_no": member.get("card_no", ""),
            "name": member.get("member_name", ""),
            "phone": member.get("mobile", ""),
            "level": member.get("level_name", "普通会员"),
            "level_code": member.get("level_code", ""),
            "balance_fen": int(member.get("balance", 0)),
            "balance_yuan": Decimal(str(member.get("balance", 0))) / 100,
            "points": int(member.get("points", 0)),
            "total_consume_fen": int(member.get("total_consume", 0)),
            "total_consume_yuan": Decimal(str(member.get("total_consume", 0))) / 100,
            "visit_count": int(member.get("visit_count", 0)),
            "last_visit_date": member.get("last_visit_date", ""),
            "birthday": member.get("birthday", ""),
            "gender": member.get("sex", ""),
            "join_date": member.get("create_time", ""),
            "discount_rate": member.get("discount_rate", 100),
        }

    async def member_consume(
        self,
        member_id: str,
        order_id: str,
        amount_fen: int,
        pay_type: str = "balance",
    ) -> Dict[str, Any]:
        """会员消费（余额/积分抵扣）"""
        return await self._request(_MEMBER_CONSUME_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "memberId": member_id,
            "orderId": order_id,
            "amount": amount_fen,
            "payType": pay_type,
        })

    async def member_recharge(
        self,
        member_id: str,
        amount_fen: int,
        gift_fen: int = 0,
        pay_method: str = "wechat",
    ) -> Dict[str, Any]:
        """会员充值"""
        return await self._request(_MEMBER_RECHARGE_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "memberId": member_id,
            "amount": amount_fen,
            "giftAmount": gift_fen,
            "payMethod": pay_method,
        })

    async def query_member_points(self, member_id: str) -> Dict[str, Any]:
        """查询会员积分明细"""
        return await self._request(_MEMBER_POINTS_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "memberId": member_id,
        })

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. 平台券核销
    # ═══════════════════════════════════════════════════════════════════════════

    async def verify_coupon(
        self,
        coupon_code: str,
        platform: CouponPlatform = CouponPlatform.MEITUAN,
    ) -> Dict[str, Any]:
        """
        验证平台优惠券（美团/抖音/大众点评/微生活）。

        Returns:
            {
                "valid": bool, "coupon_name": str, "coupon_value_fen": int,
                "min_order_fen": int, "expire_time": str, "platform": str,
                "coupon_type": str (discount/voucher/package)
            }
        """
        raw = await self._request(_COUPON_VERIFY_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "couponCode": coupon_code,
            "platform": platform.value,
        })
        return {
            "valid": raw.get("isValid", False),
            "coupon_code": coupon_code,
            "coupon_name": raw.get("couponName", ""),
            "coupon_value_fen": int(raw.get("couponValue", 0)),
            "coupon_value_yuan": Decimal(str(raw.get("couponValue", 0))) / 100,
            "min_order_fen": int(raw.get("minOrderAmount", 0)),
            "expire_time": raw.get("expireTime", ""),
            "platform": platform.value,
            "coupon_type": raw.get("couponType", "voucher"),
        }

    async def consume_coupon(
        self,
        coupon_code: str,
        order_id: str,
        platform: CouponPlatform = CouponPlatform.MEITUAN,
    ) -> Dict[str, Any]:
        """核销优惠券"""
        return await self._request(_COUPON_CONSUME_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "couponCode": coupon_code,
            "orderId": order_id,
            "platform": platform.value,
        })

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. 厨打 & KDS
    # ═══════════════════════════════════════════════════════════════════════════

    async def send_kitchen_order(
        self,
        order_id: str,
        table_code: str,
        items: List[Dict[str, Any]],
        priority: int = 0,
        scene: ConsumptionScene = ConsumptionScene.DINE_IN,
    ) -> Dict[str, Any]:
        """
        下发厨打单（按工位自动拆分）。

        Args:
            order_id:   订单ID
            table_code: 桌号
            items:      菜品列表 [{dish_id, dish_name, qty, spec, station, notes}]
            priority:   优先级（0=普通, 1=加急, 2=VIP）
            scene:      消费场景

        Returns:
            {"kitchen_tickets": [...], "kds_dispatched": bool}
        """
        kitchen_items = []
        for item in items:
            kitchen_items.append({
                "itemCode": item.get("dish_id", ""),
                "itemName": item.get("dish_name", ""),
                "qty": item.get("qty", 1),
                "spec": item.get("spec", ""),
                "station": item.get("station", ""),
                "remark": item.get("notes", ""),
                "weight": item.get("weight"),
                "weightUnit": item.get("weight_unit"),
            })

        return await self._request(_KITCHEN_ORDER_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "orderId": order_id,
            "pointCode": table_code,
            "items": kitchen_items,
            "priority": priority,
            "scene": scene.value,
        })

    async def get_kitchen_status(
        self,
        order_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询厨房出餐状态"""
        params: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
        }
        if order_id:
            params["orderId"] = order_id

        raw = await self._request(_KITCHEN_STATUS_PATH, params)
        items = raw if isinstance(raw, list) else raw.get("kitchenItems", [])
        return [
            {
                "ticket_id": str(k.get("ticket_id", "")),
                "order_id": str(k.get("order_id", "")),
                "dish_name": k.get("item_name", ""),
                "station": k.get("station", ""),
                "status": self._map_kds_status(k.get("status", 0)),
                "start_time": k.get("start_time"),
                "ready_time": k.get("ready_time"),
                "elapsed_seconds": int(k.get("elapsed", 0)),
                "target_seconds": int(k.get("target_time", 0)),
            }
            for k in items
        ]

    def _map_kds_status(self, code: int) -> str:
        mapping = {
            0: KDSOrderStatus.RECEIVED.value,
            1: KDSOrderStatus.COOKING.value,
            2: KDSOrderStatus.PLATING.value,
            3: KDSOrderStatus.READY.value,
            4: KDSOrderStatus.SERVED.value,
            5: KDSOrderStatus.RETURNED.value,
        }
        return mapping.get(code, KDSOrderStatus.RECEIVED.value)

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. 收银结账（多支付方式 + 会员 + 挂账）
    # ═══════════════════════════════════════════════════════════════════════════

    async def settle_order(
        self,
        order_id: str,
        payments: List[Dict[str, Any]],
        member_id: Optional[str] = None,
        coupon_codes: Optional[List[str]] = None,
        scene: ConsumptionScene = ConsumptionScene.DINE_IN,
    ) -> Dict[str, Any]:
        """
        结账（支持混合支付）。

        Args:
            order_id:     订单ID
            payments:     支付方式列表 [{"method": "wechat", "amount_fen": 5000}, ...]
            member_id:    会员ID（如需会员价/积分抵扣）
            coupon_codes: 优惠券码列表
            scene:        消费场景

        Returns:
            {"settle_id": str, "total_fen": int, "paid_fen": int, "change_fen": int,
             "member_points_earned": int, "receipt_url": str}
        """
        pay_list = []
        for p in payments:
            pay_list.append({
                "payMethod": p["method"],
                "payAmount": p["amount_fen"],
                "payRemark": p.get("remark", ""),
            })

        params: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "orderId": order_id,
            "payList": pay_list,
            "scene": scene.value,
        }
        if member_id:
            params["memberId"] = member_id
        if coupon_codes:
            params["couponCodes"] = coupon_codes

        raw = await self._request(_PAYMENT_SETTLE_PATH, params)
        return {
            "settle_id": str(raw.get("settle_id", "")),
            "order_id": order_id,
            "total_fen": int(raw.get("total_amount", 0)),
            "total_yuan": Decimal(str(raw.get("total_amount", 0))) / 100,
            "paid_fen": int(raw.get("paid_amount", 0)),
            "paid_yuan": Decimal(str(raw.get("paid_amount", 0))) / 100,
            "change_fen": int(raw.get("change_amount", 0)),
            "discount_fen": int(raw.get("discount_amount", 0)),
            "member_points_earned": int(raw.get("points_earned", 0)),
            "member_balance_after_fen": raw.get("member_balance"),
            "receipt_url": raw.get("receipt_url", ""),
            "settle_time": raw.get("settle_time", ""),
        }

    async def get_payment_methods(self) -> List[Dict[str, Any]]:
        """获取门店支持的支付方式"""
        params = {"centerId": self.center_id, "shopId": self.shop_id}
        raw = await self._request(_PAYMENT_METHODS_PATH, params)
        methods = raw if isinstance(raw, list) else raw.get("methods", [])
        return [
            {
                "method_code": m.get("pay_code", ""),
                "method_name": m.get("pay_name", ""),
                "is_enabled": m.get("is_enabled", True),
                "supports_member": m.get("supports_member", False),
            }
            for m in methods
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. 下单（含海鲜称重、多规格）
    # ═══════════════════════════════════════════════════════════════════════════

    async def create_order(
        self,
        table_code: str,
        party_size: int,
        items: List[Dict[str, Any]],
        scene: ConsumptionScene = ConsumptionScene.DINE_IN,
        device_type: DeviceType = DeviceType.POS_TERMINAL,
        waiter_code: Optional[str] = None,
        member_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建订单（支持海鲜称重、多规格、套餐、备注）。

        Args:
            table_code:  桌号
            party_size:  就餐人数
            items: [{
                "dish_id": str, "qty": int, "spec_id": str?,
                "weight_g": float?, "market_price_fen": int?,
                "notes": str?, "cooking_method": str?
            }]
            scene:       消费场景
            device_type: 点单设备类型
            waiter_code: 服务员工号
            member_id:   会员ID

        Returns:
            {"order_id": str, "order_number": str, "table_code": str, ...}
        """
        order_items = []
        for item in items:
            oi: Dict[str, Any] = {
                "itemCode": item["dish_id"],
                "qty": item.get("qty", 1),
            }
            if item.get("spec_id"):
                oi["specId"] = item["spec_id"]
            if item.get("weight_g"):
                oi["weight"] = item["weight_g"]
                oi["weightUnit"] = "g"
            if item.get("market_price_fen"):
                oi["marketPrice"] = item["market_price_fen"]
            if item.get("notes"):
                oi["remark"] = item["notes"]
            if item.get("cooking_method"):
                oi["cookMethod"] = item["cooking_method"]
            order_items.append(oi)

        params: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "pointCode": table_code,
            "peopleNum": party_size,
            "items": order_items,
            "scene": scene.value,
            "deviceType": device_type.value,
        }
        if waiter_code:
            params["waiterCode"] = waiter_code
        if member_id:
            params["memberId"] = member_id

        raw = await self._request(_ORDER_CREATE_PATH, params)
        return {
            "order_id": str(raw.get("bs_id", raw.get("orderId", ""))),
            "order_number": str(raw.get("bs_code", raw.get("orderNo", ""))),
            "table_code": table_code,
            "party_size": party_size,
            "scene": scene.value,
            "device_type": device_type.value,
            "total_fen": int(raw.get("total_amount", 0)),
            "total_yuan": Decimal(str(raw.get("total_amount", 0))) / 100,
            "item_count": len(order_items),
        }

    async def add_dishes_to_order(
        self,
        order_id: str,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """追加点菜（加菜）"""
        order_items = []
        for item in items:
            oi: Dict[str, Any] = {
                "itemCode": item["dish_id"],
                "qty": item.get("qty", 1),
            }
            if item.get("spec_id"):
                oi["specId"] = item["spec_id"]
            if item.get("weight_g"):
                oi["weight"] = item["weight_g"]
                oi["weightUnit"] = "g"
            if item.get("notes"):
                oi["remark"] = item["notes"]
            order_items.append(oi)

        return await self._request(_ORDER_ADD_DISH_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "orderId": order_id,
            "items": order_items,
        })

    async def void_dish(
        self,
        order_id: str,
        item_id: str,
        reason: str,
        operator_code: str,
    ) -> Dict[str, Any]:
        """退菜"""
        return await self._request(_ORDER_VOID_PATH, {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "orderId": order_id,
            "itemId": item_id,
            "reason": reason,
            "operatorCode": operator_code,
        })

    # ═══════════════════════════════════════════════════════════════════════════
    # 9. 影子同步（企业级双写对比）
    # ═══════════════════════════════════════════════════════════════════════════

    async def pull_full_snapshot(
        self,
        date_str: str,
        brand_id: str,
    ) -> Dict[str, Any]:
        """
        拉取天财商龙指定日期的全量业务快照，用于影子模式对比。

        Returns:
            {
                "orders": [...],
                "reservations": [...],
                "members_active": [...],
                "payments": [...],
                "kitchen_stats": {...},
                "coupons_consumed": [...],
                "snapshot_time": str,
            }
        """
        # 并行拉取各业务数据
        import asyncio

        orders_task = self.pull_daily_orders(date_str, brand_id)
        reservations_task = self.get_reservations(date_str)
        kitchen_task = self.get_kitchen_status()

        orders, reservations, kitchen = await asyncio.gather(
            orders_task, reservations_task, kitchen_task,
            return_exceptions=True,
        )

        return {
            "orders": orders if not isinstance(orders, Exception) else [],
            "reservations": reservations if not isinstance(reservations, Exception) else [],
            "members_active": [],  # 需单独按会员ID查询
            "payments": [],        # 从订单数据中提取
            "kitchen_stats": kitchen if not isinstance(kitchen, Exception) else {},
            "coupons_consumed": [],
            "snapshot_time": datetime.utcnow().isoformat(),
            "source_system": "tiancai_shanglong",
            "date": date_str,
        }
