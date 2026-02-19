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
            # Special handling for decision agent - use database service
            if agent_type == "decision" and action == "get_decision_report":
                from src.services.decision_service import decision_service
                result_data = await decision_service.get_decision_report(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                execution_time = time.time() - start_time

                logger.info(
                    "Decision Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

            # Special handling for reservation agent - use database service
            if agent_type == "reservation":
                from src.services.reservation_service import reservation_service

                if action == "create":
                    result_data = await reservation_service.create_reservation(
                        customer_name=params["customer_name"],
                        customer_phone=params["customer_phone"],
                        reservation_date=params["reservation_date"],
                        reservation_time=params["reservation_time"],
                        party_size=params["party_size"],
                        reservation_type=params.get("reservation_type", "regular"),
                        **{k: v for k, v in params.items() if k not in [
                            "customer_name", "customer_phone", "reservation_date",
                            "reservation_time", "party_size", "reservation_type"
                        ]}
                    )
                elif action == "list":
                    result_data = await reservation_service.get_reservations(
                        reservation_date=params.get("reservation_date"),
                        status=params.get("status"),
                        limit=params.get("limit", 100)
                    )
                elif action == "get":
                    result_data = await reservation_service.get_reservation_by_id(
                        reservation_id=params["reservation_id"]
                    )
                elif action == "confirm":
                    result_data = await reservation_service.update_reservation_status(
                        reservation_id=params["reservation_id"],
                        status="confirmed",
                        notes=params.get("notes")
                    )
                elif action == "cancel":
                    result_data = await reservation_service.cancel_reservation(
                        reservation_id=params["reservation_id"],
                        reason=params.get("reason")
                    )
                elif action == "assign_table":
                    result_data = await reservation_service.assign_table(
                        reservation_id=params["reservation_id"],
                        table_number=params["table_number"]
                    )
                elif action == "upcoming":
                    result_data = await reservation_service.get_upcoming_reservations(
                        days=params.get("days", 7)
                    )
                elif action == "statistics":
                    result_data = await reservation_service.get_reservation_statistics(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Unknown reservation action: {action}",
                        "execution_time": time.time() - start_time,
                    }

                execution_time = time.time() - start_time

                logger.info(
                    "Reservation Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

            # Special handling for order agent - use database service
            if agent_type == "order":
                from src.services.order_service import order_service

                if action == "create_order":
                    result_data = await order_service.create_order(
                        table_number=params["table_number"],
                        items=params["items"],
                        customer_name=params.get("customer_name"),
                        customer_phone=params.get("customer_phone"),
                        notes=params.get("notes"),
                        **{k: v for k, v in params.items() if k not in [
                            "table_number", "items", "customer_name", "customer_phone", "notes"
                        ]}
                    )
                elif action == "get_order":
                    result_data = await order_service.get_order(
                        order_id=params["order_id"]
                    )
                elif action == "list_orders":
                    result_data = await order_service.list_orders(
                        status=params.get("status"),
                        table_number=params.get("table_number"),
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date"),
                        limit=params.get("limit", 100)
                    )
                elif action == "update_order_status":
                    result_data = await order_service.update_order_status(
                        order_id=params["order_id"],
                        status=params["status"],
                        notes=params.get("notes")
                    )
                elif action == "add_items":
                    result_data = await order_service.add_items(
                        order_id=params["order_id"],
                        items=params["items"]
                    )
                elif action == "cancel_order":
                    result_data = await order_service.cancel_order(
                        order_id=params["order_id"],
                        reason=params.get("reason")
                    )
                elif action == "get_order_statistics":
                    result_data = await order_service.get_order_statistics(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Unknown order action: {action}",
                        "execution_time": time.time() - start_time,
                    }

                execution_time = time.time() - start_time

                logger.info(
                    "Order Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

            # Special handling for service agent - use database service
            if agent_type == "service":
                from src.services.service_service import service_quality_service

                if action == "monitor_service_quality" or action == "get_service_quality_metrics":
                    result_data = await service_quality_service.get_service_quality_metrics(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                elif action == "track_staff_performance" or action == "get_staff_performance":
                    result_data = await service_quality_service.get_staff_performance(
                        staff_id=params.get("staff_id"),
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                elif action == "record_service_quality":
                    result_data = await service_quality_service.record_service_quality(
                        metric_name=params["metric_name"],
                        value=params["value"],
                        record_date=params.get("record_date"),
                        **{k: v for k, v in params.items() if k not in ["metric_name", "value", "record_date"]}
                    )
                elif action == "get_service_report":
                    result_data = await service_quality_service.get_service_report(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Unknown service action: {action}",
                        "execution_time": time.time() - start_time,
                    }

                execution_time = time.time() - start_time

                logger.info(
                    "Service Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

            # Special handling for inventory agent - use database service
            if agent_type == "inventory":
                from src.services.inventory_service import inventory_service

                if action == "monitor_inventory":
                    result_data = await inventory_service.monitor_inventory(
                        category=params.get("category"),
                        status=params.get("status")
                    )
                elif action == "get_item":
                    result_data = await inventory_service.get_item(
                        item_id=params["item_id"]
                    )
                elif action == "generate_restock_alerts":
                    result_data = await inventory_service.generate_restock_alerts(
                        category=params.get("category")
                    )
                elif action == "record_transaction":
                    result_data = await inventory_service.record_transaction(
                        item_id=params["item_id"],
                        transaction_type=params["transaction_type"],
                        quantity=params["quantity"],
                        unit_cost=params.get("unit_cost"),
                        reference_id=params.get("reference_id"),
                        notes=params.get("notes"),
                        performed_by=params.get("performed_by")
                    )
                elif action == "get_inventory_statistics":
                    result_data = await inventory_service.get_inventory_statistics(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                elif action == "get_inventory_report":
                    result_data = await inventory_service.get_inventory_report(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Unknown inventory action: {action}",
                        "execution_time": time.time() - start_time,
                    }

                execution_time = time.time() - start_time

                logger.info(
                    "Inventory Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

            # Special handling for schedule agent - use database service
            if agent_type == "schedule":
                from src.services.schedule_service import schedule_service

                if action == "create_schedule":
                    result_data = await schedule_service.create_schedule(
                        schedule_date=params["schedule_date"],
                        shifts=params["shifts"],
                        **{k: v for k, v in params.items() if k not in ["schedule_date", "shifts"]}
                    )
                elif action == "get_schedule":
                    result_data = await schedule_service.get_schedule(
                        start_date=params["start_date"],
                        end_date=params.get("end_date")
                    )
                elif action == "get_schedule_by_date":
                    result_data = await schedule_service.get_schedule_by_date(
                        schedule_date=params["schedule_date"]
                    )
                elif action == "update_schedule":
                    result_data = await schedule_service.update_schedule(
                        schedule_id=params["schedule_id"],
                        **{k: v for k, v in params.items() if k != "schedule_id"}
                    )
                elif action == "delete_schedule":
                    result_data = await schedule_service.delete_schedule(
                        schedule_id=params["schedule_id"]
                    )
                elif action == "get_employee_schedules":
                    result_data = await schedule_service.get_employee_schedules(
                        employee_id=params["employee_id"],
                        start_date=params["start_date"],
                        end_date=params.get("end_date")
                    )
                elif action == "get_schedule_statistics":
                    result_data = await schedule_service.get_schedule_statistics(
                        start_date=params["start_date"],
                        end_date=params["end_date"]
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Unknown schedule action: {action}",
                        "execution_time": time.time() - start_time,
                    }

                execution_time = time.time() - start_time

                logger.info(
                    "Schedule Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

            # Special handling for training agent - use database service
            if agent_type == "training":
                from src.services.training_service import training_service

                if action == "assess_training_needs":
                    result_data = await training_service.assess_training_needs(
                        staff_id=params.get("staff_id"),
                        position=params.get("position")
                    )
                elif action == "record_training_completion":
                    result_data = await training_service.record_training_completion(
                        staff_id=params["staff_id"],
                        course_name=params["course_name"],
                        completion_date=params["completion_date"],
                        score=params.get("score"),
                        **{k: v for k, v in params.items() if k not in ["staff_id", "course_name", "completion_date", "score"]}
                    )
                elif action == "get_training_progress" or action == "track_training_progress":
                    result_data = await training_service.get_training_progress(
                        staff_id=params.get("staff_id"),
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                elif action == "get_training_statistics":
                    result_data = await training_service.get_training_statistics(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                elif action == "get_training_report":
                    result_data = await training_service.get_training_report(
                        start_date=params.get("start_date"),
                        end_date=params.get("end_date")
                    )
                elif action == "get_employee_training_history":
                    result_data = await training_service.get_employee_training_history(
                        staff_id=params["staff_id"]
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Unknown training action: {action}",
                        "execution_time": time.time() - start_time,
                    }

                execution_time = time.time() - start_time

                logger.info(
                    "Training Agent执行完成(使用数据库)",
                    agent_type=agent_type,
                    action=action,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "data": result_data,
                    "error": None,
                    "execution_time": execution_time,
                    "metadata": {"source": "database"},
                }

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


# 创建全局实例
agent_service = AgentService()
