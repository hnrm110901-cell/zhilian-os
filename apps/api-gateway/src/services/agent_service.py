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
            self._agents["inventory"] = InventoryAgent(default_config)
            logger.info("InventoryAgent初始化成功")
        except Exception as e:
            logger.error("InventoryAgent初始化失败", exc_info=e)

        try:
            # 初始化服务Agent
            from service.src.agent import ServiceAgent
            self._agents["service"] = ServiceAgent(default_config)
            logger.info("ServiceAgent初始化成功")
        except Exception as e:
            logger.error("ServiceAgent初始化失败", exc_info=e)

        try:
            # 初始化培训Agent
            from training.src.agent import TrainingAgent
            self._agents["training"] = TrainingAgent(default_config)
            logger.info("TrainingAgent初始化成功")
        except Exception as e:
            logger.error("TrainingAgent初始化失败", exc_info=e)

        try:
            # 初始化决策Agent
            from decision.src.agent import DecisionAgent
            self._agents["decision"] = DecisionAgent(default_config)
            logger.info("DecisionAgent初始化成功")
        except Exception as e:
            logger.error("DecisionAgent初始化失败", exc_info=e)

        try:
            # 初始化预定Agent
            from reservation.src.agent import ReservationAgent
            self._agents["reservation"] = ReservationAgent(default_config)
            logger.info("ReservationAgent初始化成功")
        except Exception as e:
            logger.error("ReservationAgent初始化失败", exc_info=e)

    async def execute_agent(
        self, agent_type: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行Agent

        Args:
            agent_type: Agent类型
            input_data: 输入数据

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

        try:
            # 根据不同的Agent类型调用不同的方法
            if agent_type == "schedule":
                result = await self._execute_schedule_agent(agent, input_data)
            elif agent_type == "order":
                result = await self._execute_order_agent(agent, input_data)
            elif agent_type == "inventory":
                result = await self._execute_inventory_agent(agent, input_data)
            elif agent_type == "service":
                result = await self._execute_service_agent(agent, input_data)
            elif agent_type == "training":
                result = await self._execute_training_agent(agent, input_data)
            elif agent_type == "decision":
                result = await self._execute_decision_agent(agent, input_data)
            elif agent_type == "reservation":
                result = await self._execute_reservation_agent(agent, input_data)
            else:
                result = {"success": False, "error": f"未实现的Agent类型: {agent_type}"}

            execution_time = time.time() - start_time
            result["execution_time"] = execution_time

            logger.info(
                "Agent执行完成",
                agent_type=agent_type,
                execution_time=execution_time,
                success=result.get("success", False),
            )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error("Agent执行失败", agent_type=agent_type, exc_info=e)
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
            }

    async def _execute_schedule_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行排班Agent"""
        action = input_data.get("action", "run")

        if action == "run":
            return await agent.run(
                store_id=input_data.get("store_id"),
                date=input_data.get("date"),
                employees=input_data.get("employees", []),
            )
        elif action == "adjust":
            return await agent.adjust_schedule(
                schedule_id=input_data.get("schedule_id"),
                adjustments=input_data.get("adjustments", []),
            )
        elif action == "get":
            return await agent.get_schedule(
                store_id=input_data.get("store_id"),
                start_date=input_data.get("start_date"),
                end_date=input_data.get("end_date"),
            )
        else:
            return {"success": False, "error": f"未知的操作: {action}"}

    async def _execute_order_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行订单Agent"""
        action = input_data.get("action", "create")

        if action == "create":
            return await agent.create_order(
                store_id=input_data.get("store_id"),
                table_id=input_data.get("table_id"),
                customer_id=input_data.get("customer_id"),
            )
        elif action == "reservation":
            return await agent.create_reservation(
                customer_name=input_data.get("customer_name"),
                customer_phone=input_data.get("customer_phone"),
                party_size=input_data.get("party_size"),
                reservation_time=input_data.get("reservation_time"),
                special_requests=input_data.get("special_requests"),
            )
        elif action == "queue":
            return await agent.join_queue(
                store_id=input_data.get("store_id"),
                customer_name=input_data.get("customer_name"),
                customer_phone=input_data.get("customer_phone"),
                party_size=input_data.get("party_size"),
            )
        else:
            return {"success": False, "error": f"未知的操作: {action}"}

    async def _execute_inventory_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行库存Agent"""
        action = input_data.get("action", "monitor")

        if action == "monitor":
            category = input_data.get("category")
            items = await agent.monitor_inventory(category=category)
            # Items might be dicts or objects, handle both
            items_list = []
            for item in items:
                if isinstance(item, dict):
                    items_list.append(item)
                else:
                    items_list.append({
                        "item_id": getattr(item, 'item_id', ''),
                        "name": getattr(item, 'name', ''),
                        "current_stock": getattr(item, 'current_stock', 0),
                        "unit": getattr(item, 'unit', ''),
                        "status": getattr(item, 'status', ''),
                    })
            return {
                "success": True,
                "items": items_list,
            }
        elif action == "predict":
            days = input_data.get("days", 7)
            predictions = await agent.predict_consumption(days=days)
            return {"success": True, "predictions": predictions}
        elif action == "alerts":
            alerts = await agent.generate_restock_alerts()
            # Handle both dict and object returns
            alerts_list = []
            for alert in alerts:
                if isinstance(alert, dict):
                    alerts_list.append(alert)
                else:
                    alerts_list.append({
                        "item_id": getattr(alert, 'item_id', ''),
                        "item_name": getattr(alert, 'item_name', ''),
                        "current_stock": getattr(alert, 'current_stock', 0),
                        "recommended_quantity": getattr(alert, 'recommended_quantity', 0),
                        "urgency": getattr(alert, 'urgency', ''),
                    })
            return {
                "success": True,
                "alerts": alerts_list,
            }
        else:
            return {"success": False, "error": f"未知的操作: {action}"}

    async def _execute_service_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行服务Agent"""
        action = input_data.get("action", "monitor")

        if action == "monitor":
            metrics = await agent.monitor_service_quality(
                start_date=input_data.get("start_date"),
                end_date=input_data.get("end_date"),
            )
            return {
                "success": True,
                "metrics": metrics,
            }
        elif action == "feedback":
            feedback_data = input_data.get("feedback_data", [])
            result = await agent.analyze_feedback(
                feedback_list=feedback_data,
            )
            return {"success": True, "analysis": result}
        elif action == "complaint":
            result = await agent.handle_complaint(
                complaint_id=input_data.get("complaint_id"),
                complaint_data=input_data.get("complaint_data", {}),
            )
            return {"success": True, "result": result}
        else:
            return {"success": False, "error": f"未知的操作: {action}"}

    async def _execute_training_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行培训Agent"""
        action = input_data.get("action", "assess")

        if action == "assess":
            needs = await agent.assess_training_needs(
                staff_id=input_data.get("staff_id"),
                position=input_data.get("position"),
            )
            return {
                "success": True,
                "needs": needs if isinstance(needs, list) else [needs],
            }
        elif action == "plan":
            plan = await agent.generate_training_plan(
                staff_id=input_data.get("staff_id"),
                training_needs=input_data.get("training_needs"),
                start_date=input_data.get("start_date"),
            )
            return {
                "success": True,
                "plan": plan,
            }
        else:
            return {"success": False, "error": f"未知的操作: {action}"}

    async def _execute_decision_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行决策Agent"""
        action = input_data.get("action", "kpi")

        if action == "kpi":
            kpis = await agent.analyze_kpis(
                start_date=input_data.get("start_date"),
                end_date=input_data.get("end_date"),
            )
            return {
                "success": True,
                "kpis": kpis if isinstance(kpis, list) else [kpis],
            }
        elif action == "insights":
            insights = await agent.generate_insights()
            return {
                "success": True,
                "insights": insights if isinstance(insights, list) else [insights],
            }
        elif action == "recommend":
            recommendations = await agent.generate_recommendations()
            return {"success": True, "recommendations": recommendations}
        else:
            return {"success": False, "error": f"未知的操作: {action}"}

    async def _execute_reservation_agent(
        self, agent: Any, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行预定Agent"""
        action = input_data.get("action", "create")

        if action == "create":
            data = input_data.get("reservation_data", {})
            reservation = await agent.create_reservation(
                customer_id=data.get("customer_id", ""),
                customer_name=data.get("customer_name", ""),
                customer_phone=data.get("customer_phone", ""),
                reservation_date=data.get("reservation_date", ""),
                reservation_time=data.get("reservation_time", ""),
                party_size=data.get("party_size", 0),
                special_requests=data.get("special_requests"),
            )
            # Convert Reservation object to dict response
            return {
                "success": True,
                "reservation_id": reservation.get("reservation_id"),
                "reservation": dict(reservation),
            }
        elif action == "confirm":
            return await agent.confirm_reservation(
                reservation_id=input_data.get("reservation_id")
            )
        elif action == "cancel":
            return await agent.cancel_reservation(
                reservation_id=input_data.get("reservation_id"),
                reason=input_data.get("reason", ""),
            )
        elif action == "get":
            return await agent.get_reservation(
                reservation_id=input_data.get("reservation_id")
            )
        else:
            return {"success": False, "error": f"未知的操作: {action}"}
