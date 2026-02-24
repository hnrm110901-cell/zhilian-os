"""
讯飞 STT/TTS 实时 WebSocket API
Shokz 设备通过此端点流式上传音频，实时获取识别结果和 TTS 响应

协议:
  客户端 → 服务端: binary frames (PCM audio chunks)
  客户端 → 服务端: JSON {"type": "end"} 表示音频结束
  服务端 → 客户端: JSON {"type": "transcript", "text": "..."}
  服务端 → 客户端: JSON {"type": "tts_audio", "audio": "<base64 PCM>"}
  服务端 → 客户端: JSON {"type": "error", "message": "..."}
"""
import asyncio
import base64
import json
from typing import Optional

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from ..services.iflytek_websocket_service import iflytek_ws_service
from ..services.voice_command_service import voice_command_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/voice-ws", tags=["voice_ws"])


@router.websocket("/stt/{store_id}")
async def stt_stream(
    websocket: WebSocket,
    store_id: str,
    device_id: Optional[str] = Query(None),
    sample_rate: int = Query(16000),
    language: str = Query("zh_cn"),
):
    """
    实时语音识别 WebSocket

    客户端流式发送 PCM 音频帧，服务端收集完毕后调用讯飞 IAT 返回识别文本。

    Usage:
        ws://host/api/v1/voice-ws/stt/{store_id}?device_id=xxx&sample_rate=16000
    """
    await websocket.accept()
    logger.info("STT WebSocket 连接", store_id=store_id, device_id=device_id)

    audio_buffer = bytearray()

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                audio_buffer.extend(message["bytes"])

            elif "text" in message:
                payload = json.loads(message["text"])
                if payload.get("type") == "end":
                    # 音频结束，调用讯飞 IAT
                    if not audio_buffer:
                        await websocket.send_text(json.dumps({"type": "error", "message": "no audio received"}))
                        continue

                    text = await iflytek_ws_service.speech_to_text(
                        audio_data=bytes(audio_buffer),
                        language=language,
                        sample_rate=sample_rate,
                    )
                    audio_buffer.clear()

                    await websocket.send_text(json.dumps({"type": "transcript", "text": text}))
                    logger.info("STT 识别完成", store_id=store_id, text=text)

    except WebSocketDisconnect:
        logger.info("STT WebSocket 断开", store_id=store_id)
    except Exception as e:
        logger.error("STT WebSocket 异常", error=str(e))
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


@router.websocket("/tts/{store_id}")
async def tts_stream(
    websocket: WebSocket,
    store_id: str,
    voice: str = Query("xiaoyan", description="发音人: xiaoyan(女)/aisjiuxu(男)"),
    speed: int = Query(50, ge=0, le=100),
    sample_rate: int = Query(16000),
):
    """
    实时语音合成 WebSocket

    客户端发送 JSON {"type": "tts", "text": "..."} ，
    服务端返回 base64 编码的 PCM 音频。

    Usage:
        ws://host/api/v1/voice-ws/tts/{store_id}?voice=xiaoyan&speed=50
    """
    await websocket.accept()
    logger.info("TTS WebSocket 连接", store_id=store_id)

    try:
        while True:
            message = await websocket.receive_text()
            payload = json.loads(message)

            if payload.get("type") == "tts":
                text = payload.get("text", "").strip()
                if not text:
                    await websocket.send_text(json.dumps({"type": "error", "message": "empty text"}))
                    continue

                audio = await iflytek_ws_service.text_to_speech(
                    text=text,
                    voice=voice,
                    speed=speed,
                    sample_rate=sample_rate,
                )
                audio_b64 = base64.b64encode(audio).decode("utf-8")
                await websocket.send_text(json.dumps({
                    "type": "tts_audio",
                    "audio": audio_b64,
                    "sample_rate": sample_rate,
                    "size": len(audio),
                }))
                logger.info("TTS 合成完成", store_id=store_id, text_len=len(text), audio_size=len(audio))

    except WebSocketDisconnect:
        logger.info("TTS WebSocket 断开", store_id=store_id)
    except Exception as e:
        logger.error("TTS WebSocket 异常", error=str(e))
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


@router.websocket("/dialog/{store_id}")
async def dialog_stream(
    websocket: WebSocket,
    store_id: str,
    device_id: Optional[str] = Query(None),
    sample_rate: int = Query(16000),
    voice: str = Query("xiaoyan"),
):
    """
    全双工语音对话 WebSocket (STT → 意图识别 → TTS)

    客户端流式发送 PCM 音频，服务端返回:
    1. {"type": "transcript", "text": "..."} — 识别文本
    2. {"type": "response_text", "text": "..."} — Agent 响应文本
    3. {"type": "tts_audio", "audio": "<base64>"} — TTS 音频

    Usage:
        ws://host/api/v1/voice-ws/dialog/{store_id}?device_id=xxx
    """
    await websocket.accept()
    logger.info("Dialog WebSocket 连接", store_id=store_id, device_id=device_id)

    audio_buffer = bytearray()

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                audio_buffer.extend(message["bytes"])

            elif "text" in message:
                payload = json.loads(message["text"])

                if payload.get("type") == "end":
                    if not audio_buffer:
                        await websocket.send_text(json.dumps({"type": "error", "message": "no audio"}))
                        continue

                    # 1. STT
                    text = await iflytek_ws_service.speech_to_text(
                        audio_data=bytes(audio_buffer),
                        language="zh_cn",
                        sample_rate=sample_rate,
                    )
                    audio_buffer.clear()
                    await websocket.send_text(json.dumps({"type": "transcript", "text": text}))

                    if not text:
                        continue

                    # 2. 意图识别 + Agent 响应 (复用 voice_command_service)
                    try:
                        cmd_result = await voice_command_service.handle_command(
                            voice_text=text,
                            store_id=store_id,
                            user_id=device_id or "ws_client",
                            db=None,
                        )
                        response_text = cmd_result.get("response_text") or cmd_result.get("message", "好的")
                    except Exception as e:
                        logger.warning("意图识别失败，使用默认响应", error=str(e))
                        response_text = "抱歉，我没有理解您的指令，请再说一遍。"

                    await websocket.send_text(json.dumps({"type": "response_text", "text": response_text}))

                    # 3. TTS
                    audio = await iflytek_ws_service.text_to_speech(
                        text=response_text,
                        voice=voice,
                    )
                    audio_b64 = base64.b64encode(audio).decode("utf-8")
                    await websocket.send_text(json.dumps({
                        "type": "tts_audio",
                        "audio": audio_b64,
                        "sample_rate": sample_rate,
                    }))

    except WebSocketDisconnect:
        logger.info("Dialog WebSocket 断开", store_id=store_id)
    except Exception as e:
        logger.error("Dialog WebSocket 异常", error=str(e))
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
