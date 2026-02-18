"""
Notification API endpoints
通知相关的API接口
"""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from ..models.user import User
from ..models.notification import NotificationType, NotificationPriority
from ..core.dependencies import get_current_active_user
from ..core.websocket import manager
from ..services.notification_service import notification_service
from ..services.multi_channel_notification import (
    multi_channel_notification_service,
    NotificationChannel,
    NotificationTemplate
)
import structlog

logger = structlog.get_logger()
router = APIRouter()


# Request/Response models
class CreateNotificationRequest(BaseModel):
    title: str
    message: str
    type: NotificationType = NotificationType.INFO
    priority: NotificationPriority = NotificationPriority.NORMAL
    user_id: Optional[str] = None
    role: Optional[str] = None
    store_id: Optional[str] = None
    extra_data: Optional[dict] = None
    source: Optional[str] = None


class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    priority: str
    user_id: Optional[str]
    role: Optional[str]
    store_id: Optional[str]
    is_read: bool
    read_at: Optional[str]
    extra_data: Optional[dict]
    source: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket连接端点
    客户端需要提供JWT token进行认证
    """
    # TODO: 验证token并获取用户信息
    # 这里简化处理,实际应该解析token获取用户信息
    from ..core.security import decode_access_token

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        role = payload.get("role")
        # store_id需要从数据库查询,这里暂时从payload获取
        store_id = payload.get("store_id")

        if not user_id:
            await websocket.close(code=1008, reason="Invalid token")
            return

        await manager.connect(websocket, user_id, role, store_id)

        try:
            while True:
                # 接收客户端消息(心跳包等)
                data = await websocket.receive_text()
                logger.debug("收到WebSocket消息", user_id=user_id, data=data)

                # 可以处理客户端发来的消息,比如心跳包
                if data == "ping":
                    await websocket.send_text("pong")

        except WebSocketDisconnect:
            manager.disconnect(websocket, user_id)
            logger.info("WebSocket连接断开", user_id=user_id)

    except Exception as e:
        logger.error("WebSocket连接错误", error=str(e))
        await websocket.close(code=1011, reason=str(e))


@router.post("/notifications", response_model=NotificationResponse)
async def create_notification(
    request: CreateNotificationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    创建通知 (需要管理员或店长权限)
    """
    # TODO: 添加权限检查,只有管理员和店长可以创建通知

    notification = await notification_service.create_notification(
        title=request.title,
        message=request.message,
        type=request.type,
        priority=request.priority,
        user_id=request.user_id,
        role=request.role,
        store_id=request.store_id,
        extra_data=request.extra_data,
        source=request.source,
        send_realtime=True,
    )

    return NotificationResponse(**notification.to_dict())


@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(
    is_read: Optional[bool] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取当前用户的通知列表
    """
    notifications = await notification_service.get_user_notifications(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
        is_read=is_read,
        limit=limit,
        offset=offset,
    )

    return [NotificationResponse(**n.to_dict()) for n in notifications]


@router.get("/notifications/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取未读通知数量
    """
    count = await notification_service.get_unread_count(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
    )

    return {"unread_count": count}


@router.put("/notifications/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    标记通知为已读
    """
    success = await notification_service.mark_as_read(
        notification_id=notification_id, user_id=str(current_user.id)
    )

    if not success:
        return {"success": False, "message": "通知不存在或无权限"}

    return {"success": True, "message": "已标记为已读"}


@router.put("/notifications/read-all")
async def mark_all_as_read(
    current_user: User = Depends(get_current_active_user),
):
    """
    标记所有通知为已读
    """
    count = await notification_service.mark_all_as_read(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
    )

    return {"success": True, "message": f"已标记{count}条通知为已读", "count": count}


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    删除通知
    """
    success = await notification_service.delete_notification(
        notification_id=notification_id, user_id=str(current_user.id)
    )

    if not success:
        return {"success": False, "message": "通知不存在或无权限"}

    return {"success": True, "message": "通知已删除"}


@router.get("/notifications/stats")
async def get_notification_stats():
    """
    获取通知系统统计信息 (管理员功能)
    """
    return {
        "active_connections": manager.get_connection_count(),
        "active_users": len(manager.get_active_users()),
    }


# 多渠道通知API
class MultiChannelNotificationRequest(BaseModel):
    channels: List[str]  # email, sms, wechat, app_push
    recipient: str
    title: str
    content: str
    extra_data: Optional[dict] = None


class TemplateNotificationRequest(BaseModel):
    template_name: str
    recipient: str
    template_vars: dict


@router.post("/notifications/multi-channel")
async def send_multi_channel_notification(
    request: MultiChannelNotificationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    发送多渠道通知

    支持的渠道:
    - email: 邮件通知
    - sms: 短信通知
    - wechat: 微信通知
    - app_push: App推送通知
    """
    try:
        # 转换渠道字符串为枚举
        channels = [NotificationChannel(ch) for ch in request.channels]

        # 发送通知
        results = await multi_channel_notification_service.send_notification(
            channels=channels,
            recipient=request.recipient,
            title=request.title,
            content=request.content,
            extra_data=request.extra_data
        )

        # 转换结果为可序列化格式
        serialized_results = {
            channel.value: success
            for channel, success in results.items()
        }

        return {
            "success": True,
            "message": "通知已发送",
            "results": serialized_results
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的通知渠道: {str(e)}")
    except Exception as e:
        logger.error("发送多渠道通知失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")


@router.post("/notifications/template")
async def send_template_notification(
    request: TemplateNotificationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    使用模板发送通知

    可用模板:
    - order_confirmed: 订单确认
    - order_ready: 订单已完成
    - inventory_low: 库存预警
    - staff_schedule: 排班通知
    - payment_success: 支付成功
    - backup_completed: 数据备份完成
    - backup_failed: 数据备份失败
    - system_alert: 系统告警
    """
    try:
        # 发送模板通知
        results = await multi_channel_notification_service.send_template_notification(
            template_name=request.template_name,
            recipient=request.recipient,
            **request.template_vars
        )

        if not results:
            raise HTTPException(status_code=404, detail=f"模板不存在: {request.template_name}")

        # 转换结果为可序列化格式
        serialized_results = {
            channel.value: success
            for channel, success in results.items()
        }

        return {
            "success": True,
            "message": "模板通知已发送",
            "template": request.template_name,
            "results": serialized_results
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("发送模板通知失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")


@router.get("/notifications/templates")
async def get_notification_templates(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取所有可用的通知模板
    """
    templates = {}
    for name, template in NotificationTemplate.TEMPLATES.items():
        templates[name] = {
            "title": template["title"],
            "content": template["content"],
            "channels": [ch.value for ch in template["channels"]],
            "priority": template["priority"],
        }

    return {
        "templates": templates,
        "count": len(templates)
    }
