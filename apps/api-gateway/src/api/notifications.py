"""
Notification API endpoints
通知相关的API接口
"""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from typing import Optional, List
from pydantic import BaseModel

from ..models.user import User
from ..models.notification import NotificationType, NotificationPriority
from ..core.dependencies import get_current_active_user
from ..core.websocket import manager
from ..services.notification_service import notification_service
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
