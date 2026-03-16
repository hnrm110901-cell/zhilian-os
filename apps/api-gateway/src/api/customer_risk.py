"""
客户风控 API — Phase P1
客户归属管理 + 离职交接 + 流失预警
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.customer_risk_service import customer_risk_service

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ──


class AssignCustomerRequest(BaseModel):
    store_id: str
    customer_phone: str
    customer_name: str
    owner_employee_id: str


class TransferCustomersRequest(BaseModel):
    store_id: str
    from_employee_id: str
    to_employee_id: str
    reason: str = "resignation"  # resignation/reorg/manual


class ResolveAlertRequest(BaseModel):
    action_result: str


# ── 客户归属 Routes ──


@router.post("/customer-ownership/assign", status_code=201)
async def assign_customer(
    req: AssignCustomerRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """分配客户归属"""
    result = await customer_risk_service.assign_customer(
        session=session,
        store_id=req.store_id,
        customer_phone=req.customer_phone,
        customer_name=req.customer_name,
        owner_employee_id=req.owner_employee_id,
    )
    await session.commit()
    return result


@router.post("/customer-ownership/transfer")
async def transfer_customers(
    req: TransferCustomersRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量交接客户（离职/调岗）"""
    result = await customer_risk_service.transfer_customers(
        session=session,
        store_id=req.store_id,
        from_employee_id=req.from_employee_id,
        to_employee_id=req.to_employee_id,
        reason=req.reason,
    )
    await session.commit()
    logger.info("customers_transferred", **result)
    return result


@router.get("/customer-ownership")
async def list_ownership(
    store_id: str = Query(..., description="门店ID"),
    employee_id: Optional[str] = Query(None, description="按销售筛选"),
    level: Optional[str] = Query(None, description="客户等级 VIP/GOLD/SILVER/NORMAL"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询客户归属列表"""
    return await customer_risk_service.list_ownership(
        session=session,
        store_id=store_id,
        employee_id=employee_id,
        level=level,
    )


@router.get("/customer-ownership/stats")
async def get_employee_customer_stats(
    store_id: str = Query(..., description="门店ID"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """各销售客户统计（客户数/总消费/平均到店次数）"""
    return await customer_risk_service.get_employee_stats(
        session=session,
        store_id=store_id,
    )


# ── 流失预警 Routes ──


@router.post("/customer-risk/scan")
async def scan_risk_customers(
    store_id: str = Query(..., description="门店ID"),
    dormant_days: int = Query(30, description="沉睡天数阈值"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """扫描流失风险客户"""
    result = await customer_risk_service.scan_risk_customers(
        session=session,
        store_id=store_id,
        dormant_days=dormant_days,
    )
    await session.commit()
    return result


@router.get("/customer-risk/alerts")
async def list_risk_alerts(
    store_id: str = Query(..., description="门店ID"),
    risk_level: Optional[str] = Query(None, description="风险等级 high/medium/low"),
    unresolved_only: bool = Query(True, description="只看未处理"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询流失预警列表"""
    return await customer_risk_service.list_risk_alerts(
        session=session,
        store_id=store_id,
        risk_level=risk_level,
        unresolved_only=unresolved_only,
    )


@router.patch("/customer-risk/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    req: ResolveAlertRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """标记预警已处理"""
    try:
        result = await customer_risk_service.resolve_alert(
            session=session,
            alert_id=alert_id,
            action_by=str(current_user.id),
            action_result=req.action_result,
        )
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
