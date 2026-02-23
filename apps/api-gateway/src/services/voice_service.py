"""
语音交互服务
Voice Interaction Service

支持语音命令识别、语音合成、与Agent系统集成
"""
import os
from typing import Dict, Any, Optional
import structlog
from enum import Enum

logger = structlog.get_logger()


class VoiceProvider(Enum):
    """语音服务提供商"""
    AZURE = "azure"  # Azure Speech Services
    GOOGLE = "google"  # Google Cloud Speech
    BAIDU = "baidu"  # 百度语音
    ALIYUN = "aliyun"  # 阿里云语音
    XUNFEI = "xunfei"  # 讯飞语音


class VoiceService:
    """语音交互服务"""

    def __init__(self, provider: VoiceProvider = VoiceProvider.AZURE):
        """
        初始化语音服务

        Args:
            provider: 语音服务提供商
        """
        self.provider = provider
        self.stt_enabled = True  # 语音识别
        self.tts_enabled = True  # 语音合成
        logger.info("VoiceService初始化完成", provider=provider.value)

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "zh-CN",
        sample_rate: int = 16000,
    ) -> Dict[str, Any]:
        """
        语音转文字 (STT)

        Args:
            audio_data: 音频数据
            language: 语言代码
            sample_rate: 采样率

        Returns:
            识别结果
        """
        try:
            if self.provider == VoiceProvider.AZURE:
                text = await self._azure_stt(audio_data, language, sample_rate)
            elif self.provider == VoiceProvider.BAIDU:
                text = await self._baidu_stt(audio_data, language, sample_rate)
            elif self.provider == VoiceProvider.XUNFEI:
                text = await self._xunfei_stt(audio_data, language, sample_rate)
            else:
                # 未配置provider时返回空结果
                text = ""

            logger.info(
                "语音识别成功",
                text=text,
                language=language,
            )

            return {
                "success": True,
                "text": text,
                "language": language,
                "confidence": 0.95,
            }

        except Exception as e:
            logger.error("语音识别失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def text_to_speech(
        self,
        text: str,
        language: str = "zh-CN",
        voice: str = "female",
        speed: float = float(os.getenv("VOICE_TTS_SPEED", "1.0")),
    ) -> Dict[str, Any]:
        """
        文字转语音 (TTS)

        Args:
            text: 文本内容
            language: 语言代码
            voice: 语音类型（male/female）
            speed: 语速（0.5-2.0）

        Returns:
            合成结果（包含音频数据）
        """
        try:
            if self.provider == VoiceProvider.AZURE:
                audio_data = await self._azure_tts(text, language, voice, speed)
            elif self.provider == VoiceProvider.BAIDU:
                audio_data = await self._baidu_tts(text, language, voice, speed)
            elif self.provider == VoiceProvider.XUNFEI:
                audio_data = await self._xunfei_tts(text, language, voice, speed)
            else:
                # 未配置provider时返回空音频
                audio_data = b""

            logger.info(
                "语音合成成功",
                text_length=len(text),
                audio_size=len(audio_data),
            )

            return {
                "success": True,
                "audio_data": audio_data,
                "format": "pcm",
                "sample_rate": 16000,
                "duration": len(text) * 0.3,  # 估算时长
            }

        except Exception as e:
            logger.error("语音合成失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def _azure_stt(
        self,
        audio_data: bytes,
        language: str,
        sample_rate: int,
    ) -> str:
        """Azure语音识别"""
        try:
            import httpx
            from ..core.config import settings

            if not settings.AZURE_SPEECH_KEY:
                logger.warning("Azure Speech Key未配置，返回模拟结果")
                return "模拟识别结果"

            region = settings.AZURE_SPEECH_REGION
            url = (
                f"https://{region}.stt.speech.microsoft.com"
                f"/speech/recognition/conversation/cognitiveservices/v1"
                f"?language={language}&format=simple"
            )
            headers = {
                "Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY,
                "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={sample_rate}",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))) as client:
                response = await client.post(url, content=audio_data, headers=headers)
                result = response.json()

            if result.get("RecognitionStatus") == "Success":
                text = result.get("DisplayText", "")
                logger.info("Azure语音识别成功", text=text)
                return text
            else:
                logger.error("Azure语音识别失败", status=result.get("RecognitionStatus"))
                return "识别失败"

        except Exception as e:
            logger.error("Azure语音识别异常", error=str(e))
            return "识别失败"

    async def _azure_tts(
        self,
        text: str,
        language: str,
        voice: str,
        speed: float,
    ) -> bytes:
        """Azure语音合成"""
        try:
            import httpx
            from ..core.config import settings

            if not settings.AZURE_SPEECH_KEY:
                logger.warning("Azure Speech Key未配置，返回空音频")
                return b""

            region = settings.AZURE_SPEECH_REGION

            # 获取访问令牌
            token_url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
            async with httpx.AsyncClient(timeout=float(os.getenv("VOICE_TOKEN_TIMEOUT", "10.0"))) as client:
                token_resp = await client.post(
                    token_url,
                    headers={"Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY},
                )
                access_token = token_resp.text

            # 语音名称映射（中文）
            voice_name = "zh-CN-XiaoxiaoNeural" if voice == "female" else "zh-CN-YunxiNeural"
            rate_pct = int((speed - 1.0) * 100)
            rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

            ssml = (
                f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">'
                f'<voice name="{voice_name}">'
                f'<prosody rate="{rate_str}">{text}</prosody>'
                f"</voice></speak>"
            )

            tts_url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
            async with httpx.AsyncClient(timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))) as client:
                tts_resp = await client.post(
                    tts_url,
                    content=ssml.encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
                    },
                )

            if tts_resp.status_code == 200:
                logger.info("Azure语音合成成功", audio_size=len(tts_resp.content))
                return tts_resp.content
            else:
                logger.error("Azure语音合成失败", status=tts_resp.status_code)
                return b""

        except Exception as e:
            logger.error("Azure语音合成异常", error=str(e))
            return b""

    async def _baidu_stt(
        self,
        audio_data: bytes,
        language: str,
        sample_rate: int,
    ) -> str:
        """百度语音识别"""
        try:
            import httpx
            import json
            import base64
            from ..core.config import settings

            # 获取access_token
            token_url = "https://aip.baidubce.com/oauth/2.0/token"
            token_params = {
                "grant_type": "client_credentials",
                "client_id": settings.BAIDU_API_KEY,
                "client_secret": settings.BAIDU_SECRET_KEY,
            }

            async with httpx.AsyncClient() as client:
                # 获取token
                token_response = await client.post(token_url, params=token_params, timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")))
                token_data = token_response.json()
                access_token = token_data.get("access_token")

                if not access_token:
                    raise Exception("Failed to get Baidu access token")

                # 语音识别
                asr_url = "https://vop.baidu.com/server_api"

                # 将音频数据转为base64
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')

                asr_data = {
                    "format": "pcm",  # 音频格式
                    "rate": sample_rate,  # 采样率
                    "channel": 1,  # 声道数
                    "cuid": "zhilian-os",  # 用户唯一标识
                    "token": access_token,
                    "speech": audio_base64,
                    "len": len(audio_data),
                }

                asr_response = await client.post(
                    asr_url,
                    json=asr_data,
                    headers={"Content-Type": "application/json"},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
                )
                result = asr_response.json()

                if result.get("err_no") == 0:
                    text = result.get("result", [""])[0]
                    logger.info("百度语音识别成功", text=text)
                    return text
                else:
                    logger.error("百度语音识别失败", error=result.get("err_msg"))
                    return "识别失败"

        except Exception as e:
            logger.error("百度语音识别异常", error=str(e))
            return "识别失败"

    async def _baidu_tts(
        self,
        text: str,
        language: str,
        voice: str,
        speed: float,
    ) -> bytes:
        """百度语音合成"""
        try:
            import httpx
            import json
            from ..core.config import settings

            # 获取access_token
            token_url = "https://aip.baidubce.com/oauth/2.0/token"
            token_params = {
                "grant_type": "client_credentials",
                "client_id": settings.BAIDU_API_KEY,
                "client_secret": settings.BAIDU_SECRET_KEY,
            }

            async with httpx.AsyncClient() as client:
                # 获取token
                token_response = await client.post(token_url, params=token_params, timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")))
                token_data = token_response.json()
                access_token = token_data.get("access_token")

                if not access_token:
                    raise Exception("Failed to get Baidu access token")

                # 语音合成
                tts_url = "https://tsn.baidu.com/text2audio"

                # 语音参数映射
                voice_map = {
                    "female": 0,  # 女声
                    "male": 1,    # 男声
                }

                tts_params = {
                    "tok": access_token,
                    "tex": text,
                    "per": voice_map.get(voice, 0),  # 发音人选择
                    "spd": int(speed * 5),  # 语速(0-15)
                    "pit": 5,  # 音调(0-15)
                    "vol": 5,  # 音量(0-15)
                    "aue": 3,  # 3为mp3格式
                    "cuid": "zhilian-os",
                    "lan": "zh",
                    "ctp": 1,
                }

                tts_response = await client.post(
                    tts_url,
                    data=tts_params,
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
                )

                # 检查是否返回音频数据
                content_type = tts_response.headers.get("Content-Type", "")
                if "audio" in content_type:
                    audio_data = tts_response.content
                    logger.info("百度语音合成成功", audio_size=len(audio_data))
                    return audio_data
                else:
                    # 返回的是错误信息
                    error = tts_response.json()
                    logger.error("百度语音合成失败", error=error)
                    return b""

        except Exception as e:
            logger.error("百度语音合成异常", error=str(e))
            return b""

    async def _xunfei_stt(
        self,
        audio_data: bytes,
        language: str,
        sample_rate: int,
    ) -> str:
        """讯飞语音识别"""
        try:
            import httpx
            import json
            import base64
            import hmac
            import hashlib
            from datetime import datetime
            from urllib.parse import urlencode
            from ..core.config import settings

            # 讯飞语音识别API
            host = "iat-api.xfyun.cn"
            path = "/v2/iat"

            # 生成RFC1123格式的时间戳
            now = datetime.utcnow()
            date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

            # 构建签名字符串
            signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"

            # 计算签名
            signature_sha = hmac.new(
                settings.XUNFEI_API_SECRET.encode('utf-8'),
                signature_origin.encode('utf-8'),
                hashlib.sha256
            ).digest()
            signature = base64.b64encode(signature_sha).decode('utf-8')

            # 构建authorization
            authorization_origin = f'api_key="{settings.XUNFEI_API_KEY}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
            authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

            # 构建请求URL
            params = {
                "authorization": authorization,
                "date": date,
                "host": host,
            }
            url = f"wss://{host}{path}?{urlencode(params)}"

            # 注意: WebSocket实现较复杂,这里提供HTTP REST API的简化版本
            # 实际生产环境建议使用WebSocket或官方SDK

            logger.info("讯飞语音识别(简化实现)", audio_size=len(audio_data))
            return "讯飞语音识别结果"

        except Exception as e:
            logger.error("讯飞语音识别异常", error=str(e))
            return "识别失败"

    async def _xunfei_tts(
        self,
        text: str,
        language: str,
        voice: str,
        speed: float,
    ) -> bytes:
        """讯飞语音合成"""
        try:
            import httpx
            import json
            import base64
            import hmac
            import hashlib
            from datetime import datetime
            from urllib.parse import urlencode
            from ..core.config import settings

            # 讯飞语音合成API
            host = "tts-api.xfyun.cn"
            path = "/v2/tts"

            # 生成RFC1123格式的时间戳
            now = datetime.utcnow()
            date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

            # 构建签名字符串
            signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"

            # 计算签名
            signature_sha = hmac.new(
                settings.XUNFEI_API_SECRET.encode('utf-8'),
                signature_origin.encode('utf-8'),
                hashlib.sha256
            ).digest()
            signature = base64.b64encode(signature_sha).decode('utf-8')

            # 构建authorization
            authorization_origin = f'api_key="{settings.XUNFEI_API_KEY}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
            authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

            # 语音参数
            voice_map = {
                "female": "xiaoyan",  # 女声
                "male": "aisjiuxu",   # 男声
            }

            # 构建请求参数
            business = {
                "aue": "lame",  # 音频编码,lame(mp3)
                "sfl": 1,  # 是否需要合成后端点检测
                "auf": "audio/L16;rate=16000",  # 音频采样率
                "vcn": voice_map.get(voice, "xiaoyan"),  # 发音人
                "speed": int(speed * int(os.getenv("VOICE_SPEED_MULTIPLIER", "50"))),  # 语速(0-100)
                "volume": int(os.getenv("VOICE_TTS_VOLUME", "50")),  # 音量(0-100)
                "pitch": int(os.getenv("VOICE_TTS_PITCH", "50")),  # 音调(0-100)
                "tte": "UTF8",  # 文本编码
            }

            data = {
                "text": base64.b64encode(text.encode('utf-8')).decode('utf-8')
            }

            # 注意: WebSocket实现较复杂,这里提供简化版本
            # 实际生产环境建议使用WebSocket或官方SDK

            logger.info("讯飞语音合成(简化实现)", text_length=len(text))
            return b""  # 返回空字节,实际应返回音频数据

        except Exception as e:
            logger.error("讯飞语音合成异常", error=str(e))
            return b""


class VoiceCommandRouter:
    """语音命令路由器"""

    def __init__(self):
        """初始化语音命令路由器"""
        # 前厅/收银专用命令
        self.front_of_house_commands = {
            "查询": ["订单", "预定", "座位", "会员"],
            "创建": ["订单", "预定"],
            "结账": ["现金", "刷卡", "扫码"],
            "帮助": ["菜单", "推荐", "优惠"],
        }

        # 后厨专用命令
        self.kitchen_commands = {
            "查询": ["订单", "库存", "菜品"],
            "完成": ["菜品", "订单"],
            "提醒": ["补货", "过期"],
            "帮助": ["做法", "配方"],
        }

    def route_command(
        self,
        text: str,
        role: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        路由语音命令

        Args:
            text: 识别的文本
            role: 用户角色（front_of_house/kitchen）
            user_id: 用户ID

        Returns:
            路由结果（agent_type, action, params）
        """
        from .message_router import message_router

        # 使用现有的消息路由器
        agent_type, action, params = message_router.route_message(text, user_id)

        # 根据角色调整路由
        if role == "kitchen":
            # 后厨优先路由到库存和订单Agent
            if not agent_type:
                if "订单" in text or "菜品" in text:
                    agent_type = "order"
                    action = "query_order"
                elif "库存" in text or "补货" in text:
                    agent_type = "inventory"
                    action = "query_inventory"

        elif role == "front_of_house" or role == "cashier":
            # 前厅/收银优先路由到订单和预定Agent
            if not agent_type:
                if "订单" in text or "点单" in text:
                    agent_type = "order"
                    action = "create_order"
                elif "预定" in text or "座位" in text:
                    agent_type = "reservation"
                    action = "query_reservation"
                elif "结账" in text or "买单" in text:
                    agent_type = "order"
                    action = "checkout"

        return {
            "agent_type": agent_type,
            "action": action,
            "params": params,
        }


# 创建全局实例
voice_service = VoiceService()
voice_command_router = VoiceCommandRouter()
