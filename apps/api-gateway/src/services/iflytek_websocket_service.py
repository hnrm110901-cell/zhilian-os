"""
讯飞 WebSocket 服务
实现讯飞 IAT (语音识别) 和 TTS (语音合成) 的 WebSocket 协议

讯飞 WebSocket 鉴权: HMAC-SHA256 签名 + Base64 拼接到 URL query string
IAT: wss://iat-api.xfyun.cn/v2/iat
TTS: wss://tts-api.xfyun.cn/v2/tts
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from email.utils import formatdate
from typing import Optional
from urllib.parse import urlencode

import structlog
import websockets

logger = structlog.get_logger()

# iFlytek API endpoints
IAT_HOST = "iat-api.xfyun.cn"
IAT_PATH = "/v2/iat"
TTS_HOST = "tts-api.xfyun.cn"
TTS_PATH = "/v2/tts"

# Audio frame config for IAT streaming
FRAME_SIZE = 1280          # bytes per frame (40ms @ 16kHz 16-bit mono)
FRAME_INTERVAL = 0.04      # seconds between frames


def _build_auth_url(host: str, path: str, api_key: str, api_secret: str) -> str:
    """构建讯飞 WebSocket 鉴权 URL"""
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    params = {"authorization": authorization, "date": date, "host": host}
    return f"wss://{host}{path}?{urlencode(params)}"


class IflytekWebSocketService:
    """讯飞 WebSocket STT/TTS 服务"""

    def __init__(self):
        self.app_id = os.getenv("XUNFEI_APP_ID", "")
        self.api_key = os.getenv("XUNFEI_API_KEY", "")
        self.api_secret = os.getenv("XUNFEI_API_SECRET", "")

    def _is_configured(self) -> bool:
        return bool(self.app_id and self.api_key and self.api_secret)

    # ------------------------------------------------------------------
    # STT — IAT (Interactive ASR Transcription)
    # ------------------------------------------------------------------

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: str = "zh_cn",
        sample_rate: int = 16000,
    ) -> str:
        """
        将 PCM 音频通过讯飞 IAT WebSocket 转为文字

        Args:
            audio_data: 原始 PCM 音频 (16-bit mono)
            language: 语言代码 (zh_cn / en_us)
            sample_rate: 采样率 (16000 / 8000)

        Returns:
            识别文本，失败时返回空字符串
        """
        if not self._is_configured():
            logger.warning("讯飞未配置，返回空识别结果")
            return ""

        url = _build_auth_url(IAT_HOST, IAT_PATH, self.api_key, self.api_secret)
        result_text = ""

        try:
            async with websockets.connect(url, ping_interval=None) as ws:
                # 发送第一帧（含业务参数）
                first_frame = {
                    "common": {"app_id": self.app_id},
                    "business": {
                        "language": language,
                        "domain": "iat",
                        "accent": "mandarin",
                        "vad_eos": 3000,
                        "dwa": "wpgs",  # 动态修正
                    },
                    "data": {
                        "status": 0,  # 0=first frame
                        "format": f"audio/L16;rate={sample_rate}",
                        "encoding": "raw",
                        "audio": base64.b64encode(audio_data[:FRAME_SIZE]).decode("utf-8"),
                    },
                }
                await ws.send(json.dumps(first_frame))

                # 流式发送剩余帧
                offset = FRAME_SIZE
                while offset < len(audio_data):
                    chunk = audio_data[offset: offset + FRAME_SIZE]
                    offset += FRAME_SIZE
                    status = 1 if offset < len(audio_data) else 2  # 1=mid, 2=last
                    frame = {
                        "data": {
                            "status": status,
                            "format": f"audio/L16;rate={sample_rate}",
                            "encoding": "raw",
                            "audio": base64.b64encode(chunk).decode("utf-8"),
                        }
                    }
                    await ws.send(json.dumps(frame))
                    await asyncio.sleep(FRAME_INTERVAL)

                # 收集识别结果
                async for message in ws:
                    resp = json.loads(message)
                    code = resp.get("code", -1)
                    if code != 0:
                        logger.error("讯飞IAT错误", code=code, message=resp.get("message"))
                        break
                    data = resp.get("data", {})
                    result = data.get("result", {})
                    ws_text = result.get("ws", [])
                    for word_group in ws_text:
                        for cw in word_group.get("cw", []):
                            result_text += cw.get("w", "")
                    if data.get("status") == 2:
                        break

        except Exception as e:
            logger.error("讯飞IAT WebSocket异常", error=str(e))

        logger.info("讯飞IAT识别完成", text=result_text)
        return result_text

    # ------------------------------------------------------------------
    # TTS — Text-to-Speech
    # ------------------------------------------------------------------

    async def text_to_speech(
        self,
        text: str,
        voice: str = "xiaoyan",
        speed: int = 50,
        volume: int = 50,
        pitch: int = 50,
        sample_rate: int = 16000,
    ) -> bytes:
        """
        将文字通过讯飞 TTS WebSocket 合成为 PCM 音频

        Args:
            text: 待合成文本 (≤8000字节)
            voice: 发音人 (xiaoyan=女声, aisjiuxu=男声)
            speed: 语速 0-100
            volume: 音量 0-100
            pitch: 音调 0-100
            sample_rate: 采样率

        Returns:
            PCM 音频字节，失败时返回 b""
        """
        if not self._is_configured():
            logger.warning("讯飞未配置，返回空音频")
            return b""

        url = _build_auth_url(TTS_HOST, TTS_PATH, self.api_key, self.api_secret)
        audio_chunks: list[bytes] = []

        try:
            async with websockets.connect(url, ping_interval=None) as ws:
                request = {
                    "common": {"app_id": self.app_id},
                    "business": {
                        "aue": "raw",          # raw PCM
                        "auf": f"audio/L16;rate={sample_rate}",
                        "vcn": voice,
                        "speed": speed,
                        "volume": volume,
                        "pitch": pitch,
                        "tte": "UTF8",
                    },
                    "data": {
                        "status": 2,           # 2=complete text (single-shot)
                        "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
                    },
                }
                await ws.send(json.dumps(request))

                async for message in ws:
                    resp = json.loads(message)
                    code = resp.get("code", -1)
                    if code != 0:
                        logger.error("讯飞TTS错误", code=code, message=resp.get("message"))
                        break
                    data = resp.get("data", {})
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        audio_chunks.append(base64.b64decode(audio_b64))
                    if data.get("status") == 2:
                        break

        except Exception as e:
            logger.error("讯飞TTS WebSocket异常", error=str(e))

        audio = b"".join(audio_chunks)
        logger.info("讯飞TTS合成完成", audio_size=len(audio))
        return audio


# Singleton
iflytek_ws_service = IflytekWebSocketService()
