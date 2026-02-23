"""
语音指令服务 (轻量级MVP)
支持Shokz骨传导耳机的基础语音交互
本地意图识别，无需云端LLM
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog
from sqlalchemy.orm import Session
import re

from ..models.store import Store
from ..models.order import Order
from ..models.inventory import InventoryItem
from ..core.database import get_db

logger = structlog.get_logger()


class VoiceIntent:
    """语音意图枚举"""
    QUEUE_STATUS = "queue_status"  # 当前排队
    ORDER_REMINDER = "order_reminder"  # 催单提醒
    INVENTORY_QUERY = "inventory_query"  # 库存查询
    REVENUE_TODAY = "revenue_today"  # 今日营收
    CALL_SUPPORT = "call_support"  # 呼叫支援


class VoiceCommandService:
    """语音指令服务 (轻量级MVP)"""

    def __init__(self):
        # 意图识别规则（基于关键词匹配，无需LLM）
        self.intent_patterns = {
            VoiceIntent.QUEUE_STATUS: [
                r"(当前|现在|目前).*(排队|等位|等待)",
                r"(排队|等位).*(多少|几个|几桌)",
                r"(有|还有).*(多少|几个|几桌).*(排队|等位)"
            ],
            VoiceIntent.ORDER_REMINDER: [
                r"(催单|提醒|超时).*(订单|单子)",
                r"(哪些|有没有).*(订单|单子).*(超时|延迟)",
                r"(订单|单子).*(催|提醒)"
            ],
            VoiceIntent.INVENTORY_QUERY: [
                r"(库存|剩余|还有).*(多少|查询|查看)",
                r"(查|查询|查看).*(库存|剩余)",
                r".*还有多少.*"
            ],
            VoiceIntent.REVENUE_TODAY: [
                r"(今天|今日|当天).*(营收|收入|流水)",
                r"(营收|收入|流水).*(多少|怎么样)",
                r"(今天|今日).*(生意|业绩)"
            ],
            VoiceIntent.CALL_SUPPORT: [
                r"(呼叫|叫|需要).*(支援|帮忙|帮助)",
                r"(人手|人员).*(不够|不足)",
                r"(忙不过来|太忙)"
            ]
        }

    def recognize_intent(self, voice_text: str) -> Optional[str]:
        """
        识别语音意图（本地规则匹配）

        Args:
            voice_text: 语音识别文本

        Returns:
            str: 意图类型，如果无法识别则返回None
        """
        try:
            voice_text = voice_text.lower().strip()

            # 遍历所有意图模式
            for intent, patterns in self.intent_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, voice_text):
                        logger.info(
                            "intent_recognized",
                            voice_text=voice_text,
                            intent=intent,
                            pattern=pattern
                        )
                        return intent

            logger.warning("intent_not_recognized", voice_text=voice_text)
            return None

        except Exception as e:
            logger.error("recognize_intent_failed", error=str(e))
            return None

    async def handle_command(
        self,
        voice_text: str,
        store_id: str,
        user_id: str,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        处理语音指令

        Args:
            voice_text: 语音识别文本
            store_id: 门店ID
            user_id: 用户ID
            db: 数据库会话

        Returns:
            Dict: 响应结果
        """
        try:
            # 识别意图
            intent = self.recognize_intent(voice_text)

            if not intent:
                return {
                    "success": False,
                    "message": "抱歉，我没有理解您的指令",
                    "voice_response": "抱歉，我没有理解您的指令，请重新说一遍"
                }

            # 根据意图处理
            if intent == VoiceIntent.QUEUE_STATUS:
                return await self._handle_queue_status(store_id, db)

            elif intent == VoiceIntent.ORDER_REMINDER:
                return await self._handle_order_reminder(store_id, db)

            elif intent == VoiceIntent.INVENTORY_QUERY:
                return await self._handle_inventory_query(store_id, voice_text, db)

            elif intent == VoiceIntent.REVENUE_TODAY:
                return await self._handle_revenue_today(store_id, db)

            elif intent == VoiceIntent.CALL_SUPPORT:
                return await self._handle_call_support(store_id, user_id, db)

            else:
                return {
                    "success": False,
                    "message": "未知的指令类型",
                    "voice_response": "抱歉，暂不支持该指令"
                }

        except Exception as e:
            logger.error("handle_command_failed", error=str(e))
            return {
                "success": False,
                "message": f"处理指令失败: {str(e)}",
                "voice_response": "抱歉，处理指令时出现错误"
            }

    async def _handle_queue_status(self, store_id: str, db: Session) -> Dict[str, Any]:
        """处理排队状态查询"""
        try:
            from ..models.queue import Queue, QueueStatus

            waiting_queues = db.query(Queue).filter(
                Queue.store_id == store_id,
                Queue.status == QueueStatus.WAITING
            ).count()

            if waiting_queues == 0:
                voice_response = "当前没有排队，可以直接接待顾客"
            else:
                # 从历史数据计算每桌平均等待时间
                from sqlalchemy import func as sa_func
                avg_actual = db.query(sa_func.avg(Queue.actual_wait_time)).filter(
                    Queue.store_id == store_id,
                    Queue.actual_wait_time.isnot(None)
                ).scalar()
                avg_wait_per_table = int(avg_actual) if avg_actual else 15
                avg_wait_time = waiting_queues * avg_wait_per_table
                voice_response = f"当前有{waiting_queues}桌排队，预计等待{avg_wait_time}分钟"

            return {
                "success": True,
                "intent": VoiceIntent.QUEUE_STATUS,
                "data": {
                    "waiting_count": waiting_queues,
                    "estimated_wait_time": avg_wait_time if waiting_queues > 0 else 0
                },
                "message": voice_response,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("handle_queue_status_failed", error=str(e))
            return {
                "success": False,
                "message": f"查询排队状态失败: {str(e)}",
                "voice_response": "抱歉，查询排队状态失败"
            }

    async def _handle_order_reminder(self, store_id: str, db: Session) -> Dict[str, Any]:
        """处理催单提醒"""
        try:
            # 查询超时订单（超过30分钟未完成）
            timeout_threshold = datetime.utcnow() - timedelta(minutes=30)

            timeout_orders = db.query(Order).filter(
                Order.store_id == store_id,
                Order.status.in_(["pending", "preparing"]),
                Order.created_at < timeout_threshold
            ).all()

            if not timeout_orders:
                voice_response = "当前没有超时订单"
            else:
                order_count = len(timeout_orders)
                # 找出最长等待时间
                max_wait = max([
                    (datetime.utcnow() - order.created_at).total_seconds() / 60
                    for order in timeout_orders
                ])
                voice_response = f"有{order_count}个订单超时，最长等待{int(max_wait)}分钟，请尽快处理"

            return {
                "success": True,
                "intent": VoiceIntent.ORDER_REMINDER,
                "data": {
                    "timeout_count": len(timeout_orders),
                    "timeout_orders": [
                        {
                            "order_id": order.id,
                            "table_number": order.table_number,
                            "wait_time": int((datetime.utcnow() - order.created_at).total_seconds() / 60)
                        }
                        for order in timeout_orders[:5]  # 最多返回5个
                    ]
                },
                "message": voice_response,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("handle_order_reminder_failed", error=str(e))
            return {
                "success": False,
                "message": f"查询超时订单失败: {str(e)}",
                "voice_response": "抱歉，查询超时订单失败"
            }

    async def _handle_inventory_query(
        self,
        store_id: str,
        voice_text: str,
        db: Session
    ) -> Dict[str, Any]:
        """处理库存查询"""
        try:
            # 从语音文本中提取物品名称
            # 简单实现：查询所有低库存物品
            low_stock_items = db.query(InventoryItem).filter(
                InventoryItem.store_id == store_id,
                InventoryItem.quantity < InventoryItem.min_quantity
            ).all()

            if not low_stock_items:
                voice_response = "当前库存充足，没有低库存物品"
            else:
                item_count = len(low_stock_items)
                item_names = "、".join([item.name for item in low_stock_items[:3]])
                voice_response = f"有{item_count}个物品库存不足，包括{item_names}等，请及时补货"

            return {
                "success": True,
                "intent": VoiceIntent.INVENTORY_QUERY,
                "data": {
                    "low_stock_count": len(low_stock_items),
                    "low_stock_items": [
                        {
                            "item_id": item.id,
                            "name": item.name,
                            "quantity": item.quantity,
                            "min_quantity": item.min_quantity
                        }
                        for item in low_stock_items[:10]
                    ]
                },
                "message": voice_response,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("handle_inventory_query_failed", error=str(e))
            return {
                "success": False,
                "message": f"查询库存失败: {str(e)}",
                "voice_response": "抱歉，查询库存失败"
            }

    async def _handle_revenue_today(self, store_id: str, db: Session) -> Dict[str, Any]:
        """处理今日营收查询"""
        try:
            # 查询今日营收
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            from sqlalchemy import func
            today_revenue = db.query(func.sum(Order.total_amount)).filter(
                Order.store_id == store_id,
                Order.created_at >= today_start,
                Order.status.in_(["completed", "paid"])
            ).scalar() or 0

            # 查询昨日营收用于对比
            yesterday_start = today_start - timedelta(days=1)
            yesterday_revenue = db.query(func.sum(Order.total_amount)).filter(
                Order.store_id == store_id,
                Order.created_at >= yesterday_start,
                Order.created_at < today_start,
                Order.status.in_(["completed", "paid"])
            ).scalar() or 0

            # 计算增长率
            if yesterday_revenue > 0:
                growth_rate = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
                if growth_rate > 0:
                    comparison = f"比昨天增长{growth_rate:.1f}%"
                else:
                    comparison = f"比昨天下降{abs(growth_rate):.1f}%"
            else:
                comparison = "昨天无营收数据"

            voice_response = f"今日营收{today_revenue:.0f}元，{comparison}"

            return {
                "success": True,
                "intent": VoiceIntent.REVENUE_TODAY,
                "data": {
                    "today_revenue": today_revenue,
                    "yesterday_revenue": yesterday_revenue,
                    "growth_rate": growth_rate if yesterday_revenue > 0 else None
                },
                "message": voice_response,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("handle_revenue_today_failed", error=str(e))
            return {
                "success": False,
                "message": f"查询今日营收失败: {str(e)}",
                "voice_response": "抱歉，查询今日营收失败"
            }

    async def _handle_call_support(
        self,
        store_id: str,
        user_id: str,
        db: Session
    ) -> Dict[str, Any]:
        """处理呼叫支援"""
        try:
            # 获取门店信息
            store = db.query(Store).filter(Store.id == store_id).first()
            if not store:
                raise ValueError(f"Store not found: {store_id}")

            # 发送支援请求到企微群
            try:
                from .wechat_work_message_service import WeChatWorkMessageService
                wechat = WeChatWorkMessageService()
                msg = f"【支援请求】\n门店：{store.name}\n请求人：{user_id}\n时间：{datetime.utcnow().strftime('%H:%M:%S')}\n请附近同事尽快赶来支援"
                await wechat.send_text_message("@all", msg)
            except Exception as we:
                logger.warning("企微支援通知发送失败", error=str(we))

            support_request = {
                "id": str(uuid.uuid4()),
                "store_id": store_id,
                "store_name": store.name,
                "requester_id": user_id,
                "request_time": datetime.utcnow().isoformat(),
                "status": "pending"
            }

            voice_response = "支援请求已发送，附近同事将尽快赶来"

            logger.info(
                "support_request_sent",
                store_id=store_id,
                user_id=user_id
            )

            return {
                "success": True,
                "intent": VoiceIntent.CALL_SUPPORT,
                "data": support_request,
                "message": voice_response,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("handle_call_support_failed", error=str(e))
            return {
                "success": False,
                "message": f"发送支援请求失败: {str(e)}",
                "voice_response": "抱歉，发送支援请求失败"
            }

    async def broadcast_meituan_queue_update(
        self,
        store_id: str,
        queue_count: int,
        estimated_wait_time: int
    ) -> Dict[str, Any]:
        """
        广播美团排队更新（每5分钟自动播报）

        Args:
            store_id: 门店ID
            queue_count: 排队数量
            estimated_wait_time: 预计等待时间（分钟）

        Returns:
            Dict: 广播结果
        """
        try:
            if queue_count == 0:
                voice_response = "美团排队已清空"
            else:
                voice_response = f"美团排队{queue_count}桌，预计等待{estimated_wait_time}分钟"

            logger.info(
                "meituan_queue_broadcast",
                store_id=store_id,
                queue_count=queue_count,
                estimated_wait_time=estimated_wait_time
            )

            return {
                "success": True,
                "type": "broadcast",
                "data": {
                    "queue_count": queue_count,
                    "estimated_wait_time": estimated_wait_time
                },
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("broadcast_meituan_queue_failed", error=str(e))
            return {
                "success": False,
                "message": f"广播美团排队失败: {str(e)}"
            }

    async def alert_timeout_order(
        self,
        store_id: str,
        table_number: str,
        wait_time: int
    ) -> Dict[str, Any]:
        """
        超时订单告警（自动播报）

        Args:
            store_id: 门店ID
            table_number: 桌号
            wait_time: 等待时间（分钟）

        Returns:
            Dict: 告警结果
        """
        try:
            voice_response = f"注意，{table_number}号桌等待超过{wait_time}分钟，请尽快处理"

            logger.warning(
                "timeout_order_alert",
                store_id=store_id,
                table_number=table_number,
                wait_time=wait_time
            )

            return {
                "success": True,
                "type": "alert",
                "data": {
                    "table_number": table_number,
                    "wait_time": wait_time
                },
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error("alert_timeout_order_failed", error=str(e))
            return {
                "success": False,
                "message": f"发送超时告警失败: {str(e)}"
            }


# 全局实例
voice_command_service = VoiceCommandService()
