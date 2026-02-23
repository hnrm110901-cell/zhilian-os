"""
错误监控和追踪模块
提供错误日志记录、性能监控和告警功能
"""
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum
import traceback
import time
from collections import defaultdict
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()


class ErrorSeverity(str, Enum):
    """错误严重程度"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """错误类别"""
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    AGENT = "agent"
    EXTERNAL_API = "external_api"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ErrorRecord:
    """错误记录"""
    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None


@dataclass
class PerformanceMetric:
    """性能指标"""
    metric_id: str
    timestamp: datetime
    endpoint: str
    duration_ms: float
    status_code: int
    method: str
    user_id: Optional[str] = None


class ErrorMonitor:
    """错误监控器 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.error_records: List[ErrorRecord] = []
        self.performance_metrics: List[PerformanceMetric] = []
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.max_records = int(os.getenv("MONITORING_MAX_RECORDS", "1000"))  # 最多保存记录数

    def log_error(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> str:
        """
        记录错误

        Args:
            message: 错误消息
            severity: 严重程度
            category: 错误类别
            exception: 异常对象
            context: 上下文信息
            user_id: 用户ID
            request_id: 请求ID
            endpoint: API端点

        Returns:
            错误ID
        """
        error_id = f"ERR_{int(time.time() * 1000)}"

        # 提取异常信息
        exception_type = None
        stack_trace = None
        if exception:
            exception_type = type(exception).__name__
            stack_trace = traceback.format_exc()

        # 创建错误记录
        error_record = ErrorRecord(
            error_id=error_id,
            timestamp=datetime.now(),
            severity=severity,
            category=category,
            message=message,
            exception_type=exception_type,
            stack_trace=stack_trace,
            context=context or {},
            user_id=user_id,
            request_id=request_id,
            endpoint=endpoint,
        )

        # 保存错误记录
        self.error_records.append(error_record)
        if len(self.error_records) > self.max_records:
            self.error_records.pop(0)

        # 更新错误计数
        count_key = f"{category.value}:{severity.value}"
        self.error_counts[count_key] += 1

        # 记录到结构化日志
        log_data = {
            "error_id": error_id,
            "severity": severity.value,
            "category": category.value,
            "message": message,
            "user_id": user_id,
            "endpoint": endpoint,
        }

        if exception_type:
            log_data["exception_type"] = exception_type

        if context:
            log_data["context"] = context

        # 根据严重程度选择日志级别
        if severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred", **log_data)
        elif severity == ErrorSeverity.ERROR:
            logger.error("Error occurred", **log_data)
        elif severity == ErrorSeverity.WARNING:
            logger.warning("Warning occurred", **log_data)
        else:
            logger.info("Event logged", **log_data)

        return error_id

    def log_performance(
        self,
        endpoint: str,
        duration_ms: float,
        status_code: int,
        method: str = "GET",
        user_id: Optional[str] = None,
    ) -> str:
        """
        记录性能指标

        Args:
            endpoint: API端点
            duration_ms: 执行时间（毫秒）
            status_code: HTTP状态码
            method: HTTP方法
            user_id: 用户ID

        Returns:
            指标ID
        """
        metric_id = f"PERF_{int(time.time() * 1000)}"

        metric = PerformanceMetric(
            metric_id=metric_id,
            timestamp=datetime.now(),
            endpoint=endpoint,
            duration_ms=duration_ms,
            status_code=status_code,
            method=method,
            user_id=user_id,
        )

        self.performance_metrics.append(metric)
        if len(self.performance_metrics) > self.max_records:
            self.performance_metrics.pop(0)

        # 记录慢请求
        if duration_ms > int(os.getenv("MONITORING_SLOW_REQUEST_MS", "1000")):  # 超过阈值
            logger.warning(
                "Slow request detected",
                endpoint=endpoint,
                duration_ms=duration_ms,
                method=method,
            )

        return metric_id

    def get_error_summary(
        self,
        time_window_minutes: int = int(os.getenv("MONITORING_ERROR_WINDOW_MINUTES", "60"))
    ) -> Dict[str, Any]:
        """
        获取错误摘要

        Args:
            time_window_minutes: 时间窗口（分钟）

        Returns:
            错误摘要统计
        """
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)

        recent_errors = [
            err for err in self.error_records
            if err.timestamp >= cutoff_time
        ]

        # 按严重程度统计
        severity_counts = defaultdict(int)
        for err in recent_errors:
            severity_counts[err.severity.value] += 1

        # 按类别统计
        category_counts = defaultdict(int)
        for err in recent_errors:
            category_counts[err.category.value] += 1

        # 最近的错误
        recent_error_list = [
            {
                "error_id": err.error_id,
                "timestamp": err.timestamp.isoformat(),
                "severity": err.severity.value,
                "category": err.category.value,
                "message": err.message,
                "endpoint": err.endpoint,
            }
            for err in sorted(recent_errors, key=lambda x: x.timestamp, reverse=True)[:10]
        ]

        return {
            "time_window_minutes": time_window_minutes,
            "total_errors": len(recent_errors),
            "severity_distribution": dict(severity_counts),
            "category_distribution": dict(category_counts),
            "recent_errors": recent_error_list,
        }

    def get_performance_summary(
        self,
        time_window_minutes: int = int(os.getenv("MONITORING_ERROR_WINDOW_MINUTES", "60"))
    ) -> Dict[str, Any]:
        """
        获取性能摘要

        Args:
            time_window_minutes: 时间窗口（分钟）

        Returns:
            性能摘要统计
        """
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)

        recent_metrics = [
            metric for metric in self.performance_metrics
            if metric.timestamp >= cutoff_time
        ]

        if not recent_metrics:
            return {
                "time_window_minutes": time_window_minutes,
                "total_requests": 0,
                "avg_duration_ms": 0,
                "max_duration_ms": 0,
                "min_duration_ms": 0,
            }

        durations = [m.duration_ms for m in recent_metrics]

        # 按端点统计
        endpoint_stats = defaultdict(lambda: {"count": 0, "total_duration": 0})
        for metric in recent_metrics:
            endpoint_stats[metric.endpoint]["count"] += 1
            endpoint_stats[metric.endpoint]["total_duration"] += metric.duration_ms

        # 计算平均响应时间
        endpoint_avg = {
            endpoint: {
                "count": stats["count"],
                "avg_duration_ms": stats["total_duration"] / stats["count"],
            }
            for endpoint, stats in endpoint_stats.items()
        }

        # 找出最慢的端点
        slowest_endpoints = sorted(
            endpoint_avg.items(),
            key=lambda x: x[1]["avg_duration_ms"],
            reverse=True
        )[:5]

        return {
            "time_window_minutes": time_window_minutes,
            "total_requests": len(recent_metrics),
            "avg_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
            "min_duration_ms": min(durations),
            "slowest_endpoints": [
                {
                    "endpoint": endpoint,
                    "count": stats["count"],
                    "avg_duration_ms": stats["avg_duration_ms"],
                }
                for endpoint, stats in slowest_endpoints
            ],
        }

    def get_error_details(self, error_id: str) -> Optional[Dict[str, Any]]:
        """
        获取错误详情

        Args:
            error_id: 错误ID

        Returns:
            错误详情
        """
        for err in self.error_records:
            if err.error_id == error_id:
                return {
                    "error_id": err.error_id,
                    "timestamp": err.timestamp.isoformat(),
                    "severity": err.severity.value,
                    "category": err.category.value,
                    "message": err.message,
                    "exception_type": err.exception_type,
                    "stack_trace": err.stack_trace,
                    "context": err.context,
                    "user_id": err.user_id,
                    "request_id": err.request_id,
                    "endpoint": err.endpoint,
                }
        return None

    def clear_old_records(self, hours: int = int(os.getenv("MONITORING_RETENTION_HOURS", "24"))):
        """
        清理旧记录

        Args:
            hours: 保留最近多少小时的记录
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        self.error_records = [
            err for err in self.error_records
            if err.timestamp >= cutoff_time
        ]

        self.performance_metrics = [
            metric for metric in self.performance_metrics
            if metric.timestamp >= cutoff_time
        ]

        logger.info(
            "Cleared old monitoring records",
            hours=hours,
            remaining_errors=len(self.error_records),
            remaining_metrics=len(self.performance_metrics),
        )


# 全局错误监控器实例
error_monitor = ErrorMonitor()
