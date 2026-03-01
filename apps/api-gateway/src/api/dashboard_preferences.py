"""
看板布局偏好 API
Dashboard Layout Preferences - 用 Redis 持久化用户自定义看板配置
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import structlog

from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()

# 默认看板布局（按角色）
DEFAULT_LAYOUTS: Dict[str, List[Dict]] = {
    "admin": [
        {"id": "hq_summary", "title": "总部概览", "type": "stat_group", "visible": True, "order": 0},
        {"id": "store_ranking", "title": "门店排名", "type": "chart", "visible": True, "order": 1},
        {"id": "pending_approvals", "title": "待审批", "type": "list", "visible": True, "order": 2},
        {"id": "ai_accuracy", "title": "AI准确率", "type": "stat", "visible": True, "order": 3},
        {"id": "system_health", "title": "系统健康", "type": "stat", "visible": True, "order": 4},
    ],
    "store_manager": [
        {"id": "daily_hub", "title": "今日备战板", "type": "summary", "visible": True, "order": 0},
        {"id": "revenue_today", "title": "今日营收", "type": "stat", "visible": True, "order": 1},
        {"id": "order_trend", "title": "订单趋势", "type": "chart", "visible": True, "order": 2},
        {"id": "inventory_alerts", "title": "库存预警", "type": "list", "visible": True, "order": 3},
        {"id": "pending_approvals", "title": "待审批", "type": "list", "visible": True, "order": 4},
        {"id": "staff_schedule", "title": "今日排班", "type": "list", "visible": True, "order": 5},
    ],
    "staff": [
        {"id": "my_schedule", "title": "我的班表", "type": "list", "visible": True, "order": 0},
        {"id": "order_trend", "title": "今日订单", "type": "stat", "visible": True, "order": 1},
        {"id": "notifications", "title": "通知", "type": "list", "visible": True, "order": 2},
    ],
}

CACHE_TTL = 86400 * 30  # 30天


class WidgetConfig(BaseModel):
    id: str
    title: Optional[str] = None
    visible: bool = True
    order: int = 0


class SaveLayoutRequest(BaseModel):
    widgets: List[WidgetConfig]


async def _get_redis():
    from ..services.redis_cache_service import RedisCacheService
    svc = RedisCacheService()
    await svc.initialize()
    return svc


@router.get("/dashboard/preferences")
async def get_dashboard_preferences(
    current_user: User = Depends(get_current_active_user),
):
    """获取当前用户的看板布局偏好，无自定义时返回角色默认布局"""
    try:
        redis_svc = await _get_redis()
        cache_key = f"dashboard_pref:{current_user.id}"
        cached = await redis_svc.get(cache_key)
        if cached:
            return {"user_id": str(current_user.id), "layout": cached, "is_custom": True}

        role = current_user.role if hasattr(current_user, "role") else "staff"
        default = DEFAULT_LAYOUTS.get(role, DEFAULT_LAYOUTS["staff"])
        return {"user_id": str(current_user.id), "layout": default, "is_custom": False}
    except Exception as e:
        logger.error("get_dashboard_preferences_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/dashboard/preferences")
async def save_dashboard_preferences(
    req: SaveLayoutRequest,
    current_user: User = Depends(get_current_active_user),
):
    """保存用户自定义看板布局"""
    try:
        redis_svc = await _get_redis()
        cache_key = f"dashboard_pref:{current_user.id}"
        layout = [w.model_dump() for w in req.widgets]
        await redis_svc.set(cache_key, layout, ttl=CACHE_TTL)
        logger.info("dashboard_preferences_saved", user_id=str(current_user.id), widgets=len(layout))
        return {"success": True, "user_id": str(current_user.id), "layout": layout}
    except Exception as e:
        logger.error("save_dashboard_preferences_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dashboard/preferences")
async def reset_dashboard_preferences(
    current_user: User = Depends(get_current_active_user),
):
    """重置为角色默认布局"""
    try:
        redis_svc = await _get_redis()
        cache_key = f"dashboard_pref:{current_user.id}"
        await redis_svc.delete(cache_key)
        role = current_user.role if hasattr(current_user, "role") else "staff"
        default = DEFAULT_LAYOUTS.get(role, DEFAULT_LAYOUTS["staff"])
        return {"success": True, "layout": default, "is_custom": False}
    except Exception as e:
        logger.error("reset_dashboard_preferences_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
