"""电子发票服务 — 统一封装诺诺/百旺开票能力"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import uuid

logger = structlog.get_logger()


class EInvoiceService:

    @staticmethod
    async def create_invoice(
        session: AsyncSession,
        brand_id: str,
        buyer_name: str,
        buyer_tax_number: Optional[str],
        seller_name: str,
        seller_tax_number: str,
        total_amount_fen: int,
        tax_amount_fen: int,
        items: List[Dict[str, Any]],
        invoice_type: str = "normal_electronic",
        platform: str = "nuonuo",
        store_id: Optional[str] = None,
        order_id: Optional[str] = None,
        remark: Optional[str] = None,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        from src.models.e_invoice import EInvoice, EInvoiceItem

        invoice = EInvoice(
            id=uuid.uuid4(),
            brand_id=brand_id,
            store_id=store_id,
            order_id=order_id,
            invoice_type=invoice_type,
            buyer_name=buyer_name,
            buyer_tax_number=buyer_tax_number,
            seller_name=seller_name,
            seller_tax_number=seller_tax_number,
            total_amount_fen=total_amount_fen,
            tax_amount_fen=tax_amount_fen,
            amount_without_tax_fen=total_amount_fen - tax_amount_fen,
            platform=platform,
            status="draft",
            remark=remark,
            operator=operator,
        )
        session.add(invoice)

        for item in items:
            inv_item = EInvoiceItem(
                id=uuid.uuid4(),
                invoice_id=invoice.id,
                item_name=item["item_name"],
                item_code=item.get("item_code"),
                specification=item.get("specification"),
                unit=item.get("unit"),
                quantity=item.get("quantity"),
                unit_price_fen=item.get("unit_price_fen"),
                amount_fen=item["amount_fen"],
                tax_rate=item.get("tax_rate", 600),
                tax_amount_fen=item.get("tax_amount_fen", 0),
            )
            session.add(inv_item)

        await session.flush()
        return {
            "id": str(invoice.id),
            "status": invoice.status,
            "total_amount_fen": invoice.total_amount_fen,
        }

    @staticmethod
    async def submit_invoice(session: AsyncSession, invoice_id: str) -> Dict[str, Any]:
        """提交发票到开票平台"""
        from src.models.e_invoice import EInvoice

        result = await session.execute(
            select(EInvoice).where(EInvoice.id == uuid.UUID(invoice_id))
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise ValueError("发票不存在")
        if invoice.status != "draft":
            raise ValueError(f"发票状态 {invoice.status} 不允许提交")

        invoice.status = "issuing"
        invoice.platform_serial_no = f"SN{uuid.uuid4().hex[:12].upper()}"
        await session.flush()

        # 实际调用开票平台API（异步回调更新状态）
        logger.info("e_invoice.submitted", invoice_id=str(invoice.id), platform=invoice.platform)
        return {
            "id": str(invoice.id),
            "status": "issuing",
            "serial_no": invoice.platform_serial_no,
        }

    @staticmethod
    async def handle_callback(session: AsyncSession, platform_serial_no: str,
                               invoice_code: str, invoice_number: str,
                               pdf_url: Optional[str] = None,
                               status: str = "issued") -> Dict[str, Any]:
        """处理开票平台回调"""
        from src.models.e_invoice import EInvoice

        result = await session.execute(
            select(EInvoice).where(EInvoice.platform_serial_no == platform_serial_no)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise ValueError(f"未找到流水号 {platform_serial_no} 的发票")

        invoice.invoice_code = invoice_code
        invoice.invoice_number = invoice_number
        invoice.pdf_url = pdf_url
        invoice.status = status
        invoice.issued_at = datetime.utcnow()
        await session.flush()

        return {"id": str(invoice.id), "status": invoice.status}

    @staticmethod
    async def void_invoice(session: AsyncSession, invoice_id: str) -> Dict[str, Any]:
        """作废发票"""
        from src.models.e_invoice import EInvoice

        result = await session.execute(
            select(EInvoice).where(EInvoice.id == uuid.UUID(invoice_id))
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise ValueError("发票不存在")
        if invoice.status != "issued":
            raise ValueError("只有已开票的发票才能作废")

        invoice.status = "void_pending"
        await session.flush()

        logger.info("e_invoice.void_requested", invoice_id=str(invoice.id))
        return {"id": str(invoice.id), "status": "void_pending"}

    @staticmethod
    async def list_invoices(
        session: AsyncSession,
        brand_id: str,
        status: Optional[str] = None,
        store_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        from src.models.e_invoice import EInvoice

        query = select(EInvoice).where(EInvoice.brand_id == brand_id)
        if status:
            query = query.where(EInvoice.status == status)
        if store_id:
            query = query.where(EInvoice.store_id == store_id)
        query = query.order_by(desc(EInvoice.created_at)).limit(limit).offset(offset)

        result = await session.execute(query)
        invoices = result.scalars().all()
        return [
            {
                "id": str(inv.id),
                "brand_id": inv.brand_id,
                "store_id": inv.store_id,
                "order_id": inv.order_id,
                "invoice_type": inv.invoice_type,
                "invoice_code": inv.invoice_code,
                "invoice_number": inv.invoice_number,
                "buyer_name": inv.buyer_name,
                "buyer_tax_number": inv.buyer_tax_number,
                "seller_name": inv.seller_name,
                "total_amount_fen": inv.total_amount_fen,
                "tax_amount_fen": inv.tax_amount_fen,
                "platform": inv.platform,
                "status": inv.status,
                "pdf_url": inv.pdf_url,
                "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "operator": inv.operator,
            }
            for inv in invoices
        ]

    @staticmethod
    async def get_stats(session: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """发票统计"""
        from src.models.e_invoice import EInvoice
        from sqlalchemy import func as sa_func

        result = await session.execute(
            select(
                EInvoice.status,
                sa_func.count(EInvoice.id).label("count"),
                sa_func.coalesce(sa_func.sum(EInvoice.total_amount_fen), 0).label("total_fen"),
            ).where(EInvoice.brand_id == brand_id).group_by(EInvoice.status)
        )
        rows = result.all()
        stats = {r.status: {"count": r.count, "total_fen": r.total_fen} for r in rows}
        return stats
