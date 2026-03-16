"""
ServiceAgent - 客户服务质量智能体

负责：客户反馈管理、服务质量监控、投诉处理、满意度分析。
委托给 ServiceQualityService 执行真实 DB 查询。
"""

import time
from typing import Any, Dict, List

import structlog
from src.core.base_agent import AgentResponse, BaseAgent

logger = structlog.get_logger()

_SUPPORTED_ACTIONS = [
    "get_feedback_summary",
    "handle_complaint",
    "get_satisfaction_score",
    "get_service_quality_metrics",
    "list_complaints",
]


class ServiceAgent(BaseAgent):
    """客户服务质量智能体"""

    def __init__(self):
        super().__init__(config={})

    def get_supported_actions(self) -> List[str]:
        return _SUPPORTED_ACTIONS

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        start = time.time()
        store_id = params.get("store_id", "STORE001")
        logger.info("service_agent.execute", action=action, store_id=store_id)

        if action not in _SUPPORTED_ACTIONS:
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(_SUPPORTED_ACTIONS)}",
                execution_time=time.time() - start,
            )

        try:
            from src.services.service_service import ServiceQualityService

            svc = ServiceQualityService(store_id=store_id)

            if action == "get_service_quality_metrics":
                data = await svc.get_service_quality_metrics(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date"),
                )

            elif action == "get_feedback_summary":
                # 复用 service_quality_metrics，提取满意度摘要
                metrics = await svc.get_service_quality_metrics(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date"),
                )
                data = {
                    "store_id": store_id,
                    "satisfaction": metrics.get("satisfaction", {}),
                    "quality_score": metrics.get("quality_score", 0),
                    "status": metrics.get("status", "unknown"),
                    "period": metrics.get("period", {}),
                }

            elif action == "get_satisfaction_score":
                metrics = await svc.get_service_quality_metrics(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date"),
                )
                satisfaction = metrics.get("satisfaction", {})
                data = {
                    "store_id": store_id,
                    "average_rating": satisfaction.get("average_rating", 0),
                    "trend": satisfaction.get("trend", "stable"),
                    "records_count": satisfaction.get("records_count", 0),
                    "quality_score": metrics.get("quality_score", 0),
                }

            elif action == "get_service_report":
                data = await svc.get_service_report(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date"),
                )

            elif action in ("handle_complaint", "list_complaints"):
                # 委托给 get_service_quality_metrics，取服务指标
                metrics = await svc.get_service_quality_metrics(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date"),
                )
                data = {
                    "store_id": store_id,
                    "action": action,
                    "service_metrics": metrics.get("service_metrics", {}),
                    "note": "详细投诉记录请通过 /api/v1/quality 端点查询",
                }

            else:
                data = {"store_id": store_id, "action": action}

        except Exception as exc:
            logger.error("service_agent.execute_failed", action=action, store_id=store_id, error=str(exc))
            return AgentResponse(
                success=False,
                error=str(exc),
                execution_time=time.time() - start,
            )

        return AgentResponse(
            success=True,
            data=data,
            execution_time=time.time() - start,
        )
