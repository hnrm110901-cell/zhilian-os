"""
损耗事件 API

端点：
  POST  /api/v1/waste-events/                        记录损耗事件
  GET   /api/v1/waste-events/{event_id}              查询事件详情
  GET   /api/v1/waste-events/store/{store_id}        门店事件列表
  POST  /api/v1/waste-events/{event_id}/analyze      手动触发五步推理
  POST  /api/v1/waste-events/{event_id}/verify       人工验证结论
  POST  /api/v1/waste-events/{event_id}/close        关闭事件
  GET   /api/v1/waste-events/store/{store_id}/summary  汇总统计
  GET   /api/v1/waste-events/store/{store_id}/root-causes  根因分布
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.models.waste_event import WasteEventStatus, WasteEventType
from src.services.waste_event_service import WasteEventService

router = APIRouter(prefix="/api/v1/waste-events", tags=["waste_events"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class WasteEventCreateIn(BaseModel):
    store_id: str
    ingredient_id: str = Field(..., description="食材 ID（InventoryItem.id）")
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., max_length=20)
    event_type: WasteEventType = WasteEventType.UNKNOWN
    dish_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    assigned_staff_id: Optional[str] = None
    notes: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    auto_analyze: bool = True


class WasteEventVerifyIn(BaseModel):
    verified_root_cause: str = Field(..., description="人工确认的根因")
    action_taken: Optional[str] = None


class WasteEventOut(BaseModel):
    id: str
    event_id: str
    store_id: str
    event_type: str
    status: str
    ingredient_id: str
    dish_id: Optional[str]
    quantity: float
    unit: str
    theoretical_qty: Optional[float]
    variance_qty: Optional[float]
    variance_pct: Optional[float]
    occurred_at: datetime
    reported_by: Optional[str]
    assigned_staff_id: Optional[str]
    root_cause: Optional[str]
    confidence: Optional[float]
    evidence: Optional[dict]
    scores: Optional[dict]
    action_taken: Optional[str]
    wechat_action_id: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=WasteEventOut, status_code=status.HTTP_201_CREATED)
async def create_waste_event(
    payload: WasteEventCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记录损耗事件（自动触发偏差计算和 Neo4j 同步）"""
    svc = WasteEventService(db)
    event = await svc.create_event(
        store_id=payload.store_id,
        ingredient_id=payload.ingredient_id,
        quantity=payload.quantity,
        unit=payload.unit,
        event_type=payload.event_type,
        dish_id=payload.dish_id,
        occurred_at=payload.occurred_at,
        reported_by=str(current_user.id),
        assigned_staff_id=payload.assigned_staff_id,
        notes=payload.notes,
        photo_urls=payload.photo_urls,
        auto_analyze=payload.auto_analyze,
    )
    await db.commit()
    return _to_out(event)


@router.get("/{event_id}", response_model=WasteEventOut)
async def get_waste_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询损耗事件详情（含推理结论）"""
    svc = WasteEventService(db)
    event = await svc.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="损耗事件不存在")
    return _to_out(event)


@router.get("/store/{store_id}", response_model=List[WasteEventOut])
async def list_store_waste_events(
    store_id: str,
    status: Optional[WasteEventStatus] = Query(None),
    event_type: Optional[WasteEventType] = Query(None),
    dish_id: Optional[str] = Query(None),
    ingredient_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询门店损耗事件列表"""
    svc = WasteEventService(db)
    events = await svc.list_events(
        store_id=store_id,
        status=status,
        event_type=event_type,
        dish_id=dish_id,
        ingredient_id=ingredient_id,
        days=days,
        limit=limit,
        offset=offset,
    )
    return [_to_out(e) for e in events]


@router.post("/{event_id}/analyze")
async def trigger_analysis(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发损耗事件五步推理"""
    svc = WasteEventService(db)
    event = await svc.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="损耗事件不存在")

    try:
        from src.ontology.reasoning import WasteReasoningEngine
        engine = WasteReasoningEngine()
        result = engine.infer_root_cause(event_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推理失败: {e}")

    if result.get("success"):
        updated = await svc.write_back_analysis(
            event_id=event_id,
            root_cause=result.get("root_cause", "unknown"),
            confidence=result.get("confidence", 0.0),
            evidence=result.get("evidence_chain", {}),
            scores=result.get("scores", {}),
        )
        await db.commit()
        return {"message": "推理完成", "result": result, "event": _to_out(updated)}
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "推理失败"))


@router.post("/{event_id}/verify")
async def verify_waste_event(
    event_id: str,
    payload: WasteEventVerifyIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """人工验证推理结论（关闭损耗 → 验证状态，更新规则命中率）"""
    svc = WasteEventService(db)
    event = await svc.verify_event(
        event_id=event_id,
        verified_root_cause=payload.verified_root_cause,
        verifier=str(current_user.id),
        action_taken=payload.action_taken,
    )
    if not event:
        raise HTTPException(status_code=404, detail="损耗事件不存在")
    await db.commit()
    return {"message": "验证完成", "event": _to_out(event)}


@router.post("/{event_id}/close")
async def close_waste_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """关闭损耗事件"""
    svc = WasteEventService(db)
    ok = await svc.close_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="损耗事件不存在")
    await db.commit()
    return {"message": "事件已关闭", "event_id": event_id}


@router.get("/store/{store_id}/summary")
async def get_waste_summary(
    store_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """门店损耗汇总（按食材排行）"""
    svc = WasteEventService(db)
    return await svc.get_store_waste_summary(store_id, days=days)


@router.get("/store/{store_id}/root-causes")
async def get_root_cause_distribution(
    store_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """门店损耗根因分布统计"""
    svc = WasteEventService(db)
    return await svc.get_root_cause_distribution(store_id, days=days)


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _to_out(e: WasteEvent) -> dict:
    return {
        "id": str(e.id),
        "event_id": e.event_id,
        "store_id": e.store_id,
        "event_type": e.event_type.value if hasattr(e.event_type, "value") else e.event_type,
        "status": e.status.value if hasattr(e.status, "value") else e.status,
        "ingredient_id": e.ingredient_id,
        "dish_id": str(e.dish_id) if e.dish_id else None,
        "quantity": float(e.quantity),
        "unit": e.unit,
        "theoretical_qty": float(e.theoretical_qty) if e.theoretical_qty else None,
        "variance_qty": float(e.variance_qty) if e.variance_qty else None,
        "variance_pct": float(e.variance_pct) if e.variance_pct is not None else None,
        "occurred_at": e.occurred_at,
        "reported_by": e.reported_by,
        "assigned_staff_id": e.assigned_staff_id,
        "root_cause": e.root_cause,
        "confidence": e.confidence,
        "evidence": e.evidence,
        "scores": e.scores,
        "action_taken": e.action_taken,
        "wechat_action_id": e.wechat_action_id,
        "notes": e.notes,
        "created_at": e.created_at,
    }
