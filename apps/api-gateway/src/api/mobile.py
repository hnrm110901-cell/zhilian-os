"""
Mobile API endpoints
移动端专用API接口 - 优化的数据结构和响应
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from ..models.user import User
from ..core.dependencies import get_current_active_user
from ..services.notification_service import notification_service
from ..services.store_service import store_service
from ..services.pos_service import pos_service
from ..services.member_service import member_service
from ..utils.geo import haversine_distance, format_distance
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
            page_size=1000,
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
    基于用户当前位置,返回指定半径内的门店列表,按距离排序
    """
    try:
        # 获取所有活跃门店
        all_stores = await store_service.get_stores(limit=1000)

        # 计算距离并过滤
        nearby_stores = []
        for store in all_stores:
            # 跳过没有地理位置信息的门店
            if store.latitude is None or store.longitude is None:
                continue

            # 计算距离
            distance = haversine_distance(
                latitude, longitude, store.latitude, store.longitude
            )

            # 只保留在半径内的门店
            if distance <= radius:
                nearby_stores.append({
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
                })

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
                page_size=1000,
            )
            orders = orders_result.get("orders", [])

            stats.update({
                "today_revenue": sum(order.get("realPrice", 0) for order in orders),
                "today_customers": sum(order.get("people", 0) for order in orders),
                "today_orders": len(orders),
                "staff_on_duty": 0,  # 需要从员工排班系统获取
            })
        except Exception as e:
            logger.warning("获取店长统计数据失败", error=str(e))
            stats.update({
                "today_revenue": 0,
                "today_customers": 0,
                "today_orders": 0,
                "staff_on_duty": 0,
            })

    elif current_user.role.value == "waiter":
        # 服务员 - 查看个人订单数据
        try:
            orders_result = await pos_service.query_orders(
                begin_date=today,
                end_date=today,
                page_index=1,
                page_size=1000,
            )
            orders = orders_result.get("orders", [])

            # 筛选当前用户的订单（假设订单中有waiter_id字段）
            my_orders = [o for o in orders if o.get("waiter_id") == str(current_user.id)]
            pending_orders = [o for o in my_orders if o.get("status") in ["pending", "preparing"]]
            completed_orders = [o for o in my_orders if o.get("status") == "completed"]

            stats.update({
                "my_orders_count": len(my_orders),
                "pending_orders": len(pending_orders),
                "completed_today": len(completed_orders),
            })
        except Exception as e:
            logger.warning("获取服务员统计数据失败", error=str(e))
            stats.update({
                "my_orders_count": 0,
                "pending_orders": 0,
                "completed_today": 0,
            })

    elif current_user.role.value in ["chef", "head_chef", "station_manager"]:
        # 厨师 - 查看待制作订单
        try:
            orders_result = await pos_service.query_orders(
                begin_date=today,
                end_date=today,
                page_index=1,
                page_size=1000,
            )
            orders = orders_result.get("orders", [])

            pending_orders = [o for o in orders if o.get("status") in ["pending", "confirmed"]]
            in_progress_orders = [o for o in orders if o.get("status") == "preparing"]
            completed_orders = [o for o in orders if o.get("status") == "completed"]

            stats.update({
                "pending_orders": len(pending_orders),
                "in_progress": len(in_progress_orders),
                "completed_today": len(completed_orders),
            })
        except Exception as e:
            logger.warning("获取厨师统计数据失败", error=str(e))
            stats.update({
                "pending_orders": 0,
                "in_progress": 0,
                "completed_today": 0,
            })

    elif current_user.role.value == "warehouse_manager":
        # 库管 - 查看库存数据
        try:
            from ..services.inventory_service import inventory_service

            # 获取低库存商品数量
            low_stock_items = await inventory_service.get_low_stock_items(
                store_id=current_user.store_id
            )

            stats.update({
                "low_stock_items": len(low_stock_items) if low_stock_items else 0,
                "pending_receive": 0,  # 需要从采购系统获取
                "today_transactions": 0,  # 需要从库存交易记录获取
            })
        except Exception as e:
            logger.warning("获取库管统计数据失败", error=str(e))
            stats.update({
                "low_stock_items": 0,
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
            page_size=100,
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
            for order in orders[:20]  # 只返回最近20条
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

