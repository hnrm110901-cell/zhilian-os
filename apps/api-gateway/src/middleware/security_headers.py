"""
安全响应头中间件
为所有响应添加浏览器安全防护头，防止 XSS、点击劫持、MIME 嗅探等攻击
"""
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 生产环境判断
_APP_ENV = os.getenv("APP_ENV", "development")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全响应头中间件

    生产环境额外启用：
    - Strict-Transport-Security (HSTS)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # 防止 MIME 类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 防止点击劫持
        response.headers["X-Frame-Options"] = "DENY"

        # 浏览器 XSS 过滤（旧版浏览器兼容）
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer 策略：跨域只发送 origin
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 权限策略：禁用不必要的浏览器特性
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # 内容安全策略
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' wss:; "
            "frame-ancestors 'none'"
        )

        # HSTS：仅在生产环境强制 HTTPS（开发环境 HTTP 也要能用）
        if _APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # 移除 server 信息泄露
        response.headers.pop("server", None)
        response.headers.pop("Server", None)

        return response
