"""
排队服务
Queue Service for managing waiting lists
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import os
import structlog
import uuid

from ..models.queue import Queue, QueueStatus
from ..core.database import get_db_session

logger = structlog.get_logger()


class QueueService:
    """排队服务"""

    async def add_to_queue(
        self,
        store_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        special_requests: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        添加到排队队列

        Args:
            store_id: 门店ID
            customer_name: 客户姓名
            customer_phone: 客户电话
            party_size: 就餐人数
            special_requests: 特殊要求

        Returns:
            排队信息
        """
        async with get_db_session() as session:
            try:
                # 生成排队号码（当天的序号）
                queue_number = await self._generate_queue_number(session, store_id)

                # 预估等待时间
                estimated_wait_time = await self._estimate_wait_time(
                    session, store_id, party_size
                )

                # 创建排队记录
                queue = Queue(
                    queue_id=str(uuid.uuid4()),
                    queue_number=queue_number,
                    store_id=store_id,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    party_size=party_size,
                    status=QueueStatus.WAITING,
                    estimated_wait_time=estimated_wait_time,
                    special_requests=special_requests,
                )

                session.add(queue)
                await session.commit()
                await session.refresh(queue)

                logger.info(
                    "客户加入排队",
                    queue_id=queue.queue_id,
                    queue_number=queue_number,
                    customer_name=customer_name,
                    party_size=party_size,
                )

                # 触发Neural System事件
                await self._emit_queue_event(
                    "queue.added",
                    queue.to_dict(),
                    store_id,
                )

                return {
                    "success": True,
                    "data": queue.to_dict(),
                    "message": f"已加入排队，您的号码是 {queue_number}",
                }

            except Exception as e:
                await session.rollback()
                logger.error("添加排队失败", error=str(e), exc_info=e)
                raise

    async def _generate_queue_number(
        self,
        session: AsyncSession,
        store_id: str,
    ) -> int:
        """
        生成排队号码（当天的序号）

        Args:
            session: 数据库会话
            store_id: 门店ID

        Returns:
            排队号码
        """
        # 获取今天的最大号码
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        result = await session.execute(
            select(func.max(Queue.queue_number))
            .where(
                and_(
                    Queue.store_id == store_id,
                    Queue.created_at >= today_start,
                )
            )
        )
        max_number = result.scalar()

        return (max_number or 0) + 1

    async def _estimate_wait_time(
        self,
        session: AsyncSession,
        store_id: str,
        party_size: int,
    ) -> int:
        """
        预估等待时间

        基于当前排队人数和历史数据估算

        Args:
            session: 数据库会话
            store_id: 门店ID
            party_size: 就餐人数

        Returns:
            预估等待时间（分钟）
        """
        # 获取当前等待人数
        result = await session.execute(
            select(func.count(Queue.queue_id))
            .where(
                and_(
                    Queue.store_id == store_id,
                    Queue.status == QueueStatus.WAITING,
                )
            )
        )
        waiting_count = result.scalar() or 0

        # 基于历史实际等待时间计算均值，fallback 15 分钟
        from datetime import timedelta
        hist_result = await session.execute(
            select(func.avg(Queue.actual_wait_time)).where(
                and_(
                    Queue.store_id == store_id,
                    Queue.actual_wait_time.isnot(None),
                    Queue.created_at >= (datetime.utcnow() - timedelta(days=7)),
                )
            )
        )
        avg_wait = hist_result.scalar()
        base_wait_time = int(avg_wait) if avg_wait else int(os.getenv("QUEUE_DEFAULT_WAIT_MINUTES", "15"))
        estimated_time = waiting_count * base_wait_time

        # 根据人数调整（大桌等待时间可能更长）
        if party_size >= int(os.getenv("QUEUE_LARGE_PARTY_SIZE", "6")):
            estimated_time = int(estimated_time * float(os.getenv("QUEUE_LARGE_PARTY_MULTIPLIER", "1.3")))

        return max(int(os.getenv("QUEUE_MIN_WAIT_MINUTES", "10")), estimated_time)  # 最少N分钟

    async def call_next(
        self,
        store_id: str,
        table_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        叫号（叫下一位）

        Args:
            store_id: 门店ID
            table_number: 分配的桌号

        Returns:
            被叫号的排队信息
        """
        async with get_db_session() as session:
            try:
                # 获取下一个等待的客户
                result = await session.execute(
                    select(Queue)
                    .where(
                        and_(
                            Queue.store_id == store_id,
                            Queue.status == QueueStatus.WAITING,
                        )
                    )
                    .order_by(Queue.queue_number)
                    .limit(1)
                )
                queue = result.scalar_one_or_none()

                if not queue:
                    return {
                        "success": False,
                        "message": "当前没有等待的客户",
                    }

                # 更新状态为已叫号
                queue.status = QueueStatus.CALLED
                queue.called_at = datetime.now()
                if table_number:
                    queue.table_number = table_number

                await session.commit()
                await session.refresh(queue)

                logger.info(
                    "叫号成功",
                    queue_id=queue.queue_id,
                    queue_number=queue.queue_number,
                    customer_name=queue.customer_name,
                )

                # 触发Neural System事件
                await self._emit_queue_event(
                    "queue.called",
                    queue.to_dict(),
                    store_id,
                )

                # 发送通知给客户
                await self._send_notification(queue)

                return {
                    "success": True,
                    "data": queue.to_dict(),
                    "message": f"已叫号 {queue.queue_number}",
                }

            except Exception as e:
                await session.rollback()
                logger.error("叫号失败", error=str(e), exc_info=e)
                raise

    async def mark_seated(
        self,
        queue_id: str,
        table_number: str,
    ) -> Dict[str, Any]:
        """
        标记为已入座

        Args:
            queue_id: 排队ID
            table_number: 桌号

        Returns:
            更新后的排队信息
        """
        async with get_db_session() as session:
            try:
                result = await session.execute(
                    select(Queue).where(Queue.queue_id == queue_id)
                )
                queue = result.scalar_one_or_none()

                if not queue:
                    return {
                        "success": False,
                        "message": "排队记录不存在",
                    }

                # 更新状态
                queue.status = QueueStatus.SEATED
                queue.seated_at = datetime.now()
                queue.table_number = table_number

                # 计算实际等待时间
                if queue.created_at:
                    wait_time = (datetime.now() - queue.created_at).total_seconds() / 60
                    queue.actual_wait_time = int(wait_time)

                await session.commit()
                await session.refresh(queue)

                logger.info(
                    "客户已入座",
                    queue_id=queue_id,
                    queue_number=queue.queue_number,
                    table_number=table_number,
                    actual_wait_time=queue.actual_wait_time,
                )

                # 触发Neural System事件
                await self._emit_queue_event(
                    "queue.seated",
                    queue.to_dict(),
                    queue.store_id,
                )

                return {
                    "success": True,
                    "data": queue.to_dict(),
                    "message": "客户已入座",
                }

            except Exception as e:
                await session.rollback()
                logger.error("标记入座失败", error=str(e), exc_info=e)
                raise

    async def cancel_queue(
        self,
        queue_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        取消排队

        Args:
            queue_id: 排队ID
            reason: 取消原因

        Returns:
            取消结果
        """
        async with get_db_session() as session:
            try:
                result = await session.execute(
                    select(Queue).where(Queue.queue_id == queue_id)
                )
                queue = result.scalar_one_or_none()

                if not queue:
                    return {
                        "success": False,
                        "message": "排队记录不存在",
                    }

                # 更新状态
                queue.status = QueueStatus.CANCELLED
                queue.cancelled_at = datetime.now()
                if reason:
                    queue.notes = f"取消原因: {reason}"

                await session.commit()
                await session.refresh(queue)

                logger.info(
                    "排队已取消",
                    queue_id=queue_id,
                    queue_number=queue.queue_number,
                    reason=reason,
                )

                # 触发Neural System事件
                await self._emit_queue_event(
                    "queue.cancelled",
                    queue.to_dict(),
                    queue.store_id,
                )

                return {
                    "success": True,
                    "data": queue.to_dict(),
                    "message": "排队已取消",
                }

            except Exception as e:
                await session.rollback()
                logger.error("取消排队失败", error=str(e), exc_info=e)
                raise

    async def get_queue_list(
        self,
        store_id: str,
        status: Optional[QueueStatus] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        获取排队列表

        Args:
            store_id: 门店ID
            status: 状态筛选
            limit: 返回数量

        Returns:
            排队列表
        """
        async with get_db_session() as session:
            try:
                query = select(Queue).where(Queue.store_id == store_id)

                if status:
                    query = query.where(Queue.status == status)

                query = query.order_by(Queue.queue_number).limit(limit)

                result = await session.execute(query)
                queues = result.scalars().all()

                return [queue.to_dict() for queue in queues]

            except Exception as e:
                logger.error("获取排队列表失败", error=str(e), exc_info=e)
                raise

    async def get_queue_stats(
        self,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        获取排队统计

        Args:
            store_id: 门店ID

        Returns:
            统计信息
        """
        async with get_db_session() as session:
            try:
                # 当前等待人数
                waiting_result = await session.execute(
                    select(func.count(Queue.queue_id))
                    .where(
                        and_(
                            Queue.store_id == store_id,
                            Queue.status == QueueStatus.WAITING,
                        )
                    )
                )
                waiting_count = waiting_result.scalar() or 0

                # 今天总排队数
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                today_result = await session.execute(
                    select(func.count(Queue.queue_id))
                    .where(
                        and_(
                            Queue.store_id == store_id,
                            Queue.created_at >= today_start,
                        )
                    )
                )
                today_total = today_result.scalar() or 0

                # 平均等待时间
                avg_wait_result = await session.execute(
                    select(func.avg(Queue.actual_wait_time))
                    .where(
                        and_(
                            Queue.store_id == store_id,
                            Queue.created_at >= today_start,
                            Queue.actual_wait_time.isnot(None),
                        )
                    )
                )
                avg_wait_time = avg_wait_result.scalar() or 0

                return {
                    "waiting_count": waiting_count,
                    "today_total": today_total,
                    "avg_wait_time": round(avg_wait_time, 1),
                    "store_id": store_id,
                }

            except Exception as e:
                logger.error("获取排队统计失败", error=str(e), exc_info=e)
                raise

    async def _send_notification(self, queue: Queue):
        """发送通知给客户"""
        try:
            # 使用多渠道通知服务
            from ..services.multi_channel_notification import multi_channel_notification

            # 构建通知消息
            message = f"【智链OS】尊敬的{queue.customer_name}，您的排队号{queue.queue_number}已到，"

            if queue.table_number:
                message += f"请前往{queue.table_number}号桌就座。"
            else:
                message += "请到前台等候安排座位。"

            # 发送短信通知（如果有手机号）
            if queue.customer_phone:
                sms_result = await multi_channel_notification.send_sms(
                    phone_number=queue.customer_phone,
                    message=message,
                    template_params={
                        "customer_name": queue.customer_name,
                        "queue_number": queue.queue_number,
                        "table_number": queue.table_number or "待分配",
                    }
                )

                if sms_result.get("success"):
                    queue.notification_sent = True
                    queue.notification_method = "sms"
                    logger.info(
                        "排队通知发送成功",
                        queue_id=queue.id,
                        phone=queue.customer_phone,
                        method="sms"
                    )

            # 同时发送企业微信通知（如果配置了）
            try:
                from ..services.wechat_trigger_service import wechat_trigger_service

                await wechat_trigger_service.trigger_push(
                    event_type="queue.called",
                    event_data={
                        "queue_number": queue.queue_number,
                        "customer_name": queue.customer_name,
                        "customer_phone": queue.customer_phone,
                        "table_number": queue.table_number or "待分配",
                        "message": message,
                    },
                    store_id=queue.store_id,
                )
                logger.info("企业微信通知已触发", queue_id=queue.id)
            except Exception as wechat_error:
                logger.warning("企业微信通知失败", error=str(wechat_error))

        except Exception as e:
            logger.warning("发送通知失败", error=str(e), queue_id=queue.id)

    async def _emit_queue_event(
        self,
        event_type: str,
        queue_data: Dict[str, Any],
        store_id: str,
    ):
        """触发Neural System事件"""
        try:
            from ..services.neural_system import neural_system

            await neural_system.emit_event(
                event_type=event_type,
                event_source="queue_service",
                data=queue_data,
                store_id=store_id,
            )
        except Exception as e:
            logger.warning("触发Neural System事件失败", error=str(e))


# 全局服务实例
queue_service = QueueService()
