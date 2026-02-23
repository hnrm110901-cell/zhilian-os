"""
缓存装饰器
Cache Decorators

提供常用的缓存装饰器，简化缓存使用
"""
import functools
import hashlib
import json
import os
from typing import Any, Callable, Optional
import structlog

logger = structlog.get_logger()


def cache_result(
    key_prefix: str,
    expire: int = int(os.getenv("CACHE_DEFAULT_EXPIRE", "300")),
    key_builder: Optional[Callable] = None
):
    """
    缓存函数结果装饰器

    Args:
        key_prefix: 缓存键前缀
        expire: 过期时间（秒）
        key_builder: 自定义键构建函数

    Example:
        @cache_result("user:permissions", expire=600)
        async def get_user_permissions(user_id: str):
            # 查询数据库
            return permissions
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            from .redis_cache_service import redis_cache

            # 构建缓存键
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # 默认键构建：使用参数生成哈希
                key_parts = [str(arg) for arg in args]
                key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                key_str = ":".join(key_parts)
                key_hash = hashlib.md5(key_str.encode()).hexdigest()[:8]
                cache_key = f"{key_prefix}:{key_hash}"

            # 尝试从缓存获取
            cached_value = await redis_cache.get(cache_key)
            if cached_value is not None:
                logger.debug("从缓存获取结果", cache_key=cache_key)
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 缓存结果
            if result is not None:
                await redis_cache.set(cache_key, result, expire=expire)
                logger.debug("缓存函数结果", cache_key=cache_key, expire=expire)

            return result

        return wrapper
    return decorator


def cache_user_permissions(expire: int = int(os.getenv("CACHE_PERMISSIONS_EXPIRE", "600"))):
    """
    缓存用户权限装饰器

    Args:
        expire: 过期时间（秒），默认10分钟

    Example:
        @cache_user_permissions(expire=600)
        async def get_user_permissions(user_id: str):
            return permissions
    """
    def key_builder(user_id: str, *args, **kwargs) -> str:
        return f"user:permissions:{user_id}"

    return cache_result("user:permissions", expire=expire, key_builder=key_builder)


def cache_user_info(expire: int = int(os.getenv("CACHE_USER_INFO_EXPIRE", "300"))):
    """
    缓存用户信息装饰器

    Args:
        expire: 过期时间（秒），默认5分钟

    Example:
        @cache_user_info(expire=300)
        async def get_user_info(user_id: str):
            return user_info
    """
    def key_builder(user_id: str, *args, **kwargs) -> str:
        return f"user:info:{user_id}"

    return cache_result("user:info", expire=expire, key_builder=key_builder)


def invalidate_cache(key_pattern: str):
    """
    清除缓存装饰器

    在函数执行后清除匹配的缓存

    Args:
        key_pattern: 缓存键模式（支持*通配符）

    Example:
        @invalidate_cache("user:permissions:*")
        async def update_user_role(user_id: str, role: str):
            # 更新用户角色
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            from .redis_cache_service import redis_cache

            # 执行函数
            result = await func(*args, **kwargs)

            # 清除缓存
            try:
                count = await redis_cache.clear_pattern(key_pattern)
                logger.info("清除缓存", pattern=key_pattern, count=count)
            except Exception as e:
                logger.warning("清除缓存失败", pattern=key_pattern, error=str(e))

            return result

        return wrapper
    return decorator


class CacheManager:
    """缓存管理器"""

    @staticmethod
    async def clear_user_cache(user_id: str):
        """清除用户相关的所有缓存"""
        from .redis_cache_service import redis_cache

        patterns = [
            f"user:info:{user_id}",
            f"user:permissions:{user_id}",
            f"user:*:{user_id}",
        ]

        total_cleared = 0
        for pattern in patterns:
            count = await redis_cache.clear_pattern(pattern)
            total_cleared += count

        logger.info("清除用户缓存", user_id=user_id, count=total_cleared)
        return total_cleared

    @staticmethod
    async def clear_all_user_caches():
        """清除所有用户缓存"""
        from .redis_cache_service import redis_cache

        count = await redis_cache.clear_pattern("user:*")
        logger.info("清除所有用户缓存", count=count)
        return count

    @staticmethod
    async def warm_up_cache(user_id: str, permissions: list, user_info: dict):
        """预热用户缓存"""
        from .redis_cache_service import redis_cache

        await redis_cache.set(f"user:permissions:{user_id}", permissions, expire=int(os.getenv("CACHE_PERMISSIONS_EXPIRE", "600")))
        await redis_cache.set(f"user:info:{user_id}", user_info, expire=int(os.getenv("CACHE_USER_INFO_EXPIRE", "300")))

        logger.info("预热用户缓存", user_id=user_id)


# 导出
__all__ = [
    "cache_result",
    "cache_user_permissions",
    "cache_user_info",
    "invalidate_cache",
    "CacheManager",
]
