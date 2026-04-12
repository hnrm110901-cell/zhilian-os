"""
POS收银 API 路由

Phase 2.2 功能对等模块 — 轻量POS收银接口。
前缀: /api/v1/pos-terminal
"""

from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.pos_terminal_service import (
    BillStatus,
    DiscountType,
    PaymentMethod,
    pos_terminal_service,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/pos-terminal", tags=["pos-terminal"])


# ============================================================
# 请求/响应模型（Pydantic）
# ============================================================

class OpenBillRequest(BaseModel):
    """开台请求"""
    store_id: str = Field(..., description="门店ID")
    table_number: str = Field(..., description="桌号")
    waiter_id: str = Field(..., description="服务员ID")


class AddItemRequest(BaseModel):
    """加菜请求"""
    dish_id: str = Field(..., description="菜品ID")
    dish_name: str = Field(..., description="菜品名称")
    quantity: int = Field(..., ge=1, description="数量")
    unit_price_fen: int = Field(..., ge=0, description="单价（分）")
    specification: str = Field("", description="规格（如：大份、小份）")
    methods: str = Field("", description="做法（如：微辣、去冰）")


class ApplyDiscountRequest(BaseModel):
    """折扣请求"""
    discount_type: DiscountType = Field(..., description="折扣类型: percentage/fixed_amount/coupon")
    discount_value: int = Field(..., description="折扣值（percentage:85=85折; fixed_amount/coupon:分）")
    description: str = Field("", description="折扣说明")


class SettleBillRequest(BaseModel):
    """结账请求"""
    payment_method: PaymentMethod = Field(..., description="支付方式")
    amount_fen: int = Field(..., ge=0, description="实收金额（分）")


class VoidBillRequest(BaseModel):
    """作废请求"""
    reason: str = Field(..., min_length=1, description="作废原因")


class BillItemResponse(BaseModel):
    """账单明细响应"""
    item_id: str
    dish_id: str
    dish_name: str
    quantity: int
    unit_price_fen: int
    unit_price_yuan: str           # 单价（元，展示用）
    subtotal_fen: int
    subtotal_yuan: str             # 小计（元，展示用）
    specification: str
    methods: str
    added_at: str


class BillResponse(BaseModel):
    """账单响应"""
    bill_id: str
    store_id: str
    table_number: str
    waiter_id: str
    status: str
    items: List[BillItemResponse]
    subtotal_fen: int
    subtotal_yuan: str
    discount_fen: int
    discount_yuan: str
    total_fen: int
    total_yuan: str                # 应收金额（元，API边界转换）
    created_at: str
    settled_at: str
    payment_method: Optional[str] = None
    void_reason: str = ""


class BillSummaryResponse(BaseModel):
    """账单汇总响应"""
    bill_id: str
    subtotal_fen: int
    subtotal_yuan: str
    discount_fen: int
    discount_yuan: str
    total_fen: int
    total_yuan: str
    item_count: int


class SettlementResponse(BaseModel):
    """结账响应"""
    bill_id: str
    success: bool
    total_fen: int
    total_yuan: str
    paid_fen: int
    paid_yuan: str
    change_fen: int
    change_yuan: str
    payment_method: str
    settled_at: str
    message: str


# ============================================================
# 辅助函数：分→元转换（仅在API边界使用）
# ============================================================

def _fen_to_yuan(fen: int) -> str:
    """分转元，保留2位小数，带¥前缀"""
    return f"¥{fen / 100:.2f}"


def _bill_to_response(bill) -> BillResponse:
    """将服务层Bill转换为API响应"""
    items = [
        BillItemResponse(
            item_id=item.item_id,
            dish_id=item.dish_id,
            dish_name=item.dish_name,
            quantity=item.quantity,
            unit_price_fen=item.unit_price_fen,
            unit_price_yuan=_fen_to_yuan(item.unit_price_fen),
            subtotal_fen=item.subtotal_fen,
            subtotal_yuan=_fen_to_yuan(item.subtotal_fen),
            specification=item.specification,
            methods=item.methods,
            added_at=item.added_at,
        )
        for item in bill.items
    ]
    return BillResponse(
        bill_id=bill.bill_id,
        store_id=bill.store_id,
        table_number=bill.table_number,
        waiter_id=bill.waiter_id,
        status=bill.status.value,
        items=items,
        subtotal_fen=bill.subtotal_fen,
        subtotal_yuan=_fen_to_yuan(bill.subtotal_fen),
        discount_fen=bill.discount_fen,
        discount_yuan=_fen_to_yuan(bill.discount_fen),
        total_fen=bill.total_fen,
        total_yuan=_fen_to_yuan(bill.total_fen),
        created_at=bill.created_at,
        settled_at=bill.settled_at,
        payment_method=bill.payment_method.value if bill.payment_method else None,
        void_reason=bill.void_reason,
    )


# ============================================================
# API 路由
# ============================================================

@router.post("/bills", summary="开台/开单")
async def open_bill(req: OpenBillRequest):
    """为指定门店的桌号创建一张新账单"""
    try:
        bill = pos_terminal_service.open_bill(
            store_id=req.store_id,
            table_number=req.table_number,
            waiter_id=req.waiter_id,
        )
        return {"success": True, "data": _bill_to_response(bill)}
    except Exception as e:
        logger.error("pos.open_bill_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bills", summary="查询门店活跃账单")
async def list_active_bills(
    store_id: str = Query(..., description="门店ID"),
):
    """获取门店所有未结账的账单"""
    try:
        bills = pos_terminal_service.get_active_bills(store_id)
        return {
            "success": True,
            "data": [_bill_to_response(b) for b in bills],
            "total": len(bills),
        }
    except Exception as e:
        logger.error("pos.list_bills_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bills/{bill_id}", summary="账单详情")
async def get_bill_detail(bill_id: str):
    """获取指定账单的完整详情"""
    try:
        detail = pos_terminal_service.get_bill_detail(bill_id)
        bill_resp = _bill_to_response(detail.bill)
        summary = BillSummaryResponse(
            bill_id=detail.summary.bill_id,
            subtotal_fen=detail.summary.subtotal_fen,
            subtotal_yuan=_fen_to_yuan(detail.summary.subtotal_fen),
            discount_fen=detail.summary.discount_fen,
            discount_yuan=_fen_to_yuan(detail.summary.discount_fen),
            total_fen=detail.summary.total_fen,
            total_yuan=_fen_to_yuan(detail.summary.total_fen),
            item_count=detail.summary.item_count,
        )
        return {"success": True, "data": {"bill": bill_resp, "summary": summary}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("pos.get_detail_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bills/{bill_id}/items", summary="加菜")
async def add_item(bill_id: str, req: AddItemRequest):
    """向账单中添加菜品"""
    try:
        item = pos_terminal_service.add_item(
            bill_id=bill_id,
            dish_id=req.dish_id,
            dish_name=req.dish_name,
            quantity=req.quantity,
            unit_price_fen=req.unit_price_fen,
            specification=req.specification,
            methods=req.methods,
        )
        return {
            "success": True,
            "data": BillItemResponse(
                item_id=item.item_id,
                dish_id=item.dish_id,
                dish_name=item.dish_name,
                quantity=item.quantity,
                unit_price_fen=item.unit_price_fen,
                unit_price_yuan=_fen_to_yuan(item.unit_price_fen),
                subtotal_fen=item.subtotal_fen,
                subtotal_yuan=_fen_to_yuan(item.subtotal_fen),
                specification=item.specification,
                methods=item.methods,
                added_at=item.added_at,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("pos.add_item_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bills/{bill_id}/items/{item_id}", summary="退菜/删除菜品")
async def remove_item(bill_id: str, item_id: str):
    """从账单中移除指定菜品"""
    try:
        pos_terminal_service.remove_item(bill_id, item_id)
        return {"success": True, "message": "菜品已移除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("pos.remove_item_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bills/{bill_id}/discount", summary="应用折扣")
async def apply_discount(bill_id: str, req: ApplyDiscountRequest):
    """对账单应用折扣（折扣/满减/优惠券）"""
    try:
        summary = pos_terminal_service.apply_discount(
            bill_id=bill_id,
            discount_type=req.discount_type,
            discount_value=req.discount_value,
            description=req.description,
        )
        return {
            "success": True,
            "data": BillSummaryResponse(
                bill_id=summary.bill_id,
                subtotal_fen=summary.subtotal_fen,
                subtotal_yuan=_fen_to_yuan(summary.subtotal_fen),
                discount_fen=summary.discount_fen,
                discount_yuan=_fen_to_yuan(summary.discount_fen),
                total_fen=summary.total_fen,
                total_yuan=_fen_to_yuan(summary.total_fen),
                item_count=summary.item_count,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("pos.apply_discount_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bills/{bill_id}/settle", summary="结账")
async def settle_bill(bill_id: str, req: SettleBillRequest):
    """结账并记录支付方式"""
    try:
        result = pos_terminal_service.settle_bill(
            bill_id=bill_id,
            payment_method=req.payment_method,
            amount_fen=req.amount_fen,
        )
        return {
            "success": True,
            "data": SettlementResponse(
                bill_id=result.bill_id,
                success=result.success,
                total_fen=result.total_fen,
                total_yuan=_fen_to_yuan(result.total_fen),
                paid_fen=result.paid_fen,
                paid_yuan=_fen_to_yuan(result.paid_fen),
                change_fen=result.change_fen,
                change_yuan=_fen_to_yuan(result.change_fen),
                payment_method=result.payment_method.value,
                settled_at=result.settled_at,
                message=result.message,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("pos.settle_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bills/{bill_id}/void", summary="作废账单")
async def void_bill(bill_id: str, req: VoidBillRequest):
    """作废未结账的账单"""
    try:
        pos_terminal_service.void_bill(bill_id, req.reason)
        return {"success": True, "message": "账单已作废"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("pos.void_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
