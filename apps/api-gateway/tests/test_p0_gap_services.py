"""
P0 Gap Services 测试
覆盖: CashierShiftService, CreditAccountService, RefundService, RushPromotionService
"""

import os
import sys
import types
import importlib.util
from datetime import datetime, timedelta, timezone

import pytest

# ── 动态加载（绕过 services/__init__.py 导入问题） ──────────────────────
src = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, src)
services_pkg = types.ModuleType("services")
services_pkg.__path__ = [os.path.join(src, "services")]
sys.modules["services"] = services_pkg


def _load(name):
    path = os.path.join(src, "services", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"services.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"services.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


cashier_mod = _load("cashier_shift_service")
credit_mod = _load("credit_account_service")
refund_mod = _load("refund_service")
rush_mod = _load("rush_promotion_service")

CashierShiftService = cashier_mod.CashierShiftService
CashDrawerCount = cashier_mod.CashDrawerCount
ShiftStatus = cashier_mod.ShiftStatus

CreditAccountService = credit_mod.CreditAccountService
AccountStatus = credit_mod.AccountStatus

RefundService = refund_mod.RefundService
RefundType = refund_mod.RefundType
RefundReason = refund_mod.RefundReason
RefundStatus = refund_mod.RefundStatus
AUTO_APPROVE_THRESHOLD_FEN = refund_mod.AUTO_APPROVE_THRESHOLD_FEN

RushPromotionService = rush_mod.RushPromotionService
RushReason = rush_mod.RushReason
RushChannel = rush_mod.RushChannel
RushStatus = rush_mod.RushStatus


# ═══════════════════════════════════════════════════════════════════════
# CashierShiftService 测试
# ═══════════════════════════════════════════════════════════════════════

class TestCashierShiftService:

    def _make_svc(self) -> CashierShiftService:
        return CashierShiftService()

    def test_open_shift_returns_open_status(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1", opening_float_fen=10000)
        assert shift.status == ShiftStatus.OPEN
        assert shift.store_id == "S001"
        assert shift.cashier_name == "张三"
        assert shift.opening_float_fen == 10000
        assert shift.open_time is not None

    def test_record_transaction_updates_cash(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1")
        assert svc.record_transaction(shift.shift_id, "cash", 5000) is True
        assert svc.record_transaction(shift.shift_id, "wechat", 3000) is True
        # 只有 cash 类型会累计到 system_cash_fen
        assert shift.system_cash_fen == 5000

    def test_record_transaction_rejects_unknown_shift(self):
        svc = self._make_svc()
        assert svc.record_transaction("nonexistent", "cash", 100) is False

    def test_close_shift_calculates_variance(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1", opening_float_fen=10000)
        svc.record_transaction(shift.shift_id, "cash", 5000)
        # 清点现金: 1张100元 = 10000分, 1张50元 = 5000分 → 共15000分
        drawer = CashDrawerCount(yuan_100=1, yuan_50=1)
        closed = svc.close_shift(shift.shift_id, drawer, notes="正常交接")
        assert closed.status == ShiftStatus.CLOSED
        # 差异 = 清点(15000) - (系统现金5000 + 备用金10000) = 0
        assert closed.variance_fen == 0

    def test_close_shift_detects_shortage(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1", opening_float_fen=10000)
        svc.record_transaction(shift.shift_id, "cash", 5000)
        # 只清点出100元(10000分)，少了5000分
        drawer = CashDrawerCount(yuan_100=1)
        closed = svc.close_shift(shift.shift_id, drawer)
        # 差异 = 10000 - (5000 + 10000) = -5000 → 短款
        assert closed.variance_fen == -5000

    def test_close_shift_raises_on_nonexistent(self):
        svc = self._make_svc()
        with pytest.raises(ValueError, match="班次不存在"):
            svc.close_shift("bad-id", CashDrawerCount())

    def test_audit_shift(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1")
        svc.close_shift(shift.shift_id, CashDrawerCount())
        audited = svc.audit_shift(shift.shift_id, "MGR01", True, "ok")
        assert audited.status == ShiftStatus.AUDITED

    def test_audit_shift_requires_closed(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1")
        with pytest.raises(ValueError, match="只有已关班"):
            svc.audit_shift(shift.shift_id, "MGR01", True)

    def test_get_shift_summary(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1", opening_float_fen=10000)
        svc.record_transaction(shift.shift_id, "cash", 3000)
        svc.record_transaction(shift.shift_id, "wechat", 2000)
        svc.record_transaction(shift.shift_id, "alipay", 1500)
        svc.record_transaction(shift.shift_id, "card", 800)
        svc.record_transaction(shift.shift_id, "other_method", 500)
        summary = svc.get_shift_summary(shift.shift_id)
        assert summary.cash_total_fen == 3000
        assert summary.wechat_total_fen == 2000
        assert summary.alipay_total_fen == 1500
        assert summary.card_total_fen == 800
        assert summary.other_total_fen == 500
        assert summary.order_count == 5

    def test_generate_handover_receipt(self):
        svc = self._make_svc()
        shift = svc.open_shift("S001", "C01", "张三", "REG-1", opening_float_fen=10000)
        svc.record_transaction(shift.shift_id, "cash", 5000)
        drawer = CashDrawerCount(yuan_100=1, yuan_50=1)
        svc.close_shift(shift.shift_id, drawer)
        receipt = svc.generate_handover_receipt(shift.shift_id)
        assert receipt["title"] == "收银交接单"
        assert receipt["cashier"] == "张三"
        assert receipt["variance_type"] == "无差异"
        assert "现金" in receipt["payment_summary"]

    def test_cash_drawer_count_total(self):
        dc = CashDrawerCount(yuan_100=2, yuan_50=1, yuan_20=3, yuan_1=5, jiao_5=2)
        # 20000 + 5000 + 6000 + 500 + 100 = 31600分
        assert dc.total_fen == 20000 + 5000 + 6000 + 500 + 100
        assert dc.total_yuan == 316.0


# ═══════════════════════════════════════════════════════════════════════
# CreditAccountService 测试
# ═══════════════════════════════════════════════════════════════════════

class TestCreditAccountService:

    def _make_svc(self) -> CreditAccountService:
        return CreditAccountService()

    def test_create_account(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000, customer_phone="13800000000")
        assert acc.customer_name == "李四"
        assert acc.credit_limit_fen == 100000
        assert acc.balance_fen == 0
        assert acc.status == AccountStatus.ACTIVE

    def test_create_account_rejects_zero_limit(self):
        svc = self._make_svc()
        with pytest.raises(ValueError, match="授信额度必须大于0"):
            svc.create_account("S001", "李四", 0)

    def test_charge_and_balance(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        txn = svc.charge_to_account(acc.account_id, 30000, order_id="ORD001")
        assert txn.amount_fen == 30000
        assert acc.balance_fen == 30000
        assert acc.available_fen == 70000

    def test_charge_exceeds_limit(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 10000)
        with pytest.raises(ValueError, match="额度不足"):
            svc.charge_to_account(acc.account_id, 20000)

    def test_charge_frozen_account(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.freeze(acc.account_id, reason="逾期")
        with pytest.raises(ValueError, match="账户已冻结"):
            svc.charge_to_account(acc.account_id, 5000)

    def test_record_payment_reduces_balance(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.charge_to_account(acc.account_id, 50000)
        txn = svc.record_payment(acc.account_id, 20000)
        assert acc.balance_fen == 30000
        assert txn.amount_fen == 20000

    def test_record_payment_floor_zero(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.charge_to_account(acc.account_id, 5000)
        svc.record_payment(acc.account_id, 99999)
        assert acc.balance_fen == 0  # max(0, 5000-99999)

    def test_freeze_and_unfreeze(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.freeze(acc.account_id)
        assert acc.status == AccountStatus.FROZEN
        svc.unfreeze(acc.account_id)
        assert acc.status == AccountStatus.ACTIVE

    def test_unfreeze_non_frozen_raises(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        with pytest.raises(ValueError, match="账户未冻结"):
            svc.unfreeze(acc.account_id)

    def test_adjust_limit(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.adjust_limit(acc.account_id, 200000)
        assert acc.credit_limit_fen == 200000

    def test_get_balance(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.charge_to_account(acc.account_id, 30000)
        bal = svc.get_balance(acc.account_id)
        assert bal["balance_fen"] == 30000
        assert bal["available_fen"] == 70000
        assert bal["status"] == "active"

    def test_get_statement(self):
        svc = self._make_svc()
        acc = svc.create_account("S001", "李四", 100000)
        svc.charge_to_account(acc.account_id, 20000)
        svc.record_payment(acc.account_id, 10000)
        stmt = svc.get_statement(acc.account_id)
        assert stmt["total_charge_fen"] == 20000
        assert stmt["total_payment_fen"] == 10000
        assert len(stmt["transactions"]) == 2


# ═══════════════════════════════════════════════════════════════════════
# RefundService 测试
# ═══════════════════════════════════════════════════════════════════════

class TestRefundService:

    def _make_svc(self) -> RefundService:
        return RefundService()

    def test_create_refund_auto_approve_small_amount(self):
        svc = self._make_svc()
        req = svc.create_refund_request(
            store_id="S001",
            order_id="ORD001",
            refund_type=RefundType.FULL,
            reason=RefundReason.CUSTOMER_REQUEST,
            original_amount_fen=4000,
            refund_amount_fen=4000,
        )
        # 4000 < 5000 → 自动审批
        assert req.status == RefundStatus.APPROVED
        assert req.approver_id == "SYSTEM_AUTO"

    def test_create_refund_pending_large_amount(self):
        svc = self._make_svc()
        req = svc.create_refund_request(
            store_id="S001",
            order_id="ORD002",
            refund_type=RefundType.FULL,
            reason=RefundReason.FOOD_QUALITY,
            original_amount_fen=10000,
            refund_amount_fen=10000,
        )
        # 10000 >= 5000 → 需人工审批
        assert req.status == RefundStatus.PENDING

    def test_create_refund_rejects_exceeding_amount(self):
        svc = self._make_svc()
        with pytest.raises(ValueError, match="退款金额不能超过原订单金额"):
            svc.create_refund_request(
                store_id="S001",
                order_id="ORD003",
                refund_type=RefundType.PARTIAL,
                reason=RefundReason.PRICE_ERROR,
                original_amount_fen=5000,
                refund_amount_fen=6000,
            )

    def test_approve_and_process(self):
        svc = self._make_svc()
        req = svc.create_refund_request(
            store_id="S001",
            order_id="ORD004",
            refund_type=RefundType.FULL,
            reason=RefundReason.DUPLICATE_PAY,
            original_amount_fen=8000,
            refund_amount_fen=8000,
        )
        assert req.status == RefundStatus.PENDING
        svc.approve(req.refund_id, "MGR01")
        assert req.status == RefundStatus.APPROVED
        svc.process_refund(req.refund_id)
        assert req.status == RefundStatus.PROCESSED
        assert req.processed_at is not None

    def test_reject_refund(self):
        svc = self._make_svc()
        req = svc.create_refund_request(
            store_id="S001",
            order_id="ORD005",
            refund_type=RefundType.ITEM,
            reason=RefundReason.OTHER,
            original_amount_fen=20000,
            refund_amount_fen=20000,
        )
        svc.reject(req.refund_id, "MGR01", reject_reason="不符合退款条件")
        assert req.status == RefundStatus.REJECTED
        assert req.reject_reason == "不符合退款条件"

    def test_process_requires_approval(self):
        svc = self._make_svc()
        req = svc.create_refund_request(
            store_id="S001",
            order_id="ORD006",
            refund_type=RefundType.FULL,
            reason=RefundReason.WRONG_ORDER,
            original_amount_fen=6000,
            refund_amount_fen=6000,
        )
        # PENDING, not approved → cannot process
        with pytest.raises(ValueError, match="退款未审批"):
            svc.process_refund(req.refund_id)

    def test_calculate_partial(self):
        svc = self._make_svc()
        items = [
            {"name": "红烧肉", "price_fen": 3800, "qty": 1},
            {"name": "蛋花汤", "price_fen": 1200, "qty": 2},
        ]
        result = svc.calculate_partial(10000, items)
        # 3800*1 + 1200*2 = 6200
        assert result["refund_amount_fen"] == 6200
        assert result["remaining_fen"] == 3800

    def test_calculate_partial_caps_at_original(self):
        svc = self._make_svc()
        items = [{"name": "龙虾", "price_fen": 50000, "qty": 1}]
        result = svc.calculate_partial(10000, items)
        assert result["refund_amount_fen"] == 10000  # capped

    def test_get_daily_stats(self):
        svc = self._make_svc()
        svc.create_refund_request("S001", "O1", RefundType.FULL, RefundReason.CUSTOMER_REQUEST, 3000, 3000)
        svc.create_refund_request("S001", "O2", RefundType.FULL, RefundReason.FOOD_QUALITY, 2000, 2000)
        stats = svc.get_daily_stats("S001")
        assert stats["total_refund_count"] == 2
        assert stats["store_id"] == "S001"

    def test_check_anomaly_no_anomaly(self):
        svc = self._make_svc()
        result = svc.check_anomaly("S001")
        assert result["has_anomaly"] is False

    def test_check_anomaly_count_threshold(self):
        svc = self._make_svc()
        for i in range(12):
            svc.create_refund_request("S001", f"O{i}", RefundType.FULL, RefundReason.CUSTOMER_REQUEST, 1000, 1000)
        result = svc.check_anomaly("S001", threshold_count=10)
        assert result["has_anomaly"] is True
        assert any(a["type"] == "退款次数过多" for a in result["anomalies"])


# ═══════════════════════════════════════════════════════════════════════
# RushPromotionService 测试
# ═══════════════════════════════════════════════════════════════════════

class TestRushPromotionService:

    def _make_svc(self) -> RushPromotionService:
        return RushPromotionService()

    def test_create_rush(self):
        svc = self._make_svc()
        rush = svc.create_rush(
            store_id="S001",
            dish_id="D001",
            dish_name="红烧肉",
            reason=RushReason.EXPIRING,
            original_price_fen=5800,
            rush_price_fen=2900,
            target_qty=10,
        )
        assert rush.status == RushStatus.ACTIVE
        assert rush.dish_name == "红烧肉"
        assert rush.discount_rate == 0.5
        assert rush.expire_at is not None

    def test_create_rush_rejects_price_not_lower(self):
        svc = self._make_svc()
        with pytest.raises(ValueError, match="急推价必须低于原价"):
            svc.create_rush("S001", "D001", "菜", RushReason.OVERSTOCK, 3000, 3000, 5)

    def test_create_rush_rejects_zero_price(self):
        svc = self._make_svc()
        with pytest.raises(ValueError, match="急推价必须大于0"):
            svc.create_rush("S001", "D001", "菜", RushReason.OVERSTOCK, 3000, 0, 5)

    def test_create_rush_rejects_zero_qty(self):
        svc = self._make_svc()
        with pytest.raises(ValueError, match="目标数量必须大于0"):
            svc.create_rush("S001", "D001", "菜", RushReason.OVERSTOCK, 3000, 1500, 0)

    def test_record_sale_and_completion(self):
        svc = self._make_svc()
        rush = svc.create_rush("S001", "D001", "红烧肉", RushReason.SLOW_SELLING, 5800, 2900, 3)
        svc.record_sale(rush.rush_id, 2)
        assert rush.sold_qty == 2
        assert rush.status == RushStatus.ACTIVE
        svc.record_sale(rush.rush_id, 1)
        assert rush.sold_qty == 3
        assert rush.status == RushStatus.COMPLETED

    def test_cancel_rush(self):
        svc = self._make_svc()
        rush = svc.create_rush("S001", "D001", "红烧肉", RushReason.OVERSTOCK, 5800, 2900, 10)
        cancelled = svc.cancel_rush(rush.rush_id, reason="食材已用完")
        assert cancelled.status == RushStatus.CANCELLED

    def test_cancel_already_cancelled_raises(self):
        svc = self._make_svc()
        rush = svc.create_rush("S001", "D001", "红烧肉", RushReason.OVERSTOCK, 5800, 2900, 10)
        svc.cancel_rush(rush.rush_id)
        with pytest.raises(ValueError, match="急推已结束"):
            svc.cancel_rush(rush.rush_id)

    def test_sync_to_channels(self):
        svc = self._make_svc()
        rush = svc.create_rush(
            "S001", "D001", "红烧肉", RushReason.EXPIRING, 5800, 2900, 10,
            channels=[RushChannel.KDS, RushChannel.POS, RushChannel.MEITUAN],
        )
        result = svc.sync_to_channels(rush.rush_id)
        assert len(result["sync_results"]) == 3
        assert "kds" in rush.synced_channels

    def test_get_effectiveness(self):
        svc = self._make_svc()
        rush = svc.create_rush("S001", "D001", "红烧肉", RushReason.EXPIRING, 5800, 2900, 10)
        svc.record_sale(rush.rush_id, 5)
        eff = svc.get_effectiveness(rush.rush_id)
        assert eff["sold_qty"] == 5
        assert eff["completion_rate"] == 0.5
        assert eff["recovered_revenue_fen"] == 2900 * 5
        assert eff["discount_loss_fen"] == (5800 - 2900) * 5

    def test_generate_kds_alert(self):
        svc = self._make_svc()
        rush = svc.create_rush("S001", "D001", "红烧肉", RushReason.EXPIRING, 5800, 2900, 10)
        alert = svc.generate_kds_alert(rush.rush_id)
        assert alert["alert_type"] == "rush_promotion"
        assert alert["remaining_qty"] == 10
        assert "急推" in alert["display_text"]

    def test_auto_detect_expiring(self):
        svc = self._make_svc()
        now = datetime.now(timezone.utc)
        inventory = [
            {"dish_id": "D1", "dish_name": "鱼", "expiry_time": now + timedelta(hours=2), "qty": 5, "price_fen": 8000},
            {"dish_id": "D2", "dish_name": "虾", "expiry_time": now + timedelta(hours=10), "qty": 3, "price_fen": 12000},
            {"dish_id": "D3", "dish_name": "牛排", "expiry_time": now + timedelta(hours=48), "qty": 2, "price_fen": 15000},
        ]
        suggestions = svc.auto_detect_expiring("S001", inventory, expiry_hours=24)
        # 鱼(2h) and 虾(10h) are within 24h; 牛排(48h) is not
        assert len(suggestions) == 2
        # sorted by hours_until_expiry ascending → 鱼 first
        assert suggestions[0]["dish_name"] == "鱼"
        assert suggestions[0]["urgency"] == "高"  # <4h
        assert suggestions[0]["discount"] == 0.5
        assert suggestions[1]["dish_name"] == "虾"
        assert suggestions[1]["urgency"] == "中"  # 4-12h
        assert suggestions[1]["discount"] == 0.7

    def test_get_active_rushes(self):
        svc = self._make_svc()
        svc.create_rush("S001", "D1", "菜A", RushReason.OVERSTOCK, 5000, 2500, 10)
        svc.create_rush("S001", "D2", "菜B", RushReason.OVERSTOCK, 4000, 2000, 5)
        rush3 = svc.create_rush("S002", "D3", "菜C", RushReason.OVERSTOCK, 3000, 1500, 3)
        active = svc.get_active_rushes("S001")
        assert len(active) == 2
        # S002 的菜不在结果中
        assert all(r.store_id == "S001" for r in active)
