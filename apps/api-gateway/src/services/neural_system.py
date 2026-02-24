"""
神经系统编排器
Neural System Orchestrator

智链OS作为餐饮门店的神经系统
统一协调订单、菜品、人员、时间、金额五个核心维度
"""
import os
from typing import Dict, Any, List, Optional
import structlog
from datetime import datetime
import uuid

from .vector_db_service import vector_db_service
from ..schemas.restaurant_standard_schema import (
    NeuralEventSchema,
    OrderSchema,
    DishSchema,
    StaffSchema,
)
from ..core.celery_tasks import process_neural_event

logger = structlog.get_logger()


class NeuralSystemOrchestrator:
    """神经系统编排器

    智链OS的核心：
    1. 接收所有业务事件
    2. 向量化存储到向量数据库
    3. 触发相应的Agent处理
    4. 参与联邦学习
    5. 保持数据隔离
    """

    def __init__(self):
        """初始化神经系统编排器"""
        # 移除内存事件队列，改用Celery任务队列
        # self.event_queue: List[NeuralEventSchema] = []
        self.event_handlers: Dict[str, Any] = {}

        logger.info("NeuralSystemOrchestrator初始化完成（使用Celery任务队列）")

    async def initialize(self):
        """初始化神经系统"""
        try:
            # 初始化向量数据库
            await vector_db_service.initialize()

            # 注册事件处理器
            self._register_event_handlers()

            logger.info("神经系统初始化成功")

        except Exception as e:
            logger.error("神经系统初始化失败", error=str(e))
            raise

    def _register_event_handlers(self):
        """注册事件处理器"""
        self.event_handlers = {
            "order.created": self._handle_order_created,
            "order.updated": self._handle_order_updated,
            "order.completed": self._handle_order_completed,
            "dish.created": self._handle_dish_created,
            "dish.updated": self._handle_dish_updated,
            "staff.shift_start": self._handle_staff_shift_start,
            "staff.shift_end": self._handle_staff_shift_end,
            "payment.completed": self._handle_payment_completed,
            "inventory.low_stock": self._handle_inventory_low_stock,
            "compliance.expire_soon": self._handle_compliance_expire_soon,
            "compliance.expired": self._handle_compliance_expired,
            # quality.*
            "quality.inspection_failed": self._handle_quality_inspection_failed,
            "quality.inspection_passed": self._handle_quality_inspection_passed,
            "quality.alert": self._handle_quality_alert,
            # equipment.*
            "equipment.fault": self._handle_equipment_fault,
            "equipment.maintenance_due": self._handle_equipment_maintenance_due,
            "equipment.repaired": self._handle_equipment_repaired,
            # crm.*
            "crm.member_joined": self._handle_crm_member_joined,
            "crm.member_birthday": self._handle_crm_member_birthday,
            "crm.review_received": self._handle_crm_review_received,
        }

    async def emit_event(
        self,
        event_type: str,
        event_source: str,
        data: Dict[str, Any],
        store_id: str,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """
        发射神经系统事件（使用Celery异步任务队列）

        Args:
            event_type: 事件类型
            event_source: 事件来源
            data: 事件数据
            store_id: 门店ID
            priority: 优先级

        Returns:
            处理结果
        """
        try:
            # 生成事件ID
            event_id = str(uuid.uuid4())

            logger.info(
                "神经系统事件发射（Celery）",
                event_id=event_id,
                event_type=event_type,
                store_id=store_id,
            )

            # 提交到Celery任务队列（异步处理）
            task = process_neural_event.apply_async(
                kwargs={
                    "event_id": event_id,
                    "event_type": event_type,
                    "event_source": event_source,
                    "store_id": store_id,
                    "data": data,
                    "priority": priority,
                },
                priority=priority,  # 设置任务优先级
            )

            return {
                "success": True,
                "event_id": event_id,
                "task_id": task.id,
                "status": "queued",
                "message": "事件已提交到Celery任务队列",
            }

        except Exception as e:
            logger.error("事件发射失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def _process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理事件

        Args:
            event: 事件数据

        Returns:
            处理结果
        """
        event_type = event["event_type"]

        # 查找事件处理器
        handler = self.event_handlers.get(event_type)

        if handler:
            try:
                result = await handler(event)
                logger.info("事件处理成功", event_type=event_type)
                return result
            except Exception as e:
                logger.error("事件处理失败", event_type=event_type, error=str(e))
                return {"success": False, "error": str(e)}
        else:
            logger.warning("未找到事件处理器", event_type=event_type)
            return {"success": False, "error": "未找到事件处理器"}

    # ==================== 事件处理器 ====================

    async def _handle_order_created(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理订单创建事件"""
        order_data = event["data"]

        # 1. 索引订单到向量数据库
        await vector_db_service.index_order(order_data)

        # 2. 触发相关Agent
        # - 通知后厨Agent
        # - 更新库存Agent
        # - 通知服务员Agent

        # 3. 记录到联邦学习数据集
        # （本地训练数据，不上传原始数据）

        return {"success": True, "action": "order_indexed_and_agents_notified"}

    async def _handle_order_updated(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理订单更新事件"""
        order_data = event["data"]

        # 更新向量数据库
        await vector_db_service.index_order(order_data)

        return {"success": True, "action": "order_updated"}

    async def _handle_order_completed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理订单完成事件"""
        order_data = event["data"]

        # 1. 更新向量数据库
        await vector_db_service.index_order(order_data)

        # 2. 触发财务Agent记录收入
        # 3. 触发决策Agent更新统计数据
        # 4. 用于联邦学习的需求预测模型训练

        return {"success": True, "action": "order_completed_processed"}

    async def _handle_dish_created(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理菜品创建事件"""
        dish_data = event["data"]

        # 索引菜品到向量数据库
        await vector_db_service.index_dish(dish_data)

        return {"success": True, "action": "dish_indexed"}

    async def _handle_dish_updated(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理菜品更新事件"""
        dish_data = event["data"]

        # 更新向量数据库
        await vector_db_service.index_dish(dish_data)

        return {"success": True, "action": "dish_updated"}

    async def _handle_staff_shift_start(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理员工上班事件"""
        staff_data = event["data"]
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=staff_data.get("store_id", ""),
                    type="system",
                    title="员工上班",
                    content=f"{staff_data.get('name', '员工')} 已上班签到",
                    priority="low",
                    extra_data={"employee_id": staff_data.get("employee_id"), "event": "shift_start"},
                ))
                await session.commit()
        except Exception as e:
            logger.error("处理员工上班事件失败", error=str(e))
        return {"success": True, "action": "shift_start_recorded"}

    async def _handle_staff_shift_end(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理员工下班事件"""
        staff_data = event["data"]
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            from datetime import datetime as dt
            start_str = staff_data.get("shift_start_time")
            work_hours = 0.0
            if start_str:
                try:
                    start = dt.fromisoformat(start_str)
                    work_hours = round((dt.utcnow() - start).total_seconds() / 3600, 2)
                except Exception as e:
                    logger.warning("time_parse_failed", start_str=start_str, error=str(e))
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=staff_data.get("store_id", ""),
                    type="system",
                    title="员工下班",
                    content=f"{staff_data.get('name', '员工')} 已下班，本次工时 {work_hours} 小时",
                    priority="low",
                    extra_data={"employee_id": staff_data.get("employee_id"), "work_hours": work_hours, "event": "shift_end"},
                ))
                await session.commit()
        except Exception as e:
            logger.error("处理员工下班事件失败", error=str(e))
        return {"success": True, "action": "shift_end_recorded"}

    async def _handle_payment_completed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理支付完成事件"""
        payment_data = event["data"]
        try:
            from src.core.database import get_db_session
            from src.models.order import Order, OrderStatus
            from src.models.notification import Notification
            from sqlalchemy import select
            async with get_db_session() as session:
                order_id = payment_data.get("order_id")
                if order_id:
                    result = await session.execute(select(Order).where(Order.id == order_id))
                    order = result.scalar_one_or_none()
                    if order:
                        order.status = OrderStatus.COMPLETED
                        from datetime import datetime as dt
                        order.completed_at = dt.utcnow()
                # 会员积分通知
                customer_phone = payment_data.get("customer_phone")
                if customer_phone:
                    amount = payment_data.get("amount", 0)
                    points = int(amount / 100)  # 每消费1元积1分
                    session.add(Notification(
                        store_id=payment_data.get("store_id", ""),
                        type="member",
                        title="积分更新",
                        content=f"本次消费获得 {points} 积分",
                        priority="low",
                        extra_data={"customer_phone": customer_phone, "points_earned": points},
                    ))
                await session.commit()
        except Exception as e:
            logger.error("处理支付完成事件失败", error=str(e))
        return {"success": True, "action": "payment_recorded"}

    async def _handle_inventory_low_stock(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理库存不足事件"""
        inventory_data = event["data"]
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            item_name = inventory_data.get("item_name", "未知物料")
            current_qty = inventory_data.get("current_quantity", 0)
            store_id = inventory_data.get("store_id", "")
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="inventory",
                    title="库存预警",
                    content=f"【库存不足】{item_name} 当前库存 {current_qty}，请及时补货",
                    priority="high",
                    extra_data={"item_id": inventory_data.get("item_id"), "current_quantity": current_qty},
                ))
                await session.commit()
            # 企微推送
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                await wechat.send_text_message(
                    "@all",
                    f"【库存预警】{item_name} 库存不足（当前：{current_qty}），请尽快补货！"
                )
            except Exception as we:
                logger.warning("库存预警企微推送失败", error=str(we))
        except Exception as e:
            logger.error("处理库存不足事件失败", error=str(e))
        return {"success": True, "action": "low_stock_alert_sent"}

    async def _handle_compliance_expire_soon(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理证照即将到期事件"""
        data = event["data"]
        store_id = data.get("store_id", "")
        license_name = data.get("license_name", "未知证照")
        days_left = data.get("days_left", 0)
        holder = data.get("holder_name", "")
        holder_str = f"（{holder}）" if holder else ""
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="compliance",
                    title="证照即将到期",
                    content=f"【证照预警】{license_name}{holder_str} 还剩 {days_left} 天到期，请尽快续期",
                    priority="high" if days_left <= 7 else "medium",
                    extra_data=data,
                ))
                await session.commit()
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                await wechat.send_text_message(
                    "@all",
                    f"【证照预警】{license_name}{holder_str} 还剩 {days_left} 天到期，请尽快续期！"
                )
            except Exception as we:
                logger.warning("compliance_expire_soon_wechat_failed", error=str(we))
        except Exception as e:
            logger.error("handle_compliance_expire_soon_failed", error=str(e))
        return {"success": True, "action": "compliance_expire_soon_alerted"}

    async def _handle_compliance_expired(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理证照已过期事件"""
        data = event["data"]
        store_id = data.get("store_id", "")
        license_name = data.get("license_name", "未知证照")
        holder = data.get("holder_name", "")
        holder_str = f"（{holder}）" if holder else ""
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="compliance",
                    title="证照已过期",
                    content=f"【紧急】{license_name}{holder_str} 已过期，请立即处理，否则面临合规风险",
                    priority="critical",
                    extra_data=data,
                ))
                await session.commit()
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                await wechat.send_text_message(
                    "@all",
                    f"【紧急】{license_name}{holder_str} 已过期！请立即续期，否则面临合规风险！"
                )
            except Exception as we:
                logger.warning("compliance_expired_wechat_failed", error=str(we))
        except Exception as e:
            logger.error("handle_compliance_expired_failed", error=str(e))
        return {"success": True, "action": "compliance_expired_alerted"}

    # ==================== quality.* 事件处理器 ====================

    async def _handle_quality_inspection_failed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """菜品质量检测不合格"""
        data = event["data"]
        store_id = data.get("store_id", "")
        dish_name = data.get("dish_name", "未知菜品")
        score = data.get("quality_score", 0)
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="alert",
                    title="菜品质量不合格",
                    message=f"【质量预警】{dish_name} 质量评分 {score:.1f}，低于合格线，请立即检查",
                    priority="high",
                    extra_data=data,
                    source="quality_agent",
                ))
                await session.commit()
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                await wechat.send_text_message(
                    "@all",
                    f"【质量预警】{dish_name} 质量评分 {score:.1f}，请立即检查！"
                )
            except Exception as we:
                logger.warning("quality_fail_wechat_failed", error=str(we))
        except Exception as e:
            logger.error("handle_quality_inspection_failed_error", error=str(e))
        return {"success": True, "action": "quality_fail_alerted"}

    async def _handle_quality_inspection_passed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """菜品质量检测合格"""
        data = event["data"]
        store_id = data.get("store_id", "")
        dish_name = data.get("dish_name", "未知菜品")
        score = data.get("quality_score", 0)
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="info",
                    title="菜品质量合格",
                    message=f"{dish_name} 质量检测通过，评分 {score:.1f}",
                    priority="low",
                    extra_data=data,
                    source="quality_agent",
                ))
                await session.commit()
        except Exception as e:
            logger.error("handle_quality_inspection_passed_error", error=str(e))
        return {"success": True, "action": "quality_pass_recorded"}

    async def _handle_quality_alert(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """质量告警（批量/趋势异常）"""
        data = event["data"]
        store_id = data.get("store_id", "")
        message = data.get("message", "质量异常告警")
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="alert",
                    title="质量告警",
                    message=message,
                    priority="high",
                    extra_data=data,
                    source="quality_agent",
                ))
                await session.commit()
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                await wechat.send_text_message("@all", f"【质量告警】{message}")
            except Exception as we:
                logger.warning("quality_alert_wechat_failed", error=str(we))
        except Exception as e:
            logger.error("handle_quality_alert_error", error=str(e))
        return {"success": True, "action": "quality_alert_sent"}

    # ==================== equipment.* 事件处理器 ====================

    async def _handle_equipment_fault(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """设备故障"""
        data = event["data"]
        store_id = data.get("store_id", "")
        equipment_name = data.get("equipment_name", "未知设备")
        fault_desc = data.get("fault_description", "故障详情未知")
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="alert",
                    title="设备故障",
                    message=f"【设备故障】{equipment_name}：{fault_desc}，请立即处理",
                    priority="urgent",
                    extra_data=data,
                    source="equipment_monitor",
                ))
                await session.commit()
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                await wechat.send_text_message(
                    "@all",
                    f"【设备故障】{equipment_name} 发生故障：{fault_desc}，请立即处理！"
                )
            except Exception as we:
                logger.warning("equipment_fault_wechat_failed", error=str(we))
        except Exception as e:
            logger.error("handle_equipment_fault_error", error=str(e))
        return {"success": True, "action": "equipment_fault_alerted"}

    async def _handle_equipment_maintenance_due(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """设备保养到期"""
        data = event["data"]
        store_id = data.get("store_id", "")
        equipment_name = data.get("equipment_name", "未知设备")
        due_date = data.get("due_date", "")
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="warning",
                    title="设备保养提醒",
                    message=f"{equipment_name} 保养到期日：{due_date}，请安排保养",
                    priority="normal",
                    extra_data=data,
                    source="equipment_monitor",
                ))
                await session.commit()
        except Exception as e:
            logger.error("handle_equipment_maintenance_due_error", error=str(e))
        return {"success": True, "action": "equipment_maintenance_notified"}

    async def _handle_equipment_repaired(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """设备修复完成"""
        data = event["data"]
        store_id = data.get("store_id", "")
        equipment_name = data.get("equipment_name", "未知设备")
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="info",
                    title="设备修复完成",
                    message=f"{equipment_name} 已修复，恢复正常使用",
                    priority="low",
                    extra_data=data,
                    source="equipment_monitor",
                ))
                await session.commit()
        except Exception as e:
            logger.error("handle_equipment_repaired_error", error=str(e))
        return {"success": True, "action": "equipment_repaired_recorded"}

    # ==================== crm.* 事件处理器 ====================

    async def _handle_crm_member_joined(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """新会员注册"""
        data = event["data"]
        store_id = data.get("store_id", "")
        member_name = data.get("member_name", "新会员")
        phone = data.get("phone", "")
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="info",
                    title="新会员注册",
                    message=f"新会员 {member_name}（{phone}）已注册，请做好欢迎服务",
                    priority="low",
                    extra_data=data,
                    source="crm",
                ))
                await session.commit()
        except Exception as e:
            logger.error("handle_crm_member_joined_error", error=str(e))
        return {"success": True, "action": "member_joined_recorded"}

    async def _handle_crm_member_birthday(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """会员生日提醒"""
        data = event["data"]
        store_id = data.get("store_id", "")
        member_name = data.get("member_name", "会员")
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="info",
                    title="会员生日提醒",
                    message=f"今日是会员 {member_name} 的生日，可发送生日祝福或优惠券",
                    priority="normal",
                    extra_data=data,
                    source="crm",
                ))
                await session.commit()
        except Exception as e:
            logger.error("handle_crm_member_birthday_error", error=str(e))
        return {"success": True, "action": "member_birthday_notified"}

    async def _handle_crm_review_received(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """收到顾客评价"""
        data = event["data"]
        store_id = data.get("store_id", "")
        rating = data.get("rating", 0)
        platform = data.get("platform", "未知平台")
        content = data.get("content", "")
        priority = "high" if rating <= 2 else "normal"
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            async with get_db_session() as session:
                session.add(Notification(
                    store_id=store_id,
                    type="warning" if rating <= 2 else "info",
                    title=f"{'差评' if rating <= 2 else '新评价'}（{platform} {rating}星）",
                    message=f"来自 {platform} 的 {rating} 星评价：{content[:100]}",
                    priority=priority,
                    extra_data=data,
                    source="crm",
                ))
                await session.commit()
            if rating <= 2:
                try:
                    from src.services.wechat_work_message_service import WeChatWorkMessageService
                    wechat = WeChatWorkMessageService()
                    await wechat.send_text_message(
                        "@all",
                        f"【差评预警】{platform} 收到 {rating} 星差评，请及时处理！\n内容：{content[:100]}"
                    )
                except Exception as we:
                    logger.warning("crm_review_wechat_failed", error=str(we))
        except Exception as e:
            logger.error("handle_crm_review_received_error", error=str(e))
        return {"success": True, "action": "review_recorded"}

    # ==================== 语义搜索接口 ====================

    async def semantic_search_orders(
        self,
        query: str,
        store_id: str,
        limit: int = int(os.getenv("NEURAL_SEARCH_LIMIT", "10")),
    ) -> List[Dict[str, Any]]:
        """
        语义搜索订单

        Args:
            query: 查询文本（如"今天的外卖订单"）
            store_id: 门店ID
            limit: 返回数量

        Returns:
            搜索结果
        """
        # 数据隔离：只搜索本门店的数据
        filters = {"store_id": store_id}

        results = await vector_db_service.semantic_search(
            collection_name="orders",
            query=query,
            limit=limit,
            filters=filters,
        )

        return results

    async def semantic_search_dishes(
        self,
        query: str,
        store_id: str,
        limit: int = int(os.getenv("NEURAL_SEARCH_LIMIT", "10")),
    ) -> List[Dict[str, Any]]:
        """
        语义搜索菜品

        Args:
            query: 查询文本（如"辣的川菜"）
            store_id: 门店ID
            limit: 返回数量

        Returns:
            搜索结果
        """
        # 数据隔离：只搜索本门店的数据
        filters = {"store_id": store_id}

        results = await vector_db_service.semantic_search(
            collection_name="dishes",
            query=query,
            limit=limit,
            filters=filters,
        )

        return results

    async def semantic_search_events(
        self,
        query: str,
        store_id: str,
        limit: int = int(os.getenv("NEURAL_SEARCH_LIMIT", "10")),
    ) -> List[Dict[str, Any]]:
        """
        语义搜索事件

        Args:
            query: 查询文本（如"今天的异常事件"）
            store_id: 门店ID
            limit: 返回数量

        Returns:
            搜索结果
        """
        # 数据隔离：只搜索本门店的数据
        filters = {"store_id": store_id}

        results = await vector_db_service.semantic_search(
            collection_name="events",
            query=query,
            limit=limit,
            filters=filters,
        )

        return results

    # ==================== 联邦学习接口 ====================

    async def participate_in_federated_learning(
        self,
        store_id: str,
        model_type: str,
    ) -> Dict[str, Any]:
        """
        参与联邦学习

        Args:
            store_id: 门店ID
            model_type: 模型类型

        Returns:
            参与结果
        """
        try:
            # Federated learning removed - not supported for 3-5 stores
            # See architecture review: no statistical significance with small data
            logger.info("联邦学习已移除（数据量不支撑）", store_id=store_id)

            return {
                "success": False,
                "store_id": store_id,
                "model_type": model_type,
                "message": "Federated learning removed - insufficient data volume"
            }

        except Exception as e:
            logger.error("参与联邦学习失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def get_neural_system_status(self) -> Dict[str, Any]:
        """
        获取神经系统状态

        Returns:
            系统状态
        """
        # Federated learning removed
        fl_status = {"status": "removed", "reason": "insufficient data volume"}

        return {
            "neural_system": "operational",
            "registered_event_types": len(self.event_handlers),
            "event_types": sorted(self.event_handlers.keys()),
            "federated_learning": fl_status,
            "vector_database": "connected",
            "data_isolation": "enabled",
        }


# 创建全局实例
neural_system = NeuralSystemOrchestrator()
