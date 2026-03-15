"""健康证管理 API — 录入/查询/到期预警/批量状态更新"""
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.health_cert_service import HealthCertService

router = APIRouter(prefix="/health-certs", tags=["health-certs"])


class CreateCertRequest(BaseModel):
    brand_id: str
    store_id: str
    employee_id: str
    employee_name: str
    certificate_number: Optional[str] = None
    issue_date: date
    expiry_date: date
    issuing_authority: Optional[str] = None
    certificate_image_url: Optional[str] = None
    physical_exam_date: Optional[date] = None
    physical_exam_result: Optional[str] = None
    notes: Optional[str] = None


class UpdateCertRequest(BaseModel):
    employee_name: Optional[str] = None
    store_id: Optional[str] = None
    certificate_number: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    certificate_image_url: Optional[str] = None
    status: Optional[str] = None
    physical_exam_date: Optional[date] = None
    physical_exam_result: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_certificate(
    req: CreateCertRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """录入健康证"""
    result = await HealthCertService.create_certificate(session, req.model_dump())
    await session.commit()
    return result


@router.get("")
async def list_certificates(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    employee_name: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """健康证列表（分页+筛选）"""
    return await HealthCertService.list_certificates(
        session, brand_id=brand_id, store_id=store_id,
        page=page, page_size=page_size, status=status,
        employee_name=employee_name,
    )


@router.get("/expiring")
async def expiring_certificates(
    brand_id: str = Query(...),
    days_ahead: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """即将到期的健康证"""
    return await HealthCertService.check_expiring(session, brand_id, days_ahead)


@router.get("/expired")
async def expired_certificates(
    brand_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """已过期的健康证"""
    return await HealthCertService.get_expired(session, brand_id)


@router.get("/stats")
async def certificate_stats(
    brand_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """健康证统计概览"""
    return await HealthCertService.get_stats(session, brand_id)


@router.get("/{cert_id}")
async def get_certificate(
    cert_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """健康证详情"""
    try:
        return await HealthCertService.get_certificate(session, cert_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{cert_id}")
async def update_certificate(
    cert_id: str,
    req: UpdateCertRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """更新健康证"""
    try:
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        result = await HealthCertService.update_certificate(session, cert_id, data)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{cert_id}")
async def delete_certificate(
    cert_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """删除健康证"""
    try:
        result = await HealthCertService.delete_certificate(session, cert_id)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/auto-update")
async def auto_update_status(
    brand_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """批量更新健康证状态（根据到期日期自动判定）"""
    result = await HealthCertService.auto_update_status(session, brand_id)
    await session.commit()
    return result
