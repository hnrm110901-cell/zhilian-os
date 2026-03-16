"""
全渠道沽清 API

端点：
  POST /api/v1/soldout/trigger        触发沽清
  POST /api/v1/soldout/restore        恢复上架
  POST /api/v1/soldout/batch          批量沽清
  GET  /api/v1/soldout/list           当前沽清列表
  GET  /api/v1/soldout/available      可售菜品列表
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.soldout_service import SoldoutService

router = APIRouter(prefix="/api/v1/soldout", tags=["soldout"])


# ---------- Schemas ----------


class SoldoutRequest(BaseModel):
    store_id: str
    dish_id: str
    reason: str = ""


class RestoreRequest(BaseModel):
    store_id: str
    dish_id: str


class BatchSoldoutRequest(BaseModel):
    store_id: str
    dish_ids: list[str]
    reason: str = ""


# ---------- Endpoints ----------


@router.post("/trigger")
async def trigger_soldout(
    req: SoldoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CHEF, UserRole.STORE_MANAGER)),
):
    """一键沽清菜品"""
    svc = SoldoutService(db, req.store_id)
    result = await svc.soldout_dish(
        dish_id=req.dish_id,
        reason=req.reason,
        operator=current_user.username if hasattr(current_user, "username") else str(current_user.id),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "沽清失败"))
    await db.commit()
    return result


@router.post("/restore")
async def restore_dish(
    req: RestoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CHEF, UserRole.STORE_MANAGER)),
):
    """恢复上架"""
    svc = SoldoutService(db, req.store_id)
    result = await svc.restore_dish(
        dish_id=req.dish_id,
        operator=current_user.username if hasattr(current_user, "username") else str(current_user.id),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "恢复上架失败"))
    await db.commit()
    return result


@router.post("/batch")
async def batch_soldout(
    req: BatchSoldoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CHEF, UserRole.STORE_MANAGER)),
):
    """批量沽清"""
    if not req.dish_ids:
        raise HTTPException(status_code=400, detail="至少需要一个菜品")
    svc = SoldoutService(db, req.store_id)
    result = await svc.batch_soldout(
        dish_ids=req.dish_ids,
        reason=req.reason,
        operator=current_user.username if hasattr(current_user, "username") else str(current_user.id),
    )
    await db.commit()
    return result


@router.get("/list")
async def get_soldout_list(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CHEF, UserRole.STORE_MANAGER, UserRole.FLOOR_MANAGER)),
):
    """获取当前沽清菜品列表"""
    svc = SoldoutService(db, store_id)
    return await svc.list_soldout()


@router.get("/available")
async def get_available_dishes(
    store_id: str,
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CHEF, UserRole.STORE_MANAGER)),
):
    """获取可售菜品列表（供沽清选择）"""
    svc = SoldoutService(db, store_id)
    return await svc.list_available(keyword=keyword)
