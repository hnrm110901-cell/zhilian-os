"""
Notification API endpoints
通知相关的API接口
"""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from ..models.user import User, UserRole
from ..models.notification import NotificationType, NotificationPriority
from ..core.dependencies import get_current_active_user, require_role
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

    使用方式:
    ws://localhost:8000/api/v1/notifications/ws?token=<your_jwt_token>
    """
    from ..core.security import decode_access_token
    from ..core.database import get_db_session
    from sqlalchemy import select

    try:
        # 验证token并获取用户信息
        payload = decode_access_token(token)
        user_id = payload.get("sub")

        if not user_id:
            await websocket.close(code=1008, reason="Invalid token: missing user_id")
            return

        # 从数据库获取完整的用户信息
        async with get_db_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                await websocket.close(code=1008, reason="User not found")
                return

            if not user.is_active:
                await websocket.close(code=1008, reason="User is inactive")
                return

        # 连接WebSocket
        await manager.connect(
            websocket,
            user_id=str(user.id),
            role=user.role.value,
            store_id=user.store_id
        )

        logger.info(
            "WebSocket连接已建立",
            user_id=user.id,
            username=user.username,
            role=user.role.value,
            store_id=user.store_id
        )

        try:
            while True:
                # 接收客户端消息(心跳包等)
                data = await websocket.receive_text()
                logger.debug("收到WebSocket消息", user_id=user_id, data=data)

                # 处理客户端发来的消息
                if data == "ping":
                    await websocket.send_text("pong")

        except WebSocketDisconnect:
            manager.disconnect(websocket, user_id)
            logger.info("WebSocket连接断开", user_id=user_id)

    except HTTPException as e:
        logger.error("WebSocket认证失败", error=str(e.detail))
        await websocket.close(code=1008, reason=str(e.detail))
    except Exception as e:
        logger.error("WebSocket连接错误", error=str(e))
        await websocket.close(code=1011, reason="Internal server error")


@router.post("/notifications", response_model=NotificationResponse)
async def create_notification(
    request: CreateNotificationRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.ASSISTANT_MANAGER)),
):
    """
    创建通知 (需要管理员、店长或店长助理权限)

    权限要求:
    - ADMIN: 可以创建任何通知
    - STORE_MANAGER: 可以创建本门店的通知
    - ASSISTANT_MANAGER: 可以创建本门店的通知
    """
    # 如果不是管理员，确保只能为自己的门店创建通知
    if current_user.role != UserRole.ADMIN:
        if request.store_id and request.store_id != current_user.store_id:
            raise HTTPException(
                status_code=403,
                detail="无权限为其他门店创建通知"
            )
        # 如果没有指定store_id，使用当前用户的store_id
        if not request.store_id:
            request.store_id = current_user.store_id

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

    logger.info(
        "通知已创建",
        notification_id=notification.id,
        creator_id=current_user.id,
        creator_role=current_user.role.value,
        target_store=request.store_id,
    )

    return NotificationResponse(**notification.to_dict())


@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(
    is_read: Optional[bool] = None,
    type: Optional[NotificationType] = Query(None, description="通知类型过滤"),
    priority: Optional[NotificationPriority] = Query(None, description="优先级过滤"),
    keyword: Optional[str] = Query(None, description="关键词搜索（标题或内容）"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取当前用户的通知列表

    支持过滤参数:
    - is_read: 是否已读
    - type: 通知类型 (info/warning/error/success/alert)
    - priority: 优先级 (low/normal/high/urgent)
    - keyword: 关键词搜索（匹配标题或内容）
    """
    notifications = await notification_service.get_user_notifications(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
        is_read=is_read,
        type_filter=type.value if type else None,
        priority_filter=priority.value if priority else None,
        keyword=keyword,
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
