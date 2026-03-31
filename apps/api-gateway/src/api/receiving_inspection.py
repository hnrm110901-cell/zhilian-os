"""
收货验收 API
前缀: /api/v1/receivings
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.receiving_inspection_service import receiving_inspection_service

router = APIRouter(prefix="/api/v1/receivings", tags=["收货验收"])


@router.post("", summary="开始收货")
async def start_receiving(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    开始收货流程，创建一张 in_progress 的收货单

    必填：store_id, receiver_id
    可选：supplier_id, supplier_name, purchase_order_id, invoice_no
    """
    required = ["store_id", "receiver_id"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填字段: {missing}")

    try:
        result = await receiving_inspection_service.start_receiving(
            store_id=data["store_id"],
            receiver_id=data["receiver_id"],
            supplier_id=data.get("supplier_id"),
            supplier_name=data.get("supplier_name"),
            purchase_order_id=data.get("purchase_order_id"),
            invoice_no=data.get("invoice_no"),
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"开始收货失败: {str(e)}")


@router.post("/{receiving_id}/items", summary="录入收货条目")
async def record_item(
    receiving_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    记录单个食材收货情况

    必填：ingredient_id, ingredient_name, unit, received_qty, quality_status
    可选：unit_price_fen, rejected_qty, temperature, expiry_date, batch_no,
           ordered_qty, quality_notes
    """
    required = ["ingredient_id", "ingredient_name", "unit", "received_qty", "quality_status"]
    missing = [f for f in required if data.get(f) is None]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填字段: {missing}")

    # 验证 quality_status 枚举值
    valid_quality = {"pass", "conditional", "reject"}
    if data["quality_status"] not in valid_quality:
        raise HTTPException(
            status_code=400,
            detail=f"quality_status 必须为 {valid_quality} 之一",
        )

    try:
        # expiry_date 转换
        expiry_date = None
        if data.get("expiry_date"):
            from datetime import date as date_type
            expiry_date = date_type.fromisoformat(data["expiry_date"])

        result = await receiving_inspection_service.record_item(
            receiving_id=receiving_id,
            ingredient_id=data["ingredient_id"],
            ingredient_name=data["ingredient_name"],
            unit=data["unit"],
            received_qty=float(data["received_qty"]),
            quality_status=data["quality_status"],
            unit_price_fen=data.get("unit_price_fen"),
            rejected_qty=float(data.get("rejected_qty", 0)),
            temperature=data.get("temperature"),
            expiry_date=expiry_date,
            batch_no=data.get("batch_no"),
            ordered_qty=data.get("ordered_qty"),
            quality_notes=data.get("quality_notes"),
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"录入收货条目失败: {str(e)}")


@router.post("/{receiving_id}/complete", summary="完成收货（触发入库）")
async def complete_receiving(
    receiving_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    完成收货：
    - pass/conditional 条目入库
    - reject 条目不入库
    - 自动创建争议记录（shortage / quality_issue）
    - 计算 total_amount_fen
    - 所有操作在同一事务内

    必填：receiver_id
    """
    receiver_id = data.get("receiver_id")
    if not receiver_id:
        raise HTTPException(status_code=400, detail="缺少必填字段: receiver_id")

    try:
        result = await receiving_inspection_service.complete_receiving(
            receiving_id=receiving_id,
            receiver_id=receiver_id,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"完成收货失败: {str(e)}")


@router.get("", summary="收货记录列表")
async def list_receivings(
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询收货记录列表（分页）"""
    try:
        import uuid
        from datetime import timedelta, datetime
        from sqlalchemy import select, desc, func, and_
        from src.core.database import get_db_session
        from src.models.receiving_inspection import PurchaseReceiving

        async with get_db_session() as session:
            since = datetime.utcnow() - timedelta(days=days)
            store_uuid = uuid.UUID(str(store_id))

            base_where = and_(
                PurchaseReceiving.store_id == store_uuid,
                PurchaseReceiving.created_at >= since,
            )

            count_stmt = select(func.count()).select_from(PurchaseReceiving).where(base_where)
            total = (await session.execute(count_stmt)).scalar_one()

            offset = (page - 1) * page_size
            stmt = (
                select(PurchaseReceiving)
                .where(base_where)
                .order_by(desc(PurchaseReceiving.created_at))
                .limit(page_size)
                .offset(offset)
            )
            r = await session.execute(stmt)
            receivings = r.scalars().all()

            items = [
                {
                    "receiving_id": str(rec.id),
                    "receiving_no": rec.receiving_no,
                    "status": rec.status.value,
                    "supplier_name": rec.supplier_name,
                    "received_at": rec.received_at.isoformat(),
                    "total_amount_fen": rec.total_amount_fen,
                    "total_amount_yuan": round(rec.total_amount_fen / 100, 2),
                }
                for rec in receivings
            ]

        return {"success": True, "data": {"total": total, "page": page, "items": items}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询收货记录失败: {str(e)}")


@router.get("/stats", summary="收货统计")
async def get_receiving_stats(
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    收货统计（供应商质量衡量）：
    - shortage_rate: 短缺率
    - quality_pass_rate: 质检通过率
    - top_dispute_suppliers: 问题最多的供应商
    """
    try:
        result = await receiving_inspection_service.get_receiving_stats(
            store_id=store_id,
            days=days,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询收货统计失败: {str(e)}")


@router.get("/{receiving_id}", summary="收货详情")
async def get_receiving(
    receiving_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取收货单详情（含明细和争议记录）"""
    try:
        import uuid
        from sqlalchemy import select
        from src.core.database import get_db_session
        from src.models.receiving_inspection import (
            PurchaseReceiving,
            PurchaseReceivingItem,
            ReceivingDispute,
        )

        async with get_db_session() as session:
            stmt = select(PurchaseReceiving).where(
                PurchaseReceiving.id == uuid.UUID(str(receiving_id))
            )
            r = await session.execute(stmt)
            receiving = r.scalar_one_or_none()
            if receiving is None:
                raise HTTPException(status_code=404, detail="收货单不存在")

            items_stmt = select(PurchaseReceivingItem).where(
                PurchaseReceivingItem.receiving_id == receiving.id
            )
            items_r = await session.execute(items_stmt)
            items = items_r.scalars().all()

            disputes_stmt = select(ReceivingDispute).where(
                ReceivingDispute.receiving_id == receiving.id
            )
            disputes_r = await session.execute(disputes_stmt)
            disputes = disputes_r.scalars().all()

            data = {
                "receiving_id": str(receiving.id),
                "receiving_no": receiving.receiving_no,
                "store_id": str(receiving.store_id),
                "supplier_name": receiving.supplier_name,
                "status": receiving.status.value,
                "received_at": receiving.received_at.isoformat(),
                "invoice_no": receiving.invoice_no,
                "total_amount_fen": receiving.total_amount_fen,
                "total_amount_yuan": round(receiving.total_amount_fen / 100, 2),
                "notes": receiving.notes,
                "items": [
                    {
                        "item_id": str(i.id),
                        "ingredient_name": i.ingredient_name,
                        "unit": i.unit,
                        "ordered_qty": i.ordered_qty,
                        "received_qty": i.received_qty,
                        "rejected_qty": i.rejected_qty,
                        "quality_status": i.quality_status.value,
                        "quality_notes": i.quality_notes,
                        "temperature": i.temperature,
                        "expiry_date": i.expiry_date.isoformat() if i.expiry_date else None,
                        "batch_no": i.batch_no,
                        "has_shortage": i.has_shortage,
                        "has_quality_issue": i.has_quality_issue,
                        "unit_price_fen": i.unit_price_fen,
                    }
                    for i in items
                ],
                "disputes": [
                    {
                        "dispute_id": str(d.id),
                        "item_id": str(d.item_id),
                        "dispute_type": d.dispute_type.value,
                        "claimed_amount_fen": d.claimed_amount_fen,
                        "resolution": d.resolution.value,
                        "notes": d.notes,
                        "created_at": d.created_at.isoformat(),
                    }
                    for d in disputes
                ],
            }
            return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询收货详情失败: {str(e)}")


@router.post("/{receiving_id}/disputes", summary="提交争议")
async def file_dispute(
    receiving_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    手动提交争议

    必填：item_id, dispute_type（shortage/quality/price/wrong_item）
    可选：claimed_amount_fen, notes
    """
    required = ["item_id", "dispute_type"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填字段: {missing}")

    valid_types = {"shortage", "quality", "price", "wrong_item"}
    if data["dispute_type"] not in valid_types:
        raise HTTPException(
            status_code=400, detail=f"dispute_type 必须为 {valid_types} 之一"
        )

    try:
        result = await receiving_inspection_service.file_dispute(
            receiving_id=receiving_id,
            item_id=data["item_id"],
            dispute_type=data["dispute_type"],
            claimed_amount_fen=data.get("claimed_amount_fen"),
            notes=data.get("notes"),
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交争议失败: {str(e)}")
