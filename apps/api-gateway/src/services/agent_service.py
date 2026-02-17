"""
Agent服务 - Agent Service
管理所有智能体的初始化和调用
"""
import time
import structlog
from typing import Dict, Any, Optional
from pathlib import Path
import sys

logger = structlog.get_logger()

# 添加agents包路径
agents_path = Path(__file__).parent.parent.parent / "packages" / "agents"
sys.path.insert(0, str(agents_path))


class AgentService:
    """Agent服务类"""

    def __init__(self):
        """初始化Agent服务"""
        self._agents: Dict[str, Any] = {}
        self._initialize_agents()
        logger.info("AgentService初始化完成")

    def _initialize_agents(self):
        """初始化所有Agent"""
        # 默认配置
        default_config = {
            "llm_config": {
                "model": "gpt-4",
                "temperature": 0.7,
            }
        }
        default_store_id = "STORE001"

        try:
            # 初始化排班Agent
            from schedule.src.agent import ScheduleAgent
            self._agents["schedule"] = ScheduleAgent(default_config)
            logger.info("ScheduleAgent初始化成功")
        except Exception as e:
            logger.error("ScheduleAgent初始化失败", exc_info=e)

        try:
            # 初始化订单Agent
            from order.src.agent import OrderAgent
            self._agents["order"] = OrderAgent(default_config)
            logger.info("OrderAgent初始化成功")
        except Exception as e:
            logger.error("OrderAgent初始化失败", exc_info=e)

        try:
            # 初始化库存Agent
            from inventory.src.agent import InventoryAgent
            self._agents["inventory"] = InventoryAgent(
                store_id=default_store_id,
                pinzhi_adapter=None,
                alert_thresholds=None
            )
            logger.info("InventoryAgent初始化成功")
        except Exception as e:
            logger.error("InventoryAgent初始化失败", exc_info=e)

        try:
            # 初始化服务Agent
            from service.src.agent import ServiceAgent
            self._agents["service"] = ServiceAgent(
                store_id=default_store_id,
                aoqiwei_adapter=None,
                quality_thresholds=None
            )
            logger.info("ServiceAgent初始化成功")
        except Exception as e:
            logger.error("ServiceAgent初始化失败", exc_info=e)

        try:
            # 初始化培训Agent
            from training.src.agent import TrainingAgent
            self._agents["training"] = TrainingAgent(
                store_id=default_store_id,
                training_config=None
            )
            logger.info("TrainingAgent初始化成功")
        except Exception as e:
            logger.error("TrainingAgent初始化失败", exc_info=e)

        try:
            # 初始化决策Agent
            from decision.src.agent import DecisionAgent
            self._agents["decision"] = DecisionAgent(
                store_id=default_store_id,
                schedule_agent=None,
                order_agent=None,
                inventory_agent=None,
                service_agent=None,
                training_agent=None,
                kpi_targets=None
            )
            logger.info("DecisionAgent初始化成功")
        except Exception as e:
            logger.error("DecisionAgent初始化失败", exc_info=e)

        try:
            # 初始化预定Agent
            from reservation.src.agent import ReservationAgent
            self._agents["reservation"] = ReservationAgent(
                store_id=default_store_id,
                order_agent=None,
                config=None
            )
            logger.info("ReservationAgent初始化成功")
        except Exception as e:
            logger.error("ReservationAgent初始化失败", exc_info=e)

    async def execute_agent(
        self, agent_type: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行Agent - 使用统一的execute接口

        Args:
            agent_type: Agent类型
            input_data: 输入数据，必须包含action和params

        Returns:
            执行结果
        """
        start_time = time.time()

        if agent_type not in self._agents:
            return {
                "success": False,
                "error": f"未知的Agent类型: {agent_type}",
                "execution_time": 0.0,
            }

        agent = self._agents[agent_type]
        action = input_data.get("action")
        params = input_data.get("params", {})

        if not action:
            return {
                "success": False,
                "error": "缺少action参数",
                "execution_time": 0.0,
            }

        try:
            # 使用统一的execute接口
            response = await agent.execute(action, params)

            execution_time = time.time() - start_time

            # 将AgentResponse转换为字典格式
            result = {
                "success": response.success,
                "data": response.data,
                "error": response.error,
                "execution_time": response.execution_time or execution_time,
                "metadata": response.metadata,
            }

            logger.info(
                "Agent执行完成",
                agent_type=agent_type,
                action=action,
                execution_time=execution_time,
                success=response.success,
            )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error("Agent执行失败", agent_type=agent_type, action=action, exc_info=e)
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
            }
