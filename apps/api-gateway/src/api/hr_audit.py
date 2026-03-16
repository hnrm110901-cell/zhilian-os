"""
HR操作审计日志查询API

端点:
  GET /hr/audit/logs                                — 查询审计日志（分页，按模块/操作人/时间范围筛选）
  GET /hr/audit/logs/{resource_type}/{resource_id}  — 查看特定资源的操作历史
  GET /hr/audit/stats                               — 审计统计（按模块/操作类型分组计数）
"""

from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.models.operation_audit_log import OperationAuditLog

logger = structlog.get_logger()
router = APIRouter()


# ── 响应模型 ─────────────────────────────────────────────


class AuditLogItem(BaseModel):
    """审计日志条目"""

    id: str
    operator_id: str
    operator_name: Optional[str] = None
    operator_role: Optional[str] = None
    action: str
    module: str
    resource_type: str
    resource_id: Optional[str] = None
    method: str
    path: str
    ip_address: Optional[str] = None
    request_body: Optional[dict] = None
    response_status: Optional[int] = None
    changes: Optional[dict] = None
    success: Optional[str] = None
    error_message: Optional[str] = None
    store_id: Optional[str] = None
    brand_id: Optional[str] = None
    created_at: Optional[str] = None


class AuditLogListResponse(BaseModel):
    """审计日志列表响应"""

    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int


class AuditStatItem(BaseModel):
    """审计统计项"""

    key: str
    count: int


class AuditStatsResponse(BaseModel):
    """审计统计响应"""

    by_module: list[AuditStatItem]
    by_action: list[AuditStatItem]
    by_operator: list[AuditStatItem]
    total: int
    period_start: str
    period_end: str


# ── 端点 ─────────────────────────────────────────────────


@router.get("/hr/audit/logs", response_model=AuditLogListResponse, summary="查询HR操作审计日志")
async def list_audit_logs(
    module: Optional[str] = Query(None, description="模块筛选: payroll/leave/attendance/..."),
    action: Optional[str] = Query(None, description="操作类型: create/update/delete/approve/reject"),
    operator_id: Optional[str] = Query(None, description="操作人ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    success: Optional[str] = Query(None, description="是否成功: true/false"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询HR操作审计日志（分页）

    支持按模块、操作人、时间范围等维度筛选，用于合规审计和操作追溯。
    """
    # 构建查询条件
    conditions = []
    if module:
        conditions.append(OperationAuditLog.module == module)
    if action:
        conditions.append(OperationAuditLog.action == action)
    if operator_id:
        conditions.append(OperationAuditLog.operator_id == operator_id)
    if store_id:
        conditions.append(OperationAuditLog.store_id == store_id)
    if success:
        conditions.append(OperationAuditLog.success == success)
    if start_date:
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(OperationAuditLog.created_at >= dt)
        except ValueError:
            pass
    if end_date:
        try:
            dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            conditions.append(OperationAuditLog.created_at < dt)
        except ValueError:
            pass

    where_clause = and_(*conditions) if conditions else True

    # 查总数
    count_stmt = select(func.count(OperationAuditLog.id)).where(where_clause)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    stmt = (
        select(OperationAuditLog)
        .where(where_clause)
        .order_by(desc(OperationAuditLog.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogItem(**log.to_dict()) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/hr/audit/logs/{resource_type}/{resource_id}",
    response_model=AuditLogListResponse,
    summary="查看特定资源的操作历史",
)
async def get_resource_audit_trail(
    resource_type: str,
    resource_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    查看特定资源（如某个员工、某条工资单）的完整操作历史

    用于追溯某个资源从创建到当前的所有变更记录。
    """
    where_clause = and_(
        OperationAuditLog.resource_type == resource_type,
        OperationAuditLog.resource_id == resource_id,
    )

    count_stmt = select(func.count(OperationAuditLog.id)).where(where_clause)
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    stmt = (
        select(OperationAuditLog)
        .where(where_clause)
        .order_by(desc(OperationAuditLog.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogItem(**log.to_dict()) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/hr/audit/stats", response_model=AuditStatsResponse, summary="审计统计概览")
async def get_audit_stats(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    审计统计概览 — 按模块/操作类型/操作人分组计数

    用于管理层快速了解系统操作热度和风险分布。
    """
    period_start = datetime.utcnow() - timedelta(days=days)
    period_end = datetime.utcnow()

    base_conditions = [OperationAuditLog.created_at >= period_start]
    if store_id:
        base_conditions.append(OperationAuditLog.store_id == store_id)
    base_where = and_(*base_conditions)

    # 总数
    total = (await db.execute(select(func.count(OperationAuditLog.id)).where(base_where))).scalar() or 0

    # 按模块分组
    by_module_stmt = (
        select(OperationAuditLog.module, func.count(OperationAuditLog.id).label("cnt"))
        .where(base_where)
        .group_by(OperationAuditLog.module)
        .order_by(desc("cnt"))
        .limit(20)
    )
    by_module = [AuditStatItem(key=row[0], count=row[1]) for row in (await db.execute(by_module_stmt)).all()]

    # 按操作类型分组
    by_action_stmt = (
        select(OperationAuditLog.action, func.count(OperationAuditLog.id).label("cnt"))
        .where(base_where)
        .group_by(OperationAuditLog.action)
        .order_by(desc("cnt"))
        .limit(20)
    )
    by_action = [AuditStatItem(key=row[0], count=row[1]) for row in (await db.execute(by_action_stmt)).all()]

    # 按操作人分组（Top 10）
    by_operator_stmt = (
        select(OperationAuditLog.operator_id, func.count(OperationAuditLog.id).label("cnt"))
        .where(base_where)
        .group_by(OperationAuditLog.operator_id)
        .order_by(desc("cnt"))
        .limit(10)
    )
    by_operator = [AuditStatItem(key=row[0], count=row[1]) for row in (await db.execute(by_operator_stmt)).all()]

    return AuditStatsResponse(
        by_module=by_module,
        by_action=by_action,
        by_operator=by_operator,
        total=total,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )
