"""电子发票 API — 开票/红冲/作废/查询"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.e_invoice_service import EInvoiceService

router = APIRouter(prefix="/e-invoices", tags=["e-invoices"])


class InvoiceItemRequest(BaseModel):
    item_name: str
    item_code: Optional[str] = None
    specification: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[int] = None
    unit_price_fen: Optional[int] = None
    amount_fen: int
    tax_rate: int = 600
    tax_amount_fen: int = 0


class CreateInvoiceRequest(BaseModel):
    brand_id: str
    buyer_name: str
    buyer_tax_number: Optional[str] = None
    seller_name: str
    seller_tax_number: str
    total_amount_fen: int
    tax_amount_fen: int = 0
    items: List[InvoiceItemRequest]
    invoice_type: str = "normal_electronic"
    platform: str = "nuonuo"
    store_id: Optional[str] = None
    order_id: Optional[str] = None
    remark: Optional[str] = None


class CallbackRequest(BaseModel):
    serial_no: str
    invoice_code: str
    invoice_number: str
    pdf_url: Optional[str] = None
    status: str = "issued"


@router.post("")
async def create_invoice(
    req: CreateInvoiceRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """创建发票（草稿）"""
    result = await EInvoiceService.create_invoice(
        session,
        brand_id=req.brand_id,
        buyer_name=req.buyer_name,
        buyer_tax_number=req.buyer_tax_number,
        seller_name=req.seller_name,
        seller_tax_number=req.seller_tax_number,
        total_amount_fen=req.total_amount_fen,
        tax_amount_fen=req.tax_amount_fen,
        items=[item.model_dump() for item in req.items],
        invoice_type=req.invoice_type,
        platform=req.platform,
        store_id=req.store_id,
        order_id=req.order_id,
        remark=req.remark,
    )
    await session.commit()
    return result


@router.post("/{invoice_id}/submit")
async def submit_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """提交开票"""
    try:
        result = await EInvoiceService.submit_invoice(session, invoice_id)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/void")
async def void_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """作废发票"""
    try:
        result = await EInvoiceService.void_invoice(session, invoice_id)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/callback")
async def invoice_callback(
    req: CallbackRequest,
    session: AsyncSession = Depends(get_db),
):
    """开票平台回调（Webhook，无需鉴权）"""
    try:
        result = await EInvoiceService.handle_callback(
            session,
            platform_serial_no=req.serial_no,
            invoice_code=req.invoice_code,
            invoice_number=req.invoice_number,
            pdf_url=req.pdf_url,
            status=req.status,
        )
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("")
async def list_invoices(
    brand_id: str = Query(...),
    status: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """发票列表"""
    return await EInvoiceService.list_invoices(
        session,
        brand_id=brand_id,
        status=status,
        store_id=store_id,
        limit=limit,
        offset=offset,
    )


@router.get("/stats")
async def invoice_stats(
    brand_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """发票统计"""
    return await EInvoiceService.get_stats(session, brand_id)
