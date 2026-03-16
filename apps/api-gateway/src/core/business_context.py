"""
BusinessContext — 跨模块上下文流动基础设施

解决问题：lifecycle_bridge 的5个桥接各自独立获取上下文，信息在模块边界丢失。

设计：
  - 轻量级 dataclass，伴随每次跨模块调用传递 who/why/how/history 上下文
  - 复用 AgentMessage 已有的 trace_id 字段
  - Redis 暂存（复用 member_context_store 的连接模式），TTL=1h
  - 持久化靠 DecisionLog.context_data JSON 字段，无新 DB 表

用法：
    ctx = BusinessContext(store_id="S001", trigger="reservation.arrived")
    ctx.add_breadcrumb("reservation:R001")
    ctx.accumulate("party_size", 8)

    # 传递到下一个模块
    ctx.add_breadcrumb("order:O001")

    # 序列化/反序列化
    d = ctx.to_dict()
    ctx2 = BusinessContext.from_dict(d)

    # 从 AgentMessage 提取
    ctx3 = BusinessContext.from_agent_message(msg)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

_BIZ_CTX_TTL = int(os.getenv("BIZ_CTX_TTL", str(3600)))  # 1h


@dataclass
class BusinessContext:
    """跨模块业务上下文，伴随调用链传递。"""

    # WHO
    store_id: str = ""
    actor_id: Optional[str] = None  # user 或 agent id
    actor_role: Optional[str] = None  # "store_manager" | "agent:schedule"
    customer_id: Optional[str] = None  # consumer_id

    # WHY
    trigger: str = ""  # "reservation.arrived" | "order.completed"
    source_event_id: Optional[str] = None
    parent_context_id: Optional[str] = None

    # HOW（追踪）
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decision_log_id: Optional[str] = None

    # HISTORY（累积）
    breadcrumbs: List[str] = field(default_factory=list)
    accumulated_data: Dict[str, Any] = field(default_factory=dict)

    def add_breadcrumb(self, crumb: str) -> "BusinessContext":
        """添加面包屑（链式调用）。"""
        self.breadcrumbs.append(crumb)
        return self

    def accumulate(self, key: str, value: Any) -> "BusinessContext":
        """累积上下文数据（链式调用）。"""
        self.accumulated_data[key] = value
        return self

    def child(self, trigger: str) -> "BusinessContext":
        """创建子上下文，继承 trace_id 和历史，设置新的 trigger。"""
        return BusinessContext(
            store_id=self.store_id,
            actor_id=self.actor_id,
            actor_role=self.actor_role,
            customer_id=self.customer_id,
            trigger=trigger,
            source_event_id=self.source_event_id,
            parent_context_id=self.trace_id,
            trace_id=self.trace_id,  # 共用 trace_id
            decision_log_id=self.decision_log_id,
            breadcrumbs=list(self.breadcrumbs),
            accumulated_data=dict(self.accumulated_data),
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（可存入 JSON 字段）。"""
        return {
            "store_id": self.store_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "customer_id": self.customer_id,
            "trigger": self.trigger,
            "source_event_id": self.source_event_id,
            "parent_context_id": self.parent_context_id,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "decision_log_id": self.decision_log_id,
            "breadcrumbs": self.breadcrumbs,
            "accumulated_data": self.accumulated_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BusinessContext":
        """从字典反序列化。"""
        return cls(
            store_id=data.get("store_id", ""),
            actor_id=data.get("actor_id"),
            actor_role=data.get("actor_role"),
            customer_id=data.get("customer_id"),
            trigger=data.get("trigger", ""),
            source_event_id=data.get("source_event_id"),
            parent_context_id=data.get("parent_context_id"),
            trace_id=data.get("trace_id", str(uuid.uuid4())),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            decision_log_id=data.get("decision_log_id"),
            breadcrumbs=list(data.get("breadcrumbs", [])),
            accumulated_data=dict(data.get("accumulated_data", {})),
        )

    @classmethod
    def from_agent_message(cls, msg: Any) -> "BusinessContext":
        """
        从 AgentMessage 提取 BusinessContext。

        如果 msg.context 已有序列化的 BusinessContext，反序列化；
        否则从 msg 的基本字段构建新的 BusinessContext。
        """
        # 优先从 msg.context 恢复
        ctx_data = getattr(msg, "context", None)
        if ctx_data and isinstance(ctx_data, dict):
            ctx = cls.from_dict(ctx_data)
            # 确保 trace_id 一致
            ctx.trace_id = getattr(msg, "trace_id", ctx.trace_id)
            return ctx

        # 从基本字段构建
        return cls(
            store_id=getattr(msg, "store_id", ""),
            actor_id=getattr(msg, "from_agent", None),
            actor_role=f"agent:{getattr(msg, 'from_agent', 'unknown')}",
            trigger=getattr(msg, "action", ""),
            trace_id=getattr(msg, "trace_id", str(uuid.uuid4())),
        )


# ── BusinessContextStore（Redis 缓存）────────────────────────────────────────

_ctx_store_instance: Optional["BusinessContextStore"] = None


async def get_business_context_store() -> Optional["BusinessContextStore"]:
    """获取全局 BusinessContextStore 单例（懒初始化）。"""
    global _ctx_store_instance
    if _ctx_store_instance is not None:
        return _ctx_store_instance

    url = os.getenv("REDIS_URL")
    if not url:
        return None

    try:
        import redis.asyncio as aioredis

        client = await aioredis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
        )
        _ctx_store_instance = BusinessContextStore(client)
        logger.info("business_context_store.initialized")
        return _ctx_store_instance
    except Exception as exc:
        logger.warning("business_context_store.init_failed", error=str(exc))
        return None


def reset_business_context_store() -> None:
    """重置单例（仅供测试使用）。"""
    global _ctx_store_instance
    _ctx_store_instance = None


class BusinessContextStore:
    """BusinessContext 的 Redis 缓存，key=biz_ctx:{trace_id}，TTL=1h。"""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def save(self, ctx: BusinessContext) -> None:
        """保存上下文到 Redis。"""
        if not self._redis:
            return
        try:
            key = f"biz_ctx:{ctx.trace_id}"
            await self._redis.setex(
                key,
                _BIZ_CTX_TTL,
                json.dumps(ctx.to_dict(), ensure_ascii=False, default=str),
            )
        except Exception as exc:
            logger.debug("business_context_store.save_failed", error=str(exc))

    async def load(self, trace_id: str) -> Optional[BusinessContext]:
        """从 Redis 加载上下文。"""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(f"biz_ctx:{trace_id}")
            if raw is None:
                return None
            return BusinessContext.from_dict(json.loads(raw))
        except Exception as exc:
            logger.debug("business_context_store.load_failed", error=str(exc))
            return None
