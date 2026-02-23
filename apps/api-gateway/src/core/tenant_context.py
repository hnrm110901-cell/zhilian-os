"""
租户上下文管理器
提供线程安全的租户隔离机制
"""
from contextvars import ContextVar
from typing import Optional
from functools import wraps
import asyncio
import structlog

logger = structlog.get_logger()

# 使用ContextVar实现线程安全的租户上下文
_tenant_context: ContextVar[Optional[str]] = ContextVar("tenant_context", default=None)


class TenantContext:
    """租户上下文管理器"""

    @staticmethod
    def get_current_tenant() -> Optional[str]:
        """获取当前租户ID"""
        return _tenant_context.get()

    @staticmethod
    def set_current_tenant(store_id: str) -> None:
        """设置当前租户ID"""
        if not store_id:
            raise ValueError("store_id cannot be empty")
        _tenant_context.set(store_id)
        logger.debug("Tenant context set", store_id=store_id)

    @staticmethod
    def clear_current_tenant() -> None:
        """清除当前租户ID"""
        _tenant_context.set(None)
        logger.debug("Tenant context cleared")

    @staticmethod
    def require_tenant() -> str:
        """
        获取当前租户ID，如果未设置则抛出异常
        用于强制要求租户上下文的场景
        """
        tenant_id = _tenant_context.get()
        if not tenant_id:
            raise RuntimeError(
                "Tenant context not set. "
                "This operation requires a valid tenant context. "
                "Please ensure the request is authenticated and has a valid store_id."
            )
        return tenant_id


def with_tenant(store_id: str):
    """
    装饰器：为函数调用设置租户上下文

    用法:
        @with_tenant("STORE001")
        async def some_function():
            pass
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            TenantContext.set_current_tenant(store_id)
            try:
                return await func(*args, **kwargs)
            finally:
                TenantContext.clear_current_tenant()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            TenantContext.set_current_tenant(store_id)
            try:
                return func(*args, **kwargs)
            finally:
                TenantContext.clear_current_tenant()

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
