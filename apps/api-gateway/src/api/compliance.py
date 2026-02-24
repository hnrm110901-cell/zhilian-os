"""
合规证照管理 API
Compliance License API
"""
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.services.compliance_service import ComplianceService
from src.agents.compliance_agent import compliance_agent
from src.models.compliance import LicenseType, LicenseStatus

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
_svc = ComplianceService()


# ── Request / Response schemas ────────────────────────────────

class LicenseCreate(BaseModel):
    store_id: str
    license_type: LicenseType
    license_name: str
    expiry_date: date
    license_number: Optional[str] = None
    holder_name: Optional[str] = None
    holder_employee_id: Optional[str] = None
    issue_date: Optional[date] = None
    remind_days_before: int = 30
    notes: Optional[str] = None


class LicenseUpdate(BaseModel):
    license_name: Optional[str] = None
    license_number: Optional[str] = None
    expiry_date: Optional[date] = None
    issue_date: Optional[date] = None
    holder_name: Optional[str] = None
    remind_days_before: Optional[int] = None
    notes: Optional[str] = None


# ── CRUD ──────────────────────────────────────────────────────

@router.post("/licenses")
async def create_license(body: LicenseCreate):
    """新增证照记录"""
    return await _svc.create_license(**body.model_dump())


@router.get("/licenses")
async def list_licenses(
    store_id: Optional[str] = Query(None),
    status: Optional[LicenseStatus] = Query(None),
    license_type: Optional[LicenseType] = Query(None),
):
    """查询证照列表，支持按门店/状态/类型过滤"""
    return await _svc.list_licenses(
        store_id=store_id, status=status, license_type=license_type
    )


@router.patch("/licenses/{license_id}")
async def update_license(license_id: str, body: LicenseUpdate):
    """更新证照信息"""
    result = await _svc.update_license(license_id, **body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="证照不存在")
    return result


@router.delete("/licenses/{license_id}")
async def delete_license(license_id: str):
    """删除证照记录"""
    ok = await _svc.delete_license(license_id)
    if not ok:
        raise HTTPException(status_code=404, detail="证照不存在")
    return {"success": True}


# ── Agent 扫描接口 ────────────────────────────────────────────

@router.post("/scan/{store_id}")
async def scan_store(
    store_id: str,
    recipient_ids: Optional[List[str]] = Query(None, description="企业微信接收人ID"),
):
    """
    触发 ComplianceAgent 扫描指定门店证照。

    返回即将到期和已过期的证照列表，并推送企业微信告警。
    """
    result = await compliance_agent.scan_store(
        store_id=store_id,
        recipient_ids=recipient_ids,
    )
    return result.to_dict()


@router.post("/scan-all")
async def scan_all_stores(
    recipient_ids: Optional[List[str]] = Query(None, description="企业微信接收人ID"),
):
    """
    触发 ComplianceAgent 扫描全部活跃门店。
    """
    result = await compliance_agent.execute(
        "scan_all", {"recipient_ids": recipient_ids}
    )
    return result.to_dict()


@router.get("/summary")
async def compliance_summary(
    store_id: Optional[str] = Query(None),
):
    """
    证照合规总览：各状态数量统计。
    """
    all_licenses = await _svc.list_licenses(store_id=store_id)
    from collections import Counter
    counts = Counter(l["status"] for l in all_licenses)
    return {
        "store_id": store_id,
        "total": len(all_licenses),
        "valid": counts.get(LicenseStatus.VALID, 0),
        "expire_soon": counts.get(LicenseStatus.EXPIRE_SOON, 0),
        "expired": counts.get(LicenseStatus.EXPIRED, 0),
        "unknown": counts.get(LicenseStatus.UNKNOWN, 0),
    }
