"""
Circuit Breaker模式实现
用于防止向量数据库Silent Failure导致的级联故障
"""
import time
import structlog
import os
from enum import Enum
from typing import Callable, Any
from functools import wraps
import asyncio

logger = structlog.get_logger()


class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 正常状态，允许请求通过
    OPEN = "open"  # 熔断状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，允许部分请求测试服务是否恢复


class CircuitBreaker:
    """
    熔断器实现

    当服务连续失败达到阈值时，熔断器打开，拒绝后续请求
    经过一段时间后，熔断器进入半开状态，允许部分请求测试服务是否恢复
    如果测试成功，熔断器关闭；如果失败，熔断器重新打开
    """

    def __init__(
        self,
        failure_threshold: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")),
        success_threshold: int = int(os.getenv("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "2")),
        timeout: float = float(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60.0")),
        expected_exception: type = Exception,
    ):
        """
        初始化熔断器

        Args:
            failure_threshold: 连续失败多少次后打开熔断器
            success_threshold: 半开状态下连续成功多少次后关闭熔断器
            timeout: 熔断器打开后多久进入半开状态
            expected_exception: 需要熔断的异常类型
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_state_change_time = time.time()

        logger.info(
            "熔断器初始化",
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
        )

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        # 如果熔断器打开且超过超时时间，进入半开状态
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time
            and time.time() - self._last_failure_time >= self.timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info("熔断器进入半开状态")

        return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        调用被保护的函数

        Args:
            func: 要调用的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerOpenError: 熔断器打开时抛出
        """
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError("熔断器已打开，拒绝请求")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        异步调用被保护的函数

        Args:
            func: 要调用的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerOpenError: 熔断器打开时抛出
        """
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError("熔断器已打开，拒绝请求")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """成功回调"""
        self._failure_count = 0

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            logger.info(
                "熔断器半开状态成功",
                success_count=self._success_count,
                success_threshold=self.success_threshold,
            )

            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._success_count = 0
                self._last_state_change_time = time.time()
                logger.info("熔断器关闭，服务恢复正常")

    def _on_failure(self):
        """失败回调"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        logger.warning(
            "熔断器记录失败",
            failure_count=self._failure_count,
            failure_threshold=self.failure_threshold,
            state=self._state,
        )

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下失败，重新打开熔断器
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._last_state_change_time = time.time()
            logger.warning("熔断器重新打开")

        elif self._failure_count >= self.failure_threshold:
            # 失败次数达到阈值，打开熔断器
            self._state = CircuitState.OPEN
            self._last_state_change_time = time.time()
            logger.error(
                "熔断器打开",
                failure_count=self._failure_count,
                failure_threshold=self.failure_threshold,
            )

    def reset(self):
        """重置熔断器"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_state_change_time = time.time()
        logger.info("熔断器已重置")

    def get_stats(self) -> dict:
        """获取熔断器统计信息"""
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
            "last_failure_time": self._last_failure_time,
            "last_state_change_time": self._last_state_change_time,
            "uptime_seconds": time.time() - self._last_state_change_time,
        }


class CircuitBreakerOpenError(Exception):
    """熔断器打开异常"""
    pass


def circuit_breaker(
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: float = 60.0,
    expected_exception: type = Exception,
    fallback: Callable = None,
):
    """
    熔断器装饰器

    Args:
        failure_threshold: 失败阈值
        success_threshold: 成功阈值
        timeout: 超时时间
        expected_exception: 预期异常
        fallback: 降级函数

    Example:
        @circuit_breaker(failure_threshold=3, timeout=30, fallback=lambda: {"status": "degraded"})
        async def risky_operation():
            # 可能失败的操作
            pass
    """
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        expected_exception=expected_exception,
    )

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await breaker.call_async(func, *args, **kwargs)
            except CircuitBreakerOpenError as e:
                logger.warning(
                    "熔断器打开，使用降级策略",
                    function=func.__name__,
                    error=str(e),
                )
                if fallback:
                    return fallback() if not asyncio.iscoroutinefunction(fallback) else await fallback()
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return breaker.call(func, *args, **kwargs)
            except CircuitBreakerOpenError as e:
                logger.warning(
                    "熔断器打开，使用降级策略",
                    function=func.__name__,
                    error=str(e),
                )
                if fallback:
                    return fallback()
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
