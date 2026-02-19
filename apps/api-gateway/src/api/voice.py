"""
语音交互API
Voice Interaction API

提供Shokz设备管理和语音交互接口
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List
import structlog

from src.core.dependencies import get_current_active_user
from src.services.shokz_service import shokz_service, DeviceType, DeviceRole
from src.services.voice_orchestrator import voice_orchestrator
from src.models import User

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class RegisterDeviceRequest(BaseModel):
    """注册设备请求"""
    device_id: str = Field(..., description="设备ID")
    device_type: str = Field(..., description="设备类型: opencomm_2, openrun_pro_2")
    role: str = Field(..., description="设备角色: front_of_house, cashier, kitchen")
    bluetooth_address: str = Field(..., description="蓝牙地址")


class VoiceCommandRequest(BaseModel):
    """语音命令请求"""
    device_id: str = Field(..., description="设备ID")
    duration_seconds: int = Field(5, description="录音时长（秒）")


class VoiceNotificationRequest(BaseModel):
    """语音通知请求"""
    device_id: str = Field(..., description="设备ID")
    message: str = Field(..., description="通知消息")
    priority: str = Field("normal", description="优先级: normal, high, urgent")


# ==================== Shokz设备管理 ====================


@router.post("/devices/register", summary="注册Shokz设备")
async def register_device(
    request: RegisterDeviceRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    注册Shokz骨传导耳机设备

    支持的设备类型:
    - opencomm_2: OpenComm 2（前厅/收银）
    - openrun_pro_2: OpenRun Pro 2（后厨）

    支持的角色:
    - front_of_house: 前厅服务员
    - cashier: 收银员
    - kitchen: 后厨厨师
    """
    try:
        # 转换枚举类型
        device_type = DeviceType(request.device_type)
        role = DeviceRole(request.role)

        result = await shokz_service.register_device(
            device_id=request.device_id,
            device_type=device_type,
            role=role,
            user_id=current_user.id,
            bluetooth_address=request.bluetooth_address,
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))

        return {
            "success": True,
            "message": "设备注册成功",
            "data": result,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的设备类型或角色: {str(e)}")
    except Exception as e:
        logger.error("设备注册失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/connect", summary="连接Shokz设备")
async def connect_device(
    device_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """连接Shokz设备"""
    try:
        result = await shokz_service.connect_device(device_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))

        return {
            "success": True,
            "message": "设备连接成功",
            "data": result,
        }

    except Exception as e:
        logger.error("设备连接失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/disconnect", summary="断开Shokz设备")
async def disconnect_device(
    device_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """断开Shokz设备"""
    try:
        result = await shokz_service.disconnect_device(device_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))

        return {
            "success": True,
            "message": "设备断开成功",
            "data": result,
        }

    except Exception as e:
        logger.error("设备断开失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}", summary="获取设备信息")
async def get_device_info(
    device_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取Shokz设备详细信息"""
    device_info = shokz_service.get_device_info(device_id)

    if not device_info:
        raise HTTPException(status_code=404, detail="设备不存在")

    return {
        "success": True,
        "data": device_info,
    }


@router.get("/devices", summary="列出所有设备")
async def list_devices(
    role: Optional[str] = None,
    connected_only: bool = False,
    current_user: User = Depends(get_current_active_user),
):
    """
    列出Shokz设备

    可选参数:
    - role: 按角色筛选（front_of_house, cashier, kitchen）
    - connected_only: 只显示已连接设备
    """
    try:
        role_enum = DeviceRole(role) if role else None
        devices = shokz_service.list_devices(
            role=role_enum,
            connected_only=connected_only,
        )

        return {
            "success": True,
            "data": devices,
            "count": len(devices),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的角色: {str(e)}")
    except Exception as e:
        logger.error("列出设备失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 语音交互 ====================


@router.post("/voice/command", summary="处理语音命令")
async def process_voice_command(
    request: VoiceCommandRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    启动语音会话并处理命令

    流程:
    1. 从Shokz设备录音
    2. 语音识别（STT）
    3. 命令路由到Agent
    4. Agent执行
    5. 语音合成（TTS）
    6. 播放响应
    """
    try:
        result = await voice_orchestrator.start_voice_session(
            device_id=request.device_id,
            duration_seconds=request.duration_seconds,
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))

        return {
            "success": True,
            "message": "语音命令处理成功",
            "data": result,
        }

    except Exception as e:
        logger.error("语音命令处理失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/command/upload", summary="上传音频处理命令")
async def process_voice_command_upload(
    device_id: str,
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    """
    上传音频文件处理语音命令

    用于测试和调试，不需要实际的Shokz设备
    """
    try:
        # 读取音频数据
        audio_data = await audio_file.read()

        result = await voice_orchestrator.process_voice_command(
            device_id=device_id,
            audio_data=audio_data,
            sample_rate=16000,
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))

        return {
            "success": True,
            "message": "语音命令处理成功",
            "data": result,
        }

    except Exception as e:
        logger.error("语音命令处理失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/notification", summary="发送语音通知")
async def send_voice_notification(
    request: VoiceNotificationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    发送语音通知到Shokz设备

    优先级:
    - normal: 普通通知（正常语速）
    - high: 重要通知（稍快语速）
    - urgent: 紧急通知（快速语速）
    """
    try:
        result = await voice_orchestrator.send_voice_notification(
            device_id=request.device_id,
            message=request.message,
            priority=request.priority,
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error"))

        return {
            "success": True,
            "message": "语音通知发送成功",
            "data": result,
        }

    except Exception as e:
        logger.error("语音通知发送失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/notification/broadcast", summary="广播语音通知")
async def broadcast_voice_notification(
    message: str,
    role: Optional[str] = None,
    priority: str = "normal",
    current_user: User = Depends(get_current_active_user),
):
    """
    向多个设备广播语音通知

    可选参数:
    - role: 只发送给特定角色的设备
    - priority: 通知优先级
    """
    try:
        # 获取目标设备列表
        role_enum = DeviceRole(role) if role else None
        devices = shokz_service.list_devices(
            role=role_enum,
            connected_only=True,
        )

        if not devices:
            return {
                "success": True,
                "message": "没有可用的设备",
                "sent_count": 0,
            }

        # 发送通知到所有设备
        sent_count = 0
        failed_devices = []

        for device in devices:
            result = await voice_orchestrator.send_voice_notification(
                device_id=device["device_id"],
                message=message,
                priority=priority,
            )

            if result["success"]:
                sent_count += 1
            else:
                failed_devices.append(device["device_id"])

        return {
            "success": True,
            "message": f"语音通知已发送到 {sent_count} 个设备",
            "sent_count": sent_count,
            "total_devices": len(devices),
            "failed_devices": failed_devices,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的角色: {str(e)}")
    except Exception as e:
        logger.error("广播语音通知失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
