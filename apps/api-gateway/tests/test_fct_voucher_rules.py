"""
业财凭证规则单元测试

- 借贷平衡校验与尾差
- 门店日结凭证：科目、金额、差额调整
- 采购入库凭证：科目、价税分离、辅助核算
- 与金蝶/用友及企业会计准则一致性
"""
import os

# 测试时提供最小环境变量，避免导入 src.services 时 AgentService 初始化触发 Settings 校验失败
for _k, _v in (
    ("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/zhilian_test"),
    ("REDIS_URL", "redis://localhost:6379/0"),
    ("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    ("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
    ("SECRET_KEY", "test-secret-key"),
    ("JWT_SECRET", "test-jwt-secret"),
):
    os.environ.setdefault(_k, _v)

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.fct_service import (
    FctService,
    DEFAULT_ACCOUNT_SALES,
    DEFAULT_ACCOUNT_TAX_PAYABLE,
    DEFAULT_ACCOUNT_BANK,
    DEFAULT_ACCOUNT_CASH,
    DEFAULT_ACCOUNT_INVENTORY,
    DEFAULT_ACCOUNT_TAX_INPUT,
    DEFAULT_ACCOUNT_PAYABLE,
    VOUCHER_BALANCE_TOLERANCE,
)


class TestVoucherBalanceHelpers:
    """借贷平衡辅助方法（与金蝶/用友一致：凭证必须借贷相等，允许 0.01 元尾差）"""

    def test_voucher_totals(self):
        total_d, total_c = FctService._voucher_totals([
            {"debit": Decimal("100.00"), "credit": Decimal(0)},
            {"debit": Decimal(0), "credit": Decimal("100.00")},
        ])
        assert total_d == Decimal("100.00")
        assert total_c == Decimal("100.00")

    def test_voucher_totals_ignores_missing(self):
        total_d, total_c = FctService._voucher_totals([
            {"debit": 50, "credit": None},
            {"debit": None, "credit": 50},
        ])
        assert total_d == Decimal(50)
        assert total_c == Decimal(50)

    def test_is_balanced_exact(self):
        assert FctService._is_balanced(Decimal("100"), Decimal("100")) is True

    def test_is_balanced_within_tolerance(self):
        assert FctService._is_balanced(Decimal("100"), Decimal("100.01")) is True
        assert FctService._is_balanced(Decimal("100.01"), Decimal("100")) is True

    def test_is_balanced_outside_tolerance(self):
        assert FctService._is_balanced(Decimal("100"), Decimal("101")) is False
        assert FctService._is_balanced(Decimal("99"), Decimal("100")) is False

    def test_tolerance_value(self):
        assert VOUCHER_BALANCE_TOLERANCE == Decimal("0.01")


class TestStoreDailySettlementVoucherRules:
    """门店日结凭证规则：借 银行存款/库存现金 贷 主营业务收入、应交税费"""

    @pytest.mark.asyncio
    async def test_store_daily_settlement_balanced_no_breakdown(self, test_db: AsyncSession):
        """无 payment_breakdown 时，单笔借银行存款，贷收入+税，应借贷平衡"""
        svc = FctService()
        body = {
            "event_id": "ev-store-001",
            "event_type": "store_daily_settlement",
            "payload": {
                "store_id": "STORE01",
                "biz_date": "2026-02-26",
                "total_sales": 10000,   # 100 元
                "total_sales_tax": 600,  # 6 元
                "discounts": 0,
            },
        }
        out = await svc.ingest_event(test_db, body)
        await test_db.commit()
        assert out is not None
        voucher = await svc.get_voucher_by_id(test_db, str(out.id))
        assert voucher is not None
        assert len(voucher.lines) >= 3  # 至少 1 借 + 收入 + 税，可能含差额调整行
        total_d = sum(l.debit or Decimal(0) for l in voucher.lines)
        total_c = sum(l.credit or Decimal(0) for l in voucher.lines)
        assert abs(total_d - total_c) <= Decimal("0.01"), "凭证应借贷平衡（含 0.01 尾差）"
        account_codes = [l.account_code for l in voucher.lines]
        assert DEFAULT_ACCOUNT_SALES in account_codes
        assert DEFAULT_ACCOUNT_TAX_PAYABLE in account_codes
        assert DEFAULT_ACCOUNT_BANK in account_codes or DEFAULT_ACCOUNT_CASH in account_codes

    @pytest.mark.asyncio
    async def test_store_daily_settlement_with_payment_breakdown_adjustment(self, test_db: AsyncSession):
        """payment_breakdown 合计与 revenue 不一致时，应自动差额调整使凭证平衡"""
        svc = FctService()
        body = {
            "event_id": "ev-store-002",
            "event_type": "store_daily_settlement",
            "payload": {
                "store_id": "STORE02",
                "biz_date": "2026-02-26",
                "total_sales": 10000,
                "total_sales_tax": 600,
                "discounts": 0,
                "payment_breakdown": [
                    {"method": "wechat", "amount": 5000},
                    {"method": "alipay", "amount": 4400},
                ],
            },
        }
        # 借方 94+94=188 元（按分/100），贷方 100-6=94 收入 + 6 税 = 100；差 88 元会触发差额调整
        out = await svc.ingest_event(test_db, body)
        await test_db.commit()
        assert out is not None
        voucher = await svc.get_voucher_by_id(test_db, str(out.id))
        assert voucher is not None
        total_d = sum(l.debit or Decimal(0) for l in voucher.lines)
        total_c = sum(l.credit or Decimal(0) for l in voucher.lines)
        assert abs(total_d - total_c) <= Decimal("0.01")

    @pytest.mark.asyncio
    async def test_store_daily_settlement_requires_biz_date(self, test_db: AsyncSession):
        """缺少 biz_date 应报错"""
        svc = FctService()
        body = {
            "event_id": "ev-store-003",
            "event_type": "store_daily_settlement",
            "payload": {"store_id": "STORE03"},
        }
        with pytest.raises(ValueError, match="biz_date"):
            await svc.ingest_event(test_db, body)


class TestPurchaseReceiptVoucherRules:
    """采购入库凭证规则：借 库存商品、应交税费-进项 贷 应付账款"""

    @pytest.mark.asyncio
    async def test_purchase_receipt_balanced(self, test_db: AsyncSession):
        """采购入库：价税分离，借贷平衡，含辅助核算"""
        svc = FctService()
        body = {
            "event_id": "ev-po-001",
            "event_type": "purchase_receipt",
            "payload": {
                "store_id": "STORE01",
                "biz_date": "2026-02-26",
                "supplier_id": "SUP001",
                "total": 10600,
                "tax": 600,
            },
        }
        out = await svc.ingest_event(test_db, body)
        await test_db.commit()
        assert out is not None
        voucher = await svc.get_voucher_by_id(test_db, str(out.id))
        assert voucher is not None
        total_d = sum(l.debit or Decimal(0) for l in voucher.lines)
        total_c = sum(l.credit or Decimal(0) for l in voucher.lines)
        assert abs(total_d - total_c) <= Decimal("0.01")
        account_codes = [l.account_code for l in voucher.lines]
        assert DEFAULT_ACCOUNT_INVENTORY in account_codes
        assert DEFAULT_ACCOUNT_PAYABLE in account_codes
        # 有税时应有进项科目
        assert DEFAULT_ACCOUNT_TAX_INPUT in account_codes
        payable_line = next(l for l in voucher.lines if l.account_code == DEFAULT_ACCOUNT_PAYABLE)
        assert payable_line.auxiliary is not None and (payable_line.auxiliary.get("supplier_id") == "SUP001" or "supplier" in str(payable_line.auxiliary).lower())

    @pytest.mark.asyncio
    async def test_purchase_receipt_requires_biz_date(self, test_db: AsyncSession):
        """缺少 biz_date 应报错"""
        svc = FctService()
        body = {
            "event_id": "ev-po-002",
            "event_type": "purchase_receipt",
            "payload": {"supplier_id": "SUP002", "total": 10000, "tax": 0},
        }
        with pytest.raises(ValueError, match="biz_date"):
            await svc.ingest_event(test_db, body)


class TestAccountCodeAlignment:
    """科目编码与企业会计准则/金蝶用友一致性"""

    def test_sales_and_tax_accounts(self):
        assert DEFAULT_ACCOUNT_SALES == "6001"
        assert DEFAULT_ACCOUNT_TAX_PAYABLE == "2221"

    def test_assets_and_payable(self):
        assert DEFAULT_ACCOUNT_CASH == "1001"
        assert DEFAULT_ACCOUNT_BANK == "1002"
        assert DEFAULT_ACCOUNT_INVENTORY == "1405"
        assert DEFAULT_ACCOUNT_PAYABLE == "2202"

    def test_tax_input_subledger(self):
        assert DEFAULT_ACCOUNT_TAX_INPUT == "2221_01"
