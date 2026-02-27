"""
业财税资金一体化（FCT）服务

- 业财事件接入与幂等
- 凭证规则引擎（占位：门店日结生成凭证）
- 凭证与总账查询
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import structlog
import uuid

from sqlalchemy import select, func, and_, literal
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String

from src.models.fct import (
    FctEvent,
    FctVoucher,
    FctVoucherLine,
    FctVoucherStatus,
    FctMaster,
    FctMasterType,
    FctCashTransaction,
    FctTaxInvoice,
    FctTaxDeclaration,
    FctPlan,
    FctPeriod,
    FctPettyCash,
    FctPettyCashRecord,
    FctPettyCashType,
    FctBudget,
    FctBudgetControl,
    FctApprovalRecord,
)

logger = structlog.get_logger()

# 默认科目编码（企业会计准则应用指南 财会〔2006〕18号，与金蝶/用友常用编码一致）
DEFAULT_ACCOUNT_CASH = "1001"            # 库存现金
DEFAULT_ACCOUNT_BANK = "1002"            # 银行存款
DEFAULT_ACCOUNT_INVENTORY = "1405"      # 库存商品
DEFAULT_ACCOUNT_PAYABLE = "2202"        # 应付账款
DEFAULT_ACCOUNT_TAX_PAYABLE = "2221"     # 应交税费（销项：应交税费-应交增值税-销项税额）
DEFAULT_ACCOUNT_TAX_INPUT = "2221_01"   # 应交税费-应交增值税-进项税额（2221 子目）
DEFAULT_ACCOUNT_SALES = "6001"           # 主营业务收入
DEFAULT_ACCOUNT_OTHER_PAYABLE = "2203"   # 其他应付款（手工收付款凭证过渡科目）
DEFAULT_ACCOUNT_RECEIVABLE = "1122"      # 应收账款（平台结算等）
DEFAULT_ACCOUNT_SALES_EXPENSE = "6601"   # 销售费用（平台佣金等）
DEFAULT_ACCOUNT_CONTRACT_LIABILITY = "2231"  # 合同负债（会员储值）

# 借贷平衡允许的尾差（元），与金蝶/用友一致
VOUCHER_BALANCE_TOLERANCE = Decimal("0.01")


def _voucher_to_dict(voucher: FctVoucher, lines: List[Any]) -> Dict[str, Any]:
    """凭证及分录转 API 用字典"""
    return {
        "id": str(voucher.id),
        "voucher_no": voucher.voucher_no,
        "tenant_id": voucher.tenant_id,
        "entity_id": voucher.entity_id,
        "biz_date": voucher.biz_date.isoformat() if voucher.biz_date else None,
        "event_type": voucher.event_type,
        "event_id": voucher.event_id,
        "status": voucher.status.value if hasattr(voucher.status, "value") else str(voucher.status),
        "description": voucher.description,
        "lines": [
            {
                "id": str(l.id),
                "line_no": l.line_no,
                "account_code": l.account_code,
                "account_name": l.account_name,
                "debit": float(l.debit or 0),
                "credit": float(l.credit or 0),
                "description": l.description,
            }
            for l in lines
        ],
    }


class FctService:
    """业财税资金服务（凭证规则对齐企业会计准则及金蝶/用友常见规范）"""

    @staticmethod
    def _voucher_totals(lines: List[Dict[str, Any]]) -> tuple:
        """计算分录借方、贷方合计（用于借贷平衡校验）。lines 项含 debit, credit（Decimal 或可转 Decimal）。"""
        total_d = Decimal(0)
        total_c = Decimal(0)
        for item in lines:
            total_d += Decimal(str(item.get("debit") or 0))
            total_c += Decimal(str(item.get("credit") or 0))
        return total_d, total_c

    @staticmethod
    def _is_balanced(total_debit: Decimal, total_credit: Decimal) -> bool:
        """借贷平衡（允许 0.01 元尾差，与财务软件一致）。"""
        return abs(total_debit - total_credit) <= VOUCHER_BALANCE_TOLERANCE

    @staticmethod
    def _traceability_attachments(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """四流合一追溯：从事件 payload 提取发票号、业务单号等，供凭证 attachments 关联（票-账-业务单）。"""
        keys = ("invoice_no", "invoice_id", "source_doc_id", "order_id", "settlement_id", "purchase_order_id")
        out = {}
        for k in keys:
            v = payload.get(k)
            if v is not None and v != "":
                out[k] = str(v)
        return out if out else None

    async def ingest_event(self, session: AsyncSession, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        接收业财事件：幂等写入事件表，经规则引擎生成凭证并落库。

        Returns:
            {"event_id", "processed", "voucher_id"|"error"}
        """
        event_id = body.get("event_id") or str(uuid.uuid4())
        tenant_id = body.get("tenant_id", "")
        entity_id = body.get("entity_id", "")
        event_type = body.get("event_type", "")
        payload = body.get("payload") or {}

        # 幂等：已存在则直接返回
        result = await session.execute(select(FctEvent).where(FctEvent.event_id == event_id))
        existing = result.scalars().one_or_none()
        if existing:
            return {
                "event_id": event_id,
                "processed": existing.processed_at is not None,
                "voucher_id": str(existing.voucher_id) if existing.voucher_id else None,
                "error": existing.error_message,
            }

        # 落事件表
        occurred_at = body.get("occurred_at", datetime.utcnow().isoformat() + "Z")
        fct_event = FctEvent(
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            source_system=body.get("source_system", "zhilian_os"),
            source_id=body.get("source_id"),
            tenant_id=tenant_id,
            entity_id=entity_id,
            payload=payload,
        )
        session.add(fct_event)
        await session.flush()

        # 凭证规则引擎（占位）
        voucher = None
        try:
            voucher = await self._rule_engine_dispatch(session, fct_event, event_type, payload)
        except Exception as e:
            logger.warning("fct rule engine error", event_id=event_id, event_type=event_type, error=str(e))
            fct_event.error_message = str(e)
        fct_event.processed_at = datetime.utcnow().isoformat() + "Z"
        if voucher:
            fct_event.voucher_id = voucher.id
        elif not fct_event.error_message:
            fct_event.error_message = f"no rule for event_type={event_type}"

        await session.commit()
        return {
            "event_id": event_id,
            "processed": True,
            "voucher_id": str(voucher.id) if voucher else None,
            "error": fct_event.error_message,
        }

    async def _rule_engine_dispatch(
        self, session: AsyncSession, fct_event: FctEvent, event_type: str, payload: Dict[str, Any]
    ) -> Optional[FctVoucher]:
        """按事件类型分发到对应规则生成凭证"""
        if event_type == "store_daily_settlement":
            return await self._rule_store_daily_settlement(session, fct_event, payload)
        if event_type == "purchase_receipt":
            return await self._rule_purchase_receipt(session, fct_event, payload)
        if event_type == "platform_settlement":
            return await self._rule_platform_settlement(session, fct_event, payload)
        if event_type == "member_stored_value":
            return await self._rule_member_stored_value(session, fct_event, payload)
        return None

    async def _rule_platform_settlement(
        self, session: AsyncSession, fct_event: FctEvent, payload: Dict[str, Any]
    ) -> FctVoucher:
        """平台结算凭证：借 银行存款、销售费用-佣金 贷 应收账款（平台）。payload: platform, settlement_no, amount(元), commission(元), period?, biz_date?"""
        entity_id = payload.get("entity_id", fct_event.entity_id)
        biz_date_str = payload.get("biz_date")
        if biz_date_str:
            biz_date = date.fromisoformat(biz_date_str) if isinstance(biz_date_str, str) else biz_date_str
        else:
            from datetime import datetime
            biz_date = datetime.utcnow().date()
        amount = Decimal(str(payload.get("amount", 0)))
        commission = Decimal(str(payload.get("commission", 0)))
        platform = str(payload.get("platform", ""))
        if amount <= 0:
            raise ValueError("platform_settlement payload amount must be > 0")
        net_receipt = amount - commission
        voucher_no = await self._next_voucher_no(session, fct_event.tenant_id, entity_id, biz_date)
        attachments = self._traceability_attachments(payload)
        voucher = FctVoucher(
            voucher_no=voucher_no,
            tenant_id=fct_event.tenant_id,
            entity_id=entity_id,
            biz_date=biz_date,
            event_type=fct_event.event_type,
            event_id=fct_event.event_id,
            status=FctVoucherStatus.DRAFT,
            description=f"平台结算 {platform} {biz_date}",
            attachments=attachments,
        )
        session.add(voucher)
        await session.flush()
        lines: List[FctVoucherLine] = []
        line_no = 1
        if net_receipt > 0:
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=line_no, account_code=DEFAULT_ACCOUNT_BANK, account_name="银行存款", debit=net_receipt, credit=Decimal(0), auxiliary={"platform": platform}, description="平台到账"))
            line_no += 1
        if commission > 0:
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=line_no, account_code=DEFAULT_ACCOUNT_SALES_EXPENSE, account_name="销售费用", debit=commission, credit=Decimal(0), auxiliary={"platform": platform}, description="平台佣金"))
            line_no += 1
        lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=line_no, account_code=DEFAULT_ACCOUNT_RECEIVABLE, account_name="应收账款", debit=Decimal(0), credit=amount, auxiliary={"platform": platform}, description=f"平台 {platform} 结算"))
        for line in lines:
            session.add(line)
        return voucher

    async def _rule_member_stored_value(
        self, session: AsyncSession, fct_event: FctEvent, payload: Dict[str, Any]
    ) -> FctVoucher:
        """会员储值/消费凭证：charge 借银行存款贷合同负债，consume 借合同负债贷主营业务收入，refund 借合同负债贷银行存款。payload: store_id, member_id?, type(charge|consume|refund), amount(元), biz_date?"""
        entity_id = payload.get("store_id", fct_event.entity_id)
        biz_date_str = payload.get("biz_date")
        if biz_date_str:
            biz_date = date.fromisoformat(biz_date_str) if isinstance(biz_date_str, str) else biz_date_str
        else:
            from datetime import datetime
            biz_date = datetime.utcnow().date()
        amount = Decimal(str(payload.get("amount", 0)))
        value_type = (payload.get("type") or payload.get("value_type") or "").lower()
        if value_type not in ("charge", "consume", "refund") or amount <= 0:
            raise ValueError("member_stored_value payload must have type in (charge,consume,refund) and amount > 0")
        voucher_no = await self._next_voucher_no(session, fct_event.tenant_id, entity_id, biz_date)
        attachments = self._traceability_attachments(payload)
        voucher = FctVoucher(
            voucher_no=voucher_no,
            tenant_id=fct_event.tenant_id,
            entity_id=entity_id,
            biz_date=biz_date,
            event_type=fct_event.event_type,
            event_id=fct_event.event_id,
            status=FctVoucherStatus.DRAFT,
            description=f"会员储值 {value_type} {biz_date}",
            attachments=attachments,
        )
        session.add(voucher)
        await session.flush()
        lines: List[FctVoucherLine] = []
        if value_type == "charge":
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=1, account_code=DEFAULT_ACCOUNT_BANK, account_name="银行存款", debit=amount, credit=Decimal(0), description="会员储值"))
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=2, account_code=DEFAULT_ACCOUNT_CONTRACT_LIABILITY, account_name="合同负债", debit=Decimal(0), credit=amount, description="会员储值"))
        elif value_type == "consume":
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=1, account_code=DEFAULT_ACCOUNT_CONTRACT_LIABILITY, account_name="合同负债", debit=amount, credit=Decimal(0), description="会员消费"))
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=2, account_code=DEFAULT_ACCOUNT_SALES, account_name="主营业务收入", debit=Decimal(0), credit=amount, description="会员消费确认收入"))
        else:
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=1, account_code=DEFAULT_ACCOUNT_CONTRACT_LIABILITY, account_name="合同负债", debit=amount, credit=Decimal(0), description="会员退款"))
            lines.append(FctVoucherLine(voucher_id=voucher.id, line_no=2, account_code=DEFAULT_ACCOUNT_BANK, account_name="银行存款", debit=Decimal(0), credit=amount, description="会员退款"))
        for line in lines:
            session.add(line)
        return voucher

    async def _rule_store_daily_settlement(
        self, session: AsyncSession, fct_event: FctEvent, payload: Dict[str, Any]
    ) -> FctVoucher:
        """门店日结凭证：借 银行存款/库存现金 贷 主营业务收入、应交税费（销项）。符合企业会计准则及金蝶/用友销售收款分录规范。"""
        store_id = payload.get("store_id", fct_event.entity_id)
        biz_date_str = payload.get("biz_date")
        if not biz_date_str:
            raise ValueError("store_daily_settlement payload must have biz_date")
        biz_date = date.fromisoformat(biz_date_str) if isinstance(biz_date_str, str) else biz_date_str
        total_sales = int(payload.get("total_sales", 0))
        total_sales_tax = int(payload.get("total_sales_tax", 0))
        payment_breakdown = payload.get("payment_breakdown") or []
        discounts = int(payload.get("discounts", 0))
        # 收入净额（分）
        revenue = total_sales - discounts

        voucher_no = await self._next_voucher_no(session, fct_event.tenant_id, fct_event.entity_id, biz_date)
        attachments = self._traceability_attachments(payload)
        voucher = FctVoucher(
            voucher_no=voucher_no,
            tenant_id=fct_event.tenant_id,
            entity_id=store_id,
            biz_date=biz_date,
            event_type=fct_event.event_type,
            event_id=fct_event.event_id,
            status=FctVoucherStatus.DRAFT,
            description=f"门店日结 {store_id} {biz_date}",
            attachments=attachments,
        )
        session.add(voucher)
        await session.flush()

        lines: List[FctVoucherLine] = []
        line_no = 1
        # 按支付方式拆分借方：银行存款 / 库存现金
        for item in payment_breakdown:
            method = (item if isinstance(item, dict) else {}).get("method", "other")
            amount = int((item if isinstance(item, dict) else {}).get("amount", 0))
            if amount <= 0:
                continue
            account_code = DEFAULT_ACCOUNT_BANK if method in ("wechat", "alipay", "bank") else DEFAULT_ACCOUNT_CASH
            lines.append(FctVoucherLine(
                voucher_id=voucher.id,
                line_no=line_no,
                account_code=account_code,
                account_name="银行存款" if account_code == DEFAULT_ACCOUNT_BANK else "库存现金",
                debit=Decimal(amount) / 100,
                credit=Decimal(0),
                auxiliary={"payment_method": method},
                description=f"日结-{method}",
            ))
            line_no += 1
        if not lines:
            # 无支付明细时合并一笔
            lines.append(FctVoucherLine(
                voucher_id=voucher.id,
                line_no=line_no,
                account_code=DEFAULT_ACCOUNT_BANK,
                account_name="银行存款",
                debit=Decimal(revenue) / 100,
                credit=Decimal(0),
                description="门店日结",
            ))
            line_no += 1
        # 贷方：主营业务收入、应交税费
        revenue_cny = Decimal(revenue) / 100
        tax_cny = Decimal(total_sales_tax) / 100
        lines.append(FctVoucherLine(
            voucher_id=voucher.id,
            line_no=line_no,
            account_code=DEFAULT_ACCOUNT_SALES,
            account_name="主营业务收入",
            debit=Decimal(0),
            credit=revenue_cny - tax_cny,
            description="门店日结收入",
        ))
        line_no += 1
        lines.append(FctVoucherLine(
            voucher_id=voucher.id,
            line_no=line_no,
            account_code=DEFAULT_ACCOUNT_TAX_PAYABLE,
            account_name="应交税费",
            debit=Decimal(0),
            credit=tax_cny,
            description="销项税",
        ))
        # 借贷平衡校验与差额调整（与金蝶/用友一致：凭证保存前必须借贷相等，允许 0.01 元尾差）
        total_d = sum(l.debit or Decimal(0) for l in lines)
        total_c = sum(l.credit or Decimal(0) for l in lines)
        diff = total_c - total_d
        if not self._is_balanced(total_d, total_c):
            line_no += 1
            if diff > 0:
                lines.append(FctVoucherLine(
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_code=DEFAULT_ACCOUNT_BANK,
                    account_name="银行存款",
                    debit=diff,
                    credit=Decimal(0),
                    description="差额调整（借方）",
                ))
            else:
                lines.append(FctVoucherLine(
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_code=DEFAULT_ACCOUNT_BANK,
                    account_name="银行存款",
                    debit=Decimal(0),
                    credit=abs(diff),
                    description="差额调整（贷方）",
                ))
        total_d = sum(l.debit or Decimal(0) for l in lines)
        total_c = sum(l.credit or Decimal(0) for l in lines)
        if not self._is_balanced(total_d, total_c):
            logger.warning("门店日结凭证借贷仍不平衡", voucher_no=voucher_no, total_debit=float(total_d), total_credit=float(total_c))
        for line in lines:
            session.add(line)
        return voucher

    async def _rule_purchase_receipt(
        self, session: AsyncSession, fct_event: FctEvent, payload: Dict[str, Any]
    ) -> FctVoucher:
        """采购入库凭证：借 库存商品、应交税费-进项税额 贷 应付账款（辅助核算供应商）。符合企业会计准则及金蝶/用友采购入账规范。"""
        store_id = payload.get("store_id", fct_event.entity_id)
        supplier_id = payload.get("supplier_id", "")
        biz_date_str = payload.get("biz_date")
        if not biz_date_str:
            raise ValueError("purchase_receipt payload must have biz_date")
        biz_date = date.fromisoformat(biz_date_str) if isinstance(biz_date_str, str) else biz_date_str
        total = int(payload.get("total", 0))
        tax = int(payload.get("tax", 0))
        # 价税分离：存货成本 = total - tax（分）
        inventory_cents = total - tax

        voucher_no = await self._next_voucher_no(session, fct_event.tenant_id, fct_event.entity_id, biz_date)
        attachments = self._traceability_attachments(payload)
        voucher = FctVoucher(
            voucher_no=voucher_no,
            tenant_id=fct_event.tenant_id,
            entity_id=store_id,
            biz_date=biz_date,
            event_type=fct_event.event_type,
            event_id=fct_event.event_id,
            status=FctVoucherStatus.DRAFT,
            description=f"采购入库 {store_id} 供应商{supplier_id} {biz_date}",
            attachments=attachments,
        )
        session.add(voucher)
        await session.flush()

        lines: List[FctVoucherLine] = []
        # 借：库存商品
        lines.append(FctVoucherLine(
            voucher_id=voucher.id,
            line_no=1,
            account_code=DEFAULT_ACCOUNT_INVENTORY,
            account_name="库存商品",
            debit=Decimal(inventory_cents) / 100,
            credit=Decimal(0),
            auxiliary={"supplier_id": supplier_id},
            description="采购入库",
        ))
        # 借：应交税费-进项
        if tax > 0:
            lines.append(FctVoucherLine(
                voucher_id=voucher.id,
                line_no=2,
                account_code=DEFAULT_ACCOUNT_TAX_INPUT,
                account_name="应交税费-进项",
                debit=Decimal(tax) / 100,
                credit=Decimal(0),
                description="进项税",
            ))
        # 贷：应付账款
        lines.append(FctVoucherLine(
            voucher_id=voucher.id,
            line_no=len(lines) + 1,
            account_code=DEFAULT_ACCOUNT_PAYABLE,
            account_name="应付账款",
            debit=Decimal(0),
            credit=Decimal(total) / 100,
            auxiliary={"supplier_id": supplier_id},
            description=f"应付供应商 {supplier_id}",
        ))
        total_d = sum(l.debit or Decimal(0) for l in lines)
        total_c = sum(l.credit or Decimal(0) for l in lines)
        if not self._is_balanced(total_d, total_c):
            logger.warning("采购入库凭证借贷不平衡", voucher_no=voucher_no, total_debit=float(total_d), total_credit=float(total_c))
        for line in lines:
            session.add(line)
        return voucher

    async def _next_voucher_no(
        self, session: AsyncSession, tenant_id: str, entity_id: str, biz_date: date
    ) -> str:
        """生成凭证号：V + 主体 + 日期 + 当日序号（占位：简单递增）"""
        result = await session.execute(
            select(func.count(FctVoucher.id)).where(
                and_(
                    FctVoucher.tenant_id == tenant_id,
                    FctVoucher.entity_id == entity_id,
                    FctVoucher.biz_date == biz_date,
                )
            )
        )
        cnt = result.scalar() or 0
        return f"V{biz_date.isoformat().replace('-', '')}{entity_id[:8]}{(cnt + 1):04d}"

    async def get_vouchers(
        self,
        session: AsyncSession,
        tenant_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """凭证列表（分页）"""
        q = select(FctVoucher).order_by(FctVoucher.biz_date.desc(), FctVoucher.voucher_no.desc())
        if tenant_id:
            q = q.where(FctVoucher.tenant_id == tenant_id)
        if entity_id:
            q = q.where(FctVoucher.entity_id == entity_id)
        if start_date:
            q = q.where(FctVoucher.biz_date >= start_date)
        if end_date:
            q = q.where(FctVoucher.biz_date <= end_date)
        if status:
            q = q.where(FctVoucher.status == status)
        count_stmt = select(func.count(FctVoucher.id))
        if tenant_id:
            count_stmt = count_stmt.where(FctVoucher.tenant_id == tenant_id)
        if entity_id:
            count_stmt = count_stmt.where(FctVoucher.entity_id == entity_id)
        if start_date:
            count_stmt = count_stmt.where(FctVoucher.biz_date >= start_date)
        if end_date:
            count_stmt = count_stmt.where(FctVoucher.biz_date <= end_date)
        if status:
            count_stmt = count_stmt.where(FctVoucher.status == status)
        total = (await session.execute(count_stmt)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        vouchers = result.scalars().all()
        return {"total": total, "items": vouchers, "skip": skip, "limit": limit}

    async def get_voucher_by_id(self, session: AsyncSession, voucher_id: str) -> Optional[FctVoucher]:
        """凭证详情（含分录），预加载 lines 避免异步下懒加载问题"""
        try:
            vid = uuid.UUID(voucher_id)
        except (ValueError, TypeError):
            return None
        result = await session.execute(
            select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == vid)
        )
        return result.scalars().one_or_none()

    def _period_to_end_date(self, period: str) -> date:
        """period YYYYMM -> 当月最后一天"""
        if not period or len(period) != 6:
            raise ValueError("period 须为 6 位 YYYYMM")
        from calendar import monthrange
        try:
            y, m = int(period[:4]), int(period[4:6])
        except ValueError:
            raise ValueError("period 须为数字 YYYYMM")
        if not (1 <= m <= 12):
            raise ValueError("period 月份须在 01-12")
        return date(y, m, monthrange(y, m)[1])

    def _period_to_dates(self, period: str) -> tuple:
        """period YYYYMM -> (start_date, end_date) 当月首末"""
        if not period or len(period) != 6:
            raise ValueError("period 须为 6 位 YYYYMM")
        from calendar import monthrange
        try:
            y, m = int(period[:4]), int(period[4:6])
        except ValueError:
            raise ValueError("period 须为数字 YYYYMM")
        if not (1 <= m <= 12):
            raise ValueError("period 月份须在 01-12")
        return date(y, m, 1), date(y, m, monthrange(y, m)[1])

    async def get_ledger_balances(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        as_of_date: Optional[date] = None,
        period: Optional[str] = None,
        posted_only: bool = True,
    ) -> Dict[str, Any]:
        """总账余额：按科目汇总凭证分录的借贷（默认仅已过账）。period=YYYYMM 时取该月月末余额（覆盖 as_of_date）。"""
        if period:
            as_of_date = self._period_to_end_date(period)
        q = (
            select(
                FctVoucherLine.account_code,
                FctVoucherLine.account_name,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("debit_total"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("credit_total"),
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(FctVoucher.tenant_id == tenant_id)
        )
        q = q.where(FctVoucher.status != FctVoucherStatus.VOIDED)
        if posted_only:
            q = q.where(FctVoucher.status == FctVoucherStatus.POSTED)
        if entity_id:
            q = q.where(FctVoucher.entity_id == entity_id)
        if as_of_date:
            q = q.where(FctVoucher.biz_date <= as_of_date)
        q = q.group_by(FctVoucherLine.account_code, FctVoucherLine.account_name)
        result = await session.execute(q)
        rows = result.all()
        balances = []
        for r in rows:
            debit_total = float(r.debit_total or 0)
            credit_total = float(r.credit_total or 0)
            balance = debit_total - credit_total
            balances.append({
                "account_code": r.account_code,
                "account_name": r.account_name or "",
                "debit_total": debit_total,
                "credit_total": credit_total,
                "balance": balance,
            })
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "as_of_date": as_of_date.isoformat() if as_of_date else None,
            "period": period,
            "posted_only": posted_only,
            "balances": balances,
        }

    async def get_report_consolidated(
        self,
        session: AsyncSession,
        tenant_id: str,
        period: str,
        group_by: Optional[str] = None,
        posted_only: bool = True,
    ) -> Dict[str, Any]:
        """合并报表：多主体总账汇总。period=YYYYMM；group_by=None 时全主体汇总，group_by=entity 时按主体返回。不做内部抵销。"""
        end_date = self._period_to_end_date(period)
        entity_ids_q = select(FctVoucher.entity_id).where(
            and_(FctVoucher.tenant_id == tenant_id, FctVoucher.entity_id.isnot(None))
        ).distinct()
        if posted_only:
            entity_ids_q = entity_ids_q.where(FctVoucher.status == FctVoucherStatus.POSTED)
        entity_ids_q = entity_ids_q.where(FctVoucher.status != FctVoucherStatus.VOIDED)
        entity_ids_q = entity_ids_q.where(FctVoucher.biz_date <= end_date)
        ent_result = await session.execute(entity_ids_q)
        entities = [r[0] for r in ent_result.all() if r[0]]
        if not entities:
            return {"tenant_id": tenant_id, "period": period, "group_by": group_by, "entities": [], "balances": [], "by_entity": {}}
        if group_by == "entity":
            by_entity: Dict[str, List[Dict[str, Any]]] = {}
            for eid in entities:
                lb = await self.get_ledger_balances(session, tenant_id=tenant_id, entity_id=eid, as_of_date=end_date, posted_only=posted_only)
                by_entity[eid] = lb.get("balances", [])
            return {"tenant_id": tenant_id, "period": period, "group_by": "entity", "entities": entities, "by_entity": by_entity}
        # 全主体汇总：按 account_code 汇总所有主体的借贷
        q = (
            select(
                FctVoucherLine.account_code,
                FctVoucherLine.account_name,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("debit_total"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("credit_total"),
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(
                and_(
                    FctVoucher.tenant_id == tenant_id,
                    FctVoucher.entity_id.in_(entities),
                    FctVoucher.status != FctVoucherStatus.VOIDED,
                    FctVoucher.biz_date <= end_date,
                )
            )
        )
        if posted_only:
            q = q.where(FctVoucher.status == FctVoucherStatus.POSTED)
        q = q.group_by(FctVoucherLine.account_code, FctVoucherLine.account_name)
        result = await session.execute(q)
        rows = result.all()
        balances = []
        for r in rows:
            debit_total = float(r.debit_total or 0)
            credit_total = float(r.credit_total or 0)
            balances.append({
                "account_code": r.account_code,
                "account_name": r.account_name or "",
                "debit_total": debit_total,
                "credit_total": credit_total,
                "balance": debit_total - credit_total,
            })
        return {"tenant_id": tenant_id, "period": period, "group_by": group_by or "all", "entities": entities, "as_of_date": end_date.isoformat(), "balances": balances}

    async def create_manual_voucher(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        biz_date: date,
        lines: List[Dict[str, Any]],
        description: Optional[str] = None,
        attachments: Optional[Dict[str, Any]] = None,
        budget_check: Optional[Dict[str, Any]] = None,
        budget_occupy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """手工/调整凭证创建：借贷必平，来源标识为 manual。可选 budget_check/budget_occupy 与预算联动。"""
        if not lines:
            raise ValueError("凭证至少需要一条分录")
        period = await self.get_period_for_date(session, tenant_id, biz_date)
        if period and getattr(period, "status", None) == "closed":
            raise ValueError("该日期所属期间已结账，无法新增凭证")
        total_d_pre = sum(Decimal(str(row.get("debit") or 0)) for row in lines)
        if budget_check:
            chk = await self.check_budget(
                session,
                tenant_id=tenant_id,
                budget_type=budget_check.get("budget_type") or "period",
                period=str(budget_check.get("period") or ""),
                category=str(budget_check.get("category") or ""),
                amount_to_use=float(budget_check.get("amount_to_use") or 0),
                entity_id=str(budget_check.get("entity_id") or entity_id or ""),
            )
            if not chk.get("allowed", True):
                raise ValueError(f"超预算：剩余 {chk.get('remaining')}，本次 {chk.get('amount_to_use')}，超出 {chk.get('over_by')}")
        else:
            ctrl = await self.get_budget_control_for(session, tenant_id=tenant_id, entity_id=entity_id, budget_type="period", category="")
            if ctrl and ctrl.get("enforce_check") and float(total_d_pre) > 0:
                period_str = biz_date.strftime("%Y%m")
                chk = await self.check_budget(
                    session,
                    tenant_id=tenant_id,
                    budget_type="period",
                    period=period_str,
                    category="",
                    amount_to_use=float(total_d_pre),
                    entity_id=entity_id or "",
                )
                if not chk.get("allowed", True):
                    raise ValueError(f"超预算（预算控制强制校验）：剩余 {chk.get('remaining')}，本次 {chk.get('amount_to_use')}，超出 {chk.get('over_by')}")
        voucher_no = await self._next_voucher_no(session, tenant_id, entity_id, biz_date)
        voucher = FctVoucher(
            voucher_no=voucher_no,
            tenant_id=tenant_id,
            entity_id=entity_id,
            biz_date=biz_date,
            event_type="manual",
            event_id=None,
            status=FctVoucherStatus.DRAFT,
            description=description or "手工凭证",
            attachments=attachments,
        )
        session.add(voucher)
        await session.flush()
        line_objs: List[FctVoucherLine] = []
        for i, row in enumerate(lines):
            line_no = i + 1
            account_code = str((row.get("account_code") or "").strip())
            if not account_code:
                raise ValueError(f"第{line_no}行缺少科目编码 account_code")
            debit = Decimal(str(row.get("debit") or 0))
            credit = Decimal(str(row.get("credit") or 0))
            line_objs.append(
                FctVoucherLine(
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_code=account_code,
                    account_name=row.get("account_name") or "",
                    debit=debit,
                    credit=credit,
                    auxiliary=row.get("auxiliary"),
                    description=row.get("description"),
                )
            )
        total_d = sum(l.debit or Decimal(0) for l in line_objs)
        total_c = sum(l.credit or Decimal(0) for l in line_objs)
        if not self._is_balanced(total_d, total_c):
            raise ValueError(f"借贷不平衡：借方合计 {total_d}，贷方合计 {total_c}，差额需在 {VOUCHER_BALANCE_TOLERANCE} 元内")
        for l in line_objs:
            session.add(l)
        await session.commit()
        if budget_occupy and float(budget_occupy.get("amount_to_use") or budget_occupy.get("amount") or 0) > 0:
            await self.occupy_budget(
                session,
                tenant_id=tenant_id,
                budget_type=budget_occupy.get("budget_type") or "period",
                period=str(budget_occupy.get("period") or ""),
                category=str(budget_occupy.get("category") or ""),
                amount=float(budget_occupy.get("amount_to_use") or budget_occupy.get("amount") or 0),
                entity_id=str(budget_occupy.get("entity_id") or entity_id or ""),
            )
        elif not budget_occupy:
            ctrl_occupy = await self.get_budget_control_for(session, tenant_id=tenant_id, entity_id=entity_id, budget_type="period", category="")
            if ctrl_occupy and ctrl_occupy.get("auto_occupy") and float(total_d_pre) > 0:
                await self.occupy_budget(
                    session,
                    tenant_id=tenant_id,
                    budget_type="period",
                    period=biz_date.strftime("%Y%m"),
                    category="",
                    amount=float(total_d_pre),
                    entity_id=entity_id or "",
                )
        await session.refresh(voucher)
        result = await session.execute(select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == voucher.id))
        voucher = result.scalars().one()
        return _voucher_to_dict(voucher, list(voucher.lines))

    async def update_voucher_status(
        self,
        session: AsyncSession,
        voucher_id: str,
        target_status: str,
        budget_check: Optional[Dict[str, Any]] = None,
        budget_occupy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """凭证状态变更：仅允许 draft→posted/rejected、pending→approved/rejected。过账时可选预算校验与占用。"""
        try:
            vid = uuid.UUID(voucher_id)
        except (ValueError, TypeError):
            raise ValueError("无效的凭证 id")
        result = await session.execute(
            select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == vid)
        )
        voucher = result.scalars().one_or_none()
        if not voucher:
            raise ValueError("凭证不存在")
        current = voucher.status.value if hasattr(voucher.status, "value") else str(voucher.status)
        target = target_status.lower()
        allowed = {
            ("draft", "posted"),
            ("draft", "rejected"),
            ("pending", "approved"),
            ("pending", "rejected"),
            ("approved", "posted"),
        }
        if (current, target) not in allowed:
            raise ValueError(f"不允许从状态 {current} 变更为 {target}，允许转换：{allowed}")
        if target == "posted":
            if not voucher.lines or len(voucher.lines) == 0:
                raise ValueError("无分录的凭证不能过账")
            period = await self.get_period_for_date(session, voucher.tenant_id, voucher.biz_date)
            if period and getattr(period, "status", None) == "closed":
                raise ValueError("该凭证所属期间已结账，无法过账")
            total_post = sum(float(l.debit or 0) for l in voucher.lines)
            if budget_check:
                chk = await self.check_budget(
                    session,
                    tenant_id=voucher.tenant_id,
                    budget_type=budget_check.get("budget_type") or "period",
                    period=str(budget_check.get("period") or ""),
                    category=str(budget_check.get("category") or ""),
                    amount_to_use=float(budget_check.get("amount_to_use") or 0),
                    entity_id=str(budget_check.get("entity_id") or voucher.entity_id or ""),
                )
                if not chk.get("allowed", True):
                    raise ValueError(f"超预算：剩余 {chk.get('remaining')}，本次 {chk.get('amount_to_use')}，超出 {chk.get('over_by')}")
            else:
                ctrl = await self.get_budget_control_for(session, tenant_id=voucher.tenant_id, entity_id=voucher.entity_id, budget_type="period", category="")
                if ctrl and ctrl.get("enforce_check") and total_post > 0:
                    period_str = voucher.biz_date.strftime("%Y%m")
                    chk = await self.check_budget(
                        session,
                        tenant_id=voucher.tenant_id,
                        budget_type="period",
                        period=period_str,
                        category="",
                        amount_to_use=total_post,
                        entity_id=voucher.entity_id or "",
                    )
                    if not chk.get("allowed", True):
                        raise ValueError(f"超预算（预算控制强制校验）：剩余 {chk.get('remaining')}，本次 {chk.get('amount_to_use')}，超出 {chk.get('over_by')}")
        voucher.status = FctVoucherStatus(target)
        await session.commit()
        if target == "posted" and budget_occupy and float(budget_occupy.get("amount_to_use") or budget_occupy.get("amount") or 0) > 0:
            await self.occupy_budget(
                session,
                tenant_id=voucher.tenant_id,
                budget_type=budget_occupy.get("budget_type") or "period",
                period=str(budget_occupy.get("period") or ""),
                category=str(budget_occupy.get("category") or ""),
                amount=float(budget_occupy.get("amount_to_use") or budget_occupy.get("amount") or 0),
                entity_id=str(budget_occupy.get("entity_id") or voucher.entity_id or ""),
            )
        elif target == "posted" and not budget_occupy:
            ctrl_occupy = await self.get_budget_control_for(session, tenant_id=voucher.tenant_id, entity_id=voucher.entity_id, budget_type="period", category="")
            if ctrl_occupy and ctrl_occupy.get("auto_occupy") and total_post > 0:
                await self.occupy_budget(
                    session,
                    tenant_id=voucher.tenant_id,
                    budget_type="period",
                    period=voucher.biz_date.strftime("%Y%m"),
                    category="",
                    amount=total_post,
                    entity_id=voucher.entity_id or "",
                )
        result = await session.execute(select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == voucher.id))
        voucher = result.scalars().one()
        return _voucher_to_dict(voucher, list(voucher.lines))

    async def void_voucher(self, session: AsyncSession, voucher_id: str) -> Dict[str, Any]:
        """凭证作废：仅 draft 或 posted 可作废，作废后不参与总账。"""
        try:
            vid = uuid.UUID(voucher_id)
        except (ValueError, TypeError):
            raise ValueError("无效的凭证 id")
        result = await session.execute(
            select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == vid)
        )
        voucher = result.scalars().one_or_none()
        if not voucher:
            raise ValueError("凭证不存在")
        current = voucher.status.value if hasattr(voucher.status, "value") else str(voucher.status)
        if current not in ("draft", "posted"):
            raise ValueError(f"仅草稿或已过账凭证可作废，当前状态：{current}")
        period = await self.get_period_for_date(session, voucher.tenant_id, voucher.biz_date)
        if period and getattr(period, "status", None) == "closed":
            raise ValueError("该凭证所属期间已结账，无法作废")
        voucher.status = FctVoucherStatus.VOIDED
        await session.commit()
        result = await session.execute(select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == voucher.id))
        voucher = result.scalars().one()
        return _voucher_to_dict(voucher, list(voucher.lines))

    async def red_flush_voucher(self, session: AsyncSession, voucher_id: str, biz_date: Optional[date] = None) -> Dict[str, Any]:
        """凭证红冲：根据已过账凭证生成红字凭证（借贷相反），新凭证为 draft，attachments 含 original_voucher_id。"""
        try:
            vid = uuid.UUID(voucher_id)
        except (ValueError, TypeError):
            raise ValueError("无效的凭证 id")
        result = await session.execute(
            select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == vid)
        )
        orig = result.scalars().one_or_none()
        if not orig:
            raise ValueError("凭证不存在")
        current = orig.status.value if hasattr(orig.status, "value") else str(orig.status)
        if current != "posted":
            raise ValueError("仅已过账凭证可红冲")
        period = await self.get_period_for_date(session, orig.tenant_id, orig.biz_date)
        if period and getattr(period, "status", None) == "closed":
            raise ValueError("该凭证所属期间已结账，无法红冲")
        flush_date = biz_date or orig.biz_date
        voucher_no = await self._next_voucher_no(session, orig.tenant_id, orig.entity_id, flush_date)
        new_v = FctVoucher(
            voucher_no=voucher_no,
            tenant_id=orig.tenant_id,
            entity_id=orig.entity_id,
            biz_date=flush_date,
            event_type="red_flush",
            event_id=None,
            status=FctVoucherStatus.DRAFT,
            description=f"红冲 {orig.voucher_no}",
            attachments={"original_voucher_id": str(orig.id)},
        )
        session.add(new_v)
        await session.flush()
        line_objs: List[FctVoucherLine] = []
        for i, line in enumerate(orig.lines or []):
            line_objs.append(
                FctVoucherLine(
                    voucher_id=new_v.id,
                    line_no=i + 1,
                    account_code=line.account_code,
                    account_name=line.account_name,
                    debit=line.credit or Decimal(0),
                    credit=line.debit or Decimal(0),
                    auxiliary=line.auxiliary,
                    description=f"红冲 {line.description or ''}".strip(),
                )
            )
        for l in line_objs:
            session.add(l)
        await session.commit()
        result = await session.execute(select(FctVoucher).options(selectinload(FctVoucher.lines)).where(FctVoucher.id == new_v.id))
        new_v = result.scalars().one()
        return _voucher_to_dict(new_v, list(new_v.lines))

    async def get_ledger_entries(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period: Optional[str] = None,
        account_code: Optional[str] = None,
        posted_only: bool = True,
        skip: int = 0,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """总账明细：按科目+主体+日期范围返回每条分录。period=YYYYMM 时覆盖 start_date/end_date 为该月。"""
        if period:
            start_date, end_date = self._period_to_dates(period)
        q = (
            select(
                FctVoucher.id.label("voucher_id"),
                FctVoucher.voucher_no,
                FctVoucher.biz_date,
                FctVoucher.entity_id,
                FctVoucherLine.id.label("line_id"),
                FctVoucherLine.line_no,
                FctVoucherLine.account_code,
                FctVoucherLine.account_name,
                FctVoucherLine.debit,
                FctVoucherLine.credit,
                FctVoucherLine.description,
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(FctVoucher.tenant_id == tenant_id)
        )
        q = q.where(FctVoucher.status != FctVoucherStatus.VOIDED)
        if posted_only:
            q = q.where(FctVoucher.status == FctVoucherStatus.POSTED)
        if entity_id:
            q = q.where(FctVoucher.entity_id == entity_id)
        if start_date:
            q = q.where(FctVoucher.biz_date >= start_date)
        if end_date:
            q = q.where(FctVoucher.biz_date <= end_date)
        if account_code:
            q = q.where(FctVoucherLine.account_code == account_code)
        q = q.order_by(FctVoucher.biz_date, FctVoucher.voucher_no, FctVoucherLine.line_no)
        count_q = (
            select(func.count(FctVoucherLine.id))
            .select_from(FctVoucherLine)
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(FctVoucher.tenant_id == tenant_id)
            .where(FctVoucher.status != FctVoucherStatus.VOIDED)
        )
        if posted_only:
            count_q = count_q.where(FctVoucher.status == FctVoucherStatus.POSTED)
        if entity_id:
            count_q = count_q.where(FctVoucher.entity_id == entity_id)
        if start_date:
            count_q = count_q.where(FctVoucher.biz_date >= start_date)
        if end_date:
            count_q = count_q.where(FctVoucher.biz_date <= end_date)
        if account_code:
            count_q = count_q.where(FctVoucherLine.account_code == account_code)
        total = (await session.execute(count_q)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        rows = result.all()
        entries = []
        for r in rows:
            entries.append({
                "voucher_id": str(r.voucher_id),
                "voucher_no": r.voucher_no,
                "biz_date": r.biz_date.isoformat() if r.biz_date else None,
                "entity_id": r.entity_id or "",
                "line_id": str(r.line_id),
                "line_no": r.line_no,
                "account_code": r.account_code,
                "account_name": r.account_name or "",
                "debit": float(r.debit or 0),
                "credit": float(r.credit or 0),
                "description": r.description or "",
            })
        out: Dict[str, Any] = {"total": total, "entries": entries, "skip": skip, "limit": limit}
        if period:
            out["period"] = period
        if start_date:
            out["start_date"] = start_date.isoformat()
        if end_date:
            out["end_date"] = end_date.isoformat()
        return out

    # ---------- 会计期间与结账 ----------
    @staticmethod
    def _period_key(d: date) -> str:
        """日期转期间键 YYYYMM"""
        return d.strftime("%Y%m")

    async def get_period_for_date(self, session: AsyncSession, tenant_id: str, d: date) -> Optional[FctPeriod]:
        """获取日期所属会计期间（按 period_key=YYYYMM），不存在则返回 None"""
        key = self._period_key(d)
        result = await session.execute(select(FctPeriod).where(and_(FctPeriod.tenant_id == tenant_id, FctPeriod.period_key == key)))
        return result.scalars().one_or_none()

    async def ensure_period(self, session: AsyncSession, tenant_id: str, period_key: str) -> FctPeriod:
        """获取或创建期间（自然月 start/end），period_key 如 202502"""
        result = await session.execute(select(FctPeriod).where(and_(FctPeriod.tenant_id == tenant_id, FctPeriod.period_key == period_key)))
        p = result.scalars().one_or_none()
        if p:
            return p
        if len(period_key) != 6:
            raise ValueError("period_key 须为 6 位 YYYYMM")
        y, m = int(period_key[:4]), int(period_key[4:6])
        from calendar import monthrange
        start_date = date(y, m, 1)
        end_date = date(y, m, monthrange(y, m)[1])
        p = FctPeriod(tenant_id=tenant_id, period_key=period_key, start_date=start_date, end_date=end_date, status="open")
        session.add(p)
        await session.flush()
        return p

    async def list_periods(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_key: Optional[str] = None,
        end_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """期间列表，可选按 period_key 范围筛选"""
        q = select(FctPeriod).where(FctPeriod.tenant_id == tenant_id).order_by(FctPeriod.period_key.desc())
        if start_key:
            q = q.where(FctPeriod.period_key >= start_key)
        if end_key:
            q = q.where(FctPeriod.period_key <= end_key)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"items": [{"id": str(r.id), "period_key": r.period_key, "start_date": r.start_date.isoformat(), "end_date": r.end_date.isoformat(), "status": r.status, "closed_at": r.closed_at} for r in rows]}

    async def close_period(self, session: AsyncSession, tenant_id: str, period_key: str) -> Dict[str, Any]:
        """结账：该期间内不得有 draft 凭证，结账后该期间禁止新增/过账/作废/红冲"""
        period = await self.ensure_period(session, tenant_id, period_key)
        if period.status == "closed":
            return {"success": True, "period_key": period_key, "status": "closed", "message": "期间已结账"}
        cnt = await session.execute(
            select(func.count(FctVoucher.id)).where(
                and_(
                    FctVoucher.tenant_id == tenant_id,
                    FctVoucher.biz_date >= period.start_date,
                    FctVoucher.biz_date <= period.end_date,
                    FctVoucher.status == FctVoucherStatus.DRAFT,
                )
            )
        )
        n = cnt.scalar() or 0
        if n > 0:
            raise ValueError(f"该期间内存在 {n} 笔草稿凭证，请先处理后再结账")
        period.status = "closed"
        period.closed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await session.commit()
        return {"success": True, "period_key": period_key, "status": "closed"}

    async def reopen_period(self, session: AsyncSession, tenant_id: str, period_key: str) -> Dict[str, Any]:
        """反结账：将期间状态改回 open（需权限控制）"""
        result = await session.execute(select(FctPeriod).where(and_(FctPeriod.tenant_id == tenant_id, FctPeriod.period_key == period_key)))
        period = result.scalars().one_or_none()
        if not period:
            raise ValueError("期间不存在")
        if period.status != "closed":
            return {"success": True, "period_key": period_key, "status": "open", "message": "期间未结账"}
        period.status = "open"
        period.closed_at = None
        await session.commit()
        return {"success": True, "period_key": period_key, "status": "open"}

    async def get_reports_stub(self, report_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """业财报表占位（period_summary 由 API 层直接调 get_report_period_summary）"""
        return {
            "report_type": report_type,
            "params": params,
            "data": [],
            "message": "Stub: implement report aggregation",
        }

    async def get_report_period_summary(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """期间业财汇总：收入、成本、税额、凭证数（从凭证分录按科目类型汇总）"""
        if entity_id == "":
            entity_id = None
        q = (
            select(
                FctVoucher.entity_id,
                func.sum(FctVoucherLine.debit).label("total_debit"),
                func.sum(FctVoucherLine.credit).label("total_credit"),
            )
            .join(FctVoucherLine, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(FctVoucher.tenant_id == tenant_id)
        )
        if entity_id:
            q = q.where(FctVoucher.entity_id == entity_id)
        if start_date:
            q = q.where(FctVoucher.biz_date >= start_date)
        if end_date:
            q = q.where(FctVoucher.biz_date <= end_date)
        q = q.group_by(FctVoucher.entity_id)
        result = await session.execute(q)
        rows = result.all()
        # 按科目类型拆分：6 开头收入，2 应交税费，1/14 资产/存货
        detail_q = (
            select(
                FctVoucher.entity_id,
                FctVoucherLine.account_code,
                func.sum(FctVoucherLine.debit).label("d"),
                func.sum(FctVoucherLine.credit).label("c"),
            )
            .join(FctVoucherLine, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(FctVoucher.tenant_id == tenant_id)
        )
        if entity_id:
            detail_q = detail_q.where(FctVoucher.entity_id == entity_id)
        if start_date:
            detail_q = detail_q.where(FctVoucher.biz_date >= start_date)
        if end_date:
            detail_q = detail_q.where(FctVoucher.biz_date <= end_date)
        detail_q = detail_q.group_by(FctVoucher.entity_id, FctVoucherLine.account_code)
        detail_result = await session.execute(detail_q)
        detail_rows = detail_result.all()
        revenue = Decimal(0)
        tax = Decimal(0)
        for r in detail_rows:
            c = float(r.c or 0)
            d = float(r.d or 0)
            if r.account_code and r.account_code.startswith("6"):
                revenue += Decimal(str(c))
            if r.account_code and ("2221" in (r.account_code or "")):
                tax += Decimal(str(c)) - Decimal(str(d))
        voucher_count_stmt = select(func.count(FctVoucher.id)).where(FctVoucher.tenant_id == tenant_id)
        if entity_id:
            voucher_count_stmt = voucher_count_stmt.where(FctVoucher.entity_id == entity_id)
        if start_date:
            voucher_count_stmt = voucher_count_stmt.where(FctVoucher.biz_date >= start_date)
        if end_date:
            voucher_count_stmt = voucher_count_stmt.where(FctVoucher.biz_date <= end_date)
        voucher_count = (await session.execute(voucher_count_stmt)).scalar() or 0
        return {
            "report_type": "period_summary",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "revenue": float(revenue),
            "tax_amount": float(tax),
            "voucher_count": voucher_count,
            "entities": [{"entity_id": r.entity_id, "total_debit": float(r.total_debit or 0), "total_credit": float(r.total_credit or 0)} for r in rows],
        }

    async def get_report_aggregate(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """业、财、税、资金四维报表汇总：业务收入/成本/毛利、凭证与总账、销项进项税额、资金收付与对账状态。"""
        if entity_id == "":
            entity_id = None
        base_filter = [FctVoucher.tenant_id == tenant_id]
        if entity_id:
            base_filter.append(FctVoucher.entity_id == entity_id)
        if start_date:
            base_filter.append(FctVoucher.biz_date >= start_date)
        if end_date:
            base_filter.append(FctVoucher.biz_date <= end_date)
        base_and = and_(*base_filter)

        # 业：按科目汇总 6001 贷方=收入，1405 借方=成本（采购入库）
        biz_q = (
            select(
                FctVoucherLine.account_code,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("d"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("c"),
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(base_and)
            .group_by(FctVoucherLine.account_code)
        )
        biz_result = await session.execute(biz_q)
        biz_rows = biz_result.all()
        revenue = Decimal(0)
        cost = Decimal(0)
        for r in biz_rows:
            c, d = Decimal(str(r.c or 0)), Decimal(str(r.d or 0))
            if r.account_code and r.account_code.startswith("6"):
                revenue += c
            if r.account_code and r.account_code == DEFAULT_ACCOUNT_INVENTORY:
                cost += d

        # 财：凭证数、总借贷
        v_count_q = select(func.count(FctVoucher.id)).where(base_and)
        v_count = (await session.execute(v_count_q)).scalar() or 0
        v_totals_q = (
            select(
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("td"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("tc"),
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(base_and)
        )
        v_totals_row = (await session.execute(v_totals_q)).one()
        total_debit = float(v_totals_row.td or 0)
        total_credit = float(v_totals_row.tc or 0)
        ledger = await self.get_ledger_balances(session, tenant_id=tenant_id, entity_id=entity_id, as_of_date=end_date)

        # 税：销项(2221 贷方)、进项(2221_01 借方)
        tax_q = (
            select(
                FctVoucherLine.account_code,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("d"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("c"),
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(base_and)
            .group_by(FctVoucherLine.account_code)
        )
        tax_result = await session.execute(tax_q)
        tax_rows = tax_result.all()
        output_tax = Decimal(0)
        input_tax = Decimal(0)
        for r in tax_rows:
            c, d = Decimal(str(r.c or 0)), Decimal(str(r.d or 0))
            if r.account_code == DEFAULT_ACCOUNT_TAX_PAYABLE:
                output_tax += c
            if r.account_code == DEFAULT_ACCOUNT_TAX_INPUT:
                input_tax += d
        net_tax = output_tax - input_tax

        # 资金：流水收付汇总、对账状态
        cash_in = Decimal(0)
        cash_out = Decimal(0)
        cash_filter = [FctCashTransaction.tenant_id == tenant_id]
        if entity_id:
            cash_filter.append(FctCashTransaction.entity_id == entity_id)
        if start_date:
            cash_filter.append(FctCashTransaction.tx_date >= start_date)
        if end_date:
            cash_filter.append(FctCashTransaction.tx_date <= end_date)
        cash_and = and_(*cash_filter)
        cash_sum_q = (
            select(FctCashTransaction.direction, func.coalesce(func.sum(FctCashTransaction.amount), 0).label("amt"))
            .where(cash_and)
            .group_by(FctCashTransaction.direction)
        )
        cash_sum_result = await session.execute(cash_sum_q)
        for r in cash_sum_result.all():
            amt = float(r.amt or 0)
            if r.direction == "in":
                cash_in += Decimal(str(amt))
            else:
                cash_out += Decimal(str(amt))
        recon = await self.get_cash_reconciliation_status(session, tenant_id=tenant_id, entity_id=entity_id)

        return {
            "report_type": "aggregate",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "business": {
                "revenue": float(revenue),
                "cost": float(cost),
                "gross_margin": float(revenue - cost),
            },
            "finance": {
                "voucher_count": v_count,
                "total_debit": total_debit,
                "total_credit": total_credit,
                "ledger": ledger,
            },
            "tax": {
                "output_tax": float(output_tax),
                "input_tax": float(input_tax),
                "net_tax": float(net_tax),
            },
            "treasury": {
                "cash_in": float(cash_in),
                "cash_out": float(cash_out),
                "unmatched_count": recon.get("unmatched_count", 0),
                "unmatched_amount": recon.get("unmatched_amount", 0),
            },
        }

    async def get_report_trend(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        group_by: str = "day",
    ) -> Dict[str, Any]:
        """期间趋势分析：按日/周/月/季汇总收入、税额、凭证数（group_by: day|week|month|quarter）。"""
        if entity_id == "":
            entity_id = None
        base_filter = [FctVoucher.tenant_id == tenant_id]
        if entity_id:
            base_filter.append(FctVoucher.entity_id == entity_id)
        if start_date:
            base_filter.append(FctVoucher.biz_date >= start_date)
        if end_date:
            base_filter.append(FctVoucher.biz_date <= end_date)
        base_and = and_(*base_filter)

        if group_by == "month":
            period_expr = func.to_char(FctVoucher.biz_date, "YYYY-MM")
        elif group_by == "quarter":
            period_expr = func.concat(
                func.to_char(FctVoucher.biz_date, "YYYY"),
                literal("-Q"),
                func.cast(func.extract("quarter", FctVoucher.biz_date), String),
            )
        elif group_by == "week":
            period_expr = func.to_char(FctVoucher.biz_date, "IYYY-IW")
        else:
            period_expr = FctVoucher.biz_date

        # 按 period + account_code 一次汇总，再在内存中按 period 聚合成收入/税额
        detail_q = (
            select(
                period_expr.label("period"),
                FctVoucherLine.account_code,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("d"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("c"),
            )
            .join(FctVoucherLine, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(base_and)
            .group_by(period_expr, FctVoucherLine.account_code)
        )
        detail_result = await session.execute(detail_q)
        detail_rows = detail_result.all()

        # 凭证数按 period 汇总
        count_q = (
            select(period_expr.label("period"), func.count(FctVoucher.id).label("cnt"))
            .where(base_and)
            .group_by(period_expr)
        )
        count_result = await session.execute(count_q)
        count_map = {str(r.period) if hasattr(r.period, "isoformat") else r.period: int(r.cnt or 0) for r in count_result.all()}

        period_stats: Dict[str, Dict[str, Any]] = {}
        for r in detail_rows:
            period_key = str(r.period) if hasattr(r.period, "isoformat") else r.period
            if period_key not in period_stats:
                period_stats[period_key] = {
                    "voucher_count": count_map.get(period_key, 0),
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                    "revenue": 0.0,
                    "cost": 0.0,
                    "tax_amount": 0.0,
                }
            c, d_val = float(r.c or 0), float(r.d or 0)
            period_stats[period_key]["total_debit"] += d_val
            period_stats[period_key]["total_credit"] += c
            if r.account_code and r.account_code.startswith("6"):
                period_stats[period_key]["revenue"] += c
            if r.account_code == DEFAULT_ACCOUNT_INVENTORY:
                period_stats[period_key]["cost"] += d_val
            if r.account_code and "2221" in (r.account_code or ""):
                period_stats[period_key]["tax_amount"] += c - d_val

        trend_items = [{"period": k, **v} for k, v in sorted(period_stats.items())]
        return {
            "report_type": "trend",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "group_by": group_by,
            "items": trend_items,
        }

    async def _entity_region_map(
        self, session: AsyncSession, tenant_id: str
    ) -> Dict[str, str]:
        """主数据中门店(store) code -> extra.region，用于按区域汇总。无 region 时用 entity_id 或空字符串。"""
        q = select(FctMaster.code, FctMaster.extra).where(
            and_(FctMaster.tenant_id == tenant_id, FctMaster.type == FctMasterType.STORE)
        )
        result = await session.execute(q)
        out: Dict[str, str] = {}
        for row in result.all():
            code = row.code or ""
            region = ""
            if row.extra and isinstance(row.extra, dict):
                region = (row.extra.get("region") or row.extra.get("region_id") or "") or ""
            out[code] = str(region).strip() if region else "_default"
        return out

    async def get_report_by_entity(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """按门店拆分汇总：每个 entity_id 的收入、成本、税额、凭证数等。"""
        base_filter = [FctVoucher.tenant_id == tenant_id]
        if start_date:
            base_filter.append(FctVoucher.biz_date >= start_date)
        if end_date:
            base_filter.append(FctVoucher.biz_date <= end_date)
        base_and = and_(*base_filter)

        # 按 entity_id + account_code 汇总
        detail_q = (
            select(
                FctVoucher.entity_id,
                FctVoucherLine.account_code,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("d"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("c"),
            )
            .join(FctVoucherLine, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(base_and)
            .group_by(FctVoucher.entity_id, FctVoucherLine.account_code)
        )
        detail_result = await session.execute(detail_q)
        detail_rows = detail_result.all()

        count_q = (
            select(FctVoucher.entity_id, func.count(FctVoucher.id).label("cnt"))
            .where(base_and)
            .group_by(FctVoucher.entity_id)
        )
        count_result = await session.execute(count_q)
        count_map: Dict[str, int] = {r.entity_id: int(r.cnt or 0) for r in count_result.all()}

        by_entity: Dict[str, Dict[str, Any]] = {}
        for r in detail_rows:
            eid = r.entity_id or ""
            if eid not in by_entity:
                by_entity[eid] = {
                    "entity_id": eid,
                    "revenue": 0.0,
                    "cost": 0.0,
                    "output_tax": 0.0,
                    "input_tax": 0.0,
                    "voucher_count": count_map.get(eid, 0),
                }
            c, d_val = float(r.c or 0), float(r.d or 0)
            if r.account_code and r.account_code.startswith("6"):
                by_entity[eid]["revenue"] += c
            if r.account_code == DEFAULT_ACCOUNT_INVENTORY:
                by_entity[eid]["cost"] += d_val
            if r.account_code == DEFAULT_ACCOUNT_TAX_PAYABLE:
                by_entity[eid]["output_tax"] += c
            if r.account_code == DEFAULT_ACCOUNT_TAX_INPUT:
                by_entity[eid]["input_tax"] += d_val

        for eid, row in by_entity.items():
            row["gross_margin"] = row["revenue"] - row["cost"]
            row["net_tax"] = row["output_tax"] - row["input_tax"]

        items = list(by_entity.values())
        items.sort(key=lambda x: (x["entity_id"],))

        return {
            "report_type": "by_entity",
            "tenant_id": tenant_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "items": items,
        }

    async def get_report_by_region(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """按区域拆分汇总：依赖主数据 FctMaster(type=store) 的 extra.region，按 region 聚合各门店指标。"""
        by_entity = await self.get_report_by_entity(
            session, tenant_id=tenant_id, start_date=start_date, end_date=end_date
        )
        entity_to_region = await self._entity_region_map(session, tenant_id=tenant_id)

        by_region: Dict[str, Dict[str, Any]] = {}
        for row in by_entity.get("items", []):
            eid = row.get("entity_id", "")
            region = entity_to_region.get(eid, "_default") or "_default"
            if region not in by_region:
                by_region[region] = {
                    "region": region,
                    "entity_count": 0,
                    "revenue": 0.0,
                    "cost": 0.0,
                    "gross_margin": 0.0,
                    "output_tax": 0.0,
                    "input_tax": 0.0,
                    "net_tax": 0.0,
                    "voucher_count": 0,
                    "entity_ids": [],
                }
            by_region[region]["entity_count"] += 1
            by_region[region]["entity_ids"].append(eid)
            by_region[region]["revenue"] += row.get("revenue", 0)
            by_region[region]["cost"] += row.get("cost", 0)
            by_region[region]["gross_margin"] += row.get("gross_margin", 0)
            by_region[region]["output_tax"] += row.get("output_tax", 0)
            by_region[region]["input_tax"] += row.get("input_tax", 0)
            by_region[region]["net_tax"] += row.get("net_tax", 0)
            by_region[region]["voucher_count"] += row.get("voucher_count", 0)

        items = list(by_region.values())
        items.sort(key=lambda x: (x["region"],))

        return {
            "report_type": "by_region",
            "tenant_id": tenant_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "items": items,
        }

    async def get_report_comparison(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        compare_type: str = "yoy",
    ) -> Dict[str, Any]:
        """同比/环比分析：compare_type=yoy 同比（同期去年）, mom 环比（上月）, qoq 环比（上季）。返回当期、基期指标及增长率。"""
        if entity_id == "":
            entity_id = None
        if not start_date or not end_date:
            return {
                "report_type": "comparison",
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "error": "start_date 与 end_date 必填",
            }
        from datetime import timedelta

        baseline_start: Optional[date] = None
        baseline_end: Optional[date] = None
        if compare_type == "yoy":
            baseline_start = date(start_date.year - 1, start_date.month, start_date.day)
            baseline_end = date(end_date.year - 1, end_date.month, end_date.day)
        elif compare_type == "mom":
            # 当期若为整月，基期为上月整月
            if start_date.day == 1 and end_date.day >= 28:
                from calendar import monthrange
                _, last = monthrange(start_date.year, start_date.month)
                if end_date.day == last:
                    baseline_end = date(start_date.year, start_date.month, 1) - timedelta(days=1)
                    baseline_start = baseline_end.replace(day=1)
                else:
                    delta = (end_date - start_date).days + 1
                    baseline_end = start_date - timedelta(days=1)
                    baseline_start = baseline_end - timedelta(days=delta - 1)
            else:
                delta = (end_date - start_date).days + 1
                baseline_end = start_date - timedelta(days=1)
                baseline_start = baseline_end - timedelta(days=delta - 1)
        elif compare_type == "qoq":
            delta = (end_date - start_date).days + 1
            baseline_end = start_date - timedelta(days=1)
            baseline_start = baseline_end - timedelta(days=delta - 1)
        else:
            return {
                "report_type": "comparison",
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "error": f"compare_type 需为 yoy|mom|qoq，当前为 {compare_type}",
            }

        current = await self.get_report_aggregate(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date
        )
        baseline = await self.get_report_aggregate(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=baseline_start, end_date=baseline_end
        )

        def _pct(current_val: float, baseline_val: float) -> Optional[float]:
            if baseline_val == 0:
                return None
            return round((current_val - baseline_val) / baseline_val * 100, 2)

        cur_b = current.get("business", {})
        cur_f = current.get("finance", {})
        cur_t = current.get("tax", {})
        cur_tr = current.get("treasury", {})
        base_b = baseline.get("business", {})
        base_f = baseline.get("finance", {})
        base_t = baseline.get("tax", {})
        base_tr = baseline.get("treasury", {})

        return {
            "report_type": "comparison",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "compare_type": compare_type,
            "current_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "business": cur_b,
                "finance": {"voucher_count": cur_f.get("voucher_count"), "total_debit": cur_f.get("total_debit"), "total_credit": cur_f.get("total_credit")},
                "tax": cur_t,
                "treasury": cur_tr,
            },
            "baseline_period": {
                "start_date": baseline_start.isoformat(),
                "end_date": baseline_end.isoformat(),
                "business": base_b,
                "finance": {"voucher_count": base_f.get("voucher_count"), "total_debit": base_f.get("total_debit"), "total_credit": base_f.get("total_credit")},
                "tax": base_t,
                "treasury": base_tr,
            },
            "pct_change": {
                "revenue": _pct(cur_b.get("revenue", 0), base_b.get("revenue", 0)),
                "cost": _pct(cur_b.get("cost", 0), base_b.get("cost", 0)),
                "gross_margin": _pct(cur_b.get("gross_margin", 0), base_b.get("gross_margin", 0)),
                "voucher_count": _pct(float(cur_f.get("voucher_count", 0)), float(base_f.get("voucher_count", 0))),
                "output_tax": _pct(cur_t.get("output_tax", 0), base_t.get("output_tax", 0)),
                "input_tax": _pct(cur_t.get("input_tax", 0), base_t.get("input_tax", 0)),
                "net_tax": _pct(cur_t.get("net_tax", 0), base_t.get("net_tax", 0)),
                "cash_in": _pct(cur_tr.get("cash_in", 0), base_tr.get("cash_in", 0)),
                "cash_out": _pct(cur_tr.get("cash_out", 0), base_tr.get("cash_out", 0)),
            },
        }

    # ---------- 年度计划与达成分析 ----------
    PLAN_METRIC_KEYS = ("revenue", "cost", "gross_margin", "output_tax", "input_tax", "net_tax", "cash_in", "cash_out", "voucher_count")
    PERIODS_IN_YEAR = {"day": 365, "week": 52, "month": 12, "quarter": 4}
    # 收入类：剩余目标 = 计划 - 实际，正=未达成，负=超额
    TARGET_REMAINING_KEYS = ("revenue", "tax_amount", "cash_in")
    # 成本/支出类：剩余预算 = 计划 - 实际，正=预算有余，负=超支
    BUDGET_REMAINING_KEYS = ("cost", "cash_out")

    async def upsert_plan(
        self,
        session: AsyncSession,
        tenant_id: str,
        plan_year: int,
        targets: Dict[str, float],
        entity_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """年度计划 upsert：按租户+主体+年度唯一，targets 为业财税资金指标年度目标。租户级计划 entity_id 存空字符串。"""
        entity_key = (entity_id or "").strip() or ""
        q = select(FctPlan).where(
            and_(
                FctPlan.tenant_id == tenant_id,
                FctPlan.plan_year == plan_year,
                FctPlan.entity_id == entity_key,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        filtered = {k: float(v) for k, v in (targets or {}).items() if k in self.PLAN_METRIC_KEYS}
        if not filtered:
            return {"success": False, "error": "targets 至少包含一个有效指标: " + ", ".join(self.PLAN_METRIC_KEYS)}
        if row:
            row.targets = {**(row.targets or {}), **filtered}
            row.extra = extra
            await session.flush()
            await session.commit()
            return {"success": True, "id": str(row.id), "action": "updated"}
        new_id = uuid.uuid4()
        session.add(FctPlan(id=new_id, tenant_id=tenant_id, entity_id=entity_key, plan_year=plan_year, targets=filtered, extra=extra))
        await session.flush()
        await session.commit()
        return {"success": True, "id": str(new_id), "action": "created"}

    async def _cash_by_period(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        granularity: str = "month",
    ) -> Dict[str, Dict[str, float]]:
        """按期间汇总资金流水：period -> { cash_in, cash_out }。与 trend 同粒度。"""
        if entity_id == "":
            entity_id = None
        base = [FctCashTransaction.tenant_id == tenant_id]
        if entity_id:
            base.append(FctCashTransaction.entity_id == entity_id)
        if start_date:
            base.append(FctCashTransaction.tx_date >= start_date)
        if end_date:
            base.append(FctCashTransaction.tx_date <= end_date)
        base_and = and_(*base)
        if granularity == "month":
            period_expr = func.to_char(FctCashTransaction.tx_date, "YYYY-MM")
        elif granularity == "quarter":
            period_expr = func.concat(
                func.to_char(FctCashTransaction.tx_date, "YYYY"),
                literal("-Q"),
                func.cast(func.extract("quarter", FctCashTransaction.tx_date), String),
            )
        elif granularity == "week":
            period_expr = func.to_char(FctCashTransaction.tx_date, "IYYY-IW")
        else:
            period_expr = FctCashTransaction.tx_date
        q = (
            select(
                period_expr.label("period"),
                FctCashTransaction.direction,
                func.coalesce(func.sum(FctCashTransaction.amount), 0).label("amt"),
            )
            .where(base_and)
            .group_by(period_expr, FctCashTransaction.direction)
        )
        result = await session.execute(q)
        out: Dict[str, Dict[str, float]] = {}
        for r in result.all():
            period_key = str(r.period) if hasattr(r.period, "isoformat") else r.period
            if period_key not in out:
                out[period_key] = {"cash_in": 0.0, "cash_out": 0.0}
            amt = float(r.amt or 0)
            if r.direction == "in":
                out[period_key]["cash_in"] += amt
            else:
                out[period_key]["cash_out"] += amt
        return out

    async def get_plan(
        self,
        session: AsyncSession,
        tenant_id: str,
        plan_year: int,
        entity_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """查询年度计划；entity_id 为空则查租户级（库存 entity_id 为空字符串）。"""
        entity_key = (entity_id or "").strip() or ""
        q = select(FctPlan).where(
            and_(
                FctPlan.tenant_id == tenant_id,
                FctPlan.plan_year == plan_year,
                FctPlan.entity_id == entity_key,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        if not row:
            return None
        return {"id": str(row.id), "tenant_id": row.tenant_id, "entity_id": row.entity_id or None, "plan_year": row.plan_year, "targets": row.targets or {}, "extra": row.extra}

    async def get_plan_vs_actual(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        entity_id: Optional[str] = None,
        granularity: str = "month",
    ) -> Dict[str, Any]:
        """年度计划 vs 实际：按日/周/月/季对比达成与差距。granularity: day|week|month|quarter。"""
        if entity_id == "":
            entity_id = None
        if not start_date or not end_date:
            return {"report_type": "plan_vs_actual", "tenant_id": tenant_id, "error": "start_date 与 end_date 必填"}
        plan_year = start_date.year
        plan_row = await self.get_plan(session, tenant_id=tenant_id, plan_year=plan_year, entity_id=entity_id or None)
        if not plan_row:
            return {
                "report_type": "plan_vs_actual",
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "plan_year": plan_year,
                "error": "未配置该年度计划，请先调用 plans 接口维护",
            }
        targets = plan_row.get("targets") or {}
        trend = await self.get_report_trend(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date, group_by=granularity
        )
        cash_by_period = await self._cash_by_period(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date, granularity=granularity
        )
        periods_in_year = self.PERIODS_IN_YEAR.get(granularity) or 12
        period_plan_denom = periods_in_year

        metric_keys = ("revenue", "cost", "tax_amount", "voucher_count", "cash_in", "cash_out")
        annual_plans = {
            "revenue": targets.get("revenue") or 0,
            "cost": targets.get("cost") or 0,
            "tax_amount": targets.get("output_tax") or targets.get("net_tax") or 0,
            "voucher_count": targets.get("voucher_count") or 0,
            "cash_in": targets.get("cash_in") or 0,
            "cash_out": targets.get("cash_out") or 0,
        }

        items_by_period: Dict[str, Dict[str, Any]] = {}
        for t in trend.get("items", []):
            period_key = t.get("period")
            if period_key is None:
                continue
            period_key = str(period_key)
            if period_key not in items_by_period:
                items_by_period[period_key] = {"period": period_key, "plan": {}, "actual": {}, "achievement_pct": {}, "gap": {}, "gap_pct": {}}
            items_by_period[period_key]["actual"]["revenue"] = t.get("revenue", 0)
            items_by_period[period_key]["actual"]["cost"] = t.get("cost", 0)
            items_by_period[period_key]["actual"]["tax_amount"] = t.get("tax_amount", 0)
            items_by_period[period_key]["actual"]["voucher_count"] = t.get("voucher_count", 0)
            cash = cash_by_period.get(period_key) or {}
            items_by_period[period_key]["actual"]["cash_in"] = cash.get("cash_in", 0)
            items_by_period[period_key]["actual"]["cash_out"] = cash.get("cash_out", 0)
            for k in metric_keys:
                annual = annual_plans.get(k) or 0
                items_by_period[period_key]["plan"][k] = round(annual / period_plan_denom, 2) if period_plan_denom else 0
            for k in metric_keys:
                plan_val = items_by_period[period_key]["plan"].get(k) or 0
                actual_val = items_by_period[period_key]["actual"].get(k) or 0
                if plan_val != 0:
                    items_by_period[period_key]["achievement_pct"][k] = round(actual_val / plan_val * 100, 2)
                    items_by_period[period_key]["gap"][k] = round(actual_val - plan_val, 2)
                    items_by_period[period_key]["gap_pct"][k] = round((actual_val - plan_val) / plan_val * 100, 2)
                else:
                    items_by_period[period_key]["achievement_pct"][k] = None
                    items_by_period[period_key]["gap"][k] = round(actual_val, 2)
                    items_by_period[period_key]["gap_pct"][k] = None

        sorted_periods = sorted(items_by_period.keys())
        year_actual: Dict[str, float] = {k: 0.0 for k in metric_keys}
        for k in metric_keys:
            year_actual[k] = sum(items_by_period[p]["actual"].get(k, 0) for p in sorted_periods)

        def _period_ordinal(period_key: str) -> int:
            """期间在年内的序号（1 起），用于累计计划。"""
            if granularity == "month" and len(period_key) >= 7:
                try:
                    return int(period_key.split("-")[1])
                except (IndexError, ValueError):
                    return 1
            if granularity == "quarter" and "Q" in period_key:
                try:
                    return int(period_key.split("-Q")[1])
                except (IndexError, ValueError):
                    return 1
            if granularity == "week":
                try:
                    return int(period_key.split("-")[1])
                except (IndexError, ValueError):
                    return 1
            if granularity == "day" and hasattr(period_key, "split"):
                try:
                    d = date.fromisoformat(period_key)
                    return d.timetuple().tm_yday
                except Exception:
                    return 1
            return 1

        cumulative_actual: Dict[str, float] = {k: 0.0 for k in metric_keys}
        for period_key in sorted_periods:
            row = items_by_period[period_key]
            for k in metric_keys:
                cumulative_actual[k] += row["actual"].get(k, 0)
            ordinal = _period_ordinal(period_key)
            cumulative_plan = {k: round((annual_plans.get(k) or 0) * ordinal / periods_in_year, 2) for k in metric_keys}
            row["cumulative_actual"] = dict(cumulative_actual)
            row["cumulative_plan"] = cumulative_plan
            row["cumulative_achievement_pct"] = {}
            # 收入类剩余目标：还差多少达成；正=未达成，负=超额
            row["target_remaining"] = {k: round((annual_plans.get(k) or 0) - cumulative_actual.get(k, 0), 2) for k in self.TARGET_REMAINING_KEYS}
            # 成本/支出类剩余预算：还剩多少可花；正=有余，负=超支
            row["budget_remaining"] = {k: round((annual_plans.get(k) or 0) - cumulative_actual.get(k, 0), 2) for k in self.BUDGET_REMAINING_KEYS}
            for k in metric_keys:
                cap = cumulative_plan.get(k) or 0
                ca = cumulative_actual.get(k) or 0
                row["cumulative_achievement_pct"][k] = round(ca / cap * 100, 2) if cap else None

        def _ach(base: float, actual: float) -> Optional[float]:
            return round(actual / base * 100, 2) if base else None

        # 年度：收入类剩余目标 / 成本/支出类剩余预算 区分
        year_target_remaining = {k: round((annual_plans.get(k) or 0) - year_actual.get(k, 0), 2) for k in self.TARGET_REMAINING_KEYS}
        year_budget_remaining = {k: round((annual_plans.get(k) or 0) - year_actual.get(k, 0), 2) for k in self.BUDGET_REMAINING_KEYS}

        return {
            "report_type": "plan_vs_actual",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "plan_year": plan_year,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "granularity": granularity,
            "year_plan": annual_plans,
            "year_actual": year_actual,
            "year_achievement_pct": {k: _ach(annual_plans.get(k) or 0, year_actual.get(k, 0)) for k in metric_keys},
            "year_target_remaining": year_target_remaining,
            "year_budget_remaining": year_budget_remaining,
            "items": [items_by_period[k] for k in sorted_periods],
        }

    # ---------- 主数据 ----------
    async def upsert_master(
        self,
        session: AsyncSession,
        tenant_id: str,
        master_type: str,
        code: str,
        name: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """主数据 upsert（门店/客商/科目/银行账户）"""
        try:
            mtype = FctMasterType(master_type)
        except ValueError:
            return {"success": False, "error": f"invalid type: {master_type}"}
        result = await session.execute(
            select(FctMaster).where(
                and_(
                    FctMaster.tenant_id == tenant_id,
                    FctMaster.type == mtype,
                    FctMaster.code == code,
                )
            )
        )
        row = result.scalars().one_or_none()
        if row:
            row.name = name
            row.extra = extra
            await session.flush()
            await session.commit()
            return {"success": True, "id": str(row.id), "action": "updated"}
        new_id = uuid.uuid4()
        session.add(FctMaster(id=new_id, tenant_id=tenant_id, type=mtype, code=code, name=name, extra=extra))
        await session.flush()
        await session.commit()
        return {"success": True, "id": str(new_id), "action": "created"}

    async def list_master(
        self,
        session: AsyncSession,
        tenant_id: str,
        master_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        count_q = select(func.count(FctMaster.id)).where(FctMaster.tenant_id == tenant_id)
        if master_type:
            try:
                count_q = count_q.where(FctMaster.type == FctMasterType(master_type))
            except ValueError:
                pass
        total = (await session.execute(count_q)).scalar() or 0
        q = select(FctMaster).where(FctMaster.tenant_id == tenant_id).order_by(FctMaster.type, FctMaster.code)
        if master_type:
            try:
                q = q.where(FctMaster.type == FctMasterType(master_type))
            except ValueError:
                pass
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        items = result.scalars().all()
        return {"total": total, "items": [{"id": str(m.id), "type": m.type.value, "code": m.code, "name": m.name, "extra": m.extra} for m in items], "skip": skip, "limit": limit}

    # ---------- 资金流水与对账（占位） ----------
    async def list_cash_transactions(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        if entity_id == "":
            entity_id = None
        q = select(FctCashTransaction).where(FctCashTransaction.tenant_id == tenant_id).order_by(FctCashTransaction.tx_date.desc())
        if entity_id:
            q = q.where(FctCashTransaction.entity_id == entity_id)
        if start_date:
            q = q.where(FctCashTransaction.tx_date >= start_date)
        if end_date:
            q = q.where(FctCashTransaction.tx_date <= end_date)
        if status:
            q = q.where(FctCashTransaction.status == status)
        count_q = select(func.count(FctCashTransaction.id)).where(FctCashTransaction.tenant_id == tenant_id)
        if entity_id:
            count_q = count_q.where(FctCashTransaction.entity_id == entity_id)
        if start_date:
            count_q = count_q.where(FctCashTransaction.tx_date >= start_date)
        if end_date:
            count_q = count_q.where(FctCashTransaction.tx_date <= end_date)
        if status:
            count_q = count_q.where(FctCashTransaction.status == status)
        total = (await session.execute(count_q)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"total": total, "items": [{"id": str(r.id), "entity_id": r.entity_id, "tx_date": r.tx_date.isoformat(), "amount": float(r.amount or 0), "direction": r.direction, "status": r.status, "description": r.description} for r in rows], "skip": skip, "limit": limit}

    async def create_cash_transaction(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        tx_date: date,
        amount: float,
        direction: str,
        description: Optional[str] = None,
        ref_id: Optional[str] = None,
        generate_voucher: bool = False,
        budget_check: Optional[Dict[str, Any]] = None,
        budget_occupy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """资金收付款/内部划拨录入：写入流水，可选生成凭证；可选预算校验与占用。"""
        direction = direction.lower()
        if direction not in ("in", "out"):
            raise ValueError("direction 必须为 in 或 out")
        amt = Decimal(str(amount))
        if amt <= 0:
            raise ValueError("amount 必须大于 0")
        if budget_check:
            chk = await self.check_budget(
                session,
                tenant_id=tenant_id,
                budget_type=budget_check.get("budget_type") or "period",
                period=str(budget_check.get("period") or ""),
                category=str(budget_check.get("category") or ""),
                amount_to_use=float(budget_check.get("amount_to_use") or amount),
                entity_id=str(budget_check.get("entity_id") or entity_id or ""),
            )
            if not chk.get("allowed", True):
                raise ValueError(f"超预算：剩余 {chk.get('remaining')}，本次 {chk.get('amount_to_use')}，超出 {chk.get('over_by')}")
        else:
            ctrl_cash = await self.get_budget_control_for(session, tenant_id=tenant_id, entity_id=entity_id, budget_type="period", category="cash")
            if ctrl_cash and ctrl_cash.get("enforce_check") and float(amount) > 0:
                period_str = tx_date.strftime("%Y%m")
                chk = await self.check_budget(
                    session,
                    tenant_id=tenant_id,
                    budget_type="period",
                    period=period_str,
                    category="cash",
                    amount_to_use=float(amount),
                    entity_id=entity_id or "",
                )
                if not chk.get("allowed", True):
                    raise ValueError(f"超预算（预算控制强制校验）：剩余 {chk.get('remaining')}，本次 {chk.get('amount_to_use')}，超出 {chk.get('over_by')}")
        tx = FctCashTransaction(
            tenant_id=tenant_id,
            entity_id=entity_id,
            tx_date=tx_date,
            amount=amt,
            direction=direction,
            ref_type="manual",
            ref_id=ref_id,
            status="pending",
            description=description or ("收款" if direction == "in" else "付款"),
        )
        session.add(tx)
        await session.flush()
        voucher_result = None
        if generate_voucher:
            voucher_no = await self._next_voucher_no(session, tenant_id, entity_id, tx_date)
            v = FctVoucher(
                voucher_no=voucher_no,
                tenant_id=tenant_id,
                entity_id=entity_id,
                biz_date=tx_date,
                event_type="manual",
                event_id=None,
                status=FctVoucherStatus.DRAFT,
                description=description or ("手工收款" if direction == "in" else "手工付款"),
                attachments={"cash_transaction_id": str(tx.id)},
            )
            session.add(v)
            await session.flush()
            line_list: List[FctVoucherLine] = []
            if direction == "in":
                l1 = FctVoucherLine(voucher_id=v.id, line_no=1, account_code=DEFAULT_ACCOUNT_BANK, account_name="银行存款", debit=amt, credit=Decimal(0), description="收款")
                l2 = FctVoucherLine(voucher_id=v.id, line_no=2, account_code=DEFAULT_ACCOUNT_OTHER_PAYABLE, account_name="其他应付款", debit=Decimal(0), credit=amt, description="手工收款")
                session.add(l1)
                session.add(l2)
                line_list = [l1, l2]
            else:
                l1 = FctVoucherLine(voucher_id=v.id, line_no=1, account_code=DEFAULT_ACCOUNT_OTHER_PAYABLE, account_name="其他应付款", debit=amt, credit=Decimal(0), description="手工付款")
                l2 = FctVoucherLine(voucher_id=v.id, line_no=2, account_code=DEFAULT_ACCOUNT_BANK, account_name="银行存款", debit=Decimal(0), credit=amt, description="付款")
                session.add(l1)
                session.add(l2)
                line_list = [l1, l2]
            await session.flush()
            tx.ref_id = str(v.id)
            voucher_result = _voucher_to_dict(v, line_list)
        await session.commit()
        if budget_occupy and float(budget_occupy.get("amount_to_use") or budget_occupy.get("amount") or amount) > 0:
            await self.occupy_budget(
                session,
                tenant_id=tenant_id,
                budget_type=budget_occupy.get("budget_type") or "period",
                period=str(budget_occupy.get("period") or ""),
                category=str(budget_occupy.get("category") or ""),
                amount=float(budget_occupy.get("amount_to_use") or budget_occupy.get("amount") or amount),
                entity_id=str(budget_occupy.get("entity_id") or entity_id or ""),
            )
        elif not budget_occupy and float(amount) > 0:
            ctrl_occupy_cash = await self.get_budget_control_for(session, tenant_id=tenant_id, entity_id=entity_id, budget_type="period", category="cash")
            if ctrl_occupy_cash and ctrl_occupy_cash.get("auto_occupy"):
                await self.occupy_budget(
                    session,
                    tenant_id=tenant_id,
                    budget_type="period",
                    period=tx_date.strftime("%Y%m"),
                    category="cash",
                    amount=float(amount),
                    entity_id=entity_id or "",
                )
        return {
            "cash_transaction": {"id": str(tx.id), "entity_id": tx.entity_id, "tx_date": tx.tx_date.isoformat(), "amount": float(tx.amount), "direction": tx.direction, "status": tx.status, "description": tx.description},
            "voucher": voucher_result,
        }

    async def get_cash_reconciliation_status(self, session: AsyncSession, tenant_id: str, entity_id: Optional[str] = None) -> Dict[str, Any]:
        """资金对账状态（未匹配笔数/金额）"""
        q = select(func.count(FctCashTransaction.id), func.coalesce(func.sum(FctCashTransaction.amount), 0)).where(
            and_(FctCashTransaction.tenant_id == tenant_id, FctCashTransaction.status == "pending")
        )
        if entity_id:
            q = q.where(FctCashTransaction.entity_id == entity_id)
        result = await session.execute(q)
        row = result.one()
        return {"tenant_id": tenant_id, "entity_id": entity_id, "unmatched_count": row[0] or 0, "unmatched_amount": float(row[1] or 0)}

    async def match_cash_transaction(
        self,
        session: AsyncSession,
        transaction_id: str,
        match_id: Optional[str] = None,
        match_type: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> Dict[str, Any]:
        """资金流水勾对：将 pending 流水标记为已匹配（或传入 match_id=None 取消匹配）。"""
        try:
            tid = uuid.UUID(transaction_id)
        except (ValueError, TypeError):
            raise ValueError("无效的流水 id")
        result = await session.execute(select(FctCashTransaction).where(FctCashTransaction.id == tid))
        tx = result.scalars().one_or_none()
        if not tx:
            raise ValueError("资金流水不存在")
        if match_id is None or match_id == "":
            if tx.status != "matched":
                raise ValueError("仅已匹配流水可取消匹配")
            tx.status = "pending"
            tx.match_id = None
            await session.commit()
            return {"success": True, "transaction_id": transaction_id, "status": "pending", "message": "已取消匹配"}
        if tx.status != "pending":
            raise ValueError("仅待匹配流水可执行勾对")
        try:
            mid = uuid.UUID(match_id)
        except (ValueError, TypeError):
            mid = None
        tx.status = "matched"
        tx.match_id = mid
        await session.commit()
        return {"success": True, "transaction_id": transaction_id, "status": "matched", "match_id": match_id}

    async def unmatch_cash_transaction(self, session: AsyncSession, transaction_id: str) -> Dict[str, Any]:
        """取消资金流水勾对。"""
        return await self.match_cash_transaction(session, transaction_id, match_id=None)

    async def import_cash_transactions(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        items: List[Dict[str, Any]],
        ref_type: str = "bank",
        skip_duplicate_ref_id: bool = True,
    ) -> Dict[str, Any]:
        """批量导入资金流水（如银行流水）。items: [{tx_date, amount, direction, ref_id?, description?}]；ref_id 可选用于去重。"""
        imported = 0
        skipped = 0
        errors: List[str] = []
        for i, row in enumerate(items):
            try:
                tx_date = row.get("tx_date")
                if tx_date is None:
                    errors.append(f"第{i+1}行缺少 tx_date")
                    skipped += 1
                    continue
                if isinstance(tx_date, str):
                    tx_date = date.fromisoformat(tx_date)
                amount = Decimal(str(row.get("amount", 0)))
                if amount <= 0:
                    errors.append(f"第{i+1}行 amount 须大于 0")
                    skipped += 1
                    continue
                direction = (row.get("direction") or "in").lower()
                if direction not in ("in", "out"):
                    errors.append(f"第{i+1}行 direction 须为 in/out")
                    skipped += 1
                    continue
                ref_id = row.get("ref_id") or row.get("bank_ref_no")
                if skip_duplicate_ref_id and ref_id:
                    ex = await session.execute(
                        select(FctCashTransaction.id).where(
                            and_(
                                FctCashTransaction.tenant_id == tenant_id,
                                FctCashTransaction.entity_id == entity_id,
                                FctCashTransaction.ref_type == ref_type,
                                FctCashTransaction.ref_id == ref_id,
                            )
                        )
                    )
                    if ex.scalars().first() is not None:
                        skipped += 1
                        continue
                tx = FctCashTransaction(
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    tx_date=tx_date,
                    amount=amount,
                    direction=direction,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    status="pending",
                    description=row.get("description") or "",
                )
                session.add(tx)
                imported += 1
            except Exception as e:
                errors.append(f"第{i+1}行: {e}")
                skipped += 1
        await session.commit()
        return {"imported": imported, "skipped": skipped, "errors": errors}

    # ---------- 税务（占位） ----------
    async def list_tax_invoices(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        invoice_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        q = select(FctTaxInvoice).where(FctTaxInvoice.tenant_id == tenant_id).order_by(FctTaxInvoice.invoice_date.desc())
        if entity_id:
            q = q.where(FctTaxInvoice.entity_id == entity_id)
        if invoice_type:
            q = q.where(FctTaxInvoice.invoice_type == invoice_type)
        if start_date:
            q = q.where(FctTaxInvoice.invoice_date >= start_date)
        if end_date:
            q = q.where(FctTaxInvoice.invoice_date <= end_date)
        count_q = select(func.count(FctTaxInvoice.id)).where(FctTaxInvoice.tenant_id == tenant_id)
        if entity_id:
            count_q = count_q.where(FctTaxInvoice.entity_id == entity_id)
        if invoice_type:
            count_q = count_q.where(FctTaxInvoice.invoice_type == invoice_type)
        if start_date:
            count_q = count_q.where(FctTaxInvoice.invoice_date >= start_date)
        if end_date:
            count_q = count_q.where(FctTaxInvoice.invoice_date <= end_date)
        total = (await session.execute(count_q)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"total": total, "items": [{"id": str(r.id), "invoice_type": r.invoice_type, "invoice_no": r.invoice_no, "amount": float(r.amount or 0), "tax_amount": float(r.tax_amount or 0), "invoice_date": r.invoice_date.isoformat() if r.invoice_date else None, "status": r.status} for r in rows], "skip": skip, "limit": limit}

    async def create_tax_invoice(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        invoice_type: str,
        invoice_no: Optional[str] = None,
        amount: Optional[float] = None,
        tax_amount: Optional[float] = None,
        invoice_date: Optional[date] = None,
        status: str = "draft",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发票登记：进项/销项，同租户下 invoice_type+invoice_no 唯一。"""
        invoice_type = (invoice_type or "").strip().lower()
        if invoice_type not in ("output", "input"):
            raise ValueError("invoice_type 必须为 output 或 input")
        if invoice_no:
            dup = await session.execute(
                select(FctTaxInvoice.id).where(
                    and_(
                        FctTaxInvoice.tenant_id == tenant_id,
                        FctTaxInvoice.invoice_type == invoice_type,
                        FctTaxInvoice.invoice_no == invoice_no,
                    )
                )
            )
            if dup.scalars().first() is not None:
                raise ValueError(f"发票号已存在：{invoice_type} {invoice_no}")
        inv = FctTaxInvoice(
            tenant_id=tenant_id,
            entity_id=entity_id or "",
            invoice_type=invoice_type,
            invoice_no=invoice_no or "",
            amount=Decimal(str(amount or 0)),
            tax_amount=Decimal(str(tax_amount or 0)),
            invoice_date=invoice_date,
            status=status or "draft",
            extra=extra,
        )
        session.add(inv)
        await session.flush()
        await session.commit()
        await session.refresh(inv)
        return {"success": True, "id": str(inv.id), "invoice_type": inv.invoice_type, "invoice_no": inv.invoice_no, "amount": float(inv.amount or 0), "tax_amount": float(inv.tax_amount or 0), "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None, "status": inv.status}

    async def update_tax_invoice(
        self,
        session: AsyncSession,
        invoice_id: str,
        invoice_no: Optional[str] = None,
        amount: Optional[float] = None,
        tax_amount: Optional[float] = None,
        invoice_date: Optional[date] = None,
        status: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """更新发票（不含 voucher_id，关联凭证用 link_invoice_to_voucher）。"""
        try:
            iid = uuid.UUID(invoice_id)
        except (ValueError, TypeError):
            raise ValueError("无效的发票 id")
        result = await session.execute(select(FctTaxInvoice).where(FctTaxInvoice.id == iid))
        inv = result.scalars().one_or_none()
        if not inv:
            raise ValueError("发票不存在")
        if invoice_no is not None:
            if inv.invoice_no != invoice_no:
                dup = await session.execute(
                    select(FctTaxInvoice.id).where(
                        and_(
                            FctTaxInvoice.tenant_id == inv.tenant_id,
                            FctTaxInvoice.invoice_type == inv.invoice_type,
                            FctTaxInvoice.invoice_no == invoice_no,
                            FctTaxInvoice.id != iid,
                        )
                    )
                )
                if dup.scalars().first() is not None:
                    raise ValueError(f"发票号已存在：{inv.invoice_type} {invoice_no}")
            inv.invoice_no = invoice_no
        if amount is not None:
            inv.amount = Decimal(str(amount))
        if tax_amount is not None:
            inv.tax_amount = Decimal(str(tax_amount))
        if invoice_date is not None:
            inv.invoice_date = invoice_date
        if status is not None:
            inv.status = status
        if extra is not None:
            inv.extra = extra
        await session.commit()
        await session.refresh(inv)
        return {"success": True, "id": str(inv.id), "invoice_no": inv.invoice_no, "amount": float(inv.amount or 0), "tax_amount": float(inv.tax_amount or 0), "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None, "status": inv.status}

    async def list_tax_declarations(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        tax_type: Optional[str] = None,
        period: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        q = select(FctTaxDeclaration).where(FctTaxDeclaration.tenant_id == tenant_id).order_by(FctTaxDeclaration.period.desc())
        if entity_id:
            q = q.where(FctTaxDeclaration.entity_id == entity_id)
        if tax_type:
            q = q.where(FctTaxDeclaration.tax_type == tax_type)
        if period:
            q = q.where(FctTaxDeclaration.period == period)
        count_q = select(func.count(FctTaxDeclaration.id)).where(FctTaxDeclaration.tenant_id == tenant_id)
        if entity_id:
            count_q = count_q.where(FctTaxDeclaration.entity_id == entity_id)
        if tax_type:
            count_q = count_q.where(FctTaxDeclaration.tax_type == tax_type)
        if period:
            count_q = count_q.where(FctTaxDeclaration.period == period)
        total = (await session.execute(count_q)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"total": total, "items": [{"id": str(r.id), "tax_type": r.tax_type, "period": r.period, "status": r.status, "declared_at": r.declared_at} for r in rows], "skip": skip, "limit": limit}

    async def get_tax_declaration_draft(
        self,
        session: AsyncSession,
        tenant_id: str,
        tax_type: str,
        period: str,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """税务申报表草稿：从总账已过账凭证取数。vat：销项(2221 贷方)、进项(2221_01 借方)。period 如 202502。"""
        start_date, end_date = self._period_to_dates(period)
        q = (
            select(
                FctVoucherLine.account_code,
                func.coalesce(func.sum(FctVoucherLine.debit), 0).label("debit_sum"),
                func.coalesce(func.sum(FctVoucherLine.credit), 0).label("credit_sum"),
            )
            .join(FctVoucher, FctVoucherLine.voucher_id == FctVoucher.id)
            .where(
                and_(
                    FctVoucher.tenant_id == tenant_id,
                    FctVoucher.status == FctVoucherStatus.POSTED,
                    FctVoucher.biz_date >= start_date,
                    FctVoucher.biz_date <= end_date,
                )
            )
        )
        if entity_id:
            q = q.where(FctVoucher.entity_id == entity_id)
        q = q.group_by(FctVoucherLine.account_code)
        result = await session.execute(q)
        rows = result.all()
        output_tax = Decimal(0)
        input_tax = Decimal(0)
        for r in rows:
            if r.account_code == DEFAULT_ACCOUNT_TAX_PAYABLE or r.account_code == "2221":
                output_tax += r.credit_sum or 0
            if r.account_code == DEFAULT_ACCOUNT_TAX_INPUT or r.account_code == "2221_01":
                input_tax += r.debit_sum or 0
        return {
            "tax_type": tax_type,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "output_tax": float(output_tax),
            "input_tax": float(input_tax),
            "net_tax": float(output_tax - input_tax),
            "source": "ledger",
        }

    # ---------- Phase 4：费控/备用金 ----------
    async def upsert_petty_cash(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        cash_type: str,
        amount_limit: float,
        status: str = "active",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """备用金主档 upsert：按租户+主体+类型唯一。cash_type: fixed / temporary。"""
        q = select(FctPettyCash).where(
            and_(
                FctPettyCash.tenant_id == tenant_id,
                FctPettyCash.entity_id == entity_id,
                FctPettyCash.cash_type == cash_type,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        limit_dec = Decimal(str(amount_limit))
        if row:
            row.amount_limit = limit_dec
            row.status = status
            row.extra = extra
            await session.flush()
            await session.commit()
            return {"success": True, "id": str(row.id), "action": "updated"}
        new_id = uuid.uuid4()
        session.add(FctPettyCash(id=new_id, tenant_id=tenant_id, entity_id=entity_id, cash_type=cash_type, amount_limit=limit_dec, current_balance=Decimal(0), status=status, extra=extra))
        await session.flush()
        await session.commit()
        return {"success": True, "id": str(new_id), "action": "created"}

    async def list_petty_cash(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        cash_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """备用金主档列表。"""
        q = select(FctPettyCash).where(FctPettyCash.tenant_id == tenant_id).order_by(FctPettyCash.entity_id, FctPettyCash.cash_type)
        if entity_id:
            q = q.where(FctPettyCash.entity_id == entity_id)
        if cash_type:
            q = q.where(FctPettyCash.cash_type == cash_type)
        count_q = select(func.count(FctPettyCash.id)).where(FctPettyCash.tenant_id == tenant_id)
        if entity_id:
            count_q = count_q.where(FctPettyCash.entity_id == entity_id)
        if cash_type:
            count_q = count_q.where(FctPettyCash.cash_type == cash_type)
        total = (await session.execute(count_q)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"total": total, "items": [{"id": str(r.id), "tenant_id": r.tenant_id, "entity_id": r.entity_id, "cash_type": r.cash_type, "amount_limit": float(r.amount_limit or 0), "current_balance": float(r.current_balance or 0), "status": r.status} for r in rows], "skip": skip, "limit": limit}

    async def add_petty_cash_record(
        self,
        session: AsyncSession,
        petty_cash_id: str,
        record_type: str,
        amount: float,
        biz_date: date,
        ref_type: Optional[str] = None,
        ref_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """备用金流水：申请(apply)/冲销(offset)/还款(repay)。申请增加余额，冲销/还款减少。"""
        try:
            pc_id = uuid.UUID(petty_cash_id)
        except (ValueError, TypeError):
            return {"success": False, "error": "invalid petty_cash_id"}
        result = await session.execute(select(FctPettyCash).where(FctPettyCash.id == pc_id))
        pc = result.scalars().one_or_none()
        if not pc:
            return {"success": False, "error": "备用金主档不存在"}
        amt = Decimal(str(amount))
        if amt <= 0:
            return {"success": False, "error": "amount 须大于 0"}
        if record_type == "apply":
            delta = amt
        elif record_type in ("offset", "repay"):
            delta = -amt
            if (pc.current_balance or Decimal(0)) < amt:
                return {"success": False, "error": "余额不足"}
        else:
            return {"success": False, "error": "record_type 须为 apply/offset/repay"}
        rec_id = uuid.uuid4()
        session.add(FctPettyCashRecord(id=rec_id, petty_cash_id=pc_id, record_type=record_type, amount=amt, biz_date=biz_date, ref_type=ref_type, ref_id=ref_id, description=description))
        pc.current_balance = (pc.current_balance or Decimal(0)) + delta
        await session.flush()
        await session.commit()
        return {"success": True, "id": str(rec_id), "record_type": record_type, "new_balance": float(pc.current_balance)}

    async def list_petty_cash_records(
        self,
        session: AsyncSession,
        petty_cash_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """备用金流水列表。"""
        try:
            pc_id = uuid.UUID(petty_cash_id)
        except (ValueError, TypeError):
            return {"total": 0, "items": [], "skip": skip, "limit": limit}
        q = select(FctPettyCashRecord).where(FctPettyCashRecord.petty_cash_id == pc_id).order_by(FctPettyCashRecord.biz_date.desc())
        if start_date:
            q = q.where(FctPettyCashRecord.biz_date >= start_date)
        if end_date:
            q = q.where(FctPettyCashRecord.biz_date <= end_date)
        count_q = select(func.count(FctPettyCashRecord.id)).where(FctPettyCashRecord.petty_cash_id == pc_id)
        if start_date:
            count_q = count_q.where(FctPettyCashRecord.biz_date >= start_date)
        if end_date:
            count_q = count_q.where(FctPettyCashRecord.biz_date <= end_date)
        total = (await session.execute(count_q)).scalar() or 0
        q = q.offset(skip).limit(limit)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"total": total, "items": [{"id": str(r.id), "record_type": r.record_type, "amount": float(r.amount), "biz_date": r.biz_date.isoformat(), "ref_type": r.ref_type, "ref_id": r.ref_id, "description": r.description} for r in rows], "skip": skip, "limit": limit}

    # ---------- Phase 4：预算占位 ----------
    async def upsert_budget(
        self,
        session: AsyncSession,
        tenant_id: str,
        budget_type: str,
        period: str,
        category: str,
        amount: float,
        entity_id: str = "",
        status: str = "active",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """预算 upsert：按租户+主体+类型+期间+类别唯一。budget_type: project / period。"""
        entity_key = (entity_id or "").strip() or ""
        q = select(FctBudget).where(
            and_(
                FctBudget.tenant_id == tenant_id,
                FctBudget.entity_id == entity_key,
                FctBudget.budget_type == budget_type,
                FctBudget.period == period,
                FctBudget.category == category,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        amt = Decimal(str(amount))
        if row:
            row.amount = amt
            row.status = status
            row.extra = extra
            await session.flush()
            await session.commit()
            return {"success": True, "id": str(row.id), "action": "updated"}
        new_id = uuid.uuid4()
        session.add(FctBudget(id=new_id, tenant_id=tenant_id, entity_id=entity_key, budget_type=budget_type, period=period, category=category, amount=amt, used=Decimal(0), status=status, extra=extra))
        await session.flush()
        await session.commit()
        return {"success": True, "id": str(new_id), "action": "created"}

    async def get_budget(
        self,
        session: AsyncSession,
        tenant_id: str,
        budget_type: str,
        period: str,
        category: str,
        entity_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """查询单条预算。"""
        entity_key = (entity_id or "").strip() or ""
        q = select(FctBudget).where(
            and_(
                FctBudget.tenant_id == tenant_id,
                FctBudget.entity_id == entity_key,
                FctBudget.budget_type == budget_type,
                FctBudget.period == period,
                FctBudget.category == category,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        if not row:
            return None
        return {"id": str(row.id), "amount": float(row.amount or 0), "used": float(row.used or 0), "remaining": float((row.amount or 0) - (row.used or 0)), "status": row.status}

    async def get_budget_control_for(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        budget_type: str = "period",
        category: str = "",
    ) -> Optional[Dict[str, Any]]:
        """预算控制配置：先按 (tenant_id, entity_id, budget_type, category) 查，再按 (tenant_id, "", budget_type, "") 查。返回 enforce_check、auto_occupy（布尔）。"""
        eid = (entity_id or "").strip() or ""
        cat = (category or "").strip() or ""
        for e_key, c_key in [(eid, cat), ("", "")]:
            q = select(FctBudgetControl).where(
                and_(
                    FctBudgetControl.tenant_id == tenant_id,
                    FctBudgetControl.entity_id == e_key,
                    FctBudgetControl.budget_type == budget_type,
                    FctBudgetControl.category == c_key,
                )
            )
            result = await session.execute(q)
            row = result.scalars().one_or_none()
            if row:
                return {
                    "id": str(row.id),
                    "enforce_check": (row.enforce_check or "").lower() == "true",
                    "auto_occupy": (row.auto_occupy or "").lower() == "true",
                }
        return None

    async def upsert_budget_control(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str = "",
        budget_type: str = "period",
        category: str = "",
        enforce_check: bool = False,
        auto_occupy: bool = False,
    ) -> Dict[str, Any]:
        """预算控制配置 upsert：按 (tenant_id, entity_id, budget_type, category) 唯一。"""
        eid = (entity_id or "").strip() or ""
        cat = (category or "").strip() or ""
        q = select(FctBudgetControl).where(
            and_(
                FctBudgetControl.tenant_id == tenant_id,
                FctBudgetControl.entity_id == eid,
                FctBudgetControl.budget_type == budget_type,
                FctBudgetControl.category == cat,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        if row:
            row.enforce_check = "true" if enforce_check else "false"
            row.auto_occupy = "true" if auto_occupy else "false"
            await session.flush()
            await session.commit()
            return {"id": str(row.id), "action": "updated"}
        new_id = uuid.uuid4()
        session.add(
            FctBudgetControl(
                id=new_id,
                tenant_id=tenant_id,
                entity_id=eid,
                budget_type=budget_type,
                category=cat,
                enforce_check="true" if enforce_check else "false",
                auto_occupy="true" if auto_occupy else "false",
            )
        )
        await session.flush()
        await session.commit()
        return {"id": str(new_id), "action": "created"}

    async def list_budget_controls(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        budget_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """预算控制配置列表（按租户，可选按主体/类型筛选）。"""
        q = select(FctBudgetControl).where(FctBudgetControl.tenant_id == tenant_id).order_by(FctBudgetControl.entity_id, FctBudgetControl.budget_type, FctBudgetControl.category)
        if entity_id is not None and entity_id != "":
            q = q.where(FctBudgetControl.entity_id == entity_id)
        if budget_type:
            q = q.where(FctBudgetControl.budget_type == budget_type)
        result = await session.execute(q)
        rows = result.scalars().all()
        items = [
            {
                "id": str(r.id),
                "tenant_id": r.tenant_id,
                "entity_id": r.entity_id or "",
                "budget_type": r.budget_type,
                "category": r.category or "",
                "enforce_check": (r.enforce_check or "").lower() == "true",
                "auto_occupy": (r.auto_occupy or "").lower() == "true",
            }
            for r in rows
        ]
        return {"tenant_id": tenant_id, "items": items}

    async def check_budget(
        self,
        session: AsyncSession,
        tenant_id: str,
        budget_type: str,
        period: str,
        category: str,
        amount_to_use: float,
        entity_id: str = "",
    ) -> Dict[str, Any]:
        """预算占用校验：是否超预算；不实际占用，仅返回是否可占用及剩余。"""
        budget = await self.get_budget(session, tenant_id=tenant_id, budget_type=budget_type, period=period, category=category, entity_id=entity_id)
        if not budget:
            return {"allowed": True, "reason": "无该预算配置", "remaining": None}
        remaining = budget.get("remaining") or 0
        allowed = remaining >= amount_to_use
        return {"allowed": allowed, "remaining": remaining, "amount_to_use": amount_to_use, "over_by": max(0, amount_to_use - remaining) if not allowed else 0}

    async def occupy_budget(
        self,
        session: AsyncSession,
        tenant_id: str,
        budget_type: str,
        period: str,
        category: str,
        amount: float,
        entity_id: str = "",
    ) -> Dict[str, Any]:
        """预算占用：增加 used；与凭证/费用联动时调用。"""
        entity_key = (entity_id or "").strip() or ""
        q = select(FctBudget).where(
            and_(
                FctBudget.tenant_id == tenant_id,
                FctBudget.entity_id == entity_key,
                FctBudget.budget_type == budget_type,
                FctBudget.period == period,
                FctBudget.category == category,
            )
        )
        result = await session.execute(q)
        row = result.scalars().one_or_none()
        if not row:
            return {"success": False, "error": "预算不存在"}
        amt = Decimal(str(amount))
        row.used = (row.used or Decimal(0)) + amt
        await session.flush()
        await session.commit()
        return {"success": True, "used": float(row.used), "remaining": float((row.amount or 0) - row.used)}

    # ---------- Phase 4：发票闭环 ----------
    async def link_invoice_to_voucher(
        self,
        session: AsyncSession,
        invoice_id: str,
        voucher_id: str,
    ) -> Dict[str, Any]:
        """发票与凭证关联（票-账闭环）。"""
        try:
            inv_id = uuid.UUID(invoice_id)
            v_id = uuid.UUID(voucher_id)
        except (ValueError, TypeError):
            return {"success": False, "error": "invalid id"}
        result = await session.execute(select(FctTaxInvoice).where(FctTaxInvoice.id == inv_id))
        inv = result.scalars().one_or_none()
        if not inv:
            return {"success": False, "error": "发票不存在"}
        inv.voucher_id = v_id
        await session.flush()
        await session.commit()
        return {"success": True, "invoice_id": invoice_id, "voucher_id": voucher_id}

    async def list_invoices_by_voucher(self, session: AsyncSession, voucher_id: str) -> Dict[str, Any]:
        """按凭证查关联发票（票-账视图）。"""
        try:
            v_id = uuid.UUID(voucher_id)
        except (ValueError, TypeError):
            return {"items": []}
        q = select(FctTaxInvoice).where(FctTaxInvoice.voucher_id == v_id)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"items": [{"id": str(r.id), "invoice_no": r.invoice_no, "invoice_type": r.invoice_type, "amount": float(r.amount or 0), "tax_amount": float(r.tax_amount or 0), "verify_status": getattr(r, "verify_status", "pending")} for r in rows]}

    async def verify_invoice_stub(self, session: AsyncSession, invoice_id: str) -> Dict[str, Any]:
        """发票验真占位：对接税控/全电后实现；当前仅更新 verify_status=verified。"""
        try:
            inv_id = uuid.UUID(invoice_id)
        except (ValueError, TypeError):
            return {"success": False, "error": "invalid invoice_id"}
        result = await session.execute(select(FctTaxInvoice).where(FctTaxInvoice.id == inv_id))
        inv = result.scalars().one_or_none()
        if not inv:
            return {"success": False, "error": "发票不存在"}
        inv.verify_status = "verified"
        inv.verified_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await session.flush()
        await session.commit()
        return {"success": True, "invoice_id": str(inv_id), "verify_status": "verified", "message": "占位实现，实际验真需对接税控/全电"}

    # ---------- Phase 4：审批流占位 ----------
    async def create_approval_record(
        self,
        session: AsyncSession,
        tenant_id: str,
        ref_type: str,
        ref_id: str,
        step: int = 1,
        status: str = "pending",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """审批记录占位：凭证/付款/费用等，与 OA 或工作流对接时扩展。"""
        new_id = uuid.uuid4()
        session.add(FctApprovalRecord(id=new_id, tenant_id=tenant_id, ref_type=ref_type, ref_id=ref_id, step=step, status=status, extra=extra))
        await session.flush()
        await session.commit()
        return {"success": True, "id": str(new_id), "ref_type": ref_type, "ref_id": ref_id, "status": status}

    async def get_approval_by_ref(self, session: AsyncSession, tenant_id: str, ref_type: str, ref_id: str) -> Dict[str, Any]:
        """按业务单查审批记录占位。"""
        q = select(FctApprovalRecord).where(
            and_(FctApprovalRecord.tenant_id == tenant_id, FctApprovalRecord.ref_type == ref_type, FctApprovalRecord.ref_id == ref_id)
        ).order_by(FctApprovalRecord.step)
        result = await session.execute(q)
        rows = result.scalars().all()
        return {"items": [{"id": str(r.id), "step": r.step, "status": r.status, "approved_at": r.approved_at, "approved_by": r.approved_by} for r in rows]}


fct_service = FctService()
