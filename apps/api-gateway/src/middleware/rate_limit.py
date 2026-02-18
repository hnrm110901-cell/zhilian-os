"""
API速率限制中间件
防止API滥用，保护系统资源
"""
import time
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta
import structlog
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger()


class RateLimiter:
    """速率限制器"""

    def __init__(self):
        # 存储每个客户端的请求记录
        # key: client_id, value: list of timestamps
        self.requests: Dict[str, list] = defaultdict(list)

        # 速率限制配置
        self.limits = {
            "default": {
                "requests": 100,  # 请求数
                "window": 60,     # 时间窗口（秒）
            },
            "auth": {
                "requests": 10,
                "window": 60,
            },
            "backup": {
                "requests": 5,
                "window": 300,  # 5分钟
            },
            "analytics": {
                "requests": 30,
                "window": 60,
            },
        }

    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识"""
        # 优先使用用户ID（如果已认证）
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"

        # 否则使用IP地址
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    def _get_limit_config(self, path: str) -> Dict[str, int]:
        """根据路径获取限制配置"""
        if "/auth/" in path:
            return self.limits["auth"]
        elif "/backup/" in path:
            return self.limits["backup"]
        elif "/analytics/" in path:
            return self.limits["analytics"]
        else:
            return self.limits["default"]

    def _clean_old_requests(self, client_id: str, window: int):
        """清理过期的请求记录"""
        now = time.time()
        cutoff = now - window

        if client_id in self.requests:
            self.requests[client_id] = [
                ts for ts in self.requests[client_id]
                if ts > cutoff
            ]

    def is_allowed(self, request: Request) -> tuple[bool, Optional[Dict]]:
        """检查请求是否允许"""
        client_id = self._get_client_id(request)
        path = request.url.path
        limit_config = self._get_limit_config(path)

        max_requests = limit_config["requests"]
        window = limit_config["window"]

        # 清理过期记录
        self._clean_old_requests(client_id, window)

        # 检查当前请求数
        current_requests = len(self.requests[client_id])

        if current_requests >= max_requests:
            # 计算重试时间
            oldest_request = min(self.requests[client_id])
            retry_after = int(oldest_request + window - time.time())

            return False, {
                "client_id": client_id,
                "limit": max_requests,
                "window": window,
                "current": current_requests,
                "retry_after": max(retry_after, 1)
            }

        # 记录新请求
        self.requests[client_id].append(time.time())

        return True, {
            "client_id": client_id,
            "limit": max_requests,
            "window": window,
            "remaining": max_requests - current_requests - 1
        }


# 全局速率限制器实例
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查和文档端点
        if request.url.path in ["/api/v1/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # 检查速率限制
        allowed, info = rate_limiter.is_allowed(request)

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


def get_rate_limiter() -> RateLimiter:
    """获取速率限制器实例"""
    return rate_limiter
