"""
调度任务监控服务
用于监控Celery Beat定时任务的执行情况
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import structlog

logger = structlog.get_logger()


class SchedulerMonitorService:
    """
    调度任务监控服务

    功能:
    - 记录任务执行
    - 统计任务指标
    - 检查任务健康
    - 生成监控报告
    """

    def __init__(self):
        # 内存存储 (生产环境应使用数据库或时序数据库)
        self.executions = []
        self.task_health = {}

    async def log_task_execution(
        self,
        task_name: str,
        task_id: str,
        execution_time_ms: float,
        success: bool,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        记录任务执行

        Args:
            task_name: 任务名称
            task_id: 任务ID
            execution_time_ms: 执行时间(毫秒)
            success: 是否成功
            result: 执行结果
            error: 错误信息
            retry_count: 重试次数

        Returns:
            记录结果
        """
        try:
            execution_record = {
                "id": task_id,
                "task_name": task_name,
                "execution_time_ms": execution_time_ms,
                "success": success,
                "result": result,
                "error": error,
                "retry_count": retry_count,
                "timestamp": datetime.now()
            }

            self.executions.append(execution_record)

            # 更新任务健康状态
            if task_name not in self.task_health:
                self.task_health[task_name] = {
                    "last_success": None,
                    "last_failure": None,
                    "consecutive_failures": 0
                }

            if success:
                self.task_health[task_name]["last_success"] = datetime.now()
                self.task_health[task_name]["consecutive_failures"] = 0
            else:
                self.task_health[task_name]["last_failure"] = datetime.now()
                self.task_health[task_name]["consecutive_failures"] += 1

            # 清理旧数据 (保留最近24小时)
            cutoff_time = datetime.now() - timedelta(hours=24)
            self.executions = [
                e for e in self.executions
                if e["timestamp"] > cutoff_time
            ]

            logger.info(
                "Task execution logged",
                task_name=task_name,
                execution_time_ms=execution_time_ms,
                success=success,
                retry_count=retry_count
            )

            return {
                "success": True,
                "execution_id": task_id
            }

        except Exception as e:
            logger.error(
                "Failed to log task execution",
                task_name=task_name,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def get_task_metrics(
        self,
        task_name: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """
        获取任务指标

        Args:
            task_name: 任务名称 (None表示所有任务)
            time_range: 时间范围 (1h/6h/24h)

        Returns:
            任务指标
        """
        try:
            # 解析时间范围
            time_ranges = {
                "1h": timedelta(hours=1),
                "6h": timedelta(hours=6),
                "24h": timedelta(hours=24)
            }
            delta = time_ranges.get(time_range, timedelta(hours=1))
            cutoff_time = datetime.now() - delta

            # 过滤执行记录
            filtered_executions = [
                e for e in self.executions
                if e["timestamp"] > cutoff_time
                and (task_name is None or e["task_name"] == task_name)
            ]

            if not filtered_executions:
                return {
                    "success": True,
                    "metrics": {
                        "total_executions": 0,
                        "success_rate": 0,
                        "avg_execution_time_ms": 0,
                        "total_retries": 0
                    }
                }

            # 计算指标
            total_executions = len(filtered_executions)
            successful_executions = sum(1 for e in filtered_executions if e["success"])
            total_execution_time = sum(e["execution_time_ms"] for e in filtered_executions)
            total_retries = sum(e["retry_count"] for e in filtered_executions)

            # 按任务名称分组
            by_task_name = defaultdict(list)
            for e in filtered_executions:
                by_task_name[e["task_name"]].append(e)

            task_breakdown = {}
            for tname, executions in by_task_name.items():
                task_breakdown[tname] = {
                    "total": len(executions),
                    "success_rate": sum(1 for e in executions if e["success"]) / len(executions) * 100,
                    "avg_execution_time_ms": sum(e["execution_time_ms"] for e in executions) / len(executions),
                    "total_retries": sum(e["retry_count"] for e in executions)
                }

            # 最近失败的任务
            recent_failures = [
                {
                    "task_name": e["task_name"],
                    "error": e["error"],
                    "timestamp": e["timestamp"].isoformat()
                }
                for e in sorted(filtered_executions, key=lambda x: x["timestamp"], reverse=True)
                if not e["success"]
            ][:10]  # 最近10个失败

            metrics = {
                "total_executions": total_executions,
                "success_rate": (successful_executions / total_executions * 100) if total_executions > 0 else 0,
                "avg_execution_time_ms": (total_execution_time / total_executions) if total_executions > 0 else 0,
                "total_retries": total_retries,
                "by_task_name": task_breakdown,
                "recent_failures": recent_failures,
                "time_range": time_range,
                "period_start": cutoff_time.isoformat(),
                "period_end": datetime.now().isoformat()
            }

            logger.info(
                "Task metrics retrieved",
                task_name=task_name,
                time_range=time_range,
                total_executions=total_executions
            )

            return {
                "success": True,
                "metrics": metrics
            }

        except Exception as e:
            logger.error(
                "Failed to get task metrics",
                task_name=task_name,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def check_task_health(
        self,
        task_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检查任务健康状态

        Args:
            task_name: 任务名称 (None表示所有任务)

        Returns:
            健康检查结果
        """
        try:
            health_status = {}

            # 检查指定任务或所有任务
            tasks_to_check = [task_name] if task_name else list(self.task_health.keys())

            for tname in tasks_to_check:
                if tname not in self.task_health:
                    health_status[tname] = {
                        "status": "unknown",
                        "message": "No execution history"
                    }
                    continue

                health = self.task_health[tname]
                last_success = health["last_success"]
                last_failure = health["last_failure"]
                consecutive_failures = health["consecutive_failures"]

                # 判断健康状态
                if consecutive_failures >= 3:
                    status = "critical"
                    message = f"连续失败{consecutive_failures}次"
                elif consecutive_failures > 0:
                    status = "warning"
                    message = f"最近失败{consecutive_failures}次"
                elif last_success:
                    # 检查是否长时间未执行
                    time_since_success = datetime.now() - last_success
                    if time_since_success > timedelta(hours=2):
                        status = "warning"
                        message = f"已{time_since_success.total_seconds() / 3600:.1f}小时未执行"
                    else:
                        status = "healthy"
                        message = "运行正常"
                else:
                    status = "unknown"
                    message = "无执行记录"

                health_status[tname] = {
                    "status": status,
                    "message": message,
                    "last_success": last_success.isoformat() if last_success else None,
                    "last_failure": last_failure.isoformat() if last_failure else None,
                    "consecutive_failures": consecutive_failures
                }

            # 整体健康评分
            if health_status:
                critical_count = sum(1 for h in health_status.values() if h["status"] == "critical")
                warning_count = sum(1 for h in health_status.values() if h["status"] == "warning")
                healthy_count = sum(1 for h in health_status.values() if h["status"] == "healthy")

                if critical_count > 0:
                    overall_status = "critical"
                elif warning_count > 0:
                    overall_status = "warning"
                elif healthy_count > 0:
                    overall_status = "healthy"
                else:
                    overall_status = "unknown"
            else:
                overall_status = "unknown"

            result = {
                "overall_status": overall_status,
                "tasks": health_status,
                "summary": {
                    "total_tasks": len(health_status),
                    "healthy": sum(1 for h in health_status.values() if h["status"] == "healthy"),
                    "warning": sum(1 for h in health_status.values() if h["status"] == "warning"),
                    "critical": sum(1 for h in health_status.values() if h["status"] == "critical"),
                    "unknown": sum(1 for h in health_status.values() if h["status"] == "unknown")
                },
                "timestamp": datetime.now().isoformat()
            }

            logger.info(
                "Task health checked",
                task_name=task_name,
                overall_status=overall_status
            )

            return {
                "success": True,
                "health": result
            }

        except Exception as e:
            logger.error(
                "Failed to check task health",
                task_name=task_name,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        获取队列统计 (模拟)

        Returns:
            队列统计数据
        """
        try:
            # 实际应该从Celery获取队列信息
            # 这里返回模拟数据
            stats = {
                "queues": {
                    "high_priority": {
                        "pending": 0,
                        "active": 0,
                        "completed_last_hour": 0
                    },
                    "default": {
                        "pending": 0,
                        "active": 0,
                        "completed_last_hour": 0
                    },
                    "low_priority": {
                        "pending": 0,
                        "active": 0,
                        "completed_last_hour": 0
                    }
                },
                "workers": {
                    "active": 1,
                    "total": 1
                },
                "timestamp": datetime.now().isoformat()
            }

            return {
                "success": True,
                "stats": stats
            }

        except Exception as e:
            logger.error(
                "Failed to get queue stats",
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }


# 全局实例
scheduler_monitor_service = SchedulerMonitorService()
