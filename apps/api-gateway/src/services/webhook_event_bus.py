"""
Webhook 事件总线

核心能力：
  1. 事件处理器注册（按事件类型分发）
  2. 异步分发（asyncio.create_task）
  3. 幂等去重（event_id，TTL 24小时）
  4. 失败重试（最多3次，指数退避）
  5. 死信队列（超过重试次数的事件记录到死信）

当前阶段使用内存队列，后续迁移到 Redis Stream。
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 事件处理器类型：接收事件字典，返回任意值
EventHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Any]]

# 去重缓存 TTL（秒）— 24小时
_DEDUP_TTL_SECONDS = 86400

# 最大重试次数
_MAX_RETRIES = 3

# 指数退避基数（秒）
_BACKOFF_BASE = 1.0


class WebhookEventBus:
    """
    Webhook 事件总线

    使用方式：
        bus = WebhookEventBus()
        bus.register("order.created", handle_order_created)
        await bus.publish("order.created", event_id="xxx", payload={...})
    """

    def __init__(self):
        # 事件类型 -> 处理器列表
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        # event_id -> 接收时间戳（用于去重）
        self._seen_events: Dict[str, float] = {}
        # 死信队列（超过重试次数的事件）
        self._dead_letter: List[Dict[str, Any]] = []
        # 处理统计
        self._stats: Dict[str, int] = defaultdict(int)

    def register(self, event_type: str, handler: EventHandler) -> None:
        """
        注册事件处理器

        同一事件类型可注册多个处理器，按注册顺序执行。

        Args:
            event_type: 事件类型，如 "order.created"
            handler: 异步处理函数
        """
        self._handlers[event_type].append(handler)
        logger.info("事件处理器已注册", event_type=event_type, handler=handler.__name__)

    def unregister(self, event_type: str, handler: EventHandler) -> bool:
        """注销事件处理器"""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    def is_duplicate(self, event_id: str) -> bool:
        """
        幂等检查：该 event_id 是否已处理过

        同时清理过期记录以防内存泄漏。
        """
        self._cleanup_expired()
        return event_id in self._seen_events

    def mark_seen(self, event_id: str) -> None:
        """标记 event_id 为已处理"""
        self._seen_events[event_id] = time.time()

    async def publish(
        self,
        event_type: str,
        event_id: str,
        payload: Dict[str, Any],
        source: str = "webhook",
    ) -> Dict[str, Any]:
        """
        发布事件到总线

        执行去重检查后，异步分发给所有已注册的处理器。

        Args:
            event_type: 事件类型
            event_id: 事件唯一ID（用于幂等去重）
            payload: 事件载荷
            source: 来源标识

        Returns:
            分发结果 {accepted, duplicate, handlers_count, event_id}
        """
        # 幂等去重
        if self.is_duplicate(event_id):
            logger.info("事件重复，已忽略", event_id=event_id, event_type=event_type)
            self._stats["duplicates"] += 1
            return {
                "accepted": False,
                "duplicate": True,
                "handlers_count": 0,
                "event_id": event_id,
            }

        # 标记为已处理
        self.mark_seen(event_id)

        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.warning("无处理器", event_type=event_type, event_id=event_id)
            self._stats["no_handler"] += 1
            return {
                "accepted": True,
                "duplicate": False,
                "handlers_count": 0,
                "event_id": event_id,
            }

        # 构造事件对象
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 异步分发给所有处理器
        self._stats["published"] += 1
        for handler in handlers:
            asyncio.create_task(
                self._dispatch_with_retry(handler, event)
            )

        return {
            "accepted": True,
            "duplicate": False,
            "handlers_count": len(handlers),
            "event_id": event_id,
        }

    async def _dispatch_with_retry(
        self,
        handler: EventHandler,
        event: Dict[str, Any],
    ) -> None:
        """
        带重试的事件分发

        失败后指数退避重试，最多 _MAX_RETRIES 次。
        超过重试次数后记录到死信队列。
        """
        last_error: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                await handler(event)
                self._stats["success"] += 1
                if attempt > 0:
                    logger.info(
                        "事件重试成功",
                        event_id=event["event_id"],
                        handler=handler.__name__,
                        attempt=attempt,
                    )
                return
            except Exception as exc:
                last_error = exc
                self._stats["retries"] += 1
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "事件处理失败，准备重试",
                        event_id=event["event_id"],
                        handler=handler.__name__,
                        attempt=attempt + 1,
                        wait_seconds=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)

        # 超过重试次数，进入死信
        self._stats["dead_letter"] += 1
        dead_entry = {
            "event": event,
            "handler": handler.__name__,
            "error": str(last_error),
            "retries": _MAX_RETRIES,
            "dead_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dead_letter.append(dead_entry)
        logger.error(
            "事件进入死信队列",
            event_id=event["event_id"],
            handler=handler.__name__,
            error=str(last_error),
        )

    def _cleanup_expired(self) -> None:
        """清理过期的去重记录"""
        now = time.time()
        expired = [
            eid for eid, ts in self._seen_events.items()
            if now - ts > _DEDUP_TTL_SECONDS
        ]
        for eid in expired:
            del self._seen_events[eid]

    def get_stats(self) -> Dict[str, Any]:
        """获取事件总线统计"""
        return {
            "published": self._stats["published"],
            "success": self._stats["success"],
            "retries": self._stats["retries"],
            "duplicates": self._stats["duplicates"],
            "dead_letter": self._stats["dead_letter"],
            "no_handler": self._stats["no_handler"],
            "registered_types": list(self._handlers.keys()),
            "seen_events_count": len(self._seen_events),
            "dead_letter_count": len(self._dead_letter),
        }

    def get_dead_letters(self) -> List[Dict[str, Any]]:
        """获取死信队列内容"""
        return list(self._dead_letter)

    def clear_dead_letters(self) -> int:
        """清空死信队列，返回清理数量"""
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count


# 模块级单例
webhook_event_bus = WebhookEventBus()
