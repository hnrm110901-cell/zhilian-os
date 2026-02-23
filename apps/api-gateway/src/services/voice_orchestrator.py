"""
语音交互编排服务
Voice Interaction Orchestrator

整合Shokz设备、语音服务和Agent系统，提供完整的语音交互流程
"""
import os
from typing import Dict, Any, Optional
import structlog

from .shokz_service import shokz_service, DeviceRole
from .voice_service import voice_service, voice_command_router
from .agent_service import AgentService
from .message_router import message_router

logger = structlog.get_logger()


class VoiceInteractionOrchestrator:
    """语音交互编排器"""

    def __init__(self):
        """初始化语音交互编排器"""
        self.agent_service = AgentService()
        logger.info("VoiceInteractionOrchestrator初始化完成")

    async def process_voice_command(
        self,
        device_id: str,
        audio_data: bytes,
        sample_rate: int = 16000,
    ) -> Dict[str, Any]:
        """
        处理语音命令（完整流程）

        Args:
            device_id: Shokz设备ID
            audio_data: 音频数据
            sample_rate: 采样率

        Returns:
            处理结果
        """
        try:
            # 1. 获取设备信息
            device_info = shokz_service.get_device_info(device_id)
            if not device_info:
                return {
                    "success": False,
                    "error": "设备不存在",
                }

            role = device_info["role"]
            user_id = device_info["user_id"]

            logger.info(
                "开始处理语音命令",
                device_id=device_id,
                role=role,
                user_id=user_id,
            )

            # 2. 语音识别（STT）
            stt_result = await voice_service.speech_to_text(
                audio_data=audio_data,
                language="zh-CN",
                sample_rate=sample_rate,
            )

            if not stt_result["success"]:
                return {
                    "success": False,
                    "error": "语音识别失败",
                    "details": stt_result,
                }

            text = stt_result["text"]
            logger.info("语音识别成功", text=text)

            # 3. 命令路由
            route_result = voice_command_router.route_command(
                text=text,
                role=role,
                user_id=user_id,
            )

            agent_type = route_result["agent_type"]
            action = route_result["action"]
            params = route_result["params"]

            if not agent_type:
                # 无法识别命令，返回帮助信息
                response_text = self._get_help_message(role)
            else:
                # 4. 调用Agent执行
                logger.info(
                    "调用Agent",
                    agent_type=agent_type,
                    action=action,
                )

                agent_result = await self.agent_service.execute_agent(
                    agent_type,
                    {
                        "action": action,
                        "params": params,
                    }
                )

                # 5. 格式化响应
                response_text = message_router.format_agent_response(
                    agent_type, action, agent_result
                )

                # 简化语音响应（去除emoji和格式化）
                response_text = self._simplify_for_voice(response_text)

            # 6. 语音合成（TTS）
            tts_result = await voice_service.text_to_speech(
                text=response_text,
                language="zh-CN",
                voice="female",
                speed=1.0,
            )

            if not tts_result["success"]:
                return {
                    "success": False,
                    "error": "语音合成失败",
                    "details": tts_result,
                }

            # 7. 发送音频到设备
            send_result = await shokz_service.send_audio(
                device_id=device_id,
                audio_data=tts_result["audio_data"],
                format="pcm",
            )

            if not send_result["success"]:
                return {
                    "success": False,
                    "error": "音频发送失败",
                    "details": send_result,
                }

            logger.info("语音命令处理完成", device_id=device_id)

            return {
                "success": True,
                "device_id": device_id,
                "recognized_text": text,
                "agent_type": agent_type,
                "action": action,
                "response_text": response_text,
            }

        except Exception as e:
            logger.error("语音命令处理失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def start_voice_session(
        self,
        device_id: str,
        duration_seconds: int = 5,
    ) -> Dict[str, Any]:
        """
        启动语音会话（录音 → 识别 → 处理 → 响应）

        Args:
            device_id: Shokz设备ID
            duration_seconds: 录音时长

        Returns:
            会话结果
        """
        try:
            # 1. 从设备接收音频
            receive_result = await shokz_service.receive_audio(
                device_id=device_id,
                duration_seconds=duration_seconds,
            )

            if not receive_result["success"]:
                return {
                    "success": False,
                    "error": "音频接收失败",
                    "details": receive_result,
                }

            # 2. 处理语音命令
            result = await self.process_voice_command(
                device_id=device_id,
                audio_data=receive_result["audio_data"],
                sample_rate=receive_result["sample_rate"],
            )

            return result

        except Exception as e:
            logger.error("语音会话失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def send_voice_notification(
        self,
        device_id: str,
        message: str,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """
        发送语音通知

        Args:
            device_id: Shokz设备ID
            message: 通知消息
            priority: 优先级（normal/high/urgent）

        Returns:
            发送结果
        """
        try:
            # 根据优先级调整语速
            speed = float(os.getenv("VOICE_SPEED_NORMAL", "1.0"))
            if priority == "high":
                speed = float(os.getenv("VOICE_SPEED_HIGH", "1.2"))
            elif priority == "urgent":
                speed = float(os.getenv("VOICE_SPEED_URGENT", "1.5"))

            # 语音合成
            tts_result = await voice_service.text_to_speech(
                text=message,
                language="zh-CN",
                voice="female",
                speed=speed,
            )

            if not tts_result["success"]:
                return {
                    "success": False,
                    "error": "语音合成失败",
                }

            # 发送音频
            send_result = await shokz_service.send_audio(
                device_id=device_id,
                audio_data=tts_result["audio_data"],
                format="pcm",
            )

            return send_result

        except Exception as e:
            logger.error("语音通知发送失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    def _simplify_for_voice(self, text: str) -> str:
        """
        简化文本用于语音播报

        Args:
            text: 原始文本

        Returns:
            简化后的文本
        """
        # 移除emoji
        import re
        text = re.sub(r'[^\w\s\u4e00-\u9fff，。！？、：；""''（）【】]', '', text)

        # 移除多余的换行和空格
        text = ' '.join(text.split())

        # 限制长度（语音播报不宜过长）
        _max_len = int(os.getenv("VOICE_MAX_TEXT_LENGTH", "200"))
        if len(text) > _max_len:
            text = text[:_max_len] + "..."

        return text

    def _get_help_message(self, role: str) -> str:
        """
        获取帮助信息

        Args:
            role: 用户角色

        Returns:
            帮助信息
        """
        if role == "kitchen":
            return "您好，我是后厨助手。您可以说：查询订单、查询库存、完成菜品、申请补货等。"
        elif role == "front_of_house":
            return "您好，我是前厅助手。您可以说：查询订单、创建预定、查询座位、会员查询等。"
        elif role == "cashier":
            return "您好，我是收银助手。您可以说：查询订单、结账买单、会员查询、优惠查询等。"
        else:
            return "您好，我是智链OS语音助手。请告诉我您需要什么帮助。"


# 创建全局实例
voice_orchestrator = VoiceInteractionOrchestrator()
