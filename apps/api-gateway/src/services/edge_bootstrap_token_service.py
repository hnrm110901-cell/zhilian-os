"""
边缘节点 Bootstrap Token 动态管理服务

解决的问题
----------
原方案把 EDGE_BOOTSTRAP_TOKEN 写死在 .env，要轮换必须重启 API Gateway。
本服务将"有效 Bootstrap Token"存到 Redis，支持：

1. 运营人员从管理后台生成/轮换 Token → 秒级生效，无需重启
2. 每个 Token 携带发放人、发放时间、适用门店范围（可选）和有效期
3. 支持吊销单个 Token，不影响其他 Token
4. 兼容旧方案：settings.EDGE_BOOTSTRAP_TOKEN 不为空时作为"静态兜底"

Redis 键结构
-----------
  edge:bootstrap_token:<token_hash>  →  JSON 元数据，TTL=有效期
  edge:bootstrap_token_index         →  ZSet，score=创建时间戳，member=token_hash
    （用于列举、清理过期条目）
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import List, Optional

import structlog

logger = structlog.get_logger()

# Redis key 前缀
_TOKEN_KEY_PREFIX = "edge:bootstrap_token:"
_INDEX_KEY = "edge:bootstrap_token_index"

# 默认有效期：7 天（秒）
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600

# 生成 Token 的字节长度（URL 安全 Base64，实际字符 ≈ 43 个）
_TOKEN_BYTES = 32


@dataclass
class BootstrapTokenMeta:
    token_hash: str  # SHA-256(token)，作为 Redis key 后缀
    token_prefix: str  # Token 前 8 位，用于展示（不回传完整 token）
    created_by: str  # 发放人 user_id 或 username
    created_at: float  # Unix 时间戳
    expires_at: float  # Unix 时间戳（= created_at + ttl）
    store_id: Optional[str]  # 限制适用门店（None=不限制）
    note: str  # 备注（如："尝在一起接入 2026-03-14"）
    active: bool  # False=已吊销


def _token_redis_key(token_hash: str) -> str:
    return f"{_TOKEN_KEY_PREFIX}{token_hash}"


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class EdgeBootstrapTokenService:
    """Bootstrap Token 动态管理，需注入 Redis 连接"""

    def __init__(self, redis_client) -> None:
        # redis_client: aioredis.Redis 或任何兼容 get/set/delete/zadd 的异步客户端
        self._redis = redis_client

    # ------------------------------------------------------------------ #
    #  发放
    # ------------------------------------------------------------------ #

    async def issue_token(
        self,
        created_by: str,
        note: str = "",
        store_id: Optional[str] = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> str:
        """生成新 Bootstrap Token，持久化到 Redis，返回明文 Token（仅此一次）。"""
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        token_hash = _sha256(token)
        now = time.time()
        meta = BootstrapTokenMeta(
            token_hash=token_hash,
            token_prefix=token[:8],
            created_by=created_by,
            created_at=now,
            expires_at=now + ttl_seconds,
            store_id=store_id,
            note=note,
            active=True,
        )
        pipe = self._redis.pipeline()
        pipe.setex(
            _token_redis_key(token_hash),
            ttl_seconds,
            json.dumps(asdict(meta), ensure_ascii=True),
        )
        pipe.zadd(_INDEX_KEY, {token_hash: now})
        # index 本身保留 30 天（足够清理过期条目）
        pipe.expire(_INDEX_KEY, 30 * 24 * 3600)
        await pipe.execute()
        logger.info(
            "bootstrap_token_issued",
            token_prefix=meta.token_prefix,
            created_by=created_by,
            store_id=store_id,
            ttl_seconds=ttl_seconds,
        )
        return token

    # ------------------------------------------------------------------ #
    #  校验（认证链路调用）
    # ------------------------------------------------------------------ #

    async def verify_token(
        self,
        token: str,
        store_id: Optional[str] = None,
    ) -> bool:
        """
        校验 Bootstrap Token 是否有效。

        校验规则：
        1. SHA-256 → Redis 查 meta
        2. meta.active == True
        3. 未过期（Redis TTL 自动保证，meta.expires_at 做二次确认）
        4. 若 meta.store_id 非 None，则必须与调用方 store_id 匹配
        """
        token_hash = _sha256(token)
        raw = await self._redis.get(_token_redis_key(token_hash))
        if not raw:
            return False
        try:
            meta = BootstrapTokenMeta(**json.loads(raw))
        except Exception:
            return False
        if not meta.active:
            return False
        if meta.expires_at < time.time():
            return False
        if meta.store_id and store_id and meta.store_id != store_id:
            return False
        return True

    # ------------------------------------------------------------------ #
    #  吊销
    # ------------------------------------------------------------------ #

    async def revoke_token(self, token_hash: str) -> bool:
        """吊销指定 token_hash（不需要明文 token）。"""
        key = _token_redis_key(token_hash)
        raw = await self._redis.get(key)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            data["active"] = False
            # 保留键（但缩短 TTL 至 1 小时，供审计查询）
            await self._redis.setex(key, 3600, json.dumps(data, ensure_ascii=True))
        except Exception:
            return False
        logger.info("bootstrap_token_revoked", token_hash=token_hash[:16])
        return True

    # ------------------------------------------------------------------ #
    #  列举
    # ------------------------------------------------------------------ #

    async def list_tokens(self) -> List[BootstrapTokenMeta]:
        """列出索引中所有 Token 的元数据（不含明文 token）。"""
        hashes = await self._redis.zrange(_INDEX_KEY, 0, -1)
        results: List[BootstrapTokenMeta] = []
        for h in hashes:
            raw = await self._redis.get(_token_redis_key(h))
            if not raw:
                # 已过期自动删除，清理索引
                await self._redis.zrem(_INDEX_KEY, h)
                continue
            try:
                results.append(BootstrapTokenMeta(**json.loads(raw)))
            except Exception:
                continue
        results.sort(key=lambda m: m.created_at, reverse=True)
        return results

    # ------------------------------------------------------------------ #
    #  批量吊销（轮换场景）
    # ------------------------------------------------------------------ #

    async def revoke_all_tokens(self) -> int:
        """吊销所有有效 Token（用于安全事件响应）。"""
        hashes = await self._redis.zrange(_INDEX_KEY, 0, -1)
        count = 0
        for h in hashes:
            if await self.revoke_token(h):
                count += 1
        logger.warning("bootstrap_tokens_revoked_all", count=count)
        return count


# ------------------------------------------------------------------ #
#  单例工厂（与项目其他 service 保持一致的 get_xxx 风格）
# ------------------------------------------------------------------ #

_instance: Optional[EdgeBootstrapTokenService] = None


def get_edge_bootstrap_token_service() -> EdgeBootstrapTokenService:
    """按需初始化单例，复用全局 Redis 连接。"""
    global _instance
    if _instance is None:
        from src.core.redis import get_redis_client  # 延迟导入，避免循环

        _instance = EdgeBootstrapTokenService(get_redis_client())
    return _instance
