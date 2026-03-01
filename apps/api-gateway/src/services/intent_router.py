"""
FEAT-001: 意图路由器

IntentRouter 负责：
1. 意图解析（基于关键词 + 上下文）
2. 权限过滤（不同角色可访问不同意图）
3. 执行对应 Handler
4. 更新 ConversationContext
"""
from typing import Any, Callable, Dict, Optional
import structlog

from ..models.conversation import ConversationContext, ConversationTurn

logger = structlog.get_logger()


# ==================== 意图 Handler 类型 ====================

HandlerFn = Callable[[str, str, ConversationContext, Optional[Any]], Any]


# ==================== 内置 Handler 占位实现 ====================

class QueryRevenueHandler:
    async def handle(self, text: str, store_id: str, context: ConversationContext, db=None) -> Dict[str, Any]:
        return {"intent": "query_revenue", "message": "正在查询今日营收...", "voice_response": "正在查询今日营收"}


class ApplyDiscountHandler:
    async def handle(self, text: str, store_id: str, context: ConversationContext, db=None) -> Dict[str, Any]:
        return {
            "intent": "apply_discount",
            "message": "折扣申请需要审批，已提交给店长",
            "voice_response": "折扣申请已提交给店长审批",
        }


class QueryQueueHandler:
    async def handle(self, text: str, store_id: str, context: ConversationContext, db=None) -> Dict[str, Any]:
        return {"intent": "query_queue", "message": "正在查询排队状态...", "voice_response": "正在查询排队状态"}


class InventoryQueryHandler:
    async def handle(self, text: str, store_id: str, context: ConversationContext, db=None) -> Dict[str, Any]:
        return {"intent": "inventory_query", "message": "正在查询库存...", "voice_response": "正在查询库存"}


class CallSupportHandler:
    async def handle(self, text: str, store_id: str, context: ConversationContext, db=None) -> Dict[str, Any]:
        return {"intent": "call_support", "message": "支援请求已发送", "voice_response": "支援请求已发送，同事正在赶来"}


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

        # 3. 执行 Handler
        handler = self._intent_map[intent]["handler"]
        try:
            result = await handler.handle(text, store_id, context, db)
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
