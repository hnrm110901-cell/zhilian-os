"""
Mobile API endpoints
移动端专用API接口 - 优化的数据结构和响应
"""

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.edge_hub import AlertLevel, AlertStatus, EdgeAlert, EdgeHub, HubStatus
from ..models.order import Order
from ..models.schedule import Schedule, Shift
from ..models.task import Task, TaskPriority, TaskStatus
from ..models.user import User
from ..services.member_service import member_service
from ..services.notification_service import notification_service
from ..services.pos_service import pos_service
from ..services.store_service import store_service
from ..utils.geo import format_distance, haversine_distance

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


class MobileActionResult(BaseModel):
    ok: bool
    message: str


class MobileShiftItem(BaseModel):
    shift_id: str
    shift_name: str
    shift_date: str
    start_time: str
    end_time: str
    position_name: str
    shift_status: str
    attendance_status: str
    related_task_count: int
    can_check_in: bool
    can_check_out: bool


class MobileTaskItem(BaseModel):
    task_id: str
    task_title: str
    task_type: str
    priority: str
    task_status: str
    deadline_at: str
    assignee_name: str
    need_evidence: bool
    need_review: bool
    task_description: Optional[str] = None
    reject_reason: Optional[str] = None
    evidence_count: int = 0


class MobileEdgeHubStatus(BaseModel):
    hub_online: bool
    open_alert_count: int
    p1_alert_count: int
    last_heartbeat: Optional[str] = None


class MobileHomeSummary(BaseModel):
    store_id: str
    as_of: str
    role_name: str
    unread_alerts_count: int
    pending_approvals_count: int
    today_revenue_yuan: float
    food_cost_pct: float
    waiting_count: int
    health_score: int
    health_level: str
    weakest_dimension: Optional[str] = None
    today_shift: Optional[MobileShiftItem] = None
    top_tasks: List[MobileTaskItem]
    edge_hub_status: Optional[MobileEdgeHubStatus] = None


class MobileShiftSummary(BaseModel):
    store_id: str
    date: str
    shifts: List[MobileShiftItem]


class MobileTaskSummary(BaseModel):
    store_id: str
    total: int
    pending_count: int
    expired_count: int
    tasks: List[MobileTaskItem]


class TaskSubmitPayload(BaseModel):
    evidence_note: Optional[str] = None
    evidence_files: Optional[List[str]] = None


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
        limit=int(os.getenv("MOBILE_DASHBOARD_NOTIF_LIMIT", "3")),
    )

    notifications_summary = MobileNotificationSummary(
        unread_count=unread_count,
        latest_notifications=[n.to_dict() for n in latest_notifications],
    )

    # 根据角色生成快捷操作
    quick_actions = _get_quick_actions_by_role(current_user.role.value)

    # 今日统计数据
    today = datetime.now().strftime("%Y-%m-%d")
    today_stats = {
        "date": today,
        "revenue": 0,
        "customers": 0,
        "orders": 0,
    }

    # 获取今日订单数据
    try:
        orders_result = await pos_service.query_orders(
            begin_date=today,
            end_date=today,
            page_index=1,
            page_size=int(os.getenv("MOBILE_PAGE_SIZE", "1000")),
        )
        orders = orders_result.get("orders", [])
        today_stats["orders"] = len(orders)
        today_stats["revenue"] = sum(order.get("realPrice", 0) for order in orders)
        today_stats["customers"] = sum(order.get("people", 0) for order in orders)
    except Exception as e:
        logger.warning("获取今日订单数据失败", error=str(e))

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

    return actions_map.get(
        role,
        [
            {"id": "home", "label": "首页", "icon": "home", "route": "/"},
            {"id": "profile", "label": "个人中心", "icon": "user", "route": "/profile"},
        ],
    )


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
        limit=int(os.getenv("MOBILE_NOTIF_LIST_LIMIT", "10")),
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
    radius: int = Query(int(os.getenv("MOBILE_STORE_SEARCH_RADIUS", "5000")), description="搜索半径(米)"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取附近门店 - 移动端地理位置功能
    基于用户当前位置,返回指定半径内的门店列表,按距离排序
    """
    try:
        # 获取所有活跃门店
        all_stores = await store_service.get_stores(limit=int(os.getenv("MOBILE_STORE_QUERY_LIMIT", "1000")))

        # 计算距离并过滤
        nearby_stores = []
        for store in all_stores:
            # 跳过没有地理位置信息的门店
            if store.latitude is None or store.longitude is None:
                continue

            # 计算距离
            distance = haversine_distance(latitude, longitude, store.latitude, store.longitude)

            # 只保留在半径内的门店
            if distance <= radius:
                nearby_stores.append(
                    {
                        "id": store.id,
                        "name": store.name,
                        "address": store.address,
                        "phone": store.phone,
                        "latitude": store.latitude,
                        "longitude": store.longitude,
                        "distance": round(distance, 2),  # 距离(米)
                        "distance_text": format_distance(distance),  # 格式化的距离文本
                        "city": store.city,
                        "district": store.district,
                        "status": store.status,
                    }
                )

        # 按距离排序
        nearby_stores.sort(key=lambda x: x["distance"])

        logger.info(
            "查询附近门店",
            user_id=str(current_user.id),
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            found_count=len(nearby_stores),
        )

        return {
            "location": {"latitude": latitude, "longitude": longitude},
            "radius": radius,
            "count": len(nearby_stores),
            "stores": nearby_stores,
        }

    except Exception as e:
        logger.error("查询附近门店失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询附近门店失败: {str(e)}")


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

    today = datetime.now().strftime("%Y-%m-%d")

    # 根据角色返回不同的统计数据
    if current_user.role.value in ["store_manager", "admin", "assistant_manager"]:
        # 店长/管理员/店长助理 - 查看门店整体数据
        try:
            orders_result = await pos_service.query_orders(
                begin_date=today,
                end_date=today,
                page_index=1,
                page_size=int(os.getenv("MOBILE_PAGE_SIZE", "1000")),
            )
            orders = orders_result.get("orders", [])

            stats.update(
                {
                    "today_revenue": sum(order.get("realPrice", 0) for order in orders),
                    "today_customers": sum(order.get("people", 0) for order in orders),
                    "today_orders": len(orders),
                    "staff_on_duty": 0,  # 需要从员工排班系统获取
                }
            )
        except Exception as e:
            logger.warning("获取店长统计数据失败", error=str(e))
            stats.update(
                {
                    "today_revenue": 0,
                    "today_customers": 0,
                    "today_orders": 0,
                    "staff_on_duty": 0,
                }
            )

    elif current_user.role.value == "waiter":
        # 服务员 - 查看个人订单数据
        try:
            orders_result = await pos_service.query_orders(
                begin_date=today,
                end_date=today,
                page_index=1,
                page_size=int(os.getenv("MOBILE_PAGE_SIZE", "1000")),
            )
            orders = orders_result.get("orders", [])

            # 筛选当前用户的订单（假设订单中有waiter_id字段）
            my_orders = [o for o in orders if o.get("waiter_id") == str(current_user.id)]
            pending_orders = [o for o in my_orders if o.get("status") in ["pending", "preparing"]]
            completed_orders = [o for o in my_orders if o.get("status") == "completed"]

            stats.update(
                {
                    "my_orders_count": len(my_orders),
                    "pending_orders": len(pending_orders),
                    "completed_today": len(completed_orders),
                }
            )
        except Exception as e:
            logger.warning("获取服务员统计数据失败", error=str(e))
            stats.update(
                {
                    "my_orders_count": 0,
                    "pending_orders": 0,
                    "completed_today": 0,
                }
            )

    elif current_user.role.value in ["chef", "head_chef", "station_manager"]:
        # 厨师 - 查看待制作订单
        try:
            orders_result = await pos_service.query_orders(
                begin_date=today,
                end_date=today,
                page_index=1,
                page_size=int(os.getenv("MOBILE_PAGE_SIZE", "1000")),
            )
            orders = orders_result.get("orders", [])

            pending_orders = [o for o in orders if o.get("status") in ["pending", "confirmed"]]
            in_progress_orders = [o for o in orders if o.get("status") == "preparing"]
            completed_orders = [o for o in orders if o.get("status") == "completed"]

            stats.update(
                {
                    "pending_orders": len(pending_orders),
                    "in_progress": len(in_progress_orders),
                    "completed_today": len(completed_orders),
                }
            )
        except Exception as e:
            logger.warning("获取厨师统计数据失败", error=str(e))
            stats.update(
                {
                    "pending_orders": 0,
                    "in_progress": 0,
                    "completed_today": 0,
                }
            )

    elif current_user.role.value == "warehouse_manager":
        # 库管 - 查看库存数据
        try:
            from ..services.inventory_service import inventory_service

            # 获取低库存商品数量
            low_stock_items = await inventory_service.get_low_stock_items(store_id=current_user.store_id)

            stats.update(
                {
                    "low_stock_items": len(low_stock_items) if low_stock_items else 0,
                    "pending_receive": 0,  # 需要从采购系统获取
                    "today_transactions": 0,  # 需要从库存交易记录获取
                }
            )
        except Exception as e:
            logger.warning("获取库管统计数据失败", error=str(e))
            stats.update(
                {
                    "low_stock_items": 0,
                    "pending_receive": 0,
                    "today_transactions": 0,
                }
            )

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


@router.get("/mobile/orders/today")
async def get_today_orders(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取今日订单 - 移动端优化版
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        result = await pos_service.query_orders(
            begin_date=today,
            end_date=today,
            page_index=1,
            page_size=int(os.getenv("MOBILE_RECENT_ORDERS_PAGE_SIZE", "100")),
        )

        orders = result.get("orders", [])

        # 精简订单数据
        simplified_orders = [
            {
                "id": order.get("billId"),
                "order_no": order.get("billNo"),
                "table_no": order.get("tableNo"),
                "people": order.get("people"),
                "amount": order.get("realPrice", 0) / 100,  # 转换为元
                "status": order.get("billStatus"),
                "time": order.get("payTime") or order.get("openTime"),
            }
            for order in orders[: int(os.getenv("MOBILE_RECENT_ORDERS_LIMIT", "20"))]  # 只返回最近N条
        ]

        return {
            "date": today,
            "total": len(orders),
            "orders": simplified_orders,
        }

    except Exception as e:
        logger.error("获取今日订单失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取今日订单失败: {str(e)}")


@router.get("/mobile/member/info")
async def get_member_info(
    card_no: Optional[str] = Query(None, description="会员卡号"),
    mobile: Optional[str] = Query(None, description="手机号"),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询会员信息 - 移动端快速查询
    """
    try:
        member = await member_service.query_member(card_no=card_no, mobile=mobile)

        # 精简会员数据
        simplified_member = {
            "card_no": member.get("cardNo"),
            "name": member.get("name"),
            "mobile": member.get("mobile"),
            "level": member.get("level"),
            "points": member.get("points"),
            "balance": member.get("balance", 0) / 100,  # 转换为元
        }

        return simplified_member

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("查询会员信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询会员信息失败: {str(e)}")


@router.get("/mobile/menu/categories")
async def get_menu_categories(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取菜单类别 - 移动端点餐功能
    """
    try:
        categories = await pos_service.get_dish_categories()

        # 精简类别数据
        simplified_categories = [
            {
                "id": cat.get("rcId"),
                "name": cat.get("rcNAME"),
                "parent_id": cat.get("fatherId"),
            }
            for cat in categories
        ]

        return {"categories": simplified_categories}

    except Exception as e:
        logger.error("获取菜单类别失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取菜单类别失败: {str(e)}")


@router.get("/mobile/menu/dishes")
async def get_menu_dishes(
    category_id: Optional[int] = Query(None, description="类别ID"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取菜品列表 - 移动端点餐功能
    """
    try:
        dishes = await pos_service.get_dishes()

        # 过滤和精简菜品数据
        filtered_dishes = [
            {
                "id": dish.get("dishesId"),
                "name": dish.get("dishesName"),
                "price": dish.get("dishPrice"),
                "category_id": dish.get("rcId"),
                "unit": dish.get("unit"),
                "is_recommend": dish.get("isRecommend") == 1,
            }
            for dish in dishes
            if category_id is None or dish.get("rcId") == category_id
        ]

        return {"dishes": filtered_dishes}

    except Exception as e:
        logger.error("获取菜品列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取菜品列表失败: {str(e)}")


@router.get("/mobile/tables")
async def get_tables(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取桌台列表 - 移动端桌台管理
    """
    try:
        tables = await pos_service.get_tables()

        # 精简桌台数据
        simplified_tables = [
            {
                "id": table.get("tableId"),
                "name": table.get("tableName"),
                "area": table.get("blName"),
            }
            for table in tables
        ]

        return {"tables": simplified_tables}

    except Exception as e:
        logger.error("获取桌台列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取桌台列表失败: {str(e)}")


def _task_priority_to_mobile(priority: Optional[str]) -> str:
    p = (priority or "").lower()
    if p == TaskPriority.URGENT.value:
        return "p0_urgent"
    if p == TaskPriority.HIGH.value:
        return "p1_high"
    if p == TaskPriority.NORMAL.value:
        return "p2_medium"
    return "p3_low"


def _task_status_to_mobile(status: Optional[str]) -> str:
    s = (status or "").lower()
    if s == TaskStatus.OVERDUE.value:
        return "expired"
    if s == TaskStatus.CANCELLED.value:
        return "rejected"
    if s == TaskStatus.COMPLETED.value:
        return "completed"
    if s == TaskStatus.IN_PROGRESS.value:
        return "in_progress"
    return "pending"


def _need_evidence(task: Task) -> bool:
    keywords = ["巡检", "inspection", "服务", "service", "安全", "safety", "异常"]
    text = f"{task.title or ''} {task.category or ''}".lower()
    return any(k.lower() in text for k in keywords)


def _need_review(task: Task) -> bool:
    keywords = ["巡检", "inspection", "培训", "training", "异常", "incident"]
    text = f"{task.title or ''} {task.category or ''}".lower()
    return any(k.lower() in text for k in keywords)


def _count_attachments(task: Task) -> int:
    if not task.attachments:
        return 0
    try:
        data = json.loads(task.attachments)
        if isinstance(data, list):
            return len(data)
    except Exception:
        return 1
    return 0


async def _build_shift_items(
    db: AsyncSession,
    store_id: str,
    schedule_date: datetime.date,
    user: User,
) -> List[MobileShiftItem]:
    shift_stmt = (
        select(Shift, Schedule)
        .join(Schedule, Shift.schedule_id == Schedule.id)
        .where(and_(Schedule.store_id == store_id, Schedule.schedule_date == schedule_date))
        .order_by(Shift.start_time.asc())
    )
    rows = (await db.execute(shift_stmt)).all()
    if not rows:
        return []

    is_store_manager = getattr(user.role, "value", user.role) in {"store_manager", "admin"}
    items: List[MobileShiftItem] = []
    for idx, (shift, schedule) in enumerate(rows):
        shift_status = "completed" if shift.is_completed else ("ongoing" if shift.is_confirmed else "upcoming")
        attendance_status = "checked_out" if shift.is_completed else ("checked_in" if shift.is_confirmed else "not_checked_in")
        can_check_in = (not shift.is_confirmed) and (is_store_manager or idx == 0)
        can_check_out = shift.is_confirmed and (not shift.is_completed)
        items.append(
            MobileShiftItem(
                shift_id=str(shift.id),
                shift_name=shift.shift_type or "班次",
                shift_date=str(schedule.schedule_date),
                start_time=shift.start_time.strftime("%H:%M"),
                end_time=shift.end_time.strftime("%H:%M"),
                position_name=shift.position or "岗位未设置",
                shift_status=shift_status,
                attendance_status=attendance_status,
                related_task_count=0,
                can_check_in=can_check_in,
                can_check_out=can_check_out,
            )
        )
    return items


def _task_to_mobile(task: Task, assignee_name: str = "待分配") -> MobileTaskItem:
    return MobileTaskItem(
        task_id=str(task.id),
        task_title=task.title,
        task_type=task.category or "sop",
        priority=_task_priority_to_mobile(task.priority.value if hasattr(task.priority, "value") else str(task.priority)),
        task_status=_task_status_to_mobile(task.status.value if hasattr(task.status, "value") else str(task.status)),
        deadline_at=(task.due_at or task.created_at or datetime.now(timezone.utc)).isoformat(),
        assignee_name=assignee_name,
        need_evidence=_need_evidence(task),
        need_review=_need_review(task),
        task_description=task.content,
        reject_reason="任务已取消，请确认原因" if (task.status == TaskStatus.CANCELLED) else None,
        evidence_count=_count_attachments(task),
    )


async def _fetch_edge_hub_status(store_id: str, db: AsyncSession) -> Optional[MobileEdgeHubStatus]:
    """Query the store's edge hub and open alerts, returning a compact status object."""
    try:
        hub = (await db.execute(select(EdgeHub).where(EdgeHub.store_id == store_id).limit(1))).scalar_one_or_none()

        alert_counts = (
            await db.execute(
                select(EdgeAlert.level, func.count(EdgeAlert.id).label("cnt"))
                .where(
                    and_(
                        EdgeAlert.store_id == store_id,
                        EdgeAlert.status == AlertStatus.OPEN,
                    )
                )
                .group_by(EdgeAlert.level)
            )
        ).all()

        total_open = sum(r.cnt for r in alert_counts)
        p1_open = sum(r.cnt for r in alert_counts if r.level == AlertLevel.P1)

        return MobileEdgeHubStatus(
            hub_online=hub is not None and hub.status == HubStatus.ONLINE,
            open_alert_count=total_open,
            p1_alert_count=p1_open,
            last_heartbeat=hub.last_heartbeat.isoformat() if hub and hub.last_heartbeat else None,
        )
    except Exception:
        return None


@router.get("/mobile/home/summary", response_model=MobileHomeSummary)
async def get_mobile_home_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    store_id = current_user.store_id
    if not store_id:
        raise HTTPException(status_code=400, detail="当前用户未绑定门店")

    today = datetime.now().date()

    shifts = await _build_shift_items(db, store_id, today, current_user)
    task_stmt = (
        select(Task)
        .where(and_(Task.store_id == store_id, Task.is_deleted != "true"))
        .order_by(Task.due_at.asc().nullslast())
        .limit(20)
    )
    task_rows = (await db.execute(task_stmt)).scalars().all()
    top_tasks = [_task_to_mobile(t, current_user.full_name or current_user.username) for t in task_rows]
    top_tasks = sorted(
        top_tasks,
        key=lambda t: ({"p0_urgent": 0, "p1_high": 1, "p2_medium": 2, "p3_low": 3}.get(t.priority, 9), t.deadline_at),
    )[:3]

    revenue_stmt = select(func.coalesce(func.sum(Order.total_amount), 0)).where(
        and_(Order.store_id == store_id, func.date(Order.order_time) == today)
    )
    revenue_value = (await db.execute(revenue_stmt)).scalar() or 0
    if isinstance(revenue_value, Decimal):
        revenue_value = float(revenue_value)

    unread_alerts_count = len([t for t in top_tasks if t.task_status == "expired"])
    pending_approvals = len([t for t in top_tasks if t.need_review and t.task_status in {"pending", "in_progress"}])
    edge_hub_status = await _fetch_edge_hub_status(store_id, db)

    return MobileHomeSummary(
        store_id=store_id,
        as_of=datetime.now(timezone.utc).isoformat(),
        role_name="店长" if (getattr(current_user.role, "value", current_user.role) == "store_manager") else "员工",
        unread_alerts_count=unread_alerts_count,
        pending_approvals_count=pending_approvals,
        today_revenue_yuan=float(revenue_value),
        food_cost_pct=31.8,
        waiting_count=0,
        health_score=82,
        health_level="good",
        weakest_dimension="成本率",
        today_shift=shifts[0] if shifts else None,
        top_tasks=top_tasks,
        edge_hub_status=edge_hub_status,
    )


@router.get("/mobile/shifts/summary", response_model=MobileShiftSummary)
async def get_mobile_shifts_summary(
    date: str = Query(..., description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    store_id = current_user.store_id
    if not store_id:
        raise HTTPException(status_code=400, detail="当前用户未绑定门店")
    try:
        schedule_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as e:
        raise HTTPException(status_code=422, detail="date 格式必须为 YYYY-MM-DD") from e

    shifts = await _build_shift_items(db, store_id, schedule_date, current_user)
    return MobileShiftSummary(store_id=store_id, date=date, shifts=shifts)


@router.post("/mobile/shifts/{shift_id}/check-in", response_model=MobileActionResult)
async def mobile_shift_check_in(
    shift_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = UUID(shift_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="无效的 shift_id") from e

    shift = (await db.execute(select(Shift).where(Shift.id == sid))).scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="班次不存在")
    if shift.is_confirmed:
        return MobileActionResult(ok=False, message="该班次已打卡")
    shift.is_confirmed = True
    await db.commit()
    return MobileActionResult(ok=True, message="打卡成功")


@router.post("/mobile/shifts/{shift_id}/check-out", response_model=MobileActionResult)
async def mobile_shift_check_out(
    shift_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = UUID(shift_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="无效的 shift_id") from e

    shift = (await db.execute(select(Shift).where(Shift.id == sid))).scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="班次不存在")
    if not shift.is_confirmed:
        return MobileActionResult(ok=False, message="请先上班打卡")
    if shift.is_completed:
        return MobileActionResult(ok=False, message="该班次已下班打卡")
    shift.is_completed = True
    await db.commit()
    return MobileActionResult(ok=True, message="下班打卡成功")


@router.get("/mobile/tasks/summary", response_model=MobileTaskSummary)
async def get_mobile_tasks_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    store_id = current_user.store_id
    if not store_id:
        raise HTTPException(status_code=400, detail="当前用户未绑定门店")

    stmt = (
        select(Task).where(and_(Task.store_id == store_id, Task.is_deleted != "true")).order_by(Task.due_at.asc().nullslast())
    )
    rows = (await db.execute(stmt)).scalars().all()
    tasks = [_task_to_mobile(t, current_user.full_name or current_user.username) for t in rows]
    pending_count = len([t for t in tasks if t.task_status in {"pending", "rejected"}])
    expired_count = len([t for t in tasks if t.task_status == "expired"])
    return MobileTaskSummary(
        store_id=store_id,
        total=len(tasks),
        pending_count=pending_count,
        expired_count=expired_count,
        tasks=tasks,
    )


@router.get("/mobile/tasks/{task_id}", response_model=MobileTaskItem)
async def get_mobile_task_detail(
    task_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tid = UUID(task_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="无效的 task_id") from e

    stmt = select(Task).where(and_(Task.id == tid, Task.store_id == current_user.store_id, Task.is_deleted != "true"))
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_to_mobile(task, current_user.full_name or current_user.username)


@router.post("/mobile/tasks/{task_id}/start", response_model=MobileActionResult)
async def mobile_task_start(
    task_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tid = UUID(task_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="无效的 task_id") from e

    stmt = select(Task).where(and_(Task.id == tid, Task.store_id == current_user.store_id, Task.is_deleted != "true"))
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in {TaskStatus.PENDING, TaskStatus.CANCELLED}:
        return MobileActionResult(
            ok=False, message=f"当前状态不可开始：{task.status.value if hasattr(task.status, 'value') else task.status}"
        )
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.now(timezone.utc)
    await db.commit()
    return MobileActionResult(ok=True, message="任务已开始")


@router.post("/mobile/tasks/{task_id}/submit", response_model=MobileActionResult)
async def mobile_task_submit(
    task_id: str,
    payload: TaskSubmitPayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tid = UUID(task_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="无效的 task_id") from e

    stmt = select(Task).where(and_(Task.id == tid, Task.store_id == current_user.store_id, Task.is_deleted != "true"))
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED, TaskStatus.PENDING}:
        return MobileActionResult(
            ok=False, message=f"当前状态不可提交：{task.status.value if hasattr(task.status, 'value') else task.status}"
        )

    if (
        _need_evidence(task)
        and not (payload.evidence_note and payload.evidence_note.strip())
        and not (payload.evidence_files or [])
    ):
        return MobileActionResult(ok=False, message="该任务要求证据，请填写说明或上传图片")

    task.result = payload.evidence_note or task.result
    if payload.evidence_files:
        try:
            existing = json.loads(task.attachments) if task.attachments else []
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        existing.extend(payload.evidence_files)
        task.attachments = json.dumps(existing, ensure_ascii=False)

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return MobileActionResult(ok=True, message="任务已提交")


@router.post("/mobile/tasks/{task_id}/evidence", response_model=dict)
async def mobile_task_upload_evidence(
    task_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tid = UUID(task_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="无效的 task_id") from e

    stmt = select(Task).where(and_(Task.id == tid, Task.store_id == current_user.store_id, Task.is_deleted != "true"))
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    filename = file.filename or f"evidence-{datetime.now().timestamp()}.bin"
    try:
        existing = json.loads(task.attachments) if task.attachments else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    existing.append(filename)
    task.attachments = json.dumps(existing, ensure_ascii=False)
    await db.commit()

    media_base_url = os.getenv("MOBILE_EVIDENCE_BASE_URL", "/uploads/evidence")
    file_url = f"{media_base_url.rstrip('/')}/{filename}"
    return {"ok": True, "message": "证据上传成功", "file_name": filename, "file_url": file_url}
