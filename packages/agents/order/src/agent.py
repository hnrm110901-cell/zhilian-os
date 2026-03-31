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
import inspect
import re
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
    OrderStatus.RESERVED.value: [OrderStatus.WAITING.value, OrderStatus.SEATED.value, OrderStatus.CANCELLED.value],
    OrderStatus.WAITING.value: [OrderStatus.SEATED.value, OrderStatus.CANCELLED.value],
    OrderStatus.SEATED.value: [OrderStatus.ORDERING.value, OrderStatus.CANCELLED.value],
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
_ALL_ORDER_STATUSES = {status.value for status in OrderStatus}


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
            "create_order", "add_dish", "calculate_dynamic_price", "recommend_dishes", "personalize_dining_suggestions",
            "suggest_cross_store_reservation",
            "get_ar_menu_preview", "parse_voice_order",
            "calculate_bill", "process_payment", "get_order",
            "modify_order", "merge_table_orders", "update_order_status", "cancel_order",
        ]

    def get_valid_next_statuses(self, current_status: str) -> List[str]:
        """返回当前状态可转换的下一状态集合。"""
        return list(_VALID_TRANSITIONS.get(current_status, []))

    async def _check_table_available(self, store_id: str, table_id: str) -> Dict[str, Any]:
        """
        可插拔桌台可用性检查。
        config["table_availability_checker"] 支持同步/异步函数，返回 bool 或 dict。
        """
        checker = self.config.get("table_availability_checker")
        if not callable(checker):
            return {"ok": True, "source": "default_open"}

        try:
            raw = checker(store_id=store_id, table_id=table_id)
            if inspect.isawaitable(raw):
                raw = await raw
        except Exception as e:
            logger.warning("table_check_failed", error=str(e), table_id=table_id)
            return {"ok": True, "source": "checker_error_fallback_open"}

        if isinstance(raw, bool):
            return {"ok": raw, "source": "table_manager"}
        if isinstance(raw, dict):
            return {
                "ok": bool(raw.get("available", False)),
                "source": str(raw.get("source", "table_manager")),
                "reason": raw.get("reason"),
            }
        return {"ok": True, "source": "checker_invalid_fallback_open"}

    async def _mark_table_occupied(self, store_id: str, table_id: str, order_id: str) -> None:
        """
        可插拔桌台占用回调。
        config["table_occupy_callback"] 支持同步/异步函数，异常时仅记录日志不阻塞下单。
        """
        callback = self.config.get("table_occupy_callback")
        if not callable(callback):
            return
        try:
            raw = callback(store_id=store_id, table_id=table_id, order_id=order_id)
            if inspect.isawaitable(raw):
                await raw
        except Exception as e:
            logger.warning("table_occupy_callback_failed", error=str(e), table_id=table_id, order_id=order_id)

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
            elif action == "calculate_dynamic_price":
                result = await self.calculate_dynamic_price(**params)
            elif action == "recommend_dishes":
                result = await self.recommend_dishes(**params)
            elif action == "personalize_dining_suggestions":
                result = await self.personalize_dining_suggestions(**params)
            elif action == "suggest_cross_store_reservation":
                result = await self.suggest_cross_store_reservation(**params)
            elif action == "get_ar_menu_preview":
                result = await self.get_ar_menu_preview(**params)
            elif action == "parse_voice_order":
                result = await self.parse_voice_order(**params)
            elif action == "calculate_bill":
                result = await self.calculate_bill(**params)
            elif action == "process_payment":
                result = await self.process_payment(**params)
            elif action == "get_order":
                result = await self.get_order(**params)
            elif action == "modify_order":
                result = await self.modify_order(**params)
            elif action == "merge_table_orders":
                result = await self.merge_table_orders(**params)
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
        same_time = self._count_confirmed_reservations(store_id, time, existing_reservations)
        max_concurrent = int(os.getenv("ORDER_MAX_CONCURRENT_RESERVATIONS", "10"))
        return same_time < max_concurrent

    def _count_confirmed_reservations(
        self, store_id: str, reservation_time: str, existing_reservations: List[Dict[str, Any]]
    ) -> int:
        return len([
            r for r in existing_reservations
            if r["store_id"] == store_id
            and r["reservation_time"] == reservation_time
            and r["status"] == "confirmed"
        ])

    def _suggest_alternative_times(
        self, store_id: str, requested_time: str, existing_reservations: List[Dict[str, Any]]
    ) -> List[str]:
        """
        预定冲突智能解决：
        - 在请求时间前后按30分钟粒度扫描候选
        - 按当前时段负载（confirmed数量）升序，再按与请求时间距离升序排序
        """
        base_time = datetime.fromisoformat(requested_time)
        max_concurrent = int(os.getenv("ORDER_MAX_CONCURRENT_RESERVATIONS", "10"))
        offsets_minutes = [30, -30, 60, -60, 90, -90, 120, -120]

        ranked: List[Dict[str, Any]] = []
        for offset in offsets_minutes:
            t = base_time + timedelta(minutes=offset)
            t_str = t.strftime("%Y-%m-%d %H:%M")
            load = self._count_confirmed_reservations(store_id, t_str, existing_reservations)
            if load >= max_concurrent:
                continue
            ranked.append(
                {
                    "time": t_str,
                    "load": load,
                    "distance": abs(offset),
                }
            )

        ranked.sort(key=lambda x: (x["load"], x["distance"]))
        return [item["time"] for item in ranked[:3]]

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

        table_check = await self._check_table_available(store_id=store_id, table_id=table_id)
        if not table_check.get("ok", False):
            reason = table_check.get("reason") or "桌台不可用"
            return {
                "success": False,
                "message": f"桌台 {table_id} 当前不可下单：{reason}",
                "table_check": table_check,
            }

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
        await self._mark_table_occupied(store_id=store_id, table_id=table_id, order_id=order_id)
        logger.info("订单创建成功", order_id=order_id)
        return {"success": True, "order": order, "table_check": table_check}

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

    async def calculate_dynamic_price(
        self,
        dish_id: str,
        base_price: float,
        demand_level: str = "normal",
        party_size: int = 2,
        request_time: Optional[str] = None,
        db: Optional[Any] = None,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        动态定价策略（MVP）：
        - 需求等级：low / normal / high
        - 大客群：>=6人小幅上浮
        - 高峰时段：11:30-13:30、18:00-20:30 小幅上浮
        """
        if base_price <= 0:
            return {"success": False, "message": "基础价格必须大于0"}

        # 动态定价系数：优先从门店级配置读取，降级使用环境变量默认值
        if db and store_id:
            try:
                from src.services.org_hierarchy_service import OrgHierarchyService
                svc = OrgHierarchyService(db)
                pricing_factors = await svc.resolve(
                    store_id,
                    "dynamic_pricing_factors",
                    default=None,
                )
            except Exception:
                pricing_factors = None
        else:
            pricing_factors = None

        if pricing_factors:
            demand_factor_map = {
                "low": float(pricing_factors.get("low", os.getenv("ORDER_PRICING_FACTOR_LOW", "0.95"))),
                "normal": float(pricing_factors.get("normal", os.getenv("ORDER_PRICING_FACTOR_NORMAL", "1.00"))),
                "high": float(pricing_factors.get("high", os.getenv("ORDER_PRICING_FACTOR_HIGH", "1.08"))),
            }
        else:
            demand_factor_map = {
                "low": float(os.getenv("ORDER_PRICING_FACTOR_LOW", "0.95")),
                "normal": float(os.getenv("ORDER_PRICING_FACTOR_NORMAL", "1.00")),
                "high": float(os.getenv("ORDER_PRICING_FACTOR_HIGH", "1.08")),
            }
        demand_factor = demand_factor_map.get(demand_level, demand_factor_map["normal"])

        group_factor = float(os.getenv("ORDER_PRICING_GROUP_FACTOR", "1.03")) if party_size >= 6 else 1.0

        peak_factor = 1.0
        peak_hit = False
        if request_time:
            try:
                dt = datetime.fromisoformat(request_time)
                hhmm = dt.hour * 60 + dt.minute
                lunch_peak = 11 * 60 + 30 <= hhmm <= 13 * 60 + 30
                dinner_peak = 18 * 60 <= hhmm <= 20 * 60 + 30
                if lunch_peak or dinner_peak:
                    peak_factor = float(os.getenv("ORDER_PRICING_PEAK_FACTOR", "1.05"))
                    peak_hit = True
            except ValueError:
                peak_factor = 1.0

        total_factor = demand_factor * group_factor * peak_factor
        suggested_price = round(base_price * total_factor, 2)

        return {
            "success": True,
            "dish_id": dish_id,
            "base_price": round(base_price, 2),
            "suggested_price": suggested_price,
            "adjustment_rate": round(total_factor - 1.0, 4),
            "factors": {
                "demand_level": demand_level,
                "demand_factor": demand_factor,
                "group_factor": group_factor,
                "peak_factor": peak_factor,
                "peak_hit": peak_hit,
            },
            "message": "动态定价计算完成",
        }

    async def modify_order(
        self,
        order_id: str,
        order: Dict[str, Any],
        modifications: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        修改订单（由调用方传入当前 order，返回 updated_order）

        modifications 支持:
          - {"action":"update_quantity","dish_id":"D001","quantity":2}
          - {"action":"remove_dish","dish_id":"D001"}
          - {"action":"update_instructions","dish_id":"D001","special_instructions":"少辣"}
        """
        logger.info("修改订单", order_id=order_id, modifications_count=len(modifications))

        dishes = [dict(d) for d in order.get("dishes", [])]
        applied: List[str] = []

        for mod in modifications:
            action = mod.get("action")
            dish_id = mod.get("dish_id")
            target = next((d for d in dishes if d.get("dish_id") == dish_id), None)

            if action == "remove_dish":
                before = len(dishes)
                dishes = [d for d in dishes if d.get("dish_id") != dish_id]
                if len(dishes) < before:
                    applied.append(f"移除菜品 {dish_id}")
                else:
                    applied.append(f"移除失败，菜品不存在 {dish_id}")
                continue

            if not target:
                applied.append(f"修改失败，菜品不存在 {dish_id}")
                continue

            if action == "update_quantity":
                quantity = int(mod.get("quantity", 0))
                if quantity <= 0:
                    applied.append(f"数量非法，菜品 {dish_id}")
                    continue
                target["quantity"] = quantity
                target["subtotal"] = round(float(target.get("price", 0)) * quantity, 2)
                applied.append(f"更新菜品 {dish_id} 数量为 {quantity}")
            elif action == "update_instructions":
                target["special_instructions"] = mod.get("special_instructions")
                applied.append(f"更新菜品 {dish_id} 备注")
            else:
                applied.append(f"未知修改动作 {action}")

        total_amount = round(sum(float(d.get("subtotal", 0)) for d in dishes), 2)
        updated_order = dict(order)
        updated_order["dishes"] = dishes
        updated_order["total_amount"] = total_amount
        updated_order["updated_at"] = datetime.now().isoformat()

        return {
            "success": True,
            "order_id": order_id,
            "updated_order": updated_order,
            "applied_modifications": applied,
            "message": f"订单修改完成，共处理 {len(modifications)} 项",
        }

    async def merge_table_orders(
        self,
        primary_order: Dict[str, Any],
        secondary_order: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        拼桌合单：将 secondary_order 合并到 primary_order，返回 merged_order。
        """
        primary_id = primary_order.get("order_id")
        secondary_id = secondary_order.get("order_id")
        logger.info("拼桌合单", primary_order_id=primary_id, secondary_order_id=secondary_id)

        if not primary_id or not secondary_id:
            return {"success": False, "message": "缺少订单ID，无法拼桌"}
        if primary_id == secondary_id:
            return {"success": False, "message": "同一订单不能拼桌"}
        if primary_order.get("store_id") != secondary_order.get("store_id"):
            return {"success": False, "message": "跨门店订单不能拼桌"}

        merged_dishes = [dict(d) for d in primary_order.get("dishes", [])]
        merged_dishes.extend([dict(d) for d in secondary_order.get("dishes", [])])
        total_amount = round(sum(float(d.get("subtotal", 0)) for d in merged_dishes), 2)

        table_ids: List[str] = []
        for table_id in [primary_order.get("table_id"), secondary_order.get("table_id")]:
            if table_id and table_id not in table_ids:
                table_ids.append(table_id)

        merged_order = dict(primary_order)
        merged_order["dishes"] = merged_dishes
        merged_order["total_amount"] = total_amount
        merged_order["merged_from_order_ids"] = [primary_id, secondary_id]
        merged_order["table_ids"] = table_ids
        merged_order["is_merged_table"] = True
        merged_order["updated_at"] = datetime.now().isoformat()

        return {
            "success": True,
            "merged_order": merged_order,
            "closed_order_id": secondary_id,
            "message": f"拼桌成功：{primary_id} + {secondary_id}",
        }

    def _translate_dish_name(self, dish_name: str, locale: str) -> str:
        """多语言菜名映射（MVP 内置词典，可后续接入真实 i18n 服务）。"""
        if locale == "zh-CN":
            return dish_name
        translations = {
            "宫保鸡丁": {"en-US": "Kung Pao Chicken"},
            "米饭": {"en-US": "Steamed Rice"},
            "招牌菜": {"en-US": "Signature Dish"},
            "鱼香肉丝": {"en-US": "Fish-Fragrant Shredded Pork"},
        }
        return translations.get(dish_name, {}).get(locale, dish_name)

    def _score_dish_ml(
        self,
        dish: Dict[str, Any],
        now: datetime,
        party_size: Optional[int],
    ) -> float:
        """
        轻量 ML 风格打分（MVP）：
        score = 频次权重 + 近期性权重 + 客群匹配权重
        """
        count = float(dish.get("count", 0))
        latest_ts = dish.get("latest_order_ts")
        recency_score = 0.0
        if isinstance(latest_ts, datetime):
            delta_days = max(0.0, (now - latest_ts).total_seconds() / 86400)
            recency_score = 1.0 / (1.0 + delta_days)

        party_fit = 0.0
        if party_size:
            if party_size >= 6 and float(dish.get("price", 0)) >= 40:
                party_fit = 1.0
            elif party_size <= 2 and float(dish.get("price", 0)) <= 30:
                party_fit = 1.0

        return round(count * 0.6 + recency_score * 0.3 + party_fit * 0.1, 6)

    async def recommend_dishes(
        self,
        store_id: str,
        recent_orders: Optional[List[Dict[str, Any]]] = None,
        customer_id: Optional[str] = None,
        party_size: Optional[int] = None,
        locale: str = "zh-CN",
        use_ml: bool = False,
    ) -> Dict[str, Any]:
        """
        推荐菜品

        Args:
            recent_orders: 近期订单列表（由调用方从DB查询后传入，用于统计热门菜品）
        """
        logger.info(
            "推荐菜品",
            store_id=store_id,
            customer_id=customer_id,
            party_size=party_size,
            locale=locale,
            use_ml=use_ml,
        )

        dish_counts: Dict[str, Dict[str, Any]] = {}
        now = datetime.now()
        for order in (recent_orders or []):
            if order.get("store_id") == store_id:
                created_at_raw = order.get("created_at")
                created_at = None
                if isinstance(created_at_raw, str):
                    try:
                        created_at = datetime.fromisoformat(created_at_raw)
                    except ValueError:
                        created_at = None
                for dish in order.get("dishes", []):
                    did = dish["dish_id"]
                    if did not in dish_counts:
                        dish_counts[did] = {"dish_id": did, "dish_name": dish["dish_name"],
                                            "price": dish["price"], "count": 0, "latest_order_ts": None}
                    dish_counts[did]["count"] += dish["quantity"]
                    if created_at:
                        prev = dish_counts[did].get("latest_order_ts")
                        if not isinstance(prev, datetime) or created_at > prev:
                            dish_counts[did]["latest_order_ts"] = created_at

        if use_ml and dish_counts:
            for d in dish_counts.values():
                d["ml_score"] = self._score_dish_ml(d, now=now, party_size=party_size)
            sorted_dishes = sorted(dish_counts.values(), key=lambda d: d["ml_score"], reverse=True)[:5]
        else:
            sorted_dishes = sorted(dish_counts.values(), key=lambda d: d["count"], reverse=True)[:5]
        if not sorted_dishes:
            sorted_dishes = [{"dish_id": "D001", "dish_name": "招牌菜", "price": 48.0, "count": 0}]

        recommendations = [
            {
                "dish_id": d["dish_id"],
                "dish_name": self._translate_dish_name(d["dish_name"], locale),
                "dish_name_zh": d["dish_name"],
                "price": d["price"],
                "reason": (
                    (
                        f"ML score {d.get('ml_score', 0):.2f}, ordered {d['count']} times"
                        if locale == "en-US" and use_ml
                        else f"Hot seller, ordered {d['count']} times"
                    )
                    if locale == "en-US" and d["count"] > 0
                    else (
                        "Recommended by store"
                        if locale == "en-US"
                        else (
                            (f"机器学习评分 {d.get('ml_score', 0):.2f}，本店热销，已点 {d['count']} 次" if use_ml else "本店热销，已点 %s 次" % d["count"])
                            if d["count"] > 0
                            else "本店推荐"
                        )
                    )
                ),
                "popularity_rank": i + 1,
                "ml_score": d.get("ml_score") if use_ml else None,
            }
            for i, d in enumerate(sorted_dishes)
        ]
        message = (
            (f"Recommended {len(recommendations)} dishes for you (ML ranking)" if use_ml else f"Recommended {len(recommendations)} dishes for you")
            if locale == "en-US"
            else (f"为您推荐{len(recommendations)}道菜品（机器学习排序）" if use_ml else f"为您推荐{len(recommendations)}道菜品")
        )
        return {"success": True, "recommendations": recommendations, "message": message, "locale": locale}

    async def personalize_dining_suggestions(
        self,
        store_id: str,
        customer_profile: Dict[str, Any],
        candidate_dishes: List[Dict[str, Any]],
        locale: str = "zh-CN",
    ) -> Dict[str, Any]:
        """
        个性化用餐建议：
        - 偏好标签匹配（taste_tags）
        - 预算匹配（budget_per_person）
        - 忌口过滤（avoid_ingredients）
        - 场景加权（scenario: business/family/date）
        """
        prefer_tags = set(customer_profile.get("taste_preferences", []))
        avoid_ingredients = set(customer_profile.get("avoid_ingredients", []))
        budget = float(customer_profile.get("budget_per_person", 0) or 0)
        scenario = str(customer_profile.get("scenario", "normal"))

        scored: List[Dict[str, Any]] = []
        for dish in candidate_dishes:
            ingredients = set(dish.get("ingredients", []))
            if avoid_ingredients.intersection(ingredients):
                continue

            score = 0.0
            reasons: List[str] = []

            dish_tags = set(dish.get("taste_tags", []))
            tag_hits = len(prefer_tags.intersection(dish_tags))
            if tag_hits > 0:
                score += tag_hits * 0.5
                reasons.append(f"口味匹配{tag_hits}项")

            price = float(dish.get("price", 0))
            if budget > 0:
                if price <= budget:
                    score += 0.4
                    reasons.append("符合预算")
                else:
                    score -= 0.2
                    reasons.append("略超预算")

            if scenario == "business" and dish.get("premium", False):
                score += 0.3
                reasons.append("商务场景加权")
            elif scenario == "family" and dish.get("shareable", False):
                score += 0.3
                reasons.append("家庭分享场景加权")
            elif scenario == "date" and dish.get("light", False):
                score += 0.3
                reasons.append("约会轻食场景加权")

            scored.append(
                {
                    **dish,
                    "personalization_score": round(score, 4),
                    "personalization_reason": "；".join(reasons) if locale != "en-US" else "; ".join(reasons),
                }
            )

        scored.sort(key=lambda x: x.get("personalization_score", 0), reverse=True)
        top = scored[:5]
        message = "已生成个性化用餐建议" if locale != "en-US" else "Personalized dining suggestions generated"
        return {
            "success": True,
            "store_id": store_id,
            "recommendations": top,
            "message": message,
            "locale": locale,
        }

    async def suggest_cross_store_reservation(
        self,
        primary_store_id: str,
        reservation_time: str,
        party_size: int,
        store_candidates: List[Dict[str, Any]],
        customer_name: Optional[str] = None,
        customer_mobile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        跨门店预定建议：
        - 当主门店冲突时，筛选可用门店
        - 按距离与容量余量排序
        """
        available: List[Dict[str, Any]] = []
        for store in store_candidates:
            store_id = store.get("store_id")
            if not store_id or store_id == primary_store_id:
                continue
            reservations = store.get("existing_reservations", [])
            if not self._check_time_availability(store_id, reservation_time, reservations):
                continue

            load = self._count_confirmed_reservations(store_id, reservation_time, reservations)
            max_concurrent = int(store.get("max_concurrent_reservations", os.getenv("ORDER_MAX_CONCURRENT_RESERVATIONS", "10")))
            capacity_left = max(0, max_concurrent - load)
            available.append(
                {
                    "store_id": store_id,
                    "store_name": store.get("store_name", store_id),
                    "distance_km": float(store.get("distance_km", 999)),
                    "capacity_left": capacity_left,
                    "reservation_time": reservation_time,
                    "party_size": party_size,
                }
            )

        available.sort(key=lambda x: (x["distance_km"], -x["capacity_left"]))
        top = available[:3]
        redirect_payload = None
        if top and customer_name and customer_mobile:
            best = top[0]
            redirect_payload = {
                "store_id": best["store_id"],
                "customer_name": customer_name,
                "customer_mobile": customer_mobile,
                "party_size": party_size,
                "reservation_time": reservation_time,
                "redirected_from": primary_store_id,
            }

        return {
            "success": True,
            "primary_store_id": primary_store_id,
            "cross_store_options": top,
            "redirect_reservation_payload": redirect_payload,
            "message": "已生成跨门店预定建议" if top else "暂无可用门店可供预定",
        }

    async def get_ar_menu_preview(
        self,
        store_id: str,
        menu_items: List[Dict[str, Any]],
        locale: str = "zh-CN",
    ) -> Dict[str, Any]:
        """
        AR菜单展示数据：
        输出每个菜品的 AR 资产地址、锚点信息与交互提示。
        """
        ar_items = []
        for item in menu_items:
            dish_id = str(item.get("dish_id", "unknown"))
            dish_name = str(item.get("dish_name", "未知菜品"))
            ar_items.append(
                {
                    "dish_id": dish_id,
                    "dish_name": dish_name,
                    "price": float(item.get("price", 0)),
                    "ar_asset_url": item.get("ar_asset_url", f"/ar-assets/{dish_id}.glb"),
                    "anchor_type": item.get("anchor_type", "tabletop"),
                    "scale_hint": item.get("scale_hint", 1.0),
                    "interaction_hint": "双指缩放，单指旋转" if locale != "en-US" else "Pinch to zoom, drag to rotate",
                }
            )
        return {
            "success": True,
            "store_id": store_id,
            "locale": locale,
            "ar_menu_items": ar_items,
            "message": "AR菜单预览已生成" if locale != "en-US" else "AR menu preview generated",
        }

    async def parse_voice_order(
        self,
        transcript: str,
        menu_catalog: List[Dict[str, Any]],
        locale: str = "zh-CN",
    ) -> Dict[str, Any]:
        """
        语音点单解析：
        从语音文本中匹配菜品和数量，返回订单草稿。
        """
        text = transcript.strip()
        if not text:
            return {"success": False, "message": "语音内容为空"}

        parsed_items: List[Dict[str, Any]] = []
        total_amount = 0.0
        remaining_text = text
        cn_num = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}

        for dish in menu_catalog:
            dish_name = str(dish.get("dish_name", ""))
            if not dish_name or dish_name not in text:
                continue

            quantity = 1
            m_digit = re.search(rf"(\d+)\s*份?\s*{re.escape(dish_name)}", text)
            if m_digit:
                quantity = int(m_digit.group(1))
            else:
                m_cn = re.search(rf"([一二两三四五])\s*份?\s*{re.escape(dish_name)}", text)
                if m_cn:
                    quantity = cn_num.get(m_cn.group(1), 1)

            price = float(dish.get("price", 0))
            subtotal = round(price * quantity, 2)
            parsed_items.append(
                {
                    "dish_id": dish.get("dish_id"),
                    "dish_name": dish_name,
                    "price": price,
                    "quantity": quantity,
                    "subtotal": subtotal,
                }
            )
            total_amount += subtotal
            remaining_text = remaining_text.replace(dish_name, "")

        return {
            "success": True,
            "locale": locale,
            "order_draft": {
                "items": parsed_items,
                "total_amount": round(total_amount, 2),
            },
            "unparsed_text": remaining_text.strip(),
            "message": "语音点单解析完成" if locale != "en-US" else "Voice order parsed",
        }

    # ==================== 结账管理 ====================

    async def calculate_bill(
        self,
        order_id: str,
        order: Dict[str, Any],
        member_id: Optional[str] = None,
        coupon_codes: Optional[List[str]] = None,
        db: Optional[Any] = None,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        计算账单

        Args:
            order: 订单数据（由调用方从DB查询后传入；订单不存在时调用方应提前返回错误）
            db: 数据库会话（可选），用于读取门店级动态配置
            store_id: 门店ID（可选），与 db 配合读取门店级动态配置
        """
        logger.info("计算账单", order_id=order_id, member_id=member_id, coupons=coupon_codes)

        total_amount = order["total_amount"]

        # 会员折扣率和优惠券额度：优先从门店级配置读取，降级使用环境变量默认值
        if member_id and db and store_id:
            try:
                from src.services.org_hierarchy_service import OrgHierarchyService
                svc = OrgHierarchyService(db)
                member_discount_rate = await svc.resolve(
                    store_id, "member_discount_rate", default=0.10
                )
                member_discount_rate = float(member_discount_rate)
            except Exception:
                member_discount_rate = float(os.getenv("ORDER_MEMBER_DISCOUNT_RATE", "0.1"))
        elif member_id:
            member_discount_rate = float(os.getenv("ORDER_MEMBER_DISCOUNT_RATE", "0.1"))
        else:
            member_discount_rate = 0.0

        member_discount = round(total_amount * member_discount_rate, 2)

        if coupon_codes:
            if db and store_id:
                try:
                    from src.services.org_hierarchy_service import OrgHierarchyService
                    svc = OrgHierarchyService(db)
                    coupon_unit = await svc.resolve(
                        store_id, "coupon_discount_amount", default=10.0
                    )
                    coupon_unit = float(coupon_unit)
                except Exception:
                    coupon_unit = float(os.getenv("ORDER_COUPON_DISCOUNT", "10.0"))
            else:
                coupon_unit = float(os.getenv("ORDER_COUPON_DISCOUNT", "10.0"))
            coupon_discount = coupon_unit * len(coupon_codes)
        else:
            coupon_discount = 0.0

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
        if current not in _ALL_ORDER_STATUSES:
            return {"success": False, "message": f"未知订单状态: {current}"}
        if new_status not in _ALL_ORDER_STATUSES:
            return {"success": False, "message": f"目标订单状态非法: {new_status}"}

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
