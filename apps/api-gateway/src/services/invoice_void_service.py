"""
发票红冲/作废服务
管理发票作废（未跨月）和红冲（已跨月），记录操作历史
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class VoidType(str, Enum):
    """作废类型"""
    VOID = "void"        # 作废（当月发票）
    RED_OFFSET = "red"   # 红冲（跨月/已认证发票）


class InvoiceStatus(str, Enum):
    NORMAL = "normal"
    VOIDED = "voided"
    RED_OFFSET = "red_offset"


@dataclass
class InvoiceRecord:
    """发票记录"""
    invoice_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    invoice_no: str = ""          # 发票号码
    invoice_code: str = ""        # 发票代码
    order_id: str = ""
    amount_fen: int = 0           # 含税金额（分）
    tax_fen: int = 0              # 税额（分）
    buyer_name: str = ""
    buyer_tax_no: str = ""
    issue_date: Optional[datetime] = None
    status: InvoiceStatus = InvoiceStatus.NORMAL

    @property
    def amount_yuan(self) -> float:
        return round(self.amount_fen / 100, 2)

    @property
    def tax_yuan(self) -> float:
        return round(self.tax_fen / 100, 2)


@dataclass
class VoidRecord:
    """作废/红冲操作记录"""
    void_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    invoice_id: str = ""
    void_type: VoidType = VoidType.VOID
    reason: str = ""
    operator_id: str = ""
    # 红冲时关联的红字发票
    red_invoice_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InvoiceVoidService:
    """发票红冲/作废服务"""

    def __init__(self):
        self._invoices: Dict[str, InvoiceRecord] = {}
        self._void_records: List[VoidRecord] = []

    def register_invoice(self, invoice: InvoiceRecord) -> InvoiceRecord:
        """注册发票（供后续作废/红冲使用）"""
        self._invoices[invoice.invoice_id] = invoice
        return invoice

    def void_invoice(
        self,
        invoice_id: str,
        reason: str,
        operator_id: str = "",
    ) -> VoidRecord:
        """
        作废发票（仅当月未认证的发票可作废）
        """
        invoice = self._get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.NORMAL:
            raise ValueError(f"发票状态不允许作废: {invoice.status.value}")
        # 检查是否当月
        now = datetime.now(timezone.utc)
        if invoice.issue_date and (
            invoice.issue_date.year != now.year or invoice.issue_date.month != now.month
        ):
            raise ValueError("跨月发票不能作废，请使用红冲")

        invoice.status = InvoiceStatus.VOIDED
        record = VoidRecord(
            invoice_id=invoice_id,
            void_type=VoidType.VOID,
            reason=reason,
            operator_id=operator_id,
        )
        self._void_records.append(record)
        logger.info("发票已作废", invoice_id=invoice_id, amount_yuan=invoice.amount_yuan)
        return record

    def red_invoice(
        self,
        invoice_id: str,
        reason: str,
        operator_id: str = "",
    ) -> Dict:
        """
        红冲发票：生成一张等额负数的红字发票来冲抵原发票
        """
        invoice = self._get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.NORMAL:
            raise ValueError(f"发票状态不允许红冲: {invoice.status.value}")

        # 生成红字发票
        red_inv = InvoiceRecord(
            store_id=invoice.store_id,
            invoice_no=f"RED-{invoice.invoice_no}",
            invoice_code=invoice.invoice_code,
            order_id=invoice.order_id,
            amount_fen=-invoice.amount_fen,  # 负数金额
            tax_fen=-invoice.tax_fen,
            buyer_name=invoice.buyer_name,
            buyer_tax_no=invoice.buyer_tax_no,
            issue_date=datetime.now(timezone.utc),
            status=InvoiceStatus.NORMAL,
        )
        self._invoices[red_inv.invoice_id] = red_inv

        # 标记原发票
        invoice.status = InvoiceStatus.RED_OFFSET
        record = VoidRecord(
            invoice_id=invoice_id,
            void_type=VoidType.RED_OFFSET,
            reason=reason,
            operator_id=operator_id,
            red_invoice_id=red_inv.invoice_id,
        )
        self._void_records.append(record)
        logger.info("发票已红冲", original_id=invoice_id, red_id=red_inv.invoice_id,
                     amount_yuan=invoice.amount_yuan)
        return {
            "original_invoice_id": invoice_id,
            "red_invoice_id": red_inv.invoice_id,
            "red_invoice_no": red_inv.invoice_no,
            "amount_fen": red_inv.amount_fen,
            "amount_yuan": red_inv.amount_yuan,
            "tax_fen": red_inv.tax_fen,
            "tax_yuan": red_inv.tax_yuan,
        }

    def get_void_history(
        self,
        store_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
    ) -> List[Dict]:
        """获取作废/红冲历史"""
        records = self._void_records
        if invoice_id:
            records = [r for r in records if r.invoice_id == invoice_id]
        if store_id:
            # 需要通过invoice关联store
            store_invoice_ids = {
                inv.invoice_id for inv in self._invoices.values() if inv.store_id == store_id
            }
            records = [r for r in records if r.invoice_id in store_invoice_ids]
        return [
            {
                "void_id": r.void_id,
                "invoice_id": r.invoice_id,
                "void_type": r.void_type.value,
                "reason": r.reason,
                "operator_id": r.operator_id,
                "red_invoice_id": r.red_invoice_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]

    def _get_invoice(self, invoice_id: str) -> InvoiceRecord:
        if invoice_id not in self._invoices:
            raise ValueError(f"发票不存在: {invoice_id}")
        return self._invoices[invoice_id]
