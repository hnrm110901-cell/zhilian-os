"""
订单协同Agent
处理预定、排位、等位、点单、结账全流程
无状态设计：状态由调用方从DB查询后传入，Agent不持有任何内存状态
"""
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime, timedelta
from enum import Enum
import structlog
import uuid
import os
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


class OrderStatus(Enum):
    """订单状态"""

    RESERVED = "reserved"
    WAITING = "waiting"
    SEATED = "seated"
    ORDERING = "ordering"
    ORDERED = "ordered"
    COOKING = "cooking"
    SERVED = "served"
    PAYING = "paying"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# 合法状态转换表（含取消规则，统一来源）
_VALID_TRANSITIONS: Dict[str, List[str]] = {
    OrderStatus.ORDERING.value: [OrderStatus.ORDERED.value, OrderStatus.CANCELLED.value],
    OrderStatus.ORDERED.value: [OrderStatus.COOKING.value, OrderStatus.CANCELLED.value],
    OrderStatus.COOKING.value: [OrderStatus.SERVED.value, OrderStatus.CANCELLED.value],
    OrderStatus.SERVED.value: [OrderStatus.PAYING.value, OrderStatus.CANCELLED.value],
    OrderStatus.PAYING.value: [OrderStatus.PAID.value, OrderStatus.CANCELLED.value],
    OrderStatus.PAID.value: [OrderStatus.COMPLETED.value],
    OrderStatus.COMPLETED.value: [],
    OrderStatus.CANCELLED.value: [],
}

# 不可取消的终态（与 _VALID_TRANSITIONS 保持一致）
_NON_CANCELLABLE = {OrderStatus.PAID.value, OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value}


class ReservationType(Enum):
    ONLINE = "online"
    PHONE = "phone"
    WALKIN = "walkin"


class PaymentMethod(Enum):
    CASH = "cash"
    WECHAT = "wechat"
    ALIPAY = "alipay"
    CARD = "card"
    MEMBER = "member"


class OrderState(TypedDict):
    order_id: str
    store_id: str
    customer_info: Dict[str, Any]
    reservation: Optional[Dict[str, Any]]
    queue_info: Optional[Dict[str, Any]]
    table_info: Optional[Dict[str, Any]]
    dishes: List[Dict[str, Any]]
    total_amount: float
    discount_amount: float
    final_amount: float
    payment_info: Optional[Dict[str, Any]]
    status: str
    created_at: str
    updated_at: str


class OrderAgent(BaseAgent):
    """订单协同Agent（无状态设计，状态由调用方传入，多进程安全）"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.average_wait_time = config.get("average_wait_time", 30)
        self.average_dining_time = config.get("average_dining_time", 90)
        # 不持有任何内存状态
        logger.info("订单协同Agent初始化", store_id=config.get("store_id"))

    def get_supported_actions(self) -> List[str]:
        return [
            "create_reservation", "join_queue", "get_queue_status",
            "create_order", "add_dish", "recommend_dishes",
            "calculate_bill", "process_payment", "get_order",
            "update_order_status", "cancel_order",
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        try:
            if action == "create_reservation":
                result = await self.create_reservation(**params)
            elif action == "join_queue":
                result = await self.join_queue(**params)
            elif action == "get_queue_status":
                result = await self.get_queue_status(**params)
            elif action == "create_order":
                result = await self.create_order(**params)
            elif action == "add_dish":
                result = await self.add_dish(**params)
            elif action == "recommend_dishes":
                result = await self.recommend_dishes(**params)
            elif action == "calculate_bill":
                result = await self.calculate_bill(**params)
            elif action == "process_payment":
                result = await self.process_payment(**params)
            elif action == "get_order":
                result = await self.get_order(**params)
            elif action == "update_order_status":
                result = await self.update_order_status(**params)
            elif action == "cancel_order":
                result = await self.cancel_order(**params)
            else:
                return AgentResponse(success=False, data=None, error=f"Unsupported action: {action}")

            return AgentResponse(
                success=result.get("success", True),
                data=result,
                error=result.get("error") if not result.get("success", True) else None,
            )
        except Exception as e:
            return AgentResponse(success=False, data=None, error=str(e))

    # ==================== 预定管理 ====================

    async def create_reservation(
        self,
        store_id: str,
        customer_name: str,
        customer_mobile: str,
        party_size: int,
        reservation_time: str,
        existing_reservations: Optional[List[Dict[str, Any]]] = None,
        special_requests: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建预定

        Args:
            existing_reservations: 当前已有预定列表（由调用方从DB查询后传入）
        """
        logger.info("创建预定", store_id=store_id, customer=customer_name,
                    party_size=party_size, time=reservation_time)

        reservations = existing_reservations or []
        if not self._check_time_availability(store_id, reservation_time, reservations):
            return {
                "success": False,
                "message": "该时间段已满，请选择其他时间",
                "alternative_times": self._suggest_alternative_times(
                    store_id, reservation_time, reservations
                ),
            }

        reservation_id = f"RSV{uuid.uuid4().hex[:12].upper()}"
        reservation = {
            "reservation_id": reservation_id,
            "store_id": store_id,
            "customer_name": customer_name,
            "customer_mobile": customer_mobile,
            "party_size": party_size,
            "reservation_time": reservation_time,
            "special_requests": special_requests,
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
        }
        logger.info("预定创建成功", reservation_id=reservation_id)
        return {"success": True, "reservation": reservation, "message": "预定成功"}

    def _check_time_availability(
        self, store_id: str, time: str, existing_reservations: List[Dict[str, Any]]
    ) -> bool:
        same_time = [
            r for r in existing_reservations
            if r["store_id"] == store_id
            and r["reservation_time"] == time
            and r["status"] == "confirmed"
        ]
        max_concurrent = int(os.getenv("ORDER_MAX_CONCURRENT_RESERVATIONS", "10"))
        return len(same_time) < max_concurrent

    def _suggest_alternative_times(
        self, store_id: str, requested_time: str, existing_reservations: List[Dict[str, Any]]
    ) -> List[str]:
        base_time = datetime.fromisoformat(requested_time)
        candidates = [base_time + timedelta(hours=i) for i in [1, 2, -1, 3]]
        alternatives = []
        for t in candidates:
            t_str = t.strftime("%Y-%m-%d %H:%M")
            if self._check_time_availability(store_id, t_str, existing_reservations):
                alternatives.append(t_str)
            if len(alternatives) >= 3:
                break
        return alternatives

    # ==================== 排位/等位管理 ====================

    async def join_queue(
        self,
        store_id: str,
        customer_name: str,
        customer_mobile: str,
        party_size: int,
        existing_queues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        加入排队

        Args:
            existing_queues: 当前门店所有排队记录（由调用方从DB查询后传入）
        """
        logger.info("加入排队", store_id=store_id, customer=customer_name, party_size=party_size)

        queues = existing_queues or []
        queue_number = self._generate_queue_number(store_id, queues)
        estimated_wait = self._estimate_wait_time(store_id, party_size, queues)

        queue_info = {
            "queue_id": f"Q{uuid.uuid4().hex[:12].upper()}",
            "queue_number": queue_number,
            "store_id": store_id,
            "customer_name": customer_name,
            "customer_mobile": customer_mobile,
            "party_size": party_size,
            "estimated_wait_minutes": estimated_wait,
            "status": "waiting",
            "joined_at": datetime.now().isoformat(),
        }
        logger.info("排队成功", queue_number=queue_number, estimated_wait=estimated_wait)
        return {
            "success": True,
            "queue_info": queue_info,
            "message": f"您的排队号是{queue_number}，预计等待{estimated_wait}分钟",
        }

    def _generate_queue_number(self, store_id: str, existing_queues: List[Dict[str, Any]]) -> str:
        """生成排队号（取历史最大序号+1，避免入座后重号）"""
        store_queues = [q for q in existing_queues if q["store_id"] == store_id]
        if not store_queues:
            return "A001"
        max_seq = 0
        for q in store_queues:
            num_part = q.get("queue_number", "A000")[1:]
            if num_part.isdigit():
                max_seq = max(max_seq, int(num_part))
        return f"A{max_seq + 1:03d}"

    def _estimate_wait_time(
        self, store_id: str, party_size: int, existing_queues: List[Dict[str, Any]]
    ) -> int:
        waiting = [q for q in existing_queues if q["store_id"] == store_id and q["status"] == "waiting"]
        turnover_factor = int(os.getenv("ORDER_TABLE_TURNOVER_FACTOR", "3"))
        base_wait = len(waiting) * (self.average_dining_time // turnover_factor)
        base_wait = max(base_wait, self.average_wait_time)
        party_factor = (party_size - 2) * int(os.getenv("ORDER_PARTY_WAIT_FACTOR", "5")) if party_size > 2 else 0
        return base_wait + party_factor

    async def get_queue_status(
        self,
        queue_id: str,
        queue: Dict[str, Any],
        all_waiting_queues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        查询排队状态

        Args:
            queue: 该排队记录（由调用方从DB查询后传入）
            all_waiting_queues: 同门店所有等待中的排队（由调用方从DB查询后传入）
        """
        logger.info("查询排队状态", queue_id=queue_id)

        waiting = sorted(all_waiting_queues or [], key=lambda q: q["joined_at"])
        ahead_count = next((i for i, q in enumerate(waiting) if q["queue_id"] == queue_id), 0)
        turnover_factor = int(os.getenv("ORDER_TABLE_TURNOVER_FACTOR", "3"))
        estimated_wait = ahead_count * (self.average_dining_time // turnover_factor)

        return {
            "success": True,
            "queue_id": queue_id,
            "status": queue["status"],
            "queue_number": queue["queue_number"],
            "ahead_count": ahead_count,
            "estimated_wait_minutes": estimated_wait,
        }

    # ==================== 点单管理 ====================

    async def create_order(
        self,
        store_id: str,
        table_id: str,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建订单（返回新订单数据，由调用方持久化到DB）"""
        logger.info("创建订单", store_id=store_id, table_id=table_id)

        order_id = f"ORD{uuid.uuid4().hex[:12].upper()}"
        order = {
            "order_id": order_id,
            "store_id": store_id,
            "table_id": table_id,
            "customer_id": customer_id,
            "dishes": [],
            "total_amount": 0,
            "status": OrderStatus.ORDERING.value,
            "created_at": datetime.now().isoformat(),
        }
        logger.info("订单创建成功", order_id=order_id)
        return {"success": True, "order": order}

    async def add_dish(
        self,
        order_id: str,
        dish_id: str,
        dish_name: str,
        price: float,
        quantity: int = 1,
        special_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        添加菜品（返回菜品数据，由调用方将 dish_item 追加到订单并更新 total_amount）
        """
        logger.info("添加菜品", order_id=order_id, dish_name=dish_name, quantity=quantity)

        dish_item = {
            "dish_id": dish_id,
            "dish_name": dish_name,
            "price": price,
            "quantity": quantity,
            "special_instructions": special_instructions,
            "subtotal": price * quantity,
        }
        return {"success": True, "message": f"已添加{quantity}份{dish_name}", "dish_item": dish_item}

    async def recommend_dishes(
        self,
        store_id: str,
        recent_orders: Optional[List[Dict[str, Any]]] = None,
        customer_id: Optional[str] = None,
        party_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        推荐菜品

        Args:
            recent_orders: 近期订单列表（由调用方从DB查询后传入，用于统计热门菜品）
        """
        logger.info("推荐菜品", store_id=store_id, customer_id=customer_id, party_size=party_size)

        dish_counts: Dict[str, Dict[str, Any]] = {}
        for order in (recent_orders or []):
            if order.get("store_id") == store_id:
                for dish in order.get("dishes", []):
                    did = dish["dish_id"]
                    if did not in dish_counts:
                        dish_counts[did] = {"dish_id": did, "dish_name": dish["dish_name"],
                                            "price": dish["price"], "count": 0}
                    dish_counts[did]["count"] += dish["quantity"]

        sorted_dishes = sorted(dish_counts.values(), key=lambda d: d["count"], reverse=True)[:5]
        if not sorted_dishes:
            sorted_dishes = [{"dish_id": "D001", "dish_name": "招牌菜", "price": 48.0, "count": 0}]

        recommendations = [
            {
                "dish_id": d["dish_id"],
                "dish_name": d["dish_name"],
                "price": d["price"],
                "reason": f"本店热销，已点 {d['count']} 次" if d["count"] > 0 else "本店推荐",
                "popularity_rank": i + 1,
            }
            for i, d in enumerate(sorted_dishes)
        ]
        return {"success": True, "recommendations": recommendations,
                "message": f"为您推荐{len(recommendations)}道菜品"}

    # ==================== 结账管理 ====================

    async def calculate_bill(
        self,
        order_id: str,
        order: Dict[str, Any],
        member_id: Optional[str] = None,
        coupon_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        计算账单

        Args:
            order: 订单数据（由调用方从DB查询后传入；订单不存在时调用方应提前返回错误）
        """
        logger.info("计算账单", order_id=order_id, member_id=member_id, coupons=coupon_codes)

        total_amount = order["total_amount"]
        member_discount_rate = float(os.getenv("ORDER_MEMBER_DISCOUNT_RATE", "0.1")) if member_id else 0
        member_discount = round(total_amount * member_discount_rate, 2)
        coupon_discount = float(os.getenv("ORDER_COUPON_DISCOUNT", "10.0")) * len(coupon_codes) if coupon_codes else 0
        final_amount = max(0.0, total_amount - member_discount - coupon_discount)

        bill = {
            "order_id": order_id,
            "total_amount": total_amount,
            "member_discount": member_discount,
            "coupon_discount": coupon_discount,
            "final_amount": final_amount,
            "breakdown": {"dishes_total": total_amount, "service_fee": 0, "tax": 0},
        }
        logger.info("账单计算完成", final_amount=final_amount)
        return {"success": True, "bill": bill}

    async def process_payment(
        self,
        order_id: str,
        payment_method: str,
        amount: float,
        payment_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """处理支付（返回支付记录和新状态，由调用方更新DB中的订单）"""
        logger.info("处理支付", order_id=order_id, method=payment_method, amount=amount)

        payment_id = f"PAY{uuid.uuid4().hex[:12].upper()}"
        payment_result = {
            "payment_id": payment_id,
            "order_id": order_id,
            "payment_method": payment_method,
            "amount": amount,
            "status": "success",
            "paid_at": datetime.now().isoformat(),
        }
        logger.info("支付成功", payment_id=payment_id)
        return {
            "success": True,
            "payment": payment_result,
            "new_status": OrderStatus.PAID.value,
            "message": "支付成功",
        }

    # ==================== 订单查询与状态管理 ====================

    async def get_order(self, order_id: str, order: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        查询订单

        Args:
            order: 订单数据（由调用方从DB查询后传入）
        """
        logger.info("查询订单", order_id=order_id)
        if not order:
            return {"success": False, "message": "订单不存在"}
        return {"success": True, "order": order}

    async def update_order_status(
        self,
        order_id: str,
        new_status: str,
        order: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        更新订单状态（使用统一的 _VALID_TRANSITIONS 表校验）

        Args:
            order: 当前订单数据（由调用方从DB查询后传入）
        """
        logger.info("更新订单状态", order_id=order_id, new_status=new_status)

        current = order.get("status", "")
        allowed = _VALID_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            return {"success": False, "message": f"不允许从 {current} 转换到 {new_status}"}

        return {
            "success": True,
            "order_id": order_id,
            "old_status": current,
            "status": new_status,
            "updated_at": datetime.now().isoformat(),
            "message": "订单状态已更新",
        }

    async def cancel_order(
        self,
        order_id: str,
        order: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        取消订单（与 update_order_status 使用同一套取消规则）

        Args:
            order: 当前订单数据（由调用方从DB查询后传入）
        """
        logger.info("取消订单", order_id=order_id, reason=reason)

        current_status = order.get("status", "")
        if current_status in _NON_CANCELLABLE:
            return {"success": False, "message": f"订单状态为 {current_status}，无法取消"}

        needs_refund = current_status == OrderStatus.PAYING.value
        return {
            "success": True,
            "order_id": order_id,
            "needs_refund": needs_refund,
            "new_status": OrderStatus.CANCELLED.value,
            "cancel_reason": reason,
            "cancelled_at": datetime.now().isoformat(),
            "message": "订单已取消",
        }
