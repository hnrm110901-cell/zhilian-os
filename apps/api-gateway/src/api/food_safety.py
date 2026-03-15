"""
食品安全追溯 API — /api/v1/food-safety
提供食材溯源记录和安全检查记录的 CRUD 接口。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import require_role
from ..models.user import User, UserRole
from ..services.food_safety_service import FoodSafetyService

router = APIRouter(prefix="/api/v1/food-safety", tags=["food-safety"])

svc = FoodSafetyService()


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class TraceRecordCreate(BaseModel):
    brand_id: str
    store_id: str
    ingredient_name: str
    ingredient_id: Optional[str] = None
    batch_number: str
    supplier_name: str
    supplier_id: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None
    receive_date: date
    quantity: float
    unit: str
    origin: Optional[str] = None
    certificate_url: Optional[str] = None
    qr_code: Optional[str] = None
    temperature_on_receive: Optional[float] = None
    status: Optional[str] = "normal"
    notes: Optional[str] = None


class TraceStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class InspectionCreate(BaseModel):
    brand_id: str
    store_id: str
    inspection_type: str
    inspector_name: str
    inspection_date: date
    score: Optional[int] = None
    status: Optional[str] = "pending"
    items: List[Dict[str, Any]] = []
    photos: Optional[List[str]] = None
    corrective_actions: Optional[str] = None
    next_inspection_date: Optional[date] = None


# ── 序列化辅助 ────────────────────────────────────────────────────────────────

def _serialize_trace(r) -> Dict[str, Any]:
    return {
        "id": str(r.id),
        "brand_id": r.brand_id,
        "store_id": r.store_id,
        "ingredient_name": r.ingredient_name,
        "ingredient_id": r.ingredient_id,
        "batch_number": r.batch_number,
        "supplier_name": r.supplier_name,
        "supplier_id": r.supplier_id,
        "production_date": str(r.production_date) if r.production_date else None,
        "expiry_date": str(r.expiry_date) if r.expiry_date else None,
        "receive_date": str(r.receive_date) if r.receive_date else None,
        "quantity": float(r.quantity),
        "unit": r.unit,
        "origin": r.origin,
        "certificate_url": r.certificate_url,
        "qr_code": r.qr_code,
        "temperature_on_receive": float(r.temperature_on_receive) if r.temperature_on_receive else None,
        "status": r.status,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    }


def _serialize_inspection(r) -> Dict[str, Any]:
    return {
        "id": str(r.id),
        "brand_id": r.brand_id,
        "store_id": r.store_id,
        "inspection_type": r.inspection_type,
        "inspector_name": r.inspector_name,
        "inspection_date": str(r.inspection_date) if r.inspection_date else None,
        "score": r.score,
        "status": r.status,
        "items": r.items or [],
        "photos": r.photos,
        "corrective_actions": r.corrective_actions,
        "next_inspection_date": str(r.next_inspection_date) if r.next_inspection_date else None,
        "created_at": str(r.created_at) if r.created_at else None,
    }


# ── 溯源记录端点 ──────────────────────────────────────────────────────────────

@router.post("/traces")
async def create_trace_record(
    body: TraceRecordCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """创建食材溯源记录"""
    record = await svc.create_trace_record(db, body.model_dump())
    await db.commit()
    return _serialize_trace(record)


@router.get("/traces")
async def list_trace_records(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    ingredient_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询溯源记录"""
    records, total = await svc.list_trace_records(
        db, brand_id, store_id, page, page_size, status, ingredient_name,
    )
    return {
        "items": [_serialize_trace(r) for r in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/traces/expiring")
async def get_expiring_items(
    brand_id: str = Query(...),
    days_ahead: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询即将过期的食材"""
    records = await svc.check_expiring_items(db, brand_id, days_ahead)
    return {"items": [_serialize_trace(r) for r in records]}


@router.get("/traces/{record_id}")
async def get_trace_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取单条溯源记录"""
    record = await svc.get_trace_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="溯源记录不存在")
    return _serialize_trace(record)


@router.put("/traces/{record_id}/status")
async def update_trace_status(
    record_id: str,
    body: TraceStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """更新溯源记录状态（如召回）"""
    record = await svc.update_trace_status(db, record_id, body.status, body.notes)
    if not record:
        raise HTTPException(status_code=404, detail="溯源记录不存在")
    await db.commit()
    return _serialize_trace(record)


# ── 安全检查端点 ──────────────────────────────────────────────────────────────

@router.post("/inspections")
async def create_inspection(
    body: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """创建食品安全检查记录"""
    inspection = await svc.create_inspection(db, body.model_dump())
    await db.commit()
    return _serialize_inspection(inspection)


@router.get("/inspections")
async def list_inspections(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    inspection_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询检查记录"""
    records, total = await svc.list_inspections(
        db, brand_id, store_id, page, page_size, inspection_type,
    )
    return {
        "items": [_serialize_inspection(r) for r in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/inspections/{inspection_id}")
async def get_inspection(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取单条检查记录"""
    inspection = await svc.get_inspection(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="检查记录不存在")
    return _serialize_inspection(inspection)


# ── 统计端点 ──────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_food_safety_stats(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取食品安全统计概览"""
    return await svc.get_stats(db, brand_id)
