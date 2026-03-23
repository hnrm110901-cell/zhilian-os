"""
采购工作台 API 路由

Phase 2.2 功能对等模块 — 采购全生命周期管理接口。
前缀: /api/v1/purchase
"""

from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.purchase_workbench_service import (
    ReceiveItem,
    purchase_workbench_service,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/purchase", tags=["采购工作台"])


# ============================================================
# 请求/响应模型（Pydantic）
# ============================================================

class POItemRequest(BaseModel):
    """采购明细项（请求）"""
    ingredient_id: str = Field(..., description="食材ID")
    ingredient_name: str = Field(..., description="食材名称")
    ordered_qty: float = Field(..., gt=0, description="下单数量")
    unit: str = Field("kg", description="单位")
    unit_price_fen: int = Field(..., ge=0, description="单价（分）")


class CreatePORequest(BaseModel):
    """创建采购单请求"""
    store_id: str = Field(..., description="门店ID")
    supplier_id: str = Field(..., description="供应商ID")
    supplier_name: str = Field(..., description="供应商名称")
    items: List[POItemRequest] = Field(..., min_length=1, description="采购明细")
    note: str = Field("", description="备注")


class ConfirmItemRequest(BaseModel):
    """供应商确认明细"""
    item_id: str = Field(..., description="采购明细ID")
    confirmed_qty: float = Field(..., ge=0, description="确认数量")


class SupplierConfirmRequest(BaseModel):
    """供应商确认请求"""
    confirmed_items: List[ConfirmItemRequest] = Field(..., description="确认明细")


class ReceiveItemRequest(BaseModel):
    """收货明细"""
    item_id: str = Field(..., description="采购明细ID")
    received_qty: float = Field(..., ge=0, description="实收数量")
    unit_price_fen: Optional[int] = Field(None, description="实际单价（分），为空则用下单价")
    quality_ok: bool = Field(True, description="质量是否合格")
    quality_note: str = Field("", description="质量备注")


class ReceiveGoodsRequest(BaseModel):
    """收货请求"""
    received_items: List[ReceiveItemRequest] = Field(..., min_length=1, description="收货明细")


class POItemResponse(BaseModel):
    """采购明细项（响应）"""
    item_id: str
    ingredient_id: str
    ingredient_name: str
    unit: str
    ordered_qty: float
    unit_price_fen: int
    unit_price_yuan: str
    ordered_amount_fen: int
    ordered_amount_yuan: str
    confirmed_qty: float
    received_qty: float
    received_amount_fen: int
    received_amount_yuan: str


class POResponse(BaseModel):
    """采购单响应"""
    order_id: str
    store_id: str
    supplier_id: str
    supplier_name: str
    status: str
    items: List[POItemResponse]
    total_ordered_fen: int
    total_ordered_yuan: str
    total_confirmed_fen: int
    total_confirmed_yuan: str
    total_received_fen: int
    total_received_yuan: str
    created_at: str
    submitted_at: str
    confirmed_at: str
    received_at: str
    reconciled_at: str
    note: str


class ReceiveResultResponse(BaseModel):
    """收货结果响应"""
    order_id: str
    fully_received: bool
    received_items_count: int
    total_received_fen: int
    total_received_yuan: str
    variance_items: List[dict]
    message: str


class ReconcileIssueResponse(BaseModel):
    """对账差异项响应"""
    item_id: str
    ingredient_name: str
    issue_type: str
    expected_value: str
    actual_value: str
    variance_fen: int
    variance_yuan: str


class ReconcileResultResponse(BaseModel):
    """对账结果响应"""
    order_id: str
    is_clean: bool
    total_ordered_fen: int
    total_ordered_yuan: str
    total_received_fen: int
    total_received_yuan: str
    variance_fen: int
    variance_yuan: str
    issues: List[ReconcileIssueResponse]


class SuggestedItemResponse(BaseModel):
    """AI建议采购项响应"""
    ingredient_id: str
    ingredient_name: str
    current_stock: float
    suggested_qty: float
    unit: str
    estimated_unit_price_fen: int
    estimated_unit_price_yuan: str
    estimated_amount_fen: int
    estimated_amount_yuan: str
    reason: str


class SuggestedOrderResponse(BaseModel):
    """AI建议采购单响应"""
    supplier_id: str
    supplier_name: str
    items: List[SuggestedItemResponse]
    total_estimated_fen: int
    total_estimated_yuan: str
    confidence: float
    reasoning: str


class SupplierPerformanceResponse(BaseModel):
    """供应商绩效响应"""
    supplier_id: str
    supplier_name: str
    total_orders: int
    on_time_rate: float
    quality_pass_rate: float
    avg_price_variance_rate: float
    total_amount_fen: int
    total_amount_yuan: str


# ============================================================
# 辅助函数
# ============================================================

def _fen_to_yuan(fen: int) -> str:
    """分转元，保留2位小数，带¥前缀"""
    return f"¥{fen / 100:.2f}"


def _po_to_response(order) -> POResponse:
    """将服务层PurchaseOrder转换为API响应"""
    items = [
        POItemResponse(
            item_id=item.item_id,
            ingredient_id=item.ingredient_id,
            ingredient_name=item.ingredient_name,
            unit=item.unit,
            ordered_qty=item.ordered_qty,
            unit_price_fen=item.unit_price_fen,
            unit_price_yuan=_fen_to_yuan(item.unit_price_fen),
            ordered_amount_fen=item.ordered_amount_fen,
            ordered_amount_yuan=_fen_to_yuan(item.ordered_amount_fen),
            confirmed_qty=item.confirmed_qty,
            received_qty=item.received_qty,
            received_amount_fen=item.received_amount_fen,
            received_amount_yuan=_fen_to_yuan(item.received_amount_fen),
        )
        for item in order.items
    ]
    return POResponse(
        order_id=order.order_id,
        store_id=order.store_id,
        supplier_id=order.supplier_id,
        supplier_name=order.supplier_name,
        status=order.status.value,
        items=items,
        total_ordered_fen=order.total_ordered_fen,
        total_ordered_yuan=_fen_to_yuan(order.total_ordered_fen),
        total_confirmed_fen=order.total_confirmed_fen,
        total_confirmed_yuan=_fen_to_yuan(order.total_confirmed_fen),
        total_received_fen=order.total_received_fen,
        total_received_yuan=_fen_to_yuan(order.total_received_fen),
        created_at=order.created_at,
        submitted_at=order.submitted_at,
        confirmed_at=order.confirmed_at,
        received_at=order.received_at,
        reconciled_at=order.reconciled_at,
        note=order.note,
    )


# ============================================================
# API 路由
# ============================================================

@router.post("/orders", summary="创建采购单")
async def create_purchase_order(req: CreatePORequest):
    """创建采购单（草稿状态）"""
    try:
        items_data = [
            {
                "ingredient_id": item.ingredient_id,
                "ingredient_name": item.ingredient_name,
                "ordered_qty": item.ordered_qty,
                "unit": item.unit,
                "unit_price_fen": item.unit_price_fen,
            }
            for item in req.items
        ]
        order = purchase_workbench_service.create_purchase_order(
            store_id=req.store_id,
            supplier_id=req.supplier_id,
            supplier_name=req.supplier_name,
            items=items_data,
            note=req.note,
        )
        return {"success": True, "data": _po_to_response(order)}
    except Exception as e:
        logger.error("purchase.create_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders", summary="查询采购单列表")
async def list_purchase_orders(
    store_id: str = Query(..., description="门店ID"),
):
    """获取门店所有采购单"""
    try:
        orders = purchase_workbench_service.get_orders(store_id)
        return {
            "success": True,
            "data": [_po_to_response(o) for o in orders],
            "total": len(orders),
        }
    except Exception as e:
        logger.error("purchase.list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_id}/submit", summary="提交采购单")
async def submit_order(order_id: str):
    """提交采购单给供应商"""
    try:
        order = purchase_workbench_service.submit_order(order_id)
        return {"success": True, "data": _po_to_response(order)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("purchase.submit_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_id}/confirm", summary="供应商确认")
async def supplier_confirm(order_id: str, req: SupplierConfirmRequest):
    """供应商确认采购单（可调整数量）"""
    try:
        confirmed_items = [
            {"item_id": item.item_id, "confirmed_qty": item.confirmed_qty}
            for item in req.confirmed_items
        ]
        order = purchase_workbench_service.supplier_confirm(order_id, confirmed_items)
        return {"success": True, "data": _po_to_response(order)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("purchase.confirm_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_id}/receive", summary="收货")
async def receive_goods(order_id: str, req: ReceiveGoodsRequest):
    """录入收货信息（支持分批收货）"""
    try:
        received_items = [
            ReceiveItem(
                item_id=item.item_id,
                received_qty=item.received_qty,
                unit_price_fen=item.unit_price_fen,
                quality_ok=item.quality_ok,
                quality_note=item.quality_note,
            )
            for item in req.received_items
        ]
        result = purchase_workbench_service.receive_goods(order_id, received_items)
        return {
            "success": True,
            "data": ReceiveResultResponse(
                order_id=result.order_id,
                fully_received=result.fully_received,
                received_items_count=result.received_items_count,
                total_received_fen=result.total_received_fen,
                total_received_yuan=_fen_to_yuan(result.total_received_fen),
                variance_items=result.variance_items,
                message=result.message,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("purchase.receive_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_id}/reconcile", summary="对账")
async def reconcile_order(order_id: str):
    """对账：比较下单 vs 实收的数量和金额差异"""
    try:
        result = purchase_workbench_service.reconcile_order(order_id)
        issues = [
            ReconcileIssueResponse(
                item_id=issue.item_id,
                ingredient_name=issue.ingredient_name,
                issue_type=issue.issue_type.value,
                expected_value=issue.expected_value,
                actual_value=issue.actual_value,
                variance_fen=issue.variance_fen,
                variance_yuan=_fen_to_yuan(issue.variance_fen),
            )
            for issue in result.issues
        ]
        return {
            "success": True,
            "data": ReconcileResultResponse(
                order_id=result.order_id,
                is_clean=result.is_clean,
                total_ordered_fen=result.total_ordered_fen,
                total_ordered_yuan=_fen_to_yuan(result.total_ordered_fen),
                total_received_fen=result.total_received_fen,
                total_received_yuan=_fen_to_yuan(result.total_received_fen),
                variance_fen=result.variance_fen,
                variance_yuan=_fen_to_yuan(result.variance_fen),
                issues=issues,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("purchase.reconcile_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions/{store_id}", summary="AI采购建议")
async def get_suggested_orders(store_id: str):
    """基于库存和消耗预测，获取AI智能采购建议"""
    try:
        suggestions = purchase_workbench_service.get_suggested_orders(store_id)
        data = [
            SuggestedOrderResponse(
                supplier_id=s.supplier_id,
                supplier_name=s.supplier_name,
                items=[
                    SuggestedItemResponse(
                        ingredient_id=item.ingredient_id,
                        ingredient_name=item.ingredient_name,
                        current_stock=item.current_stock,
                        suggested_qty=item.suggested_qty,
                        unit=item.unit,
                        estimated_unit_price_fen=item.estimated_unit_price_fen,
                        estimated_unit_price_yuan=_fen_to_yuan(item.estimated_unit_price_fen),
                        estimated_amount_fen=item.estimated_amount_fen,
                        estimated_amount_yuan=_fen_to_yuan(item.estimated_amount_fen),
                        reason=item.reason,
                    )
                    for item in s.items
                ],
                total_estimated_fen=s.total_estimated_fen,
                total_estimated_yuan=_fen_to_yuan(s.total_estimated_fen),
                confidence=s.confidence,
                reasoning=s.reasoning,
            )
            for s in suggestions
        ]
        return {"success": True, "data": data, "total": len(data)}
    except Exception as e:
        logger.error("purchase.suggestions_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suppliers/{supplier_id}/performance", summary="供应商绩效")
async def get_supplier_performance(supplier_id: str):
    """获取供应商历史绩效数据"""
    try:
        perf = purchase_workbench_service.get_supplier_performance(supplier_id)
        return {
            "success": True,
            "data": SupplierPerformanceResponse(
                supplier_id=perf.supplier_id,
                supplier_name=perf.supplier_name,
                total_orders=perf.total_orders,
                on_time_rate=perf.on_time_rate,
                quality_pass_rate=perf.quality_pass_rate,
                avg_price_variance_rate=perf.avg_price_variance_rate,
                total_amount_fen=perf.total_amount_fen,
                total_amount_yuan=_fen_to_yuan(perf.total_amount_fen),
            ),
        }
    except Exception as e:
        logger.error("purchase.performance_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
