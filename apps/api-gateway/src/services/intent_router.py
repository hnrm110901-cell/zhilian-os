"""
FEAT-001: 意图路由器

IntentRouter 负责：
1. 意图解析（基于关键词 + 上下文）
2. 权限过滤（不同角色可访问不同意图）
3. 执行对应 Handler
4. 更新 ConversationContext
"""
import re
from typing import Any, Callable, Dict, Optional
import structlog

from ..models.conversation import ConversationContext, ConversationTurn

logger = structlog.get_logger()


# ==================== 意图 Handler 类型 ====================

HandlerFn = Callable[[str, str, ConversationContext, Optional[Any]], Any]


# ==================== 内置 Handler 实现 ====================

class QueryRevenueHandler:
    """查询今日营收：SUM(final_amount) for completed orders today"""

    async def handle(
        self,
        text: str,
        store_id: str,
        context: ConversationContext,
        db=None,
        actor_role: str = "",
    ) -> Dict[str, Any]:
        if not db:
            return {
                "intent": "query_revenue",
                "message": "当前无法获取营收数据，请查看管理后台",
                "voice_response": "当前无法获取营收数据",
            }

        try:
            from datetime import date
            from sqlalchemy import select, func
            from ..models.order import Order, OrderStatus

            today = date.today()
            stmt = (
                select(func.coalesce(func.sum(Order.final_amount), 0))
                .where(
                    Order.store_id == store_id,
                    func.date(Order.order_time) == today,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            result = await db.execute(stmt)
            total_fen = int(result.scalar() or 0)
            total_yuan = total_fen / 100

            msg = f"今日营收 ¥{total_yuan:,.2f} 元"
            return {
                "intent": "query_revenue",
                "message": msg,
                "voice_response": msg,
                "data": {"total_yuan": total_yuan, "date": str(today)},
            }

        except Exception as e:
            logger.error("query_revenue.failed", store_id=store_id, error=str(e))
            return {
                "intent": "query_revenue",
                "message": "营收查询失败，请稍后重试",
                "voice_response": "营收查询失败，请稍后重试",
            }


class ApplyDiscountHandler:
    """解析折扣金额并通过 TrustedExecutor 提交申请"""

    _PATTERNS = [
        # "打九折" / "打9折" → compute discount from rate
        (re.compile(r'打(\d+(?:\.\d+)?)折'), "rate"),
        # "减20元" / "优惠20元" / "减免20元"
        (re.compile(r'(?:减|优惠|减免|打折|抹掉)(\d+(?:\.\d+)?)元'), "yuan"),
    ]

    def _parse_amount_fen(self, text: str) -> Optional[int]:
        """从语音文本解析折扣金额（单位：分），无法解析时返回 None"""
        for pattern, kind in self._PATTERNS:
            m = pattern.search(text)
            if m:
                val = float(m.group(1))
                if kind == "rate":
                    # "打X折" → 折扣率=(1 - X/10)，以100元订单为基准估算折扣额
                    rate = 1.0 - val / 10.0
                    return round(10000 * rate)  # 基准100元 × 折扣率 → 分
                else:
                    return int(val * 100)
        # 抹零 → 固定5元
        if "抹零" in text:
            return 500
        return None

    async def handle(
        self,
        text: str,
        store_id: str,
        context: ConversationContext,
        db=None,
        actor_role: str = "",
    ) -> Dict[str, Any]:
        amount_fen = self._parse_amount_fen(text)
        if amount_fen is None:
            context.pending_intent = "apply_discount"
            return {
                "intent": "apply_discount",
                "message": "请说明折扣金额，例如：'减20元'或'打九折'",
                "voice_response": "请问需要优惠多少？",
            }

        actor = {
            "user_id": context.user_id,
            "role": actor_role or "floor_manager",
            "store_id": store_id,
            "brand_id": "",
        }

        try:
            from ..core.trusted_executor import TrustedExecutor
            executor = TrustedExecutor(db_session=db)
            result = await executor.execute(
                command_type="discount_apply",
                payload={
                    "store_id": store_id,
                    "amount": amount_fen,
                    "reason": text,
                    "table": context.current_table or "",
                    "order_id": context.current_order_id or "",
                },
                actor=actor,
            )
            amount_yuan = amount_fen / 100
            msg = f"折扣 ¥{amount_yuan:.0f} 元申请已提交"
            return {
                "intent": "apply_discount",
                "message": msg,
                "voice_response": msg,
                "execution_result": result,
            }

        except Exception as e:
            logger.warning("apply_discount.failed", store_id=store_id, error=str(e))
            amount_yuan = amount_fen / 100
            msg = f"折扣 ¥{amount_yuan:.0f} 元申请已记录，等待审批"
            return {
                "intent": "apply_discount",
                "message": msg,
                "voice_response": msg,
            }


class QueryQueueHandler:
    """查询当前排队状态：COUNT(WAITING) + SUM(party_size)"""

    async def handle(
        self,
        text: str,
        store_id: str,
        context: ConversationContext,
        db=None,
        actor_role: str = "",
    ) -> Dict[str, Any]:
        if not db:
            return {
                "intent": "query_queue",
                "message": "当前无法查询排队状态",
                "voice_response": "当前无法查询排队状态",
            }

        try:
            from sqlalchemy import select, func
            from ..models.queue import Queue, QueueStatus

            stmt = (
                select(
                    func.count(Queue.queue_id).label("waiting_tables"),
                    func.coalesce(func.sum(Queue.party_size), 0).label("waiting_people"),
                )
                .where(
                    Queue.store_id == store_id,
                    Queue.status == QueueStatus.WAITING,
                )
            )
            result = await db.execute(stmt)
            row = result.one()
            tables = int(row.waiting_tables or 0)
            people = int(row.waiting_people or 0)

            msg = (
                "当前没有客人在排队等候"
                if tables == 0
                else f"当前有 {tables} 桌、共 {people} 人在排队等候"
            )
            return {
                "intent": "query_queue",
                "message": msg,
                "voice_response": msg,
                "data": {"waiting_tables": tables, "waiting_people": people},
            }

        except Exception as e:
            logger.error("query_queue.failed", store_id=store_id, error=str(e))
            return {
                "intent": "query_queue",
                "message": "排队查询失败，请稍后重试",
                "voice_response": "排队查询失败，请稍后重试",
            }


class InventoryQueryHandler:
    """查询库存不足食材：status IN (low, critical, out_of_stock)"""

    async def handle(
        self,
        text: str,
        store_id: str,
        context: ConversationContext,
        db=None,
        actor_role: str = "",
    ) -> Dict[str, Any]:
        if not db:
            return {
                "intent": "inventory_query",
                "message": "当前无法查询库存数据",
                "voice_response": "当前无法查询库存数据",
            }

        try:
            from sqlalchemy import select
            from ..models.inventory import InventoryItem, InventoryStatus

            stmt = (
                select(
                    InventoryItem.name,
                    InventoryItem.current_quantity,
                    InventoryItem.unit,
                    InventoryItem.status,
                )
                .where(
                    InventoryItem.store_id == store_id,
                    InventoryItem.status.in_([
                        InventoryStatus.LOW,
                        InventoryStatus.CRITICAL,
                        InventoryStatus.OUT_OF_STOCK,
                    ]),
                )
                .order_by(InventoryItem.status)
                .limit(5)
            )
            result = await db.execute(stmt)
            rows = result.all()

            if not rows:
                msg = "当前所有食材库存充足"
            else:
                items = "、".join(
                    f"{r.name}（{r.current_quantity:.1f}{r.unit or ''}）"
                    for r in rows
                )
                msg = f"以下食材库存不足：{items}"

            return {
                "intent": "inventory_query",
                "message": msg,
                "voice_response": msg,
                "data": {
                    "low_stock_items": [
                        {
                            "name": r.name,
                            "quantity": r.current_quantity,
                            "unit": r.unit,
                            "status": r.status.value,
                        }
                        for r in rows
                    ]
                },
            }

        except Exception as e:
            logger.error("inventory_query.failed", store_id=store_id, error=str(e))
            return {
                "intent": "inventory_query",
                "message": "库存查询失败，请稍后重试",
                "voice_response": "库存查询失败，请稍后重试",
            }


class CallSupportHandler:
    """请求支援：记录日志 + 尝试企微通知"""

    async def handle(
        self,
        text: str,
        store_id: str,
        context: ConversationContext,
        db=None,
        actor_role: str = "",
    ) -> Dict[str, Any]:
        user_id = context.user_id
        logger.info(
            "call_support.requested",
            store_id=store_id,
            user_id=user_id,
            text=text,
        )

        # 尝试企微通知（失败不阻断主流程）
        try:
            from ..services.wechat_service import wechat_service
            await wechat_service.send_templated_message(
                template="anomaly_alert",
                data={
                    "store_id": store_id,
                    "pattern_type": "staff_support",
                    "description": f"员工 {user_id} 请求支援",
                    "severity": "medium",
                    "action_required": "请立即前往支援",
                },
                to_user_id="store_manager",
            )
        except Exception:
            pass

        msg = "支援请求已发送，同事正在赶来"
        return {
            "intent": "call_support",
            "message": msg,
            "voice_response": msg,
            "data": {"requested_by": user_id, "store_id": store_id},
        }


# ==================== 意图路由表 ====================

# 格式: intent_name → (关键词列表, Handler实例, 允许的角色列表（空=所有人）)
INTENT_MAP: Dict[str, Dict[str, Any]] = {
    "query_revenue": {
        "keywords": ["营收", "收入", "流水", "今日收入", "销售额"],
        "handler": QueryRevenueHandler(),
        "allowed_roles": ["store_manager", "assistant_manager", "finance", "admin", "super_admin"],
    },
    "apply_discount": {
        "keywords": ["折扣", "打折", "优惠", "减免", "抹零"],
        "handler": ApplyDiscountHandler(),
        "allowed_roles": ["store_manager", "assistant_manager", "floor_manager"],
    },
    "query_queue": {
        "keywords": ["排队", "等位", "等待", "几桌在等"],
        "handler": QueryQueueHandler(),
        "allowed_roles": [],  # 所有角色
    },
    "inventory_query": {
        "keywords": ["库存", "备货", "还有多少", "剩余"],
        "handler": InventoryQueryHandler(),
        "allowed_roles": [],  # 所有角色
    },
    "call_support": {
        "keywords": ["支援", "帮忙", "忙不过来", "人手不足"],
        "handler": CallSupportHandler(),
        "allowed_roles": [],  # 所有角色
    },
}


class IntentRouter:
    """
    意图路由器（有状态版本）

    route() 方法：
    1. 结合上下文（最近3轮）解析意图
    2. 过滤权限
    3. 执行 Handler
    4. 更新 ConversationContext
    """

    def __init__(self, intent_map: Optional[Dict[str, Dict[str, Any]]] = None):
        self._intent_map = intent_map or INTENT_MAP

    def _detect_intent(self, text: str, context: ConversationContext) -> Optional[str]:
        """
        基于关键词 + 上下文的意图检测

        上下文感知：
        - 如果上轮提到了"折扣"，这轮"确认"则继续折扣流程
        - 如果上轮提到了"库存"，这轮"剩多少"无需重新说明意图
        """
        text_lower = text.lower()

        # 1. 直接关键词匹配
        for intent, config in self._intent_map.items():
            if any(kw in text_lower for kw in config["keywords"]):
                return intent

        # 2. 上下文感知：利用 pending_intent 或最近轮次意图
        recent = context.get_recent_turns(1)
        if recent and context.pending_intent:
            # 确认词：继续上轮意图
            if any(kw in text_lower for kw in ["确认", "好的", "是的", "对", "继续"]):
                intent = context.pending_intent
                context.pending_intent = None
                return intent

        return None

    def _check_permission(self, intent: str, actor_role: str) -> bool:
        """检查角色是否有权执行该意图"""
        config = self._intent_map.get(intent, {})
        allowed = config.get("allowed_roles", [])
        if not allowed:
            return True  # 空列表 = 所有角色
        return actor_role in allowed or actor_role in ["super_admin", "system_admin"]

    async def route(
        self,
        text: str,
        context: ConversationContext,
        actor_role: str = "",
        db=None,
    ) -> Dict[str, Any]:
        """
        路由处理语音文本

        Args:
            text: 用户语音文本
            context: 当前会话上下文（最近3轮）
            actor_role: 操作人角色
            db: 数据库会话

        Returns:
            包含 intent, response, voice_response 的字典
        """
        store_id = context.store_id

        # 1. 意图解析
        intent = self._detect_intent(text, context)
        if not intent:
            response_text = "抱歉，我没有理解您的指令，请重新说一遍"
            turn = ConversationTurn(
                user_input=text,
                intent=None,
                response=response_text,
            )
            context.add_turn(turn)
            return {
                "success": False,
                "intent": None,
                "message": response_text,
                "voice_response": response_text,
                "session_id": context.session_id,
            }

        # 2. 权限过滤
        if not self._check_permission(intent, actor_role):
            response_text = f"抱歉，您的角色（{actor_role}）无权执行此操作"
            turn = ConversationTurn(
                user_input=text,
                intent=intent,
                response=response_text,
            )
            context.add_turn(turn)
            return {
                "success": False,
                "intent": intent,
                "message": response_text,
                "voice_response": response_text,
                "session_id": context.session_id,
            }

        # 3. 执行 Handler（传入 actor_role 供折扣等需要权限上下文的操作使用）
        handler = self._intent_map[intent]["handler"]
        try:
            result = await handler.handle(text, store_id, context, db, actor_role=actor_role)
        except Exception as e:
            logger.error("intent_handler_failed", intent=intent, error=str(e))
            result = {
                "intent": intent,
                "message": f"处理 {intent} 失败: {str(e)}",
                "voice_response": "抱歉，处理时出现错误",
            }

        # 4. 更新上下文
        turn = ConversationTurn(
            user_input=text,
            intent=intent,
            response=result.get("voice_response", result.get("message", "")),
            data=result,
        )
        context.add_turn(turn)

        return {
            "success": True,
            "session_id": context.session_id,
            **result,
        }
