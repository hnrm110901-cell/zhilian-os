"""
P1 Gap Services 完整测试
覆盖10个服务，每个至少5个测试用例
"""

import os
import sys
import types
import importlib.util
from datetime import date, datetime, time, timedelta, timezone

import pytest

# ── 导入引导 ──────────────────────────────────────────────
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


# 加载模块
_discount = _load("discount_permission_service")
_pending = _load("pending_order_service")
_rounding = _load("rounding_service")
_invoice = _load("invoice_void_service")
_stored = _load("stored_value_service")
_birthday = _load("birthday_trigger_service")
_auto = _load("auto_accept_service")
_self_co = _load("self_checkout_service")
_barcode = _load("barcode_service")
_asset = _load("asset_management_service")

# 解包类
DiscountPermissionService = _discount.DiscountPermissionService
DiscountRole = _discount.DiscountRole
ApprovalStatus = _discount.ApprovalStatus

PendingOrderService = _pending.PendingOrderService
PendingStatus = _pending.PendingStatus

RoundingService = _rounding.RoundingService
RoundingLevel = _rounding.RoundingLevel

InvoiceVoidService = _invoice.InvoiceVoidService
InvoiceRecord = _invoice.InvoiceRecord
InvoiceStatus = _invoice.InvoiceStatus
VoidType = _invoice.VoidType

StoredValueService = _stored.StoredValueService
CardStatus = _stored.CardStatus

BirthdayTriggerService = _birthday.BirthdayTriggerService
MemberInfo = _birthday.MemberInfo
BirthdayBenefit = _birthday.BirthdayBenefit

AutoAcceptService = _auto.AutoAcceptService
StoreAcceptConfig = _auto.StoreAcceptConfig
AcceptStrategy = _auto.AcceptStrategy

SelfCheckoutService = _self_co.SelfCheckoutService
CheckoutStatus = _self_co.CheckoutStatus

BarcodeService = _barcode.BarcodeService
BarcodeType = _barcode.BarcodeType

AssetManagementService = _asset.AssetManagementService
AssetCategory = _asset.AssetCategory
AssetStatus = _asset.AssetStatus


# ══════════════════════════════════════════════════════════
# 1. DiscountPermissionService
# ══════════════════════════════════════════════════════════

class TestDiscountPermissionService:

    def setup_method(self):
        self.svc = DiscountPermissionService()

    def test_cashier_allowed_within_limit(self):
        """收银员在权限内打9折应允许"""
        result = self.svc.check_permission(DiscountRole.CASHIER.value, 0.90)
        assert result["allowed"] is True
        assert result["need_approval"] is False

    def test_cashier_denied_beyond_limit(self):
        """收银员打8折应需要审批"""
        result = self.svc.check_permission(DiscountRole.CASHIER.value, 0.80)
        assert result["allowed"] is False
        assert result["need_approval"] is True
        assert result["approval_role_needed"] is not None

    def test_store_manager_70_percent(self):
        """店长可以打7折"""
        result = self.svc.check_permission(DiscountRole.STORE_MANAGER.value, 0.70)
        assert result["allowed"] is True

    def test_invalid_discount_rate_raises(self):
        """折扣率超出范围应报错"""
        with pytest.raises(ValueError, match="折扣率必须在0到1之间"):
            self.svc.check_permission(DiscountRole.CASHIER.value, 1.5)

    def test_request_approval_auto_approved(self):
        """权限内折扣自动通过"""
        approval = self.svc.request_approval(
            store_id="S001",
            order_id="O001",
            requester_id="U001",
            requester_role=DiscountRole.STORE_MANAGER.value,
            discount_rate=0.75,
            original_amount_fen=10000,
            reason="常客优惠",
        )
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.discounted_amount_fen == 7500

    def test_request_approval_pending(self):
        """权限外折扣需审批"""
        approval = self.svc.request_approval(
            store_id="S001",
            order_id="O002",
            requester_id="U002",
            requester_role=DiscountRole.CASHIER.value,
            discount_rate=0.70,
            original_amount_fen=20000,
        )
        assert approval.status == ApprovalStatus.PENDING

    def test_approve_discount(self):
        """审批通过折扣"""
        approval = self.svc.request_approval(
            store_id="S001", order_id="O003", requester_id="U003",
            requester_role=DiscountRole.CASHIER.value,
            discount_rate=0.60, original_amount_fen=10000,
        )
        approved = self.svc.approve_discount(
            approval.approval_id, "MGR01", DiscountRole.AREA_MANAGER.value,
        )
        assert approved.status == ApprovalStatus.APPROVED

    def test_reject_discount(self):
        """拒绝折扣"""
        approval = self.svc.request_approval(
            store_id="S001", order_id="O004", requester_id="U004",
            requester_role=DiscountRole.CASHIER.value,
            discount_rate=0.50, original_amount_fen=10000,
        )
        rejected = self.svc.reject_discount(approval.approval_id, "MGR02", "不合理")
        assert rejected.status == ApprovalStatus.REJECTED

    def test_update_config(self):
        """更新折扣权限配置"""
        self.svc.update_config(DiscountRole.CASHIER.value, 0.85)
        config = self.svc.get_config()
        assert config[DiscountRole.CASHIER.value] == 0.85


# ══════════════════════════════════════════════════════════
# 2. PendingOrderService
# ══════════════════════════════════════════════════════════

class TestPendingOrderService:

    def setup_method(self):
        self.svc = PendingOrderService(expire_minutes=60)

    def _items(self):
        return [
            {"dish_id": "D1", "name": "红烧肉", "qty": 2, "price_fen": 3800},
            {"dish_id": "D2", "name": "米饭", "qty": 3, "price_fen": 200},
        ]

    def test_park_order(self):
        """挂单应正确计算总额"""
        order = self.svc.park_order("S001", "R01", "C01", self._items())
        assert order.total_fen == 2 * 3800 + 3 * 200  # 8200
        assert order.status == PendingStatus.PENDING
        assert order.total_yuan == 82.0

    def test_resume_order(self):
        """恢复挂单"""
        order = self.svc.park_order("S001", "R01", "C01", self._items())
        resumed = self.svc.resume_order(order.pending_id)
        assert resumed.status == PendingStatus.RESUMED

    def test_resume_expired_order_raises(self):
        """恢复过期挂单应报错"""
        svc = PendingOrderService(expire_minutes=0)
        order = svc.park_order("S001", "R01", "C01", self._items())
        # 手动设置过期时间为过去
        order.expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        with pytest.raises(ValueError, match="挂单已过期"):
            svc.resume_order(order.pending_id)

    def test_list_pending(self):
        """列出门店挂单"""
        self.svc.park_order("S001", "R01", "C01", self._items())
        self.svc.park_order("S001", "R02", "C02", self._items())
        self.svc.park_order("S002", "R01", "C03", self._items())
        pending = self.svc.list_pending("S001")
        assert len(pending) == 2

    def test_list_pending_filter_register(self):
        """按收银台过滤挂单"""
        self.svc.park_order("S001", "R01", "C01", self._items())
        self.svc.park_order("S001", "R02", "C02", self._items())
        pending = self.svc.list_pending("S001", register_id="R01")
        assert len(pending) == 1

    def test_cancel_order(self):
        """取消挂单"""
        order = self.svc.park_order("S001", "R01", "C01", self._items())
        cancelled = self.svc.cancel(order.pending_id, reason="顾客离开")
        assert cancelled.status == PendingStatus.CANCELLED

    def test_auto_expire(self):
        """自动过期检查"""
        order = self.svc.park_order("S001", "R01", "C01", self._items())
        order.expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        expired_ids = self.svc.auto_expire()
        assert order.pending_id in expired_ids


# ══════════════════════════════════════════════════════════
# 3. RoundingService
# ══════════════════════════════════════════════════════════

class TestRoundingService:

    def setup_method(self):
        self.svc = RoundingService()

    def test_round_fen_no_change(self):
        """抹分级别不改变金额"""
        result = RoundingService.round_amount(1234, RoundingLevel.FEN)
        assert result["rounded_fen"] == 1234
        assert result["loss_fen"] == 0

    def test_round_jiao(self):
        """抹角：1234分 -> 1230分"""
        result = RoundingService.round_amount(1234, RoundingLevel.JIAO)
        assert result["rounded_fen"] == 1230
        assert result["loss_fen"] == 4

    def test_round_yuan(self):
        """抹元：1234分 -> 1200分"""
        result = RoundingService.round_amount(1234, RoundingLevel.YUAN)
        assert result["rounded_fen"] == 1200
        assert result["loss_fen"] == 34

    def test_negative_amount_raises(self):
        """负金额应报错"""
        with pytest.raises(ValueError, match="金额不能为负"):
            RoundingService.round_amount(-100, RoundingLevel.JIAO)

    def test_apply_rounding_records(self):
        """应用抹零并记录"""
        record = self.svc.apply_rounding("O001", "S001", 5678, RoundingLevel.YUAN)
        assert record.rounded_fen == 5600
        assert record.loss_fen == 78
        assert record.order_id == "O001"

    def test_batch_stats(self):
        """统计抹零损失"""
        self.svc.apply_rounding("O001", "S001", 1234, RoundingLevel.JIAO)
        self.svc.apply_rounding("O002", "S001", 5678, RoundingLevel.YUAN)
        stats = self.svc.batch_stats("S001")
        assert stats["total_count"] == 2
        assert stats["total_loss_fen"] == 4 + 78  # jiao:4, yuan:78

    def test_calculate_loss_no_record(self):
        """计算抹零损失但不记录"""
        result = self.svc.calculate_loss(999, RoundingLevel.JIAO)
        assert result["loss_fen"] == 9
        stats = self.svc.batch_stats("S001")
        assert stats["total_count"] == 0


# ══════════════════════════════════════════════════════════
# 4. InvoiceVoidService
# ══════════════════════════════════════════════════════════

class TestInvoiceVoidService:

    def setup_method(self):
        self.svc = InvoiceVoidService()

    def _make_invoice(self, store_id="S001", amount_fen=10000, issue_date=None):
        inv = InvoiceRecord(
            store_id=store_id,
            invoice_no="INV-001",
            invoice_code="CODE-001",
            order_id="O001",
            amount_fen=amount_fen,
            tax_fen=600,
            buyer_name="测试客户",
            buyer_tax_no="123456789",
            issue_date=issue_date or datetime.now(timezone.utc),
        )
        self.svc.register_invoice(inv)
        return inv

    def test_register_invoice(self):
        """注册发票"""
        inv = self._make_invoice()
        assert inv.status == InvoiceStatus.NORMAL

    def test_void_invoice_current_month(self):
        """当月发票作废"""
        inv = self._make_invoice()
        void_rec = self.svc.void_invoice(inv.invoice_id, "金额错误", "OP01")
        assert void_rec.void_type == VoidType.VOID
        assert inv.status == InvoiceStatus.VOIDED

    def test_void_cross_month_raises(self):
        """跨月发票不能作废"""
        past_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
        inv = self._make_invoice(issue_date=past_date)
        with pytest.raises(ValueError, match="跨月发票不能作废"):
            self.svc.void_invoice(inv.invoice_id, "金额错误")

    def test_red_invoice(self):
        """红冲发票"""
        inv = self._make_invoice()
        result = self.svc.red_invoice(inv.invoice_id, "退款", "OP01")
        assert result["amount_fen"] == -10000
        assert inv.status == InvoiceStatus.RED_OFFSET
        assert result["red_invoice_no"].startswith("RED-")

    def test_void_already_voided_raises(self):
        """已作废发票不能再次作废"""
        inv = self._make_invoice()
        self.svc.void_invoice(inv.invoice_id, "错误")
        with pytest.raises(ValueError, match="发票状态不允许作废"):
            self.svc.void_invoice(inv.invoice_id, "再次作废")

    def test_get_void_history(self):
        """获取作废历史"""
        inv = self._make_invoice()
        self.svc.void_invoice(inv.invoice_id, "错误", "OP01")
        history = self.svc.get_void_history(invoice_id=inv.invoice_id)
        assert len(history) == 1
        assert history[0]["void_type"] == "void"

    def test_get_void_history_by_store(self):
        """按门店获取作废历史"""
        inv = self._make_invoice(store_id="S099")
        self.svc.red_invoice(inv.invoice_id, "退款", "OP01")
        history = self.svc.get_void_history(store_id="S099")
        assert len(history) == 1


# ══════════════════════════════════════════════════════════
# 5. StoredValueService
# ══════════════════════════════════════════════════════════

class TestStoredValueService:

    def setup_method(self):
        self.svc = StoredValueService()

    def _make_card(self, store_id="S001"):
        return self.svc.create_card(store_id, "CUST01", "张三")

    def test_create_card(self):
        """创建储值卡"""
        card = self._make_card()
        assert card.cash_balance_fen == 0
        assert card.status == CardStatus.ACTIVE

    def test_recharge(self):
        """直接充值"""
        card = self._make_card()
        card = self.svc.recharge(card.card_id, 20000)
        assert card.cash_balance_fen == 20000
        assert card.total_recharge_fen == 20000

    def test_add_rule_and_apply(self):
        """添加充值规则并应用"""
        card = self._make_card()
        rule = self.svc.add_rule("充200送30", 20000, 3000)
        card = self.svc.apply_rule(card.card_id, rule.rule_id)
        assert card.cash_balance_fen == 20000
        assert card.gift_balance_fen == 3000
        assert card.total_balance_fen == 23000

    def test_consume_gift_first(self):
        """消费先扣赠送余额"""
        card = self._make_card()
        self.svc.recharge(card.card_id, 10000)
        rule = self.svc.add_rule("充100送50", 10000, 5000)
        self.svc.apply_rule(card.card_id, rule.rule_id)
        # 现金: 10000+10000=20000, 赠送: 5000
        self.svc.consume(card.card_id, 6000)
        assert card.gift_balance_fen == 0  # 赠送5000先扣完
        assert card.cash_balance_fen == 19000  # 再扣现金1000

    def test_refund_card(self):
        """退卡只退现金余额"""
        card = self._make_card()
        self.svc.recharge(card.card_id, 20000)
        rule = self.svc.add_rule("充200送30", 20000, 3000)
        self.svc.apply_rule(card.card_id, rule.rule_id)
        result = self.svc.refund_card(card.card_id)
        assert result["refundable_fen"] == 40000  # 两次充值20000
        assert result["non_refundable_fen"] == 3000
        assert card.status == CardStatus.REFUNDED

    def test_consume_insufficient_raises(self):
        """余额不足应报错"""
        card = self._make_card()
        self.svc.recharge(card.card_id, 1000)
        with pytest.raises(ValueError, match="余额不足"):
            self.svc.consume(card.card_id, 2000)

    def test_get_rules(self):
        """获取规则列表"""
        self.svc.add_rule("充100送10", 10000, 1000)
        self.svc.add_rule("充200送30", 20000, 3000, store_id="S001")
        rules = self.svc.get_rules(store_id="S001")
        assert len(rules) == 2  # 全局 + S001

    def test_add_rule_invalid_raises(self):
        """无效规则应报错"""
        with pytest.raises(ValueError, match="充值和赠送金额必须大于0"):
            self.svc.add_rule("无效", 0, 1000)


# ══════════════════════════════════════════════════════════
# 6. BirthdayTriggerService
# ══════════════════════════════════════════════════════════

class TestBirthdayTriggerService:

    def setup_method(self):
        self.svc = BirthdayTriggerService()

    def _register_member(self, member_id="M001", name="李四",
                         birthday=None, store_id="S001"):
        m = MemberInfo(
            member_id=member_id, name=name,
            phone="13800138000",
            birthday=birthday or date.today(),
            store_id=store_id,
        )
        self.svc.register_member(m)
        return m

    def test_check_birthday_today(self):
        """检测当日生日会员"""
        self._register_member(birthday=date.today())
        matches = self.svc.check_birthday_today("S001")
        assert len(matches) == 1

    def test_check_birthday_no_match(self):
        """非生日日期不匹配"""
        yesterday = date.today() - timedelta(days=10)
        self._register_member(birthday=yesterday)
        matches = self.svc.check_birthday_today("S001")
        assert len(matches) == 0

    def test_check_birthday_advance_days(self):
        """提前天数匹配"""
        tomorrow = date.today() + timedelta(days=1)
        self._register_member(birthday=tomorrow)
        matches = self.svc.check_birthday_today("S001", advance_days=1)
        assert len(matches) == 1

    def test_generate_notification(self):
        """生成生日通知"""
        m = self._register_member()
        notif = self.svc.generate_notification(m)
        assert "生日快乐" in notif.message
        assert notif.member_name == "李四"

    def test_apply_discount(self):
        """应用生日折扣"""
        result = self.svc.apply_discount("M001", 10000)
        assert result["discounted_fen"] == 8800  # 默认0.88折
        assert result["savings_fen"] == 1200

    def test_run_daily_check(self):
        """每日定时检查"""
        self._register_member(member_id="M001", birthday=date.today())
        self._register_member(member_id="M002", birthday=date.today())
        notifications = self.svc.run_daily_check("S001", advance_days=0)
        assert len(notifications) == 2

    def test_get_default_benefit(self):
        """获取默认生日权益"""
        benefit = self.svc.get_benefits()
        assert benefit.discount_rate == 0.88
        assert benefit.free_dish == "长寿面"


# ══════════════════════════════════════════════════════════
# 7. AutoAcceptService
# ══════════════════════════════════════════════════════════

class TestAutoAcceptService:

    def setup_method(self):
        self.svc = AutoAcceptService()

    def test_default_manual(self):
        """默认手动接单"""
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is False
        assert result["strategy"] == "manual"

    def test_always_accept(self):
        """始终自动接单"""
        config = StoreAcceptConfig(store_id="S001", strategy=AcceptStrategy.ALWAYS)
        self.svc.set_config(config)
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is True

    def test_hours_within(self):
        """时段内自动接单"""
        config = StoreAcceptConfig(
            store_id="S001",
            strategy=AcceptStrategy.HOURS,
            auto_hours_start=time(10, 0),
            auto_hours_end=time(21, 0),
        )
        self.svc.set_config(config)
        check_time = datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc)
        result = self.svc.should_auto_accept("S001", check_time=check_time)
        assert result["accept"] is True

    def test_hours_outside(self):
        """时段外不接单"""
        config = StoreAcceptConfig(
            store_id="S001",
            strategy=AcceptStrategy.HOURS,
            auto_hours_start=time(10, 0),
            auto_hours_end=time(21, 0),
        )
        self.svc.set_config(config)
        check_time = datetime(2026, 3, 26, 22, 0, tzinfo=timezone.utc)
        result = self.svc.should_auto_accept("S001", check_time=check_time)
        assert result["accept"] is False

    def test_capacity_ok(self):
        """产能充足时接单"""
        config = StoreAcceptConfig(
            store_id="S001",
            strategy=AcceptStrategy.CAPACITY,
            max_concurrent_orders=20,
            current_orders=10,
        )
        self.svc.set_config(config)
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is True

    def test_capacity_full(self):
        """产能满时不接单"""
        config = StoreAcceptConfig(
            store_id="S001",
            strategy=AcceptStrategy.CAPACITY,
            max_concurrent_orders=20,
            current_orders=20,
        )
        self.svc.set_config(config)
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is False

    def test_blackout_period(self):
        """黑名单时段不接单"""
        config = StoreAcceptConfig(
            store_id="S001",
            strategy=AcceptStrategy.ALWAYS,
            blackout_periods=[(time(11, 30), time(13, 30))],
        )
        self.svc.set_config(config)
        check_time = datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc)
        result = self.svc.should_auto_accept("S001", check_time=check_time)
        assert result["accept"] is False

    def test_disabled(self):
        """关闭自动接单"""
        config = StoreAcceptConfig(
            store_id="S001", strategy=AcceptStrategy.ALWAYS, enabled=False,
        )
        self.svc.set_config(config)
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is False


# ══════════════════════════════════════════════════════════
# 8. SelfCheckoutService
# ══════════════════════════════════════════════════════════

class TestSelfCheckoutService:

    def setup_method(self):
        self.svc = SelfCheckoutService(qr_expire_minutes=15)

    def test_generate_checkout_qr(self):
        """生成结账二维码"""
        co = self.svc.generate_checkout_qr("S001", "T01", "O001", 5000)
        assert co.amount_fen == 5000
        assert co.qr_code.startswith("https://pay.tunxiang.cn/checkout/")
        assert co.status == CheckoutStatus.PENDING

    def test_generate_zero_amount_raises(self):
        """金额为0应报错"""
        with pytest.raises(ValueError, match="结账金额必须大于0"):
            self.svc.generate_checkout_qr("S001", "T01", "O001", 0)

    def test_verify_payment_success(self):
        """支付验证成功"""
        co = self.svc.generate_checkout_qr("S001", "T01", "O001", 5000)
        result = self.svc.verify_payment(co.checkout_id, "wechat", "PAY001", 5000)
        assert result["verified"] is True
        assert co.status == CheckoutStatus.PAID

    def test_verify_payment_amount_mismatch(self):
        """金额不匹配"""
        co = self.svc.generate_checkout_qr("S001", "T01", "O001", 5000)
        result = self.svc.verify_payment(co.checkout_id, "wechat", "PAY001", 4000)
        assert result["verified"] is False
        assert "金额不匹配" in result["reason"]

    def test_verify_payment_expired(self):
        """二维码过期"""
        co = self.svc.generate_checkout_qr("S001", "T01", "O001", 5000)
        co.qr_expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        result = self.svc.verify_payment(co.checkout_id, "wechat", "PAY001", 5000)
        assert result["verified"] is False
        assert "过期" in result["reason"]

    def test_complete_checkout(self):
        """完成结账"""
        co = self.svc.generate_checkout_qr("S001", "T01", "O001", 5000)
        self.svc.verify_payment(co.checkout_id, "wechat", "PAY001", 5000)
        completed = self.svc.complete_checkout(co.checkout_id)
        assert completed.status == CheckoutStatus.COMPLETED

    def test_complete_unpaid_raises(self):
        """未支付不能完成"""
        co = self.svc.generate_checkout_qr("S001", "T01", "O001", 5000)
        with pytest.raises(ValueError, match="只有已支付的订单才能完成"):
            self.svc.complete_checkout(co.checkout_id)


# ══════════════════════════════════════════════════════════
# 9. BarcodeService
# ══════════════════════════════════════════════════════════

class TestBarcodeService:

    def setup_method(self):
        self.svc = BarcodeService()

    def test_generate_internal(self):
        """生成内部条码"""
        rec = self.svc.generate(
            BarcodeType.INTERNAL, "ITEM01", "五花肉",
            store_id="S001", price_fen=2800, unit="kg",
        )
        assert rec.barcode_value.startswith("INT-")
        assert rec.price_yuan == 28.0

    def test_generate_ean13(self):
        """生成EAN13条码（实现取MD5前12位数字化）"""
        rec = self.svc.generate(BarcodeType.EAN13, "ITEM02", "大米")
        assert rec.barcode_value.isdigit()
        assert len(rec.barcode_value) <= 13

    def test_generate_custom_value(self):
        """自定义条码值"""
        rec = self.svc.generate(
            BarcodeType.CODE128, "ITEM03", "酱油",
            barcode_value="CUSTOM-001",
        )
        assert rec.barcode_value == "CUSTOM-001"

    def test_scan_found(self):
        """扫码识别"""
        rec = self.svc.generate(
            BarcodeType.INTERNAL, "ITEM01", "五花肉",
            barcode_value="TEST-SCAN-001",
        )
        found = self.svc.scan("TEST-SCAN-001")
        assert found is not None
        assert found.item_name == "五花肉"

    def test_scan_not_found(self):
        """扫码未识别"""
        result = self.svc.scan("UNKNOWN-CODE")
        assert result is None

    def test_duplicate_barcode_raises(self):
        """重复条码应报错"""
        self.svc.generate(BarcodeType.INTERNAL, "ITEM01", "A", barcode_value="DUP-001")
        with pytest.raises(ValueError, match="条码已存在"):
            self.svc.generate(BarcodeType.INTERNAL, "ITEM02", "B", barcode_value="DUP-001")

    def test_batch_inbound(self):
        """批量入库"""
        self.svc.generate(BarcodeType.INTERNAL, "I1", "五花肉",
                          barcode_value="BC001", price_fen=2800)
        self.svc.generate(BarcodeType.INTERNAL, "I2", "大米",
                          barcode_value="BC002", price_fen=500)
        result = self.svc.batch_inbound("S001", [
            {"barcode_value": "BC001", "qty": 5},
            {"barcode_value": "BC002", "qty": 10},
            {"barcode_value": "BC999", "qty": 1},  # 不存在
        ])
        assert len(result["success"]) == 2
        assert len(result["not_found"]) == 1
        assert result["total_qty"] == 15
        assert result["total_amount_fen"] == 2800 * 5 + 500 * 10

    def test_generate_label(self):
        """生成标签数据"""
        self.svc.generate(BarcodeType.INTERNAL, "I1", "五花肉",
                          barcode_value="LBL001", price_fen=2800, unit="kg")
        label = self.svc.generate_label("LBL001")
        assert label["item_name"] == "五花肉"
        assert label["price_text"] == "¥28.0"
        assert label["unit"] == "kg"


# ══════════════════════════════════════════════════════════
# 10. AssetManagementService
# ══════════════════════════════════════════════════════════

class TestAssetManagementService:

    def setup_method(self):
        self.svc = AssetManagementService()

    def _register_asset(self, name="冰箱", category=AssetCategory.REFRIGERATION,
                        price_fen=500000, purchase_date=None):
        return self.svc.register(
            store_id="S001", name=name, category=category,
            purchase_price_fen=price_fen,
            purchase_date=purchase_date or date(2024, 1, 1),
            salvage_value_fen=50000,
        )

    def test_register_asset(self):
        """登记资产"""
        asset = self._register_asset()
        assert asset.name == "冰箱"
        assert asset.purchase_price_yuan == 5000.0

    def test_register_invalid_price_raises(self):
        """购入价为0应报错"""
        with pytest.raises(ValueError, match="购入价必须大于0"):
            self.svc.register("S001", "破冰箱", AssetCategory.OTHER, 0)

    def test_calculate_depreciation(self):
        """计算折旧"""
        asset = self._register_asset(purchase_date=date(2023, 1, 1))
        dep = self.svc.calculate_depreciation(asset.asset_id, as_of_date=date(2025, 1, 1))
        # 8年使用年限(冷链), (500000-50000)/8 = 56250/年, 2年 = 112500
        assert dep["annual_depreciation_fen"] == 56250
        assert dep["years_used"] == pytest.approx(2.0, abs=0.02)

    def test_schedule_maintenance(self):
        """安排维护计划"""
        asset = self._register_asset()
        updated = self.svc.schedule_maintenance(asset.asset_id, interval_days=30)
        assert updated.next_maintenance == date.today() + timedelta(days=30)

    def test_record_maintenance(self):
        """记录维护"""
        asset = self._register_asset()
        record = self.svc.record_maintenance(
            asset.asset_id, "更换压缩机", cost_fen=80000, operator="维修工张",
        )
        assert record.cost_yuan == 800.0
        assert asset.last_maintenance == date.today()

    def test_scrap_asset(self):
        """报废资产"""
        asset = self._register_asset()
        scrapped = self.svc.scrap(asset.asset_id, reason="无法修复")
        assert scrapped.status == AssetStatus.SCRAPPED

    def test_scrap_already_scrapped_raises(self):
        """已报废资产不能再次报废"""
        asset = self._register_asset()
        self.svc.scrap(asset.asset_id)
        with pytest.raises(ValueError, match="资产已报废"):
            self.svc.scrap(asset.asset_id)

    def test_get_report(self):
        """获取门店资产报告"""
        self._register_asset(name="冰箱1")
        self._register_asset(name="冰箱2", price_fen=300000)
        report = self.svc.get_report("S001")
        assert report["total_assets"] == 2
        assert report["total_purchase_fen"] == 800000

    def test_default_useful_life(self):
        """默认折旧年限按类别设定"""
        asset = self.svc.register(
            "S001", "POS机", AssetCategory.POS_DEVICE, 100000,
            purchase_date=date(2024, 1, 1),
        )
        assert asset.useful_life_years == 3  # POS设备默认3年
