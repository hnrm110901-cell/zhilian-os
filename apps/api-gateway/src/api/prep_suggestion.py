"""
智能备料建议 API

端点：
  POST /api/v1/prep-suggestion/generate     生成备料建议
  POST /api/v1/prep-suggestion/confirm       确认建议 → 生成采购单
  GET  /api/v1/prep-suggestion/history       历史查询
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.prep_suggestion_service import PrepSuggestionService

router = APIRouter(prefix="/api/v1/prep-suggestion", tags=["prep-suggestion"])


# ---------- Schemas ----------


class GenerateRequest(BaseModel):
    store_id: str
    target_date: Optional[date] = None


class ConfirmItem(BaseModel):
    ingredient_id: str
    qty: float


class ConfirmRequest(BaseModel):
    store_id: str
    items: list[ConfirmItem]
    notes: str = ""


# ---------- Endpoints ----------


@router.post("/generate")
async def generate_suggestion(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER, UserRole.CHEF)),
):
    """生成智能备料建议单"""
    svc = PrepSuggestionService(db, req.store_id)
    result = await svc.generate_suggestions(req.target_date)
    return result


@router.post("/confirm")
async def confirm_suggestion(
    req: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER, UserRole.CHEF)),
):
    """确认备料建议并生成采购申请单"""
    if not req.items:
        raise HTTPException(status_code=400, detail="至少需要一项食材")

    svc = PrepSuggestionService(db, req.store_id)
    result = await svc.confirm_suggestion(
        suggestion_items=[item.model_dump() for item in req.items],
        created_by=current_user.username if hasattr(current_user, "username") else str(current_user.id),
        notes=req.notes,
    )
    await db.commit()
    return result


@router.get("/history")
async def get_suggestion_history(
    store_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER, UserRole.CHEF)),
):
    """查询备料建议生成的采购单历史"""
    svc = PrepSuggestionService(db, store_id)
    return await svc.list_history(limit=limit)
