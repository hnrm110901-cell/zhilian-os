"""
MemberContextStore — 私域会员实时上下文缓存

将会员核心画像缓存在 Redis，实现：
  1. journey_orchestrator._get_member_profile() 读缓存，避免每步执行都查 DB
  2. scan_lifecycle_transitions 状态转移后 invalidate，保证一致性
  3. refresh_private_domain_rfm 批量 invalidate，RFM 刷新后缓存自动重建

Key 格式：member_ctx:{store_id}:{customer_id}
Value：JSON 字符串
TTL：25 小时（稍大于 24h RFM 刷新周期，防止 stale data）

降级策略：Redis 不可用时所有方法静默返回 None / 空操作，业务不中断。
"""

from __future__ import annotations

import inspect
import json
import os
from typing import Any, Dict, Optional

import redis.exceptions
import structlog

logger = structlog.get_logger()

_CTX_TTL = int(os.getenv("MEMBER_CTX_TTL", str(25 * 3600)))  # 25h


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


# ── Redis key 构造（纯函数）────────────────────────────────────────────────────


def make_context_key(store_id: str, customer_id: str) -> str:
    """
    生成会员上下文 Redis key。

    格式：member_ctx:{store_id}:{customer_id}

    >>> make_context_key("S001", "C001")
    'member_ctx:S001:C001'
    """
    return f"member_ctx:{store_id}:{customer_id}"


# ── 模块级单例（懒初始化）─────────────────────────────────────────────────────

_store_instance: Optional["MemberContextStore"] = None


async def get_context_store() -> Optional["MemberContextStore"]:
    """
    获取全局 MemberContextStore 单例（懒初始化）。

    REDIS_URL 未配置时返回 None，调用方按无缓存处理。
    """
    global _store_instance
    if _store_instance is not None:
        return _store_instance

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
        _store_instance = MemberContextStore(client)
        logger.info("member_context_store.initialized", url=url[:30])
        return _store_instance
    except (redis.exceptions.RedisError, ConnectionError, OSError) as exc:
        logger.warning("member_context_store.init_failed", error=str(exc))
        return None


def reset_context_store() -> None:
    """重置单例（仅供测试使用）。"""
    global _store_instance
    _store_instance = None


# ── 核心服务类 ────────────────────────────────────────────────────────────────


class MemberContextStore:
    """
    会员实时上下文 Redis 缓存服务。

    所有方法在 Redis 不可用时静默降级，业务不受影响。
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def get(self, store_id: str, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        读取会员上下文缓存。

        Returns:
            dict（含 frequency / monetary / recency_days /
                  lifecycle_state / maslow_level / last_updated）
            或 None（缓存未命中 / Redis 不可用）
        """
        if not self._redis:
            return None
        try:
            raw = await _maybe_await(self._redis.get(make_context_key(store_id, customer_id)))
            if raw is None:
                return None
            return json.loads(raw)
        except (redis.exceptions.RedisError, ConnectionError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.debug(
                "member_context_store.get_failed",
                store_id=store_id,
                customer_id=customer_id,
                error=str(exc),
            )
            return None

    async def set(
        self,
        store_id: str,
        customer_id: str,
        data: Dict[str, Any],
        ttl: int = _CTX_TTL,
    ) -> None:
        """
        写入会员上下文缓存。

        Args:
            data: 任意可 JSON 序列化的 dict
            ttl:  过期秒数，默认 25h
        """
        if not self._redis:
            return
        try:
            await _maybe_await(
                self._redis.setex(
                    make_context_key(store_id, customer_id),
                    ttl,
                    json.dumps(data, ensure_ascii=False, default=str),
                )
            )
        except (redis.exceptions.RedisError, ConnectionError, TypeError, ValueError) as exc:
            logger.debug(
                "member_context_store.set_failed",
                store_id=store_id,
                customer_id=customer_id,
                error=str(exc),
            )

    async def invalidate(self, store_id: str, customer_id: str) -> None:
        """
        删除会员上下文缓存（状态转移后调用）。

        不存在的 key 不报错。
        """
        if not self._redis:
            return
        try:
            await _maybe_await(self._redis.delete(make_context_key(store_id, customer_id)))
            logger.debug(
                "member_context_store.invalidated",
                store_id=store_id,
                customer_id=customer_id,
            )
        except (redis.exceptions.RedisError, ConnectionError) as exc:
            logger.debug(
                "member_context_store.invalidate_failed",
                store_id=store_id,
                customer_id=customer_id,
                error=str(exc),
            )

    async def invalidate_store(self, store_id: str) -> int:
        """
        批量删除某门店所有会员的上下文缓存。

        用于 RFM 批量刷新后的全量 invalidate。

        Returns:
            删除的 key 数量（Redis 不可用时返回 0）
        """
        if not self._redis:
            return 0
        try:
            pattern = f"member_ctx:{store_id}:*"
            deleted = 0
            keys_iter = await _maybe_await(self._redis.scan_iter(match=pattern, count=200))
            if hasattr(keys_iter, "__aiter__"):
                async for key in keys_iter:
                    await _maybe_await(self._redis.delete(key))
                    deleted += 1
            else:
                for key in keys_iter or []:
                    await _maybe_await(self._redis.delete(key))
                    deleted += 1
            logger.info(
                "member_context_store.store_invalidated",
                store_id=store_id,
                deleted=deleted,
            )
            return deleted
        except (redis.exceptions.RedisError, ConnectionError) as exc:
            logger.warning(
                "member_context_store.invalidate_store_failed",
                store_id=store_id,
                error=str(exc),
            )
            return 0
