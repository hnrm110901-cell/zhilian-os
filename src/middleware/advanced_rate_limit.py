"""
Advanced Rate Limiting Middleware
高级速率限制中间件

Provides sophisticated rate limiting with multiple strategies:
- IP-based rate limiting
- User-based rate limiting
- Endpoint-specific limits
- Sliding window algorithm
- Redis-backed distributed rate limiting
"""

import os
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
import time
import hashlib
from collections import defaultdict
from dataclasses import dataclass
import redis
import json


@dataclass
class RateLimitRule:
    """Rate limit rule configuration"""
    requests: int  # Number of requests allowed
    window: int  # Time window in seconds
    scope: str  # 'ip', 'user', 'endpoint', 'global'


class RateLimiter:
    """
    Advanced Rate Limiter
    高级速率限制器

    Features:
    - Multiple rate limiting strategies
    - Sliding window algorithm
    - Redis-backed for distributed systems
    - Per-endpoint custom limits
    - Whitelist/blacklist support
    - Rate limit headers (X-RateLimit-*)

    Algorithms:
    - Fixed Window: Simple counter reset at fixed intervals
    - Sliding Window: More accurate, considers request timestamps
    - Token Bucket: Allows bursts while maintaining average rate
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        default_limit: int = int(os.getenv("RATE_LIMIT_DEFAULT_REQUESTS", "100")),
        default_window: int = int(os.getenv("RATE_LIMIT_DEFAULT_WINDOW", "60")),
        enable_redis: bool = True
    ):
        self.redis_client = redis_client
        self.default_limit = default_limit
        self.default_window = default_window
        self.enable_redis = enable_redis

        # In-memory fallback (for development/testing)
        self.memory_store: Dict[str, list] = defaultdict(list)

        # Endpoint-specific limits
        self.endpoint_limits: Dict[str, RateLimitRule] = {}

        # Whitelist (no rate limiting)
        self.whitelist: set = set()

        # Blacklist (always blocked)
        self.blacklist: set = set()

        # Initialize default endpoint limits
        self._initialize_default_limits()

    def _initialize_default_limits(self):
        """Initialize default rate limits for different endpoints"""
        # Public endpoints - stricter limits
        self.endpoint_limits["/api/v1/auth/login"] = RateLimitRule(
            requests=int(os.getenv("RATE_LIMIT_LOGIN_REQUESTS", "5")),
            window=60,
            scope="ip"
        )
        self.endpoint_limits["/api/v1/auth/register"] = RateLimitRule(
            requests=int(os.getenv("RATE_LIMIT_REGISTER_REQUESTS", "3")),
            window=int(os.getenv("RATE_LIMIT_REGISTER_WINDOW", "3600")),
            scope="ip"
        )

        # API endpoints - moderate limits
        self.endpoint_limits["/api/v1/agents/*"] = RateLimitRule(
            requests=int(os.getenv("RATE_LIMIT_AGENT_REQUESTS", "100")),
            window=60,
            scope="user"
        )

        # Heavy operations - stricter limits
        self.endpoint_limits["/api/v1/analytics/*"] = RateLimitRule(
            requests=int(os.getenv("RATE_LIMIT_ANALYTICS_REQUESTS", "20")),
            window=60,
            scope="user"
        )

        # Webhook endpoints - very strict
        self.endpoint_limits["/api/v1/webhooks/*"] = RateLimitRule(
            requests=int(os.getenv("RATE_LIMIT_WEBHOOK_REQUESTS", "10")),
            window=60,
            scope="ip"
        )

    def add_to_whitelist(self, identifier: str):
        """Add IP or user to whitelist"""
        self.whitelist.add(identifier)

    def add_to_blacklist(self, identifier: str):
        """Add IP or user to blacklist"""
        self.blacklist.add(identifier)

    def set_endpoint_limit(
        self,
        endpoint: str,
        requests: int,
        window: int,
        scope: str = "user"
    ):
        """Set custom rate limit for specific endpoint"""
        self.endpoint_limits[endpoint] = RateLimitRule(
            requests=requests,
            window=window,
            scope=scope
        )

    def _get_identifier(
        self,
        request: Request,
        scope: str
    ) -> str:
        """Get identifier based on scope"""
        if scope == "ip":
            # Get client IP
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return request.client.host if request.client else "unknown"

        elif scope == "user":
            # Get user ID from auth token
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Hash token for privacy
                return hashlib.sha256(token.encode()).hexdigest()[:16]
            # Fallback to IP if not authenticated
            return self._get_identifier(request, "ip")

        elif scope == "endpoint":
            return request.url.path

        else:  # global
            return "global"

    def _get_rate_limit_rule(
        self,
        endpoint: str
    ) -> RateLimitRule:
        """Get rate limit rule for endpoint"""
        # Exact match
        if endpoint in self.endpoint_limits:
            return self.endpoint_limits[endpoint]

        # Wildcard match
        for pattern, rule in self.endpoint_limits.items():
            if pattern.endswith("/*"):
                prefix = pattern[:-2]
                if endpoint.startswith(prefix):
                    return rule

        # Default rule
        return RateLimitRule(
            requests=self.default_limit,
            window=self.default_window,
            scope="user"
        )

    def _check_rate_limit_redis(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using Redis (sliding window)
        使用Redis检查速率限制（滑动窗口算法）

        Returns:
            (allowed, remaining, reset_time)
        """
        if not self.redis_client:
            return self._check_rate_limit_memory(key, limit, window)

        try:
            now = time.time()
            window_start = now - window

            # Redis key
            redis_key = f"rate_limit:{key}"

            # Remove old entries
            self.redis_client.zremrangebyscore(
                redis_key,
                0,
                window_start
            )

            # Count requests in current window
            current_count = self.redis_client.zcard(redis_key)

            if current_count < limit:
                # Add current request
                self.redis_client.zadd(
                    redis_key,
                    {str(now): now}
                )
                # Set expiry
                self.redis_client.expire(redis_key, window)

                remaining = limit - current_count - 1
                reset_time = int(now + window)
                return True, remaining, reset_time
            else:
                # Get oldest request time
                oldest = self.redis_client.zrange(
                    redis_key,
                    0,
                    0,
                    withscores=True
                )
                if oldest:
                    reset_time = int(oldest[0][1] + window)
                else:
                    reset_time = int(now + window)

                return False, 0, reset_time

        except Exception as e:
            # Fallback to memory if Redis fails
            print(f"Redis error: {e}, falling back to memory")
            return self._check_rate_limit_memory(key, limit, window)

    def _check_rate_limit_memory(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using in-memory store (fallback)
        使用内存存储检查速率限制（备用方案）
        """
        now = time.time()
        window_start = now - window

        # Get request timestamps for this key
        timestamps = self.memory_store[key]

        # Remove old timestamps
        timestamps = [ts for ts in timestamps if ts > window_start]
        self.memory_store[key] = timestamps

        if len(timestamps) < limit:
            # Allow request
            timestamps.append(now)
            remaining = limit - len(timestamps)
            reset_time = int(now + window)
            return True, remaining, reset_time
        else:
            # Deny request
            reset_time = int(timestamps[0] + window)
            return False, 0, reset_time

    async def check_rate_limit(
        self,
        request: Request
    ) -> tuple[bool, Dict[str, str]]:
        """
        Check if request should be rate limited
        检查请求是否应该被限流

        Returns:
            (allowed, headers)
        """
        endpoint = request.url.path

        # Get rate limit rule
        rule = self._get_rate_limit_rule(endpoint)

        # Get identifier
        identifier = self._get_identifier(request, rule.scope)

        # Check whitelist
        if identifier in self.whitelist:
            return True, {
                "X-RateLimit-Limit": str(rule.requests),
                "X-RateLimit-Remaining": str(rule.requests),
                "X-RateLimit-Reset": str(int(time.time() + rule.window))
            }

        # Check blacklist
        if identifier in self.blacklist:
            return False, {
                "X-RateLimit-Limit": "0",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + rule.window))
            }

        # Create rate limit key
        key = f"{rule.scope}:{identifier}:{endpoint}"

        # Check rate limit
        allowed, remaining, reset_time = self._check_rate_limit_redis(
            key,
            rule.requests,
            rule.window
        )

        # Prepare headers
        headers = {
            "X-RateLimit-Limit": str(rule.requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
            "X-RateLimit-Window": str(rule.window)
        }

        return allowed, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate Limit Middleware
    速率限制中间件

    Automatically applies rate limiting to all requests.
    """

    def __init__(
        self,
        app,
        redis_client: Optional[redis.Redis] = None,
        default_limit: int = int(os.getenv("RATE_LIMIT_DEFAULT_REQUESTS", "100")),
        default_window: int = 60
    ):
        super().__init__(app)
        self.rate_limiter = RateLimiter(
            redis_client=redis_client,
            default_limit=default_limit,
            default_window=default_window
        )

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        # Skip rate limiting for health check and metrics
        if request.url.path in ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Check rate limit
        allowed, headers = await self.rate_limiter.check_rate_limit(request)

        if not allowed:
            # Rate limit exceeded
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": headers.get("X-RateLimit-Reset")
                },
                headers=headers
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response


# Decorator for function-level rate limiting
def rate_limit(
    requests: int = 10,
    window: int = 60,
    scope: str = "user"
):
    """
    Decorator for function-level rate limiting
    函数级别的速率限制装饰器

    Usage:
        @rate_limit(requests=5, window=60, scope="ip")
        async def my_endpoint():
            pass
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # Get request from kwargs
            request = kwargs.get("request")
            if not request:
                # Try to find request in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request:
                # Create temporary rate limiter
                limiter = RateLimiter()
                limiter.set_endpoint_limit(
                    request.url.path,
                    requests,
                    window,
                    scope
                )

                # Check rate limit
                allowed, headers = await limiter.check_rate_limit(request)

                if not allowed:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded",
                        headers=headers
                    )

            # Call original function
            return await func(*args, **kwargs)

        return wrapper
    return decorator
