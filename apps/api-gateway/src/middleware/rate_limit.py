"""
API速率限制中间件
防止API滥用，保护系统资源
使用Redis存储，支持分布式部署
"""
import time
import os
from typing import Dict, Optional
from datetime import datetime, timedelta
import structlog
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis.asyncio as redis
import json

logger = structlog.get_logger()


class RedisRateLimiter:
    """基于Redis的速率限制器"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        初始化Redis速率限制器

        Args:
            redis_url: Redis连接URL
        """
        self.redis_client = None
        self.redis_url = redis_url
        self._initialized = False

        # 速率限制配置（支持环境变量覆盖）
        self.limits = {
            "default": {
                "requests": int(os.getenv("RATE_LIMIT_DEFAULT_REQUESTS", "100")),
                "window": int(os.getenv("RATE_LIMIT_DEFAULT_WINDOW", "60")),
            },
            "auth": {
                "requests": int(os.getenv("RATE_LIMIT_AUTH_REQUESTS", "10")),
                "window": int(os.getenv("RATE_LIMIT_AUTH_WINDOW", "60")),
            },
            "oauth": {
                "requests": int(os.getenv("RATE_LIMIT_OAUTH_REQUESTS", "5")),
                "window": int(os.getenv("RATE_LIMIT_OAUTH_WINDOW", "300")),
            },
            "backup": {
                "requests": int(os.getenv("RATE_LIMIT_BACKUP_REQUESTS", "5")),
                "window": int(os.getenv("RATE_LIMIT_BACKUP_WINDOW", "300")),
            },
            "analytics": {
                "requests": int(os.getenv("RATE_LIMIT_ANALYTICS_REQUESTS", "30")),
                "window": int(os.getenv("RATE_LIMIT_ANALYTICS_WINDOW", "60")),
            },
        }

    async def initialize(self):
        """初始化Redis连接"""
        if self._initialized:
            return

        try:
            self.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            await self.redis_client.ping()
            self._initialized = True
            logger.info("速率限制器Redis连接初始化成功")
        except Exception as e:
            logger.error("速率限制器Redis连接初始化失败", error=str(e))
            raise

    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识"""
        # 优先使用用户ID（如果已认证）
        if hasattr(request.state, "user") and request.state.user:
            user_id = getattr(request.state.user, "id", None)
            if user_id:
                return f"user:{user_id}"

        # 否则使用IP地址
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    def _get_limit_config(self, path: str) -> Dict[str, int]:
        """根据路径获取限制配置"""
        if "/auth/login" in path or "/auth/register" in path:
            return self.limits["auth"]
        elif "/auth/oauth/" in path:
            return self.limits["oauth"]
        elif "/backup/" in path:
            return self.limits["backup"]
        elif "/analytics/" in path:
            return self.limits["analytics"]
        else:
            return self.limits["default"]

    def _get_redis_key(self, client_id: str, path: str) -> str:
        """生成Redis键"""
        return f"rate_limit:{client_id}:{path}"

    async def is_allowed(self, request: Request) -> tuple[bool, Optional[Dict]]:
        """
        检查请求是否允许

        使用Redis的INCR和EXPIRE命令实现滑动窗口限流

        Args:
            request: FastAPI请求对象

        Returns:
            (是否允许, 限流信息)
        """
        # 确保Redis已初始化
        if not self._initialized:
            await self.initialize()

        client_id = self._get_client_id(request)
        path = request.url.path
        limit_config = self._get_limit_config(path)

        max_requests = limit_config["requests"]
        window = limit_config["window"]

        redis_key = self._get_redis_key(client_id, path)

        try:
            # 使用Redis Pipeline提升性能
            pipe = self.redis_client.pipeline()

            # 获取当前计数
            pipe.get(redis_key)
            # 增加计数
            pipe.incr(redis_key)
            # 设置过期时间
            pipe.expire(redis_key, window)

            results = await pipe.execute()
            current_count = int(results[0]) if results[0] else 0
            new_count = int(results[1])

            if current_count >= max_requests:
                # 获取TTL计算重试时间
                ttl = await self.redis_client.ttl(redis_key)
                retry_after = max(ttl, 1)

                return False, {
                    "client_id": client_id,
                    "limit": max_requests,
                    "window": window,
                    "current": current_count,
                    "retry_after": retry_after
                }

            return True, {
                "client_id": client_id,
                "limit": max_requests,
                "window": window,
                "remaining": max_requests - new_count
            }

        except redis.RedisError as e:
            logger.error("Redis rate limiter error", error=str(e))
            # Redis故障时，允许请求通过（降级策略）
            return True, {
                "client_id": client_id,
                "limit": max_requests,
                "window": window,
                "remaining": max_requests,
                "fallback": True
            }

    async def reset(self, client_id: str, path: str = "*"):
        """
        重置客户端的速率限制

        Args:
            client_id: 客户端ID
            path: 路径（*表示所有路径）
        """
        try:
            if path == "*":
                # 删除该客户端的所有限流记录
                pattern = f"rate_limit:{client_id}:*"
                keys = []
                async for key in self.redis_client.scan_iter(match=pattern):
                    keys.append(key)

                if keys:
                    await self.redis_client.delete(*keys)
            else:
                redis_key = self._get_redis_key(client_id, path)
                await self.redis_client.delete(redis_key)

            logger.info("Rate limit reset", client_id=client_id, path=path)
        except redis.RedisError as e:
            logger.error("Failed to reset rate limit", error=str(e))

    async def get_stats(self, client_id: str) -> Dict:
        """
        获取客户端的限流统计信息

        Args:
            client_id: 客户端ID

        Returns:
            统计信息字典
        """
        try:
            pattern = f"rate_limit:{client_id}:*"
            stats = {}

            async for key in self.redis_client.scan_iter(match=pattern):
                count = await self.redis_client.get(key)
                ttl = await self.redis_client.ttl(key)
                path = key.split(":", 2)[2]

                stats[path] = {
                    "count": int(count) if count else 0,
                    "ttl": ttl
                }

            return stats
        except redis.RedisError as e:
            logger.error("Failed to get rate limit stats", error=str(e))
            return {}

    async def close(self):
        """关闭Redis连接"""
        await self.redis_client.close()


# 全局速率限制器实例（需要在应用启动时初始化）
rate_limiter: Optional[RedisRateLimiter] = None


def init_rate_limiter(redis_url: str = "redis://localhost:6379/0"):
    """
    初始化全局速率限制器

    Args:
        redis_url: Redis连接URL
    """
    global rate_limiter
    rate_limiter = RedisRateLimiter(redis_url)
    logger.info("Redis rate limiter initialized", redis_url=redis_url)


async def close_rate_limiter():
    """关闭速率限制器"""
    global rate_limiter
    if rate_limiter:
        await rate_limiter.close()
        logger.info("Redis rate limiter closed")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查和文档端点
        if request.url.path in ["/api/v1/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # 如果速率限制器未初始化，跳过限流
        if rate_limiter is None:
            logger.warning("Rate limiter not initialized, skipping rate limit check")
            return await call_next(request)

        # 检查速率限制
        allowed, info = await rate_limiter.is_allowed(request)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_id=info["client_id"],
                path=request.url.path,
                limit=info["limit"],
                window=info["window"]
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please try again in {info['retry_after']} seconds.",
                    "limit": info["limit"],
                    "window": info["window"],
                    "retry_after": info["retry_after"]
                },
                headers={
                    "Retry-After": str(info["retry_after"]),
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Window": str(info["window"]),
                }
            )

        # 请求允许，添加速率限制头
        response = await call_next(request)

        if "remaining" in info:
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Window"] = str(info["window"])

        return response


def get_rate_limiter() -> RedisRateLimiter:
    """获取速率限制器实例"""
    return rate_limiter
