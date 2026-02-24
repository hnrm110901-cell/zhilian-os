"""
美团等位集成辅助服务
Meituan Queue Integration Helper

在本地排队操作时自动同步到美团系统
"""
from typing import Dict, Any, Optional
import time
from datetime import datetime
import structlog

from .meituan_queue_service import meituan_queue_service
from ..models.queue import Queue, QueueStatus

logger = structlog.get_logger()


class MeituanQueueIntegration:
    """美团等位集成辅助"""

    async def sync_queue_to_meituan(
        self,
        queue: Queue,
        app_auth_token: str,
        table_type_id: int,
    ) -> Optional[str]:
        """
        同步排队订单到美团

        Args:
            queue: 排队记录
            app_auth_token: 美团授权token
            table_type_id: 美团桌型ID

        Returns:
            美团订单ID (orderViewId)
        """
        try:
            # 构建订单数据
            order_data = {
                "peopleCount": queue.party_size,
                "orderId": queue.queue_id,
                "num": queue.queue_number,
                "index": await self._calculate_queue_index(queue),
                "tableTypeId": table_type_id,
                "takeNumTime": int(queue.created_at.timestamp() * 1000),
            }

            # 添加可选字段
            if queue.customer_phone:
                order_data["mobile"] = queue.customer_phone

            if queue.special_requests:
                order_data["remark"] = queue.special_requests

            # 同步到美团
            result = await meituan_queue_service.sync_offline_order(
                app_auth_token=app_auth_token,
                order_data=order_data,
            )

            if result.get("code") == "OP_SUCCESS":
                order_view_id = result.get("data", {}).get("orderViewId")
                logger.info(
                    "排队订单已同步到美团",
                    queue_id=queue.queue_id,
                    order_view_id=order_view_id,
                )
                return order_view_id
            else:
                logger.error(
                    "同步排队订单到美团失败",
                    queue_id=queue.queue_id,
                    error=result.get("msg"),
                )
                return None

        except Exception as e:
            logger.error(
                "同步排队订单到美团异常",
                queue_id=queue.queue_id,
                error=str(e),
                exc_info=e,
            )
            return None

    async def update_queue_status_to_meituan(
        self,
        queue: Queue,
        app_auth_token: str,
        order_view_id: str,
    ) -> bool:
        """
        更新排队状态到美团

        Args:
            queue: 排队记录
            app_auth_token: 美团授权token
            order_view_id: 美团订单ID

        Returns:
            是否成功
        """
        try:
            # 映射状态
            meituan_status = meituan_queue_service.map_local_status_to_meituan(
                queue.status.value
            )

            # 计算队列位置
            index = await self._calculate_queue_index(queue)

            # 更新到美团
            result = await meituan_queue_service.update_order_status(
                app_auth_token=app_auth_token,
                order_view_id=order_view_id,
                order_id=queue.queue_id,
                status=meituan_status,
                index=index,
            )

            if result.get("code") == "OP_SUCCESS":
                logger.info(
                    "排队状态已更新到美团",
                    queue_id=queue.queue_id,
                    status=queue.status.value,
                    meituan_status=meituan_status,
                )
                return True
            else:
                logger.error(
                    "更新排队状态到美团失败",
                    queue_id=queue.queue_id,
                    error=result.get("msg"),
                )
                return False

        except Exception as e:
            logger.error(
                "更新排队状态到美团异常",
                queue_id=queue.queue_id,
                error=str(e),
                exc_info=e,
            )
            return False

    async def _calculate_queue_index(self, queue: Queue) -> int:
        """
        计算队列位置

        Args:
            queue: 排队记录

        Returns:
            队列位置（从1开始）
        """
        from ..core.database import get_db_session
        from sqlalchemy import select, and_, func

        async with get_db_session() as session:
            # 计算前面有多少个等待的订单
            result = await session.execute(
                select(func.count(Queue.queue_id))
                .where(
                    and_(
                        Queue.store_id == queue.store_id,
                        Queue.status == QueueStatus.WAITING,
                        Queue.queue_number < queue.queue_number,
                    )
                )
            )
            count = result.scalar() or 0

            # 位置从1开始，所以加1
            return count + 1

    async def handle_meituan_online_queue(
        self,
        order_view_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        table_type_id: int,
        store_id: str,
        app_auth_token: str,
    ) -> Dict[str, Any]:
        """
        处理美团线上取号

        当用户通过美团/大众点评App取号时，需要在本地创建排队记录并回调美团

        Args:
            order_view_id: 美团订单ID
            customer_name: 客户姓名
            customer_phone: 客户电话
            party_size: 就餐人数
            table_type_id: 美团桌型ID
            store_id: 门店ID
            app_auth_token: 美团授权token

        Returns:
            处理结果
        """
        try:
            from .queue_service import queue_service

            # 在本地创建排队记录
            result = await queue_service.add_to_queue(
                store_id=store_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                party_size=party_size,
            )

            if result["success"]:
                queue_data = result["data"]

                # 回调美团取号成功
                callback_result = await meituan_queue_service.callback_queue_number_result(
                    app_auth_token=app_auth_token,
                    order_view_id=order_view_id,
                    success=True,
                    order_data={
                        "tableTypeId": table_type_id,
                        "orderId": queue_data["queue_id"],
                        "index": await self._calculate_queue_index_by_id(queue_data["queue_id"]),
                        "num": queue_data["queue_number"],
                        "takeNumTime": int(queue_data["created_at"].timestamp() * 1000) if isinstance(queue_data["created_at"], datetime) else int(time.time() * 1000),
                    },
                )

                logger.info(
                    "美团线上取号处理成功",
                    order_view_id=order_view_id,
                    queue_id=queue_data["queue_id"],
                )

                return {
                    "success": True,
                    "queue_data": queue_data,
                    "callback_result": callback_result,
                }
            else:
                # 回调美团取号失败
                await meituan_queue_service.callback_queue_number_result(
                    app_auth_token=app_auth_token,
                    order_view_id=order_view_id,
                    success=False,
                    error_msg="本地排队系统繁忙，请稍后再试",
                )

                return {
                    "success": False,
                    "error": "创建本地排队记录失败",
                }

        except Exception as e:
            logger.error(
                "处理美团线上取号异常",
                order_view_id=order_view_id,
                error=str(e),
                exc_info=e,
            )

            # 回调美团取号失败
            try:
                await meituan_queue_service.callback_queue_number_result(
                    app_auth_token=app_auth_token,
                    order_view_id=order_view_id,
                    success=False,
                    error_msg="系统异常，请稍后再试",
                )
            except Exception as e:
                logger.warning("meituan_callback_failed", error=str(e))

    async def _calculate_queue_index_by_id(self, queue_id: str) -> int:
        """根据queue_id计算队列位置"""
        from ..core.database import get_db_session
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(
                select(Queue).where(Queue.queue_id == queue_id)
            )
            queue = result.scalar_one_or_none()

            if queue:
                return await self._calculate_queue_index(queue)

            return 1


# 全局服务实例
meituan_queue_integration = MeituanQueueIntegration()
