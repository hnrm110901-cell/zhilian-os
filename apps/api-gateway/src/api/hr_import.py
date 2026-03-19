"""
花名册导入API — Excel上传/预览/确认
"""

from typing import Dict, Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.hr_roster_import import HRRosterImportService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/hr/import/roster/preview")
async def preview_roster_import(
    file: UploadFile = File(...),
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """上传花名册Excel，预览列映射"""
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx/.xls 文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=400, detail="文件大小不能超过10MB")

    svc = HRRosterImportService(brand_id=brand_id)
    result = await svc.preview_import(db, content)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/hr/import/roster/confirm")
async def confirm_roster_import(
    file: UploadFile = File(...),
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None, description="默认门店ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """确认导入花名册"""
    content = await file.read()
    svc = HRRosterImportService(brand_id=brand_id, store_id=store_id)
    result = await svc.confirm_import(db, content, default_store_id=store_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    await db.commit()
    return result


@router.get("/hr/import/templates")
async def get_import_templates(
    current_user: User = Depends(get_current_active_user),
):
    """获取导入模板说明"""
    from ..services.hr_roster_import import LECAI_COLUMN_MAP

    return {
        "supported_formats": ["乐才HR", "钉钉", "企业微信"],
        "lecai_columns": list(LECAI_COLUMN_MAP.keys()),
        "required_columns": ["工号", "姓名", "门店"],
        "download_url": None,  # 后续提供模板下载
    }


# ── 组织架构API ──

from sqlalchemy import select

from ..models.organization import Organization


@router.get("/hr/organizations")
async def get_organizations(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取组织架构树"""
    result = await db.execute(
        select(Organization)
        .where(
            Organization.brand_id == brand_id,
            Organization.is_active.is_(True),
        )
        .order_by(Organization.level, Organization.sort_order)
    )
    orgs = result.scalars().all()

    items = []
    for org in orgs:
        items.append(
            {
                "id": str(org.id),
                "name": org.name,
                "code": org.code,
                "parent_id": str(org.parent_id) if org.parent_id else None,
                "level": org.level,
                "org_type": org.org_type,
                "store_id": org.store_id,
                "manager_id": org.manager_id,
                "sort_order": org.sort_order,
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/hr/organizations")
async def create_organization(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建组织节点"""
    org = Organization(
        brand_id=data["brand_id"],
        name=data["name"],
        code=data["code"],
        parent_id=data.get("parent_id"),
        level=data.get("level", 6),
        org_type=data.get("org_type", "department"),
        store_id=data.get("store_id"),
        manager_id=data.get("manager_id"),
        sort_order=data.get("sort_order", 0),
    )
    db.add(org)
    await db.commit()
    return {"id": str(org.id), "message": "组织节点创建成功"}
