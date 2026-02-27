"""
BOM API — 物料清单版本化配方管理

端点：
  POST   /api/v1/bom/                   创建新版 BOM
  GET    /api/v1/bom/{bom_id}           查询 BOM 详情（含明细行）
  GET    /api/v1/bom/dish/{dish_id}/active   查询菜品当前激活版本
  GET    /api/v1/bom/dish/{dish_id}/history  查询菜品所有历史版本
  GET    /api/v1/bom/store/{store_id}   查询门店所有 BOM
  POST   /api/v1/bom/{bom_id}/approve   审核 BOM
  POST   /api/v1/bom/{bom_id}/deactivate  停用 BOM
  DELETE /api/v1/bom/{bom_id}           删除未审核 BOM

  POST   /api/v1/bom/{bom_id}/items/    添加食材明细行
  PUT    /api/v1/bom/items/{item_id}    更新食材明细行
  DELETE /api/v1/bom/items/{item_id}   删除食材明细行

  POST   /api/v1/bom/{bom_id}/sync      手动触发 Neo4j 同步
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.bom_service import BOMService

router = APIRouter(prefix="/api/v1/bom", tags=["bom"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class BOMItemIn(BaseModel):
    ingredient_id: str = Field(..., description="食材 ID（InventoryItem.id）")
    standard_qty: float = Field(..., gt=0, description="标准用量")
    unit: str = Field(..., max_length=20, description="单位（克/毫升/个）")
    raw_qty: Optional[float] = Field(None, description="毛料用量")
    unit_cost: Optional[int] = Field(None, description="单位成本（分）")
    waste_factor: float = Field(0.0, ge=0, le=1, description="预期损耗系数")
    is_key_ingredient: bool = Field(False, description="是否核心食材")
    is_optional: bool = Field(False, description="是否可选配料")
    prep_notes: Optional[str] = None


class BOMItemUpdate(BaseModel):
    standard_qty: Optional[float] = Field(None, gt=0)
    raw_qty: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=20)
    unit_cost: Optional[int] = None
    waste_factor: Optional[float] = Field(None, ge=0, le=1)
    is_key_ingredient: Optional[bool] = None
    prep_notes: Optional[str] = None


class BOMItemOut(BaseModel):
    id: UUID
    bom_id: UUID
    ingredient_id: str
    standard_qty: float
    raw_qty: Optional[float]
    unit: str
    unit_cost: Optional[int]
    waste_factor: float
    is_key_ingredient: bool
    is_optional: bool
    prep_notes: Optional[str]

    model_config = {"from_attributes": True}


class BOMCreateIn(BaseModel):
    store_id: str = Field(..., description="门店 ID")
    dish_id: str = Field(..., description="菜品 UUID")
    version: str = Field(..., max_length=20, description="版本号，如 v1、2026-03")
    effective_date: Optional[datetime] = None
    yield_rate: float = Field(1.0, gt=0, le=1, description="出成率")
    standard_portion: Optional[float] = None
    prep_time_minutes: Optional[int] = None
    notes: Optional[str] = None
    activate: bool = Field(True, description="创建后立即激活（停用旧版本）")
    items: List[BOMItemIn] = Field(default_factory=list, description="初始食材明细行")


class BOMOut(BaseModel):
    id: UUID
    store_id: str
    dish_id: UUID
    version: str
    effective_date: datetime
    expiry_date: Optional[datetime]
    yield_rate: float
    standard_portion: Optional[float]
    prep_time_minutes: Optional[int]
    is_active: bool
    is_approved: bool
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    notes: Optional[str]
    created_by: Optional[str]
    items: List[BOMItemOut] = []
    total_cost: float = 0.0

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=BOMOut, status_code=status.HTTP_201_CREATED)
async def create_bom(
    payload: BOMCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新版 BOM（可同时附带食材明细行）"""
    svc = BOMService(db)
    bom = await svc.create_bom(
        store_id=payload.store_id,
        dish_id=payload.dish_id,
        version=payload.version,
        effective_date=payload.effective_date,
        yield_rate=payload.yield_rate,
        standard_portion=payload.standard_portion,
        prep_time_minutes=payload.prep_time_minutes,
        notes=payload.notes,
        created_by=str(current_user.id),
        activate=payload.activate,
    )

    # 批量添加初始食材行
    for item_in in payload.items:
        await svc.add_bom_item(
            bom_id=str(bom.id),
            ingredient_id=item_in.ingredient_id,
            standard_qty=item_in.standard_qty,
            unit=item_in.unit,
            raw_qty=item_in.raw_qty,
            unit_cost=item_in.unit_cost,
            waste_factor=item_in.waste_factor,
            is_key_ingredient=item_in.is_key_ingredient,
            is_optional=item_in.is_optional,
            prep_notes=item_in.prep_notes,
        )

    await db.commit()
    await db.refresh(bom)

    # 异步触发 Neo4j 同步（不阻断响应）
    try:
        await svc.sync_to_neo4j(bom)
    except Exception:
        pass

    return _serialize_bom(bom)


@router.get("/{bom_id}", response_model=BOMOut)
async def get_bom(
    bom_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询 BOM 详情（含食材明细行）"""
    svc = BOMService(db)
    bom = await svc.get_bom(bom_id)
    if not bom:
        raise HTTPException(status_code=404, detail="BOM 不存在")
    return _serialize_bom(bom)


@router.get("/dish/{dish_id}/active", response_model=BOMOut)
async def get_active_bom(
    dish_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询菜品当前激活的 BOM 版本"""
    svc = BOMService(db)
    bom = await svc.get_active_bom(dish_id)
    if not bom:
        raise HTTPException(status_code=404, detail="该菜品尚无激活的 BOM")
    return _serialize_bom(bom)


@router.get("/dish/{dish_id}/history", response_model=List[BOMOut])
async def get_bom_history(
    dish_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询菜品所有历史 BOM 版本（时间旅行）"""
    svc = BOMService(db)
    boms = await svc.get_bom_history(dish_id)
    return [_serialize_bom(b) for b in boms]


@router.get("/store/{store_id}", response_model=List[BOMOut])
async def list_boms(
    store_id: str,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询门店 BOM 列表"""
    svc = BOMService(db)
    boms = await svc.list_boms(store_id, active_only=active_only)
    return [_serialize_bom(b) for b in boms]


@router.post("/{bom_id}/approve", response_model=BOMOut)
async def approve_bom(
    bom_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审核 BOM 版本（需管理员/厨师长权限）"""
    svc = BOMService(db)
    bom = await svc.approve_bom(bom_id, approver=str(current_user.id))
    if not bom:
        raise HTTPException(status_code=404, detail="BOM 不存在")
    await db.commit()
    return _serialize_bom(bom)


@router.post("/{bom_id}/deactivate")
async def deactivate_bom(
    bom_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """停用 BOM 版本"""
    svc = BOMService(db)
    ok = await svc.deactivate_bom(bom_id)
    if not ok:
        raise HTTPException(status_code=404, detail="BOM 不存在")
    await db.commit()
    return {"message": "BOM 已停用", "bom_id": bom_id}


@router.delete("/{bom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bom(
    bom_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除未审核 BOM"""
    svc = BOMService(db)
    ok = await svc.delete_bom(bom_id)
    if not ok:
        raise HTTPException(status_code=400, detail="BOM 不存在或已审核，无法删除")
    await db.commit()


# ── BOMItem endpoints ─────────────────────────────────────────────────────────

@router.post("/{bom_id}/items/", response_model=BOMItemOut, status_code=status.HTTP_201_CREATED)
async def add_bom_item(
    bom_id: str,
    payload: BOMItemIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """向 BOM 添加食材明细行"""
    svc = BOMService(db)
    item = await svc.add_bom_item(
        bom_id=bom_id,
        ingredient_id=payload.ingredient_id,
        standard_qty=payload.standard_qty,
        unit=payload.unit,
        raw_qty=payload.raw_qty,
        unit_cost=payload.unit_cost,
        waste_factor=payload.waste_factor,
        is_key_ingredient=payload.is_key_ingredient,
        is_optional=payload.is_optional,
        prep_notes=payload.prep_notes,
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=BOMItemOut)
async def update_bom_item(
    item_id: str,
    payload: BOMItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 BOM 食材明细行"""
    svc = BOMService(db)
    item = await svc.update_bom_item(
        item_id=item_id,
        standard_qty=payload.standard_qty,
        raw_qty=payload.raw_qty,
        unit=payload.unit,
        unit_cost=payload.unit_cost,
        waste_factor=payload.waste_factor,
        is_key_ingredient=payload.is_key_ingredient,
        prep_notes=payload.prep_notes,
    )
    if not item:
        raise HTTPException(status_code=404, detail="BOM 明细行不存在")
    await db.commit()
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bom_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 BOM 食材明细行"""
    svc = BOMService(db)
    ok = await svc.remove_bom_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="BOM 明细行不存在")
    await db.commit()


@router.post("/{bom_id}/sync")
async def sync_bom_to_neo4j(
    bom_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发 BOM→Neo4j 本体同步"""
    svc = BOMService(db)
    bom = await svc.get_bom(bom_id)
    if not bom:
        raise HTTPException(status_code=404, detail="BOM 不存在")
    await svc.sync_to_neo4j(bom)
    return {"message": "同步已触发", "bom_id": bom_id, "version": bom.version}


# ── Internal helper ───────────────────────────────────────────────────────────

def _serialize_bom(bom) -> dict:
    """将 BOMTemplate ORM 对象转为可序列化字典"""
    items = []
    for it in (bom.items or []):
        items.append({
            "id": it.id,
            "bom_id": it.bom_id,
            "ingredient_id": it.ingredient_id,
            "standard_qty": float(it.standard_qty),
            "raw_qty": float(it.raw_qty) if it.raw_qty else None,
            "unit": it.unit,
            "unit_cost": it.unit_cost,
            "waste_factor": float(it.waste_factor) if it.waste_factor else 0.0,
            "is_key_ingredient": bool(it.is_key_ingredient),
            "is_optional": bool(it.is_optional),
            "prep_notes": it.prep_notes,
        })
    return {
        "id": bom.id,
        "store_id": bom.store_id,
        "dish_id": bom.dish_id,
        "version": bom.version,
        "effective_date": bom.effective_date,
        "expiry_date": bom.expiry_date,
        "yield_rate": float(bom.yield_rate),
        "standard_portion": float(bom.standard_portion) if bom.standard_portion else None,
        "prep_time_minutes": bom.prep_time_minutes,
        "is_active": bom.is_active,
        "is_approved": bom.is_approved,
        "approved_by": bom.approved_by,
        "approved_at": bom.approved_at,
        "notes": bom.notes,
        "created_by": bom.created_by,
        "items": items,
        "total_cost": bom.total_cost,
    }
