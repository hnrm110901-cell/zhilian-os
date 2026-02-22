"""
多模态优雅降级服务
Multimodal Graceful Fallback Service

核心理念：
- 语音是增强，不是唯一
- 连续2次ASR失败 → 立即降级
- 环境噪音>85dB → 自动切换模式
- 关键指令 → 多通道并发

降级链路：
1. 语音交互（Primary）
2. 智能手表震动（Fallback 1）
3. 前厅POS弹窗（Fallback 2）
4. 后厨KDS大屏红字（Fallback 3）
5. 企微/飞书强推送（Final）
"""

from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel
import asyncio
import logging

logger = logging.getLogger(__name__)


class MessagePriority(str, Enum):
    """消息优先级"""
    CRITICAL = "critical"  # 严重：多通道并发
    HIGH = "high"          # 高：快速降级
    MEDIUM = "medium"      # 中：正常降级
    LOW = "low"            # 低：单通道即可


class DeliveryChannel(str, Enum):
    """投递通道"""
    VOICE = "voice"                    # 语音（骨传导耳机）
    SMARTWATCH = "smartwatch"          # 智能手表震动
    POS_POPUP = "pos_popup"            # POS弹窗
    KDS_SCREEN = "kds_screen"          # 后厨KDS大屏
    ENTERPRISE_IM = "enterprise_im"    # 企微/飞书


class DeliveryStatus(str, Enum):
    """投递状态"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class EnvironmentCondition(BaseModel):
    """环境条件"""
    noise_level_db: float              # 噪音水平（分贝）
    asr_failure_count: int             # ASR连续失败次数
    user_location: str                 # 用户位置（前厅/后厨）
    peak_hour: bool                    # 是否高峰期
    network_quality: str               # 网络质量（good/fair/poor）


class Message(BaseModel):
    """消息"""
    message_id: str
    content: str
    priority: MessagePriority
    category: str                      # 催菜/缺货/预警/通知
    target_user: str
    created_at: datetime
    expires_at: Optional[datetime]


class DeliveryResult(BaseModel):
    """投递结果"""
    message_id: str
    channel: DeliveryChannel
    status: DeliveryStatus
    delivered_at: Optional[datetime]
    response_time_ms: Optional[int]
    error_message: Optional[str]


class MultimodalFallbackService:
    """多模态优雅降级服务"""

    def __init__(self):
        self.asr_failure_threshold = 2      # ASR失败阈值
        self.noise_threshold_db = 85.0      # 噪音阈值
        self.response_timeout_ms = 3000     # 响应超时（毫秒）

    async def deliver_message(
        self,
        message: Message,
        environment: EnvironmentCondition
    ) -> List[DeliveryResult]:
        """
        投递消息（自动选择最佳通道）

        Args:
            message: 消息内容
            environment: 环境条件

        Returns:
            投递结果列表
        """
        # 判断是否需要多通道并发
        if self._requires_multi_channel(message, environment):
            return await self._deliver_multi_channel(message, environment)

        # 单通道降级链路
        return await self._deliver_with_fallback(message, environment)

    def _requires_multi_channel(
        self,
        message: Message,
        environment: EnvironmentCondition
    ) -> bool:
        """判断是否需要多通道并发"""
        # 严重优先级消息
        if message.priority == MessagePriority.CRITICAL:
            return True

        # 高峰期 + 高优先级
        if environment.peak_hour and message.priority == MessagePriority.HIGH:
            return True

        # 关键类别（催菜、缺货）
        if message.category in ["urgent_order", "out_of_stock"]:
            return True

        return False

    async def _deliver_multi_channel(
        self,
        message: Message,
        environment: EnvironmentCondition
    ) -> List[DeliveryResult]:
        """多通道并发投递"""
        logger.info(
            f"Multi-channel delivery for message {message.message_id}"
        )

        # 选择所有可用通道
        channels = self._select_channels_for_multi_delivery(environment)

        # 并发投递
        tasks = [
            self._deliver_to_channel(message, channel, environment)
            for channel in channels
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        delivery_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Channel {channels[i]} delivery failed: {result}")
                delivery_results.append(DeliveryResult(
                    message_id=message.message_id,
                    channel=channels[i],
                    status=DeliveryStatus.FAILED,
                    delivered_at=None,
                    response_time_ms=None,
                    error_message=str(result)
                ))
            else:
                delivery_results.append(result)

        return delivery_results

    async def _deliver_with_fallback(
        self,
        message: Message,
        environment: EnvironmentCondition
    ) -> List[DeliveryResult]:
        """单通道降级链路投递"""
        logger.info(
            f"Fallback delivery for message {message.message_id}"
        )

        # 获取降级链路
        fallback_chain = self._get_fallback_chain(environment)

        results = []

        for channel in fallback_chain:
            # 尝试投递
            result = await self._deliver_to_channel(
                message, channel, environment
            )
            results.append(result)

            # 如果成功，停止降级
            if result.status == DeliveryStatus.SUCCESS:
                logger.info(
                    f"Message {message.message_id} delivered via {channel}"
                )
                break

            # 如果失败，继续下一个通道
            logger.warning(
                f"Channel {channel} failed, falling back to next channel"
            )

        return results

    def _get_fallback_chain(
        self,
        environment: EnvironmentCondition
    ) -> List[DeliveryChannel]:
        """获取降级链路"""
        # 判断是否应该跳过语音
        skip_voice = (
            environment.noise_level_db > self.noise_threshold_db or
            environment.asr_failure_count >= self.asr_failure_threshold
        )

        if skip_voice:
            logger.info(
                f"Skipping voice channel: "
                f"noise={environment.noise_level_db}dB, "
                f"asr_failures={environment.asr_failure_count}"
            )
            # 直接从智能手表开始
            return [
                DeliveryChannel.SMARTWATCH,
                DeliveryChannel.POS_POPUP,
                DeliveryChannel.KDS_SCREEN,
                DeliveryChannel.ENTERPRISE_IM
            ]

        # 正常降级链路（从语音开始）
        if environment.user_location == "kitchen":
            # 后厨：优先KDS大屏
            return [
                DeliveryChannel.VOICE,
                DeliveryChannel.KDS_SCREEN,
                DeliveryChannel.SMARTWATCH,
                DeliveryChannel.ENTERPRISE_IM
            ]
        else:
            # 前厅：优先POS弹窗
            return [
                DeliveryChannel.VOICE,
                DeliveryChannel.SMARTWATCH,
                DeliveryChannel.POS_POPUP,
                DeliveryChannel.ENTERPRISE_IM
            ]

    def _select_channels_for_multi_delivery(
        self,
        environment: EnvironmentCondition
    ) -> List[DeliveryChannel]:
        """选择多通道投递的通道列表"""
        channels = []

        # 根据环境选择合适的通道
        if environment.noise_level_db <= self.noise_threshold_db:
            channels.append(DeliveryChannel.VOICE)

        channels.append(DeliveryChannel.SMARTWATCH)

        if environment.user_location == "kitchen":
            channels.append(DeliveryChannel.KDS_SCREEN)
        else:
            channels.append(DeliveryChannel.POS_POPUP)

        # 严重消息总是包含企微/飞书
        channels.append(DeliveryChannel.ENTERPRISE_IM)

        return channels

    async def _deliver_to_channel(
        self,
        message: Message,
        channel: DeliveryChannel,
        environment: EnvironmentCondition
    ) -> DeliveryResult:
        """投递到指定通道"""
        start_time = datetime.now()

        try:
            if channel == DeliveryChannel.VOICE:
                success = await self._deliver_via_voice(message, environment)
            elif channel == DeliveryChannel.SMARTWATCH:
                success = await self._deliver_via_smartwatch(message)
            elif channel == DeliveryChannel.POS_POPUP:
                success = await self._deliver_via_pos_popup(message)
            elif channel == DeliveryChannel.KDS_SCREEN:
                success = await self._deliver_via_kds_screen(message)
            elif channel == DeliveryChannel.ENTERPRISE_IM:
                success = await self._deliver_via_enterprise_im(message)
            else:
                success = False

            response_time = int(
                (datetime.now() - start_time).total_seconds() * 1000
            )

            return DeliveryResult(
                message_id=message.message_id,
                channel=channel,
                status=DeliveryStatus.SUCCESS if success else DeliveryStatus.FAILED,
                delivered_at=datetime.now() if success else None,
                response_time_ms=response_time,
                error_message=None if success else "Delivery failed"
            )

        except asyncio.TimeoutError:
            return DeliveryResult(
                message_id=message.message_id,
                channel=channel,
                status=DeliveryStatus.TIMEOUT,
                delivered_at=None,
                response_time_ms=self.response_timeout_ms,
                error_message="Delivery timeout"
            )
        except Exception as e:
            logger.error(f"Channel {channel} delivery error: {e}")
            return DeliveryResult(
                message_id=message.message_id,
                channel=channel,
                status=DeliveryStatus.FAILED,
                delivered_at=None,
                response_time_ms=None,
                error_message=str(e)
            )

    async def _deliver_via_voice(
        self,
        message: Message,
        environment: EnvironmentCondition
    ) -> bool:
        """通过语音投递"""
        # 检查环境是否适合语音
        if environment.noise_level_db > self.noise_threshold_db:
            logger.warning("Noise level too high for voice delivery")
            return False

        # 调用语音服务
        try:
            from ..services.voice_service import voice_service
            await asyncio.wait_for(
                voice_service.speak(message.content, message.target_user),
                timeout=self.response_timeout_ms / 1000
            )
            return True
        except Exception as e:
            logger.error(f"Voice delivery failed: {e}")
            return False

    async def _deliver_via_smartwatch(self, message: Message) -> bool:
        """通过智能手表投递（保存到通知队列，由手表端轮询）"""
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification, NotificationType, NotificationPriority
            async with get_db_session() as session:
                notif = Notification(
                    title="手表通知",
                    message=message.content,
                    type=NotificationType.INFO,
                    priority=NotificationPriority.HIGH,
                    extra_data={"channel": "smartwatch", "target_user": message.target_user},
                )
                session.add(notif)
                await session.commit()
            logger.info(f"Smartwatch delivery queued: {message.content}")
            return True
        except Exception as e:
            logger.error(f"Smartwatch delivery failed: {e}")
            return False

    async def _deliver_via_pos_popup(self, message: Message) -> bool:
        """通过POS弹窗投递（保存到通知队列，由POS端轮询）"""
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification, NotificationType, NotificationPriority
            async with get_db_session() as session:
                notif = Notification(
                    title="POS弹窗通知",
                    message=message.content,
                    type=NotificationType.ALERT,
                    priority=NotificationPriority.URGENT,
                    extra_data={"channel": "pos_popup", "target_user": message.target_user},
                )
                session.add(notif)
                await session.commit()
            logger.info(f"POS popup delivery queued: {message.content}")
            return True
        except Exception as e:
            logger.error(f"POS popup delivery failed: {e}")
            return False

    async def _deliver_via_kds_screen(self, message: Message) -> bool:
        """通过KDS大屏投递（保存到通知队列，由KDS端轮询）"""
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification, NotificationType, NotificationPriority
            async with get_db_session() as session:
                notif = Notification(
                    title="KDS大屏通知",
                    message=message.content,
                    type=NotificationType.INFO,
                    priority=NotificationPriority.HIGH,
                    extra_data={"channel": "kds_screen", "target_user": message.target_user},
                )
                session.add(notif)
                await session.commit()
            logger.info(f"KDS screen delivery queued: {message.content}")
            return True
        except Exception as e:
            logger.error(f"KDS screen delivery failed: {e}")
            return False

    async def _deliver_via_enterprise_im(self, message: Message) -> bool:
        """通过企微/飞书投递"""
        try:
            from ..services.enterprise_service import enterprise_service
            await asyncio.wait_for(
                enterprise_service.send_message(
                    message.target_user,
                    message.content
                ),
                timeout=self.response_timeout_ms / 1000
            )
            return True
        except Exception as e:
            logger.error(f"Enterprise IM delivery failed: {e}")
            return False

    async def monitor_environment(
        self,
        user_id: str
    ) -> EnvironmentCondition:
        """
        监控环境条件

        Args:
            user_id: 用户ID

        Returns:
            环境条件
        """
        # 从业务系统判断是否高峰期（11-14点 或 17-21点）
        # ASR失败次数从 Notification 表查询最近记录
        current_hour = datetime.now().hour
        peak_hour = (11 <= current_hour <= 14) or (17 <= current_hour <= 21)

        asr_failure_count = 0
        try:
            from src.core.database import get_db_session
            from src.models.notification import Notification
            from sqlalchemy import select, func
            from datetime import timedelta

            cutoff = datetime.now() - timedelta(minutes=30)
            async with get_db_session() as session:
                result = await session.execute(
                    select(func.count(Notification.id)).where(
                        Notification.created_at >= cutoff,
                        Notification.extra_data["channel"].astext == "asr_failure",
                    )
                )
                asr_failure_count = result.scalar() or 0
        except Exception:
            pass

        return EnvironmentCondition(
            noise_level_db=75.0 if peak_hour else 55.0,
            asr_failure_count=asr_failure_count,
            user_location="front",
            peak_hour=peak_hour,
            network_quality="good"
        )

    def get_delivery_statistics(
        self,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """获取投递统计（从 Notification 表聚合）"""
        import asyncio
        from datetime import timedelta

        async def _query():
            from src.core.database import get_db_session
            from src.models.notification import Notification
            from sqlalchemy import select, func

            cutoff = datetime.now() - timedelta(hours=time_range_hours)
            async with get_db_session() as session:
                total_result = await session.execute(
                    select(func.count(Notification.id)).where(Notification.created_at >= cutoff)
                )
                total = total_result.scalar() or 0

                by_type_result = await session.execute(
                    select(Notification.type, func.count(Notification.id).label("cnt"))
                    .where(Notification.created_at >= cutoff)
                    .group_by(Notification.type)
                )
                by_priority_result = await session.execute(
                    select(Notification.priority, func.count(Notification.id).label("cnt"))
                    .where(Notification.created_at >= cutoff)
                    .group_by(Notification.priority)
                )
                read_result = await session.execute(
                    select(func.count(Notification.id)).where(
                        Notification.created_at >= cutoff,
                        Notification.is_read == True,
                    )
                )
                read_count = read_result.scalar() or 0

            return {
                "total_messages": total,
                "by_channel": {row.type: row.cnt for row in by_type_result.all()},
                "by_priority": {row.priority: row.cnt for row in by_priority_result.all()},
                "success_rate": round(read_count / total, 2) if total > 0 else 0.0,
                "average_response_time_ms": 0,
            }

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.ensure_future(_query())
                return {"total_messages": 0, "by_channel": {}, "by_priority": {}, "success_rate": 0.0, "average_response_time_ms": 0}
            return loop.run_until_complete(_query())
        except Exception as e:
            logger.warning(f"获取投递统计失败: {e}")
            return {"total_messages": 0, "by_channel": {}, "by_priority": {}, "success_rate": 0.0, "average_response_time_ms": 0}


# 全局实例
multimodal_fallback = MultimodalFallbackService()
