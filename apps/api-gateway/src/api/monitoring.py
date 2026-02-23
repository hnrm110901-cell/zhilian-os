"""
监控API端点
提供错误和性能监控数据的查询接口
"""
import os
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory
from ..core.dependencies import get_current_active_user, require_permission
from ..core.permissions import Permission
from ..models.user import User
from ..services.agent_monitor_service import agent_monitor_service
from ..services.scheduler_monitor_service import scheduler_monitor_service

router = APIRouter()


class ErrorSummaryResponse(BaseModel):
    """错误摘要响应"""
    time_window_minutes: int
    total_errors: int
    severity_distribution: Dict[str, int]
    category_distribution: Dict[str, int]
    recent_errors: List[Dict[str, Any]]


class PerformanceSummaryResponse(BaseModel):
    """性能摘要响应"""
    time_window_minutes: int
    total_requests: int
    avg_duration_ms: float
    max_duration_ms: float
    min_duration_ms: float
    slowest_endpoints: List[Dict[str, Any]]


@router.get("/monitoring/errors/summary", response_model=ErrorSummaryResponse)
async def get_error_summary(
    time_window: int = Query(60, description="时间窗口（分钟）", ge=1, le=1440),
    current_user: User = Depends(require_permission(Permission.SYSTEM_LOGS)),
):
    """
    获取错误摘要统计

    返回指定时间窗口内的错误统计信息。

    **认证要求**: 需要 `system:logs` 权限

    **查询参数**:
    - `time_window`: 时间窗口（分钟），默认60分钟，最大1440分钟（24小时）

    **示例响应**:
    ```json
    {
        "time_window_minutes": 60,
        "total_errors": 15,
        "severity_distribution": {
            "error": 10,
            "warning": 3,
            "critical": 2
        },
        "category_distribution": {
            "database": 5,
            "authentication": 3,
            "agent": 7
        },
        "recent_errors": [
            {
                "error_id": "ERR_1708246800000",
                "timestamp": "2024-02-18T10:30:00",
                "severity": "error",
                "category": "database",
                "message": "Database connection timeout",
                "endpoint": "/api/v1/agents/decision"
            }
        ]
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未认证
    - `403 Forbidden`: 权限不足
    """
    summary = error_monitor.get_error_summary(time_window_minutes=time_window)
    return ErrorSummaryResponse(**summary)


@router.get("/monitoring/errors/{error_id}")
async def get_error_details(
    error_id: str,
    current_user: User = Depends(require_permission(Permission.SYSTEM_LOGS)),
):
    """
    获取错误详情

    返回指定错误的完整详细信息，包括堆栈跟踪和上下文。

    **认证要求**: 需要 `system:logs` 权限

    **路径参数**:
    - `error_id`: 错误ID

    **示例响应**:
    ```json
    {
        "error_id": "ERR_1708246800000",
        "timestamp": "2024-02-18T10:30:00",
        "severity": "error",
        "category": "database",
        "message": "Database connection timeout",
        "exception_type": "TimeoutError",
        "stack_trace": "Traceback (most recent call last):\\n...",
        "context": {
            "query": "SELECT * FROM orders",
            "timeout": 30
        },
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "request_id": "req_123456",
        "endpoint": "/api/v1/agents/decision"
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未认证
    - `403 Forbidden`: 权限不足
    - `404 Not Found`: 错误ID不存在
    """
    error_details = error_monitor.get_error_details(error_id)

    if not error_details:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="错误记录不存在")

    return error_details


@router.get("/monitoring/performance/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    time_window: int = Query(60, description="时间窗口（分钟）", ge=1, le=1440),
    current_user: User = Depends(require_permission(Permission.SYSTEM_LOGS)),
):
    """
    获取性能摘要统计

    返回指定时间窗口内的API性能统计信息。

    **认证要求**: 需要 `system:logs` 权限

    **查询参数**:
    - `time_window`: 时间窗口（分钟），默认60分钟，最大1440分钟（24小时）

    **示例响应**:
    ```json
    {
        "time_window_minutes": 60,
        "total_requests": 1250,
        "avg_duration_ms": 145.5,
        "max_duration_ms": 2340.0,
        "min_duration_ms": 12.3,
        "slowest_endpoints": [
            {
                "endpoint": "/api/v1/agents/decision",
                "count": 45,
                "avg_duration_ms": 856.2
            },
            {
                "endpoint": "/api/v1/agents/inventory",
                "count": 120,
                "avg_duration_ms": 234.5
            }
        ]
    }
    ```

    **使用场景**:
    - 识别性能瓶颈
    - 监控API响应时间
    - 优化慢查询

    **错误响应**:
    - `401 Unauthorized`: 未认证
    - `403 Forbidden`: 权限不足
    """
    summary = error_monitor.get_performance_summary(time_window_minutes=time_window)
    return PerformanceSummaryResponse(**summary)


@router.post("/monitoring/errors/clear")
async def clear_old_errors(
    hours: int = Query(24, description="保留最近多少小时的记录", ge=1, le=168),
    current_user: User = Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    清理旧的监控记录

    删除超过指定时间的错误和性能记录。

    **认证要求**: 需要 `system:config` 权限

    **查询参数**:
    - `hours`: 保留最近多少小时的记录，默认24小时，最大168小时（7天）

    **示例响应**:
    ```json
    {
        "message": "已清理旧记录",
        "hours": 24,
        "remaining_errors": 150,
        "remaining_metrics": 1200
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未认证
    - `403 Forbidden`: 权限不足
    """
    error_monitor.clear_old_records(hours=hours)

    return {
        "message": "已清理旧记录",
        "hours": hours,
        "remaining_errors": len(error_monitor.error_records),
        "remaining_metrics": len(error_monitor.performance_metrics),
    }


# ==================== Agent监控端点 ====================

@router.get("/monitoring/agents/metrics")
async def get_agent_metrics(
    agent_type: Optional[str] = Query(None, description="Agent类型"),
    time_range: str = Query("1h", description="时间范围 (1h/6h/24h)"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取Agent性能指标

    返回Agent的调用次数、成功率、响应时间等指标
    """
    result = await agent_monitor_service.get_agent_metrics(agent_type, time_range)
    return result


@router.get("/monitoring/agents/quality/{agent_type}")
async def analyze_agent_quality(
    agent_type: str,
    time_range: str = Query("24h", description="时间范围"),
    current_user: User = Depends(get_current_active_user),
):
    """
    分析Agent决策质量

    返回质量评分、等级和改进建议
    """
    result = await agent_monitor_service.analyze_decision_quality(agent_type, time_range)
    return result


@router.get("/monitoring/agents/realtime")
async def get_agent_realtime_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取Agent实时统计

    返回最近1小时和5分钟的实时数据
    """
    result = await agent_monitor_service.get_realtime_stats()
    return result


# ==================== 调度任务监控端点 ====================

@router.get("/monitoring/scheduler/metrics")
async def get_scheduler_metrics(
    task_name: Optional[str] = Query(None, description="任务名称"),
    time_range: str = Query("1h", description="时间范围 (1h/6h/24h)"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取调度任务指标

    返回任务执行次数、成功率、执行时间等指标
    """
    result = await scheduler_monitor_service.get_task_metrics(task_name, time_range)
    return result


@router.get("/monitoring/scheduler/health")
async def check_scheduler_health(
    task_name: Optional[str] = Query(None, description="任务名称"),
    current_user: User = Depends(get_current_active_user),
):
    """
    检查调度任务健康状态

    返回任务健康状态和告警信息
    """
    result = await scheduler_monitor_service.check_task_health(task_name)
    return result


@router.get("/monitoring/scheduler/queue")
async def get_queue_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取队列统计

    返回队列积压、活跃任务等信息
    """
    result = await scheduler_monitor_service.get_queue_stats()
    return result


# ==================== 监控大盘 ====================

@router.get("/monitoring/dashboard")
async def get_monitoring_dashboard(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取监控大盘数据

    返回完整的监控概览，包括Agent和调度任务的所有指标
    """
    # Agent指标
    agent_metrics = await agent_monitor_service.get_agent_metrics(time_range="1h")
    agent_realtime = await agent_monitor_service.get_realtime_stats()

    # 调度任务指标
    scheduler_metrics = await scheduler_monitor_service.get_task_metrics(time_range="1h")
    scheduler_health = await scheduler_monitor_service.check_task_health()
    queue_stats = await scheduler_monitor_service.get_queue_stats()

    # 错误监控
    error_summary = error_monitor.get_error_summary(time_window_minutes=int(os.getenv("MONITORING_ERROR_WINDOW_MINUTES", "60")))

    return {
        "success": True,
        "dashboard": {
            "agents": {
                "metrics": agent_metrics.get("metrics", {}),
                "realtime": agent_realtime.get("stats", {})
            },
            "scheduler": {
                "metrics": scheduler_metrics.get("metrics", {}),
                "health": scheduler_health.get("health", {}),
                "queue": queue_stats.get("stats", {})
            },
            "errors": error_summary
        }
    }
