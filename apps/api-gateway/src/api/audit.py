"""
审计日志API
"""
from typing import Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_permission
from src.core.permissions import Permission
from src.services.audit_log_service import audit_log_service
from src.models import User

router = APIRouter()


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: str
    action: str
    resource_type: str
    resource_id: Optional[str]
    user_id: str
    username: Optional[str]
    user_role: Optional[str]
    description: Optional[str]
    ip_address: Optional[str]
    request_method: Optional[str]
    request_path: Optional[str]
    status: str
    error_message: Optional[str]
    store_id: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.get("/logs")
async def get_audit_logs(
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AUDIT_READ)),
):
    """
    查询审计日志

    需要AUDIT_READ权限
    """
    # 转换日期为datetime
    start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
    end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None

    logs, total = await audit_log_service.get_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        store_id=store_id,
        start_date=start_datetime,
        end_date=end_datetime,
        search_query=search,
        skip=skip,
        limit=limit,
        db=db
    )

    return {
        "logs": [log.to_dict() for log in logs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/logs/user/{user_id}/stats")
async def get_user_activity_stats(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AUDIT_READ)),
):
    """
    获取用户活动统计

    需要AUDIT_READ权限
    """
    stats = await audit_log_service.get_user_activity_stats(
        user_id=user_id,
        days=days,
        db=db
    )

    return stats


@router.get("/logs/system/stats")
async def get_system_activity_stats(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AUDIT_READ)),
):
    """
    获取系统活动统计

    需要AUDIT_READ权限
    """
    stats = await audit_log_service.get_system_activity_stats(
        days=days,
        db=db
    )

    return stats


@router.delete("/logs/cleanup")
async def cleanup_old_logs(
    days: int = Query(90, ge=30, le=365, description="保留天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AUDIT_DELETE)),
):
    """
    清理旧日志

    需要AUDIT_DELETE权限
    """
    count = await audit_log_service.delete_old_logs(
        days=days,
        db=db
    )

    return {
        "success": True,
        "message": f"已删除 {count} 条旧日志",
        "deleted_count": count,
    }


@router.get("/logs/actions")
async def get_available_actions(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取所有可用的操作类型
    """
    from src.models.audit_log import AuditAction

    actions = [
        attr for attr in dir(AuditAction)
        if not attr.startswith('_') and isinstance(getattr(AuditAction, attr), str)
    ]

    return {
        "actions": actions,
        "count": len(actions),
    }


@router.get("/logs/resource-types")
async def get_available_resource_types(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取所有可用的资源类型
    """
    from src.models.audit_log import ResourceType

    resource_types = [
        attr for attr in dir(ResourceType)
        if not attr.startswith('_') and isinstance(getattr(ResourceType, attr), str)
    ]

    return {
        "resource_types": resource_types,
        "count": len(resource_types),
    }
