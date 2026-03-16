"""
TrainingAgent - 员工培训管理智能体

负责：培训需求评估、培训计划生成、进度追踪、技能差距分析。
委托给 TrainingService 执行真实 DB 查询。
"""

import time
from typing import Any, Dict, List

import structlog
from src.core.base_agent import AgentResponse, BaseAgent

logger = structlog.get_logger()

_SUPPORTED_ACTIONS = [
    "assess_training_needs",
    "generate_training_plan",
    "get_training_progress",
    "analyze_skill_gaps",
    "list_training_records",
    "get_certification_status",
]


class TrainingAgent(BaseAgent):
    """员工培训管理智能体"""

    def __init__(self):
        super().__init__(config={})

    def get_supported_actions(self) -> List[str]:
        return _SUPPORTED_ACTIONS

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        start = time.time()
        store_id = params.get("store_id", "STORE001")
        logger.info("training_agent.execute", action=action, store_id=store_id)

        if action not in _SUPPORTED_ACTIONS:
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(_SUPPORTED_ACTIONS)}",
                execution_time=time.time() - start,
            )

        try:
            from src.services.training_service import TrainingService

            svc = TrainingService(store_id=store_id)

            if action == "assess_training_needs":
                data = await svc.assess_training_needs(
                    staff_id=params.get("staff_id"),
                    position=params.get("position"),
                )

            elif action == "generate_training_plan":
                # 先评估需求，再包装为"计划"输出
                needs = await svc.assess_training_needs(
                    staff_id=params.get("staff_id"),
                    position=params.get("position"),
                )
                data = {
                    "store_id": store_id,
                    "plan_type": "training_plan",
                    "staff_id": params.get("staff_id"),
                    "position": params.get("position"),
                    "training_needs": needs,
                    "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
                }

            elif action == "get_training_progress":
                data = await svc.get_training_progress(
                    staff_id=params.get("staff_id"),
                )

            elif action == "analyze_skill_gaps":
                # 评估需求即技能差距分析
                needs = await svc.assess_training_needs(
                    staff_id=params.get("staff_id"),
                    position=params.get("position"),
                )
                data = {
                    "store_id": store_id,
                    "skill_gaps": needs,
                    "position": params.get("position"),
                }

            elif action in ("list_training_records", "get_certification_status"):
                data = await svc.get_training_statistics()

            else:
                data = {"store_id": store_id, "action": action}

        except Exception as exc:
            logger.error("training_agent.execute_failed", action=action, store_id=store_id, error=str(exc))
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
