"""
重试机制工具模块（移植自 BettaFish，适配屯象OS async/structlog/httpx 环境）

提供指数退避重试装饰器，增强 LLM API 调用和外部 HTTP 请求的健壮性。

两类装饰器：
  @async_retry(config)          — 关键调用，最终失败时抛异常（LLM调用）
  @async_graceful_retry(config) — 非关键调用，最终失败时返回默认值（推送通知）

同步版本（sync_retry / sync_graceful_retry）供非 async 场景使用。

预设配置：
  LLM_RETRY_CONFIG    — LLM API（速率限制，长退避）
  WECHAT_RETRY_CONFIG — 企业微信 HTTP（短退避）
  HTTP_RETRY_CONFIG   — 通用外部 HTTP（短退避）
  DB_RETRY_CONFIG     — 数据库连接（极短退避）
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

import structlog

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────────────────

def _default_retry_exceptions() -> Tuple[Type[Exception], ...]:
    """收集所有可用的网络/API异常类型（动态导入，避免强依赖）"""
    exceptions: list[Type[Exception]] = [ConnectionError, TimeoutError, OSError]

    try:
        import httpx
        exceptions += [
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
        ]
    except ImportError:
        pass

    try:
        import openai
        exceptions += [
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        ]
    except ImportError:
        pass

    try:
        import anthropic
        exceptions += [
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
        ]
    except ImportError:
        pass

    return tuple(exceptions)


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    initial_delay: float = 1.0       # 首次等待秒数
    backoff_factor: float = 2.0      # 每次翻倍：1s → 2s → 4s
    max_delay: float = 60.0          # 单次等待上限
    retry_on_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=_default_retry_exceptions
    )


# ─────────────────────────────────────────────────────────────────────────────
# 预设配置
# ─────────────────────────────────────────────────────────────────────────────

LLM_RETRY_CONFIG = RetryConfig(
    max_retries=4,
    initial_delay=30.0,     # LLM 速率限制通常需要等 30s+
    backoff_factor=2.0,
    max_delay=300.0,        # 最长单次等 5 分钟
)

WECHAT_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=2.0,
    backoff_factor=2.0,
    max_delay=30.0,
)

HTTP_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    backoff_factor=2.0,
    max_delay=10.0,
)

DB_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    initial_delay=1.0,
    backoff_factor=1.5,
    max_delay=10.0,
)


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────────────────────

def _calc_delay(config: RetryConfig, attempt: int) -> float:
    """计算第 attempt 次失败后的等待时间（指数退避）"""
    return min(config.initial_delay * (config.backoff_factor ** attempt), config.max_delay)


# ─────────────────────────────────────────────────────────────────────────────
# 异步装饰器（主要）
# ─────────────────────────────────────────────────────────────────────────────

def async_retry(config: Optional[RetryConfig] = None):
    """
    关键异步调用的重试装饰器。

    失败超过 max_retries 次后抛出最后一个异常。
    适用于：LLM API、必须成功的 HTTP 请求。

    用法::

        @async_retry(LLM_RETRY_CONFIG)
        async def generate_with_context(self, ...): ...
    """
    effective_config = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None

            for attempt in range(effective_config.max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(
                            "retry_succeeded",
                            func=func.__qualname__,
                            attempt=attempt + 1,
                        )
                    return result

                except effective_config.retry_on_exceptions as exc:
                    last_exc = exc
                    if attempt == effective_config.max_retries:
                        logger.error(
                            "retry_exhausted",
                            func=func.__qualname__,
                            max_retries=effective_config.max_retries,
                            error=str(exc),
                        )
                        raise

                    delay = _calc_delay(effective_config, attempt)
                    logger.warning(
                        "retry_scheduled",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        next_attempt=attempt + 2,
                        delay_seconds=round(delay, 1),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

            # 安全兜底（逻辑上不可达）
            if last_exc:
                raise last_exc

        return wrapper
    return decorator


def async_graceful_retry(
    config: Optional[RetryConfig] = None,
    default_return: Any = None,
):
    """
    非关键异步调用的优雅重试装饰器。

    失败超过 max_retries 次后返回 default_return，不抛异常，保证主流程继续。
    适用于：WeChat 推送、报告生成等非阻塞通知。

    用法::

        @async_graceful_retry(WECHAT_RETRY_CONFIG, default_return={"success": False})
        async def get_access_token(self): ...
    """
    effective_config = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(effective_config.max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(
                            "graceful_retry_succeeded",
                            func=func.__qualname__,
                            attempt=attempt + 1,
                        )
                    return result

                except effective_config.retry_on_exceptions as exc:
                    if attempt == effective_config.max_retries:
                        logger.warning(
                            "graceful_retry_exhausted_returning_default",
                            func=func.__qualname__,
                            max_retries=effective_config.max_retries,
                            error=str(exc),
                            default_return=default_return,
                        )
                        return default_return

                    delay = _calc_delay(effective_config, attempt)
                    logger.warning(
                        "graceful_retry_scheduled",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        delay_seconds=round(delay, 1),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

            return default_return

        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# 同步装饰器（供非 async 场景使用）
# ─────────────────────────────────────────────────────────────────────────────

def sync_retry(config: Optional[RetryConfig] = None):
    """同步版重试装饰器，参数与 async_retry 相同。"""
    effective_config = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None

            for attempt in range(effective_config.max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(
                            "sync_retry_succeeded",
                            func=func.__qualname__,
                            attempt=attempt + 1,
                        )
                    return result

                except effective_config.retry_on_exceptions as exc:
                    last_exc = exc
                    if attempt == effective_config.max_retries:
                        logger.error(
                            "sync_retry_exhausted",
                            func=func.__qualname__,
                            error=str(exc),
                        )
                        raise

                    delay = _calc_delay(effective_config, attempt)
                    logger.warning(
                        "sync_retry_scheduled",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        delay_seconds=round(delay, 1),
                        error=str(exc),
                    )
                    time.sleep(delay)

            if last_exc:
                raise last_exc

        return wrapper
    return decorator


def sync_graceful_retry(
    config: Optional[RetryConfig] = None,
    default_return: Any = None,
):
    """同步版优雅重试装饰器，参数与 async_graceful_retry 相同。"""
    effective_config = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(effective_config.max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except effective_config.retry_on_exceptions as exc:
                    if attempt == effective_config.max_retries:
                        logger.warning(
                            "sync_graceful_retry_exhausted",
                            func=func.__qualname__,
                            error=str(exc),
                        )
                        return default_return

                    delay = _calc_delay(effective_config, attempt)
                    logger.warning(
                        "sync_graceful_retry_scheduled",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        delay_seconds=round(delay, 1),
                        error=str(exc),
                    )
                    time.sleep(delay)

            return default_return

        return wrapper
    return decorator
