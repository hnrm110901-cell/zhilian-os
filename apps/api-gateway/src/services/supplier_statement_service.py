"""
供应商对账单服务
按供应商+日期范围生成对账单、查看应付账款、对账调差
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class ReconcileStatus(str, Enum):
    PENDING = "pending"       # 待对账
    MATCHED = "matched"       # 已核对一致
    DISPUTED = "disputed"     # 有差异待处理
    RESOLVED = "resolved"     # 差异已处理


@dataclass
class PurchaseEntry:
    """采购明细"""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    supplier_id: str = ""
    store_id: str = ""
    item_name: str = ""
    qty: float = 0
    unit: str = ""
    unit_price_fen: int = 0
    amount_fen: int = 0  # qty * unit_price（分）
    delivery_date: Optional[date] = None
    invoice_no: str = ""

    @property
    def amount_yuan(self) -> float:
        return round(self.amount_fen / 100, 2)

    @property
    def unit_price_yuan(self) -> float:
        return round(self.unit_price_fen / 100, 2)


@dataclass
class PaymentRecord:
    """付款记录"""
    payment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    supplier_id: str = ""
    amount_fen: int = 0
    payment_date: Optional[date] = None
    method: str = ""  # "bank_transfer" / "cash" / "check"
    reference: str = ""

    @property
    def amount_yuan(self) -> float:
        return round(self.amount_fen / 100, 2)


class SupplierStatementService:
    """供应商对账单服务"""

    def __init__(self):
        self._entries: List[PurchaseEntry] = []
        self._payments: List[PaymentRecord] = []

    def add_entry(self, entry: PurchaseEntry) -> PurchaseEntry:
        """添加采购明细"""
        self._entries.append(entry)
        return entry

    def add_payment(self, payment: PaymentRecord) -> PaymentRecord:
        """添加付款记录"""
        self._payments.append(payment)
        return payment

    def generate_statement(
        self,
        supplier_id: str,
        start_date: date,
        end_date: date,
        store_id: Optional[str] = None,
    ) -> Dict:
        """
        按供应商+日期范围生成对账单
        """
        # 筛选采购明细
        entries = [
            e for e in self._entries
            if e.supplier_id == supplier_id
            and e.delivery_date is not None
            and start_date <= e.delivery_date <= end_date
        ]
        if store_id:
            entries = [e for e in entries if e.store_id == store_id]

        # 筛选付款
        payments = [
            p for p in self._payments
            if p.supplier_id == supplier_id
            and p.payment_date is not None
            and start_date <= p.payment_date <= end_date
        ]

        total_purchase_fen = sum(e.amount_fen for e in entries)
        total_payment_fen = sum(p.amount_fen for p in payments)
        balance_fen = total_purchase_fen - total_payment_fen

        return {
            "supplier_id": supplier_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "item_name": e.item_name,
                    "qty": e.qty,
                    "unit": e.unit,
                    "unit_price_yuan": e.unit_price_yuan,
                    "amount_fen": e.amount_fen,
                    "amount_yuan": e.amount_yuan,
                    "delivery_date": e.delivery_date.isoformat() if e.delivery_date else "",
                    "invoice_no": e.invoice_no,
                }
                for e in entries
            ],
            "payments": [
                {
                    "payment_id": p.payment_id,
                    "amount_fen": p.amount_fen,
                    "amount_yuan": p.amount_yuan,
                    "date": p.payment_date.isoformat() if p.payment_date else "",
                    "method": p.method,
                }
                for p in payments
            ],
            "summary": {
                "total_purchase_fen": total_purchase_fen,
                "total_purchase_yuan": round(total_purchase_fen / 100, 2),
                "total_payment_fen": total_payment_fen,
                "total_payment_yuan": round(total_payment_fen / 100, 2),
                "balance_fen": balance_fen,
                "balance_yuan": round(balance_fen / 100, 2),
                "entry_count": len(entries),
            },
        }

    def get_payables(self, supplier_id: Optional[str] = None) -> List[Dict]:
        """获取应付账款汇总（按供应商）"""
        # 按供应商汇总
        supplier_totals: Dict[str, Dict] = {}
        for e in self._entries:
            if supplier_id and e.supplier_id != supplier_id:
                continue
            if e.supplier_id not in supplier_totals:
                supplier_totals[e.supplier_id] = {"purchase_fen": 0, "paid_fen": 0}
            supplier_totals[e.supplier_id]["purchase_fen"] += e.amount_fen

        for p in self._payments:
            if supplier_id and p.supplier_id != supplier_id:
                continue
            if p.supplier_id in supplier_totals:
                supplier_totals[p.supplier_id]["paid_fen"] += p.amount_fen

        result = []
        for sid, totals in supplier_totals.items():
            balance = totals["purchase_fen"] - totals["paid_fen"]
            if balance > 0:
                result.append({
                    "supplier_id": sid,
                    "total_purchase_fen": totals["purchase_fen"],
                    "total_purchase_yuan": round(totals["purchase_fen"] / 100, 2),
                    "total_paid_fen": totals["paid_fen"],
                    "total_paid_yuan": round(totals["paid_fen"] / 100, 2),
                    "payable_fen": balance,
                    "payable_yuan": round(balance / 100, 2),
                })
        result.sort(key=lambda x: x["payable_fen"], reverse=True)
        return result

    def reconcile(
        self,
        supplier_id: str,
        supplier_total_fen: int,
        start_date: date,
        end_date: date,
    ) -> Dict:
        """
        对账：比较我方记录与供应商报来的总额
        """
        statement = self.generate_statement(supplier_id, start_date, end_date)
        our_total = statement["summary"]["total_purchase_fen"]
        difference_fen = our_total - supplier_total_fen

        if difference_fen == 0:
            status = ReconcileStatus.MATCHED
        else:
            status = ReconcileStatus.DISPUTED

        result = {
            "supplier_id": supplier_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "our_total_fen": our_total,
            "our_total_yuan": round(our_total / 100, 2),
            "supplier_total_fen": supplier_total_fen,
            "supplier_total_yuan": round(supplier_total_fen / 100, 2),
            "difference_fen": difference_fen,
            "difference_yuan": round(difference_fen / 100, 2),
            "status": status.value,
        }
        logger.info("供应商对账", supplier_id=supplier_id, status=status.value,
                     diff_yuan=result["difference_yuan"])
        return result
