"""
Mobile API endpoints
移动端专用API接口 - 优化的数据结构和响应
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from ..models.user import User
from ..core.dependencies import get_current_active_user
from ..services.notification_service import notification_service
from ..services.store_service import store_service
import structlog

logger = structlog.get_logger()
router = APIRouter()


# 移动端响应模型 - 精简版
class MobileUserInfo(BaseModel):
    """移动端用户信息 - 精简版"""
    id: str
    username: str
    full_name: str
    role: str
    store_id: Optional[str]
    store_name: Optional[str] = None


class MobileNotificationSummary(BaseModel):
    """移动端通知摘要"""
    unread_count: int
    latest_notifications: List[dict]


class MobileDashboard(BaseModel):
    """移动端仪表盘数据"""
    user: MobileUserInfo
    notifications: MobileNotificationSummary
    quick_actions: List[dict]
    today_stats: dict


@router.get("/mobile/dashboard")
async def get_mobile_dashboard(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取移动端仪表盘数据
    一次请求获取所有首屏需要的数据,减少请求次数
    """
    # 获取用户信息
    user_info = MobileUserInfo(
        id=str(current_user.id),
        username=current_user.username,
        full_name=current_user.full_name or current_user.username,
        role=current_user.role.value,
        store_id=current_user.store_id,
    )

    # 获取门店名称
    if current_user.store_id:
        store = await store_service.get_store(current_user.store_id)
        if store:
            user_info.store_name = store.name

    # 获取未读通知
    unread_count = await notification_service.get_unread_count(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
    )

    # 获取最新3条通知
    latest_notifications = await notification_service.get_user_notifications(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
        limit=3,
    )

    notifications_summary = MobileNotificationSummary(
        unread_count=unread_count,
        latest_notifications=[n.to_dict() for n in latest_notifications],
    )

    # 根据角色生成快捷操作
    quick_actions = _get_quick_actions_by_role(current_user.role.value)

    # 今日统计数据(占位符)
    today_stats = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "revenue": 0,  # TODO: 从订单表查询
        "customers": 0,  # TODO: 从订单表查询
        "orders": 0,  # TODO: 从订单表查询
    }

    dashboard = MobileDashboard(
        user=user_info,
        notifications=notifications_summary,
        quick_actions=quick_actions,
        today_stats=today_stats,
    )

    return dashboard


def _get_quick_actions_by_role(role: str) -> List[dict]:
    """根据角色返回快捷操作"""
    actions_map = {
        "waiter": [
            {"id": "new_order", "label": "新建订单", "icon": "plus", "route": "/orders/new"},
            {"id": "my_orders", "label": "我的订单", "icon": "list", "route": "/orders/mine"},
            {"id": "notifications", "label": "通知", "icon": "bell", "route": "/notifications"},
        ],
        "store_manager": [
            {"id": "dashboard", "label": "数据看板", "icon": "chart", "route": "/dashboard"},
            {"id": "staff", "label": "员工管理", "icon": "users", "route": "/staff"},
            {"id": "inventory", "label": "库存管理", "icon": "box", "route": "/inventory"},
            {"id": "reports", "label": "报表", "icon": "file", "route": "/reports"},
        ],
        "chef": [
            {"id": "orders", "label": "待制作订单", "icon": "cooking", "route": "/kitchen/orders"},
            {"id": "menu", "label": "菜单", "icon": "book", "route": "/menu"},
        ],
        "warehouse_manager": [
            {"id": "inventory", "label": "库存盘点", "icon": "box", "route": "/inventory"},
            {"id": "receive", "label": "入库", "icon": "download", "route": "/inventory/receive"},
            {"id": "alerts", "label": "库存预警", "icon": "alert", "route": "/inventory/alerts"},
        ],
    }

    return actions_map.get(role, [
        {"id": "home", "label": "首页", "icon": "home", "route": "/"},
        {"id": "profile", "label": "个人中心", "icon": "user", "route": "/profile"},
    ])


@router.get("/mobile/notifications/summary")
async def get_notifications_summary(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取通知摘要 - 移动端优化版
    只返回必要的字段,减少数据传输
    """
    unread_count = await notification_service.get_unread_count(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
    )

    notifications = await notification_service.get_user_notifications(
        user_id=str(current_user.id),
        role=current_user.role.value,
        store_id=current_user.store_id,
        is_read=False,
        limit=10,
    )

    # 精简通知数据
    simplified_notifications = [
        {
            "id": str(n.id),
            "title": n.title,
            "message": n.message[:50] + "..." if len(n.message) > 50 else n.message,  # 截断长消息
            "type": n.type,
            "priority": n.priority,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]

    return {
        "unread_count": unread_count,
        "notifications": simplified_notifications,
    }


@router.post("/mobile/batch/mark-read")
async def batch_mark_notifications_read(
    notification_ids: List[str],
    current_user: User = Depends(get_current_active_user),
):
    """
    批量标记通知为已读 - 移动端批量操作
    减少网络请求次数
    """
    success_count = 0
    for notification_id in notification_ids:
        if await notification_service.mark_as_read(notification_id, str(current_user.id)):
            success_count += 1

    return {
        "success": True,
        "marked_count": success_count,
        "total": len(notification_ids),
    }


@router.get("/mobile/stores/nearby")
async def get_nearby_stores(
    latitude: float = Query(..., description="纬度"),
    longitude: float = Query(..., description="经度"),
    radius: int = Query(5000, description="搜索半径(米)"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取附近门店 - 移动端地理位置功能
    TODO: 实现基于地理位置的门店搜索
    """
    # 占位符实现
    stores = await store_service.get_stores(limit=10)

    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "radius": radius,
        "stores": [
            {
                "id": store.id,
                "name": store.name,
                "address": store.address,
                "phone": store.phone,
                "distance": 0,  # TODO: 计算实际距离
            }
            for store in stores
        ],
    }


@router.get("/mobile/quick-stats")
async def get_quick_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取快速统计数据 - 移动端首屏数据
    返回最关键的统计指标
    """
    stats = {
        "user_role": current_user.role.value,
        "store_id": current_user.store_id,
    }

    # 根据角色返回不同的统计数据
    if current_user.role.value == "store_manager":
        stats.update({
            "today_revenue": 0,  # TODO: 实际数据
            "today_customers": 0,
            "today_orders": 0,
            "staff_on_duty": 0,
        })
    elif current_user.role.value == "waiter":
        stats.update({
            "my_orders_count": 0,  # TODO: 实际数据
            "pending_orders": 0,
            "completed_today": 0,
        })
    elif current_user.role.value == "chef":
        stats.update({
            "pending_orders": 0,  # TODO: 实际数据
            "in_progress": 0,
            "completed_today": 0,
        })
    elif current_user.role.value == "warehouse_manager":
        stats.update({
            "low_stock_items": 0,  # TODO: 实际数据
            "pending_receive": 0,
            "today_transactions": 0,
        })

    return stats


@router.get("/mobile/health")
async def mobile_health_check():
    """
    移动端健康检查
    用于检测API可用性和响应时间
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


@router.post("/mobile/feedback")
async def submit_mobile_feedback(
    feedback: dict,
    current_user: User = Depends(get_current_active_user),
):
    """
    提交移动端反馈
    收集用户体验反馈
    """
    logger.info(
        "移动端反馈",
        user_id=str(current_user.id),
        feedback_type=feedback.get("type"),
        content=feedback.get("content"),
    )

    return {
        "success": True,
        "message": "感谢您的反馈",
    }
