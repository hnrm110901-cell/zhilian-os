"""
门店间调拨 API
前缀: /api/v1/transfers
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.inter_store_transfer_service import inter_store_transfer_service

router = APIRouter(prefix="/api/v1/transfers", tags=["门店间调拨"])


@router.post("", summary="创建调拨申请")
async def create_transfer(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    创建门店间调拨申请

    必填字段：
    - from_store_id: 调出门店ID
    - to_store_id: 调入门店ID
    - brand_id: 品牌ID（必须同品牌）
    - items: 调拨明细列表 [{ingredient_id, ingredient_name, unit, requested_qty, unit_cost_fen?}]
    - requester_id: 申请人ID
    """
    required = ["from_store_id", "to_store_id", "brand_id", "items", "requester_id"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填字段: {missing}")

    try:
        result = await inter_store_transfer_service.create_transfer_request(
            from_store_id=data["from_store_id"],
            to_store_id=data["to_store_id"],
            brand_id=data["brand_id"],
            items=data["items"],
            requester_id=data["requester_id"],
            notes=data.get("notes"),
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建调拨申请失败: {str(e)}")


@router.get("", summary="调拨列表")
async def list_transfers(
    store_id: str = Query(..., description="门店ID"),
    direction: str = Query("inbound", description="inbound=待收货 / outbound=待发货"),
    history: bool = Query(False, description="是否查询历史（按日期范围）"),
    days: int = Query(30, ge=1, le=365, description="历史查询天数"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    调拨列表
    - direction=inbound: 我是调入方，待收货的
    - direction=outbound: 我是调出方，待发货的
    - history=true: 查询历史记录（分页）
    """
    try:
        if history:
            result = await inter_store_transfer_service.get_transfer_history(
                store_id=store_id,
                days=days,
                page=page,
                page_size=page_size,
            )
        else:
            items = await inter_store_transfer_service.get_pending_transfers(
                store_id=store_id,
                direction=direction,
            )
            result = {"items": items, "total": len(items)}
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询调拨列表失败: {str(e)}")


@router.get("/{transfer_id}", summary="调拨详情")
async def get_transfer(
    transfer_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取调拨单详情"""
    try:
        result = await inter_store_transfer_service.get_transfer_history(
            store_id="00000000-0000-0000-0000-000000000000",  # 查单条时绕过 store 过滤
            days=3650,
            page=1,
            page_size=1,
        )
        # 简单实现：直接用单例服务的内部方法
        from sqlalchemy import select
        import uuid
        from src.core.database import get_db_session
        from src.models.inter_store_transfer import InterStoreTransferRequest, InterStoreTransferItem

        async with get_db_session() as session:
            stmt = select(InterStoreTransferRequest).where(
                InterStoreTransferRequest.id == uuid.UUID(str(transfer_id))
            )
            r = await session.execute(stmt)
            transfer = r.scalar_one_or_none()
            if transfer is None:
                raise HTTPException(status_code=404, detail="调拨单不存在")

            items_stmt = select(InterStoreTransferItem).where(
                InterStoreTransferItem.transfer_id == transfer.id
            )
            items_r = await session.execute(items_stmt)
            items = items_r.scalars().all()

            data = inter_store_transfer_service._format_transfer(transfer)
            data["items"] = [
                {
                    "item_id": str(i.id),
                    "ingredient_id": str(i.ingredient_id),
                    "ingredient_name": i.ingredient_name,
                    "unit": i.unit,
                    "requested_qty": i.requested_qty,
                    "dispatched_qty": i.dispatched_qty,
                    "received_qty": i.received_qty,
                    "unit_cost_fen": i.unit_cost_fen,
                    "qty_variance": i.qty_variance,
                    "variance_reason": i.variance_reason,
                }
                for i in items
            ]
            return {"success": True, "data": data}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询调拨详情失败: {str(e)}")


@router.post("/{transfer_id}/approve", summary="审批调拨")
async def approve_transfer(
    transfer_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    审批调拨申请（pending -> approved）

    必填：approver_id
    """
    approver_id = data.get("approver_id")
    if not approver_id:
        raise HTTPException(status_code=400, detail="缺少必填字段: approver_id")

    try:
        result = await inter_store_transfer_service.approve_transfer(
            transfer_id=transfer_id,
            approver_id=approver_id,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"审批失败: {str(e)}")


@router.post("/{transfer_id}/dispatch", summary="确认发货")
async def dispatch_transfer(
    transfer_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    确认发货（approved -> dispatched），同时从调出库扣减库存

    必填：actual_items [{ingredient_name, dispatched_qty}]
    """
    actual_items = data.get("actual_items")
    if not actual_items:
        raise HTTPException(status_code=400, detail="缺少必填字段: actual_items")

    try:
        result = await inter_store_transfer_service.dispatch_transfer(
            transfer_id=transfer_id,
            actual_items=actual_items,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发货操作失败: {str(e)}")


@router.post("/{transfer_id}/receive", summary="确认收货")
async def receive_transfer(
    transfer_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    确认收货（dispatched -> received/partial），增加调入库库存

    必填：received_items [{ingredient_name, received_qty, variance_reason?}]
    """
    received_items = data.get("received_items")
    if not received_items:
        raise HTTPException(status_code=400, detail="缺少必填字段: received_items")

    try:
        result = await inter_store_transfer_service.receive_transfer(
            transfer_id=transfer_id,
            received_items=received_items,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"收货操作失败: {str(e)}")
