"""
监控中间件
自动记录请求性能和错误
"""
import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class MonitoringMiddleware(BaseHTTPMiddleware):
    """
    监控中间件

    自动记录所有请求的性能指标和错误
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # 生成请求ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # 记录请求开始时间
        start_time = time.time()

        # 提取用户信息（如果已认证）
        user_id = None
        if hasattr(request.state, "user"):
            user_id = str(request.state.user.id)

        # 记录请求信息
        logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=user_id,
        )

        try:
            # 处理请求
            response = await call_next(request)

            # 计算执行时间
            duration_ms = (time.time() - start_time) * 1000

            # 记录性能指标
            error_monitor.log_performance(
                endpoint=request.url.path,
                duration_ms=duration_ms,
                status_code=response.status_code,
                method=request.method,
                user_id=user_id,
            )

            # 记录请求完成
            logger.info(
                "Request completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=user_id,
            )

            # 添加响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

            return response

        except Exception as exc:
            # 计算执行时间
            duration_ms = (time.time() - start_time) * 1000

            # 确定错误类别
            category = self._categorize_error(exc)

            # 记录错误
            error_monitor.log_error(
                message=str(exc),
                severity=ErrorSeverity.ERROR,
                category=category,
                exception=exc,
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
                user_id=user_id,
                request_id=request_id,
                endpoint=request.url.path,
            )

            # 记录到日志
            logger.error(
                "Request failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                error=str(exc),
                user_id=user_id,
                exc_info=exc,
            )

            # 重新抛出异常，让FastAPI的异常处理器处理
            raise

    def _categorize_error(self, exc: Exception) -> ErrorCategory:
        """
        根据异常类型确定错误类别

        Args:
            exc: 异常对象

        Returns:
            错误类别
        """
        exc_name = type(exc).__name__

        # 数据库相关错误
        if any(keyword in exc_name.lower() for keyword in ["database", "sql", "connection", "timeout"]):
            return ErrorCategory.DATABASE

        # 认证相关错误
        if any(keyword in exc_name.lower() for keyword in ["auth", "token", "credential"]):
            return ErrorCategory.AUTHENTICATION

        # 授权相关错误
        if any(keyword in exc_name.lower() for keyword in ["permission", "forbidden", "unauthorized"]):
            return ErrorCategory.AUTHORIZATION

        # 验证相关错误
        if any(keyword in exc_name.lower() for keyword in ["validation", "invalid", "format"]):
            return ErrorCategory.VALIDATION

        # 外部API相关错误
        if any(keyword in exc_name.lower() for keyword in ["http", "request", "api", "client"]):
            return ErrorCategory.EXTERNAL_API

        return ErrorCategory.SYSTEM
