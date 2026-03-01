"""
FEAT-001: 语音会话上下文模型

ConversationTurn + ConversationContext 使语音交互具有状态（记忆最近3轮对话）。
存储在 Redis，TTL 30分钟（会话超时自动清除）。
"""
import json
import uuid
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

CONVERSATION_TTL = 30 * 60  # 30分钟


class ConversationTurn(BaseModel):
    """单轮对话记录"""
    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_input: str
    intent: Optional[str] = None
    response: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationContext(BaseModel):
    """会话上下文（有状态，最近3轮）"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    turns: List[ConversationTurn] = Field(default_factory=list)

    # 会话元数据（跨轮次记忆）
    current_table: Optional[str] = None     # 当前操作桌号
    current_order_id: Optional[str] = None  # 当前订单ID
    pending_intent: Optional[str] = None    # 待确认意图（多步操作用）

    MAX_TURNS: ClassVar[int] = 3  # 保留最近3轮

    def add_turn(self, turn: ConversationTurn) -> None:
        """添加对话轮次，超过 MAX_TURNS 时移除最旧的"""
        self.turns.append(turn)
        if len(self.turns) > self.MAX_TURNS:
            self.turns = self.turns[-self.MAX_TURNS:]
        self.last_active = datetime.utcnow()

    def get_recent_turns(self, n: int = 3) -> List[ConversationTurn]:
        """获取最近 N 轮对话"""
        return self.turns[-n:]

    def get_context_summary(self) -> str:
        """生成上下文摘要（提供给 NLU）"""
        if not self.turns:
            return ""
        lines = []
        for turn in self.get_recent_turns():
            lines.append(f"用户: {turn.user_input}")
            lines.append(f"系统: {turn.response[:100]}")
        return "\n".join(lines)


class ConversationStore:
    """
    ConversationContext 的 Redis 存储

    Key 格式: conversation:{session_id}
    TTL: 30分钟
    """

    REDIS_KEY_PREFIX = "conversation:"

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _key(self, session_id: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}{session_id}"

    async def load(self, session_id: str) -> Optional[ConversationContext]:
        """从 Redis 加载会话上下文"""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(self._key(session_id))
            if not raw:
                return None
            return ConversationContext(**json.loads(raw))
        except Exception as e:
            logger.warning("conversation.load_failed", session_id=session_id, error=str(e))
            return None

    async def save(self, context: ConversationContext) -> bool:
        """保存会话上下文"""
        if not self._redis:
            return False
        try:
            key = self._key(context.session_id)
            raw = context.model_dump_json()
            await self._redis.set(key, raw, ex=CONVERSATION_TTL)
            return True
        except Exception as e:
            logger.error("conversation.save_failed", session_id=context.session_id, error=str(e))
            return False

    async def expire(self, session_id: str) -> bool:
        """使会话立即过期"""
        if not self._redis:
            return False
        try:
            await self._redis.delete(self._key(session_id))
            return True
        except Exception as e:
            logger.warning("conversation.expire_failed", session_id=session_id, error=str(e))
            return False

    async def get_or_create(
        self,
        session_id: Optional[str],
        store_id: str,
        user_id: str,
    ) -> ConversationContext:
        """加载已有会话或创建新会话"""
        if session_id:
            context = await self.load(session_id)
            if context:
                return context
        # 创建新会话
        return ConversationContext(
            store_id=store_id,
            user_id=user_id,
        )
