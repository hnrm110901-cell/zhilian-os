"""
供应商B2B采购单 API
前缀: /api/v1/supplier-b2b
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.supplier_b2b_service import supplier_b2b_service

router = APIRouter(prefix="/supplier-b2b", tags=["供应商B2B"])


@router.post("/orders")
async def create_order(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """创建采购单（含明细行）"""
    required = ["brand_id", "supplier_id", "supplier_name", "items"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")

    if not data["items"] or len(data["items"]) == 0:
        raise HTTPException(status_code=400, detail="至少需要一项采购明细")

    try:
        order = await supplier_b2b_service.create_order(db, data)
        await db.commit()
        return {"success": True, "data": order}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建采购单失败: {str(e)}")


@router.get("/orders")
async def list_orders(
    brand_id: str = Query(..., description="品牌ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    supplier_id: Optional[str] = Query(None, description="供应商ID筛选"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询采购单列表"""
    try:
        result = await supplier_b2b_service.list_orders(db, brand_id, page, page_size, status, supplier_id)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询采购单失败: {str(e)}")


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取采购单详情"""
    result = await supplier_b2b_service.get_order(db, order_id)
    if not result:
        raise HTTPException(status_code=404, detail="采购单不存在")
    return {"success": True, "data": result}


@router.post("/orders/{order_id}/submit")
async def submit_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """提交采购单给供应商"""
    try:
        result = await supplier_b2b_service.submit_order(db, order_id)
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"提交采购单失败: {str(e)}")


@router.post("/orders/{order_id}/receive")
async def receive_order(
    order_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """收货确认"""
    received_items = data.get("received_items", [])
    try:
        result = await supplier_b2b_service.receive_order(db, order_id, received_items)
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"收货失败: {str(e)}")


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    data: Dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """取消采购单"""
    reason = data.get("reason")
    try:
        result = await supplier_b2b_service.cancel_order(db, order_id, reason)
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"取消采购单失败: {str(e)}")


@router.get("/stats")
async def get_stats(
    brand_id: str = Query(..., description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """采购单统计概览"""
    try:
        result = await supplier_b2b_service.get_stats(db, brand_id)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")
