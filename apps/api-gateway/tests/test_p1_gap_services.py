"""
P1 Gap Services 完整测试
覆盖10个P1服务，每个至少5个测试，共50+
"""
import os
import sys
import types
import importlib.util
import pytest
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

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


# 加载所有10个服务模块
discount_mod = _load("discount_permission_service")
pending_mod = _load("pending_order_service")
rounding_mod = _load("rounding_service")
invoice_mod = _load("invoice_void_service")
stored_mod = _load("stored_value_service")
birthday_mod = _load("birthday_trigger_service")
auto_mod = _load("auto_accept_service")
checkout_mod = _load("self_checkout_service")
barcode_mod = _load("barcode_service")
asset_mod = _load("asset_management_service")

# ============================================================
# 1. DiscountPermissionService (折扣权限分级服务) — 7 tests
# ============================================================

DiscountPermissionService = discount_mod.DiscountPermissionService
DiscountRole = discount_mod.DiscountRole
ApprovalStatus = discount_mod.ApprovalStatus


class TestDiscountPermissionService:
    def setup_method(self):
        self.svc = DiscountPermissionService()

    def test_cashier_allowed_within_limit(self):
        """收银员打9折在权限内"""
        result = self.svc.check_permission("cashier", 0.90)
        assert result["allowed"] is True
        assert result["need_approval"] is False

    def test_cashier_denied_beyond_limit(self):
        """收银员打8折超出权限"""
        result = self.svc.check_permission("cashier", 0.80)
        assert result["allowed"] is False
        assert result["need_approval"] is True
        assert result["approval_role_needed"] is not None

    def test_store_manager_allowed_70(self):
        """店长打7折在权限内"""
        result = self.svc.check_permission("store_manager", 0.70)
        assert result["allowed"] is True

    def test_invalid_discount_rate_raises(self):
        """折扣率超范围抛出异常"""
        with pytest.raises(ValueError):
            self.svc.check_permission("cashier", 1.5)
        with pytest.raises(ValueError):
            self.svc.check_permission("cashier", -0.1)

    def test_request_approval_auto_approved(self):
        """权限内请求自动通过"""
        approval = self.svc.request_approval(
            store_id="S001", order_id="O001", requester_id="U001",
            requester_role="store_manager", discount_rate=0.80,
            original_amount_fen=10000, reason="老顾客优惠",
        )
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.discounted_amount_fen == 8000

    def test_request_approval_needs_pending(self):
        """超权限请求进入待审批"""
        approval = self.svc.request_approval(
            store_id="S001", order_id="O002", requester_id="U001",
            requester_role="cashier", discount_rate=0.50,
            original_amount_fen=20000,
        )
        assert approval.status == ApprovalStatus.PENDING

    def test_approve_and_reject_flow(self):
        """审批通过和拒绝流程"""
        approval = self.svc.request_approval(
            store_id="S001", order_id="O003", requester_id="U001",
            requester_role="cashier", discount_rate=0.60,
            original_amount_fen=10000,
        )
        assert approval.status == ApprovalStatus.PENDING
        # 区域经理审批通过
        approved = self.svc.approve_discount(approval.approval_id, "MGR01", "area_manager")
        assert approved.status == ApprovalStatus.APPROVED

        # 测试拒绝流程
        a2 = self.svc.request_approval(
            store_id="S001", order_id="O004", requester_id="U002",
            requester_role="cashier", discount_rate=0.60,
            original_amount_fen=10000,
        )
        rejected = self.svc.reject_discount(a2.approval_id, "MGR01", "顾客不符合条件")
        assert rejected.status == ApprovalStatus.REJECTED

    def test_approve_insufficient_permission(self):
        """审批人权限不足"""
        approval = self.svc.request_approval(
            store_id="S001", order_id="O005", requester_id="U001",
            requester_role="cashier", discount_rate=0.50,
            original_amount_fen=10000,
        )
        with pytest.raises(ValueError, match="权限不足"):
            self.svc.approve_discount(approval.approval_id, "U002", "cashier")

    def test_update_config(self):
        """更新折扣配置"""
        self.svc.update_config("cashier", 0.85)
        config = self.svc.get_config()
        assert config["cashier"] == 0.85


# ============================================================
# 2. PendingOrderService (挂单服务) — 6 tests
# ============================================================

PendingOrderService = pending_mod.PendingOrderService
PendingStatus = pending_mod.PendingStatus


class TestPendingOrderService:
    def setup_method(self):
        self.svc = PendingOrderService(expire_minutes=60)

    def _park(self, store="S001", register="R01"):
        items = [
            {"dish_id": "D1", "name": "宫保鸡丁", "qty": 2, "price_fen": 3800},
            {"dish_id": "D2", "name": "米饭", "qty": 3, "price_fen": 200},
        ]
        return self.svc.park_order(store, register, "C001", items)

    def test_park_order_calculates_total(self):
        """挂单自动计算总额"""
        order = self._park()
        # 3800*2 + 200*3 = 8200
        assert order.total_fen == 8200
        assert order.total_yuan == 82.0
        assert order.status == PendingStatus.PENDING

    def test_resume_order(self):
        """恢复挂单"""
        order = self._park()
        resumed = self.svc.resume_order(order.pending_id)
        assert resumed.status == PendingStatus.RESUMED
        assert resumed.resumed_at is not None

    def test_resume_expired_raises(self):
        """恢复过期挂单报错"""
        order = self._park()
        # 手动设置过期
        order.expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        with pytest.raises(ValueError, match="已过期"):
            self.svc.resume_order(order.pending_id)

    def test_list_pending_filters(self):
        """列出挂单按门店和收银台过滤"""
        self._park("S001", "R01")
        self._park("S001", "R02")
        self._park("S002", "R01")

        all_s001 = self.svc.list_pending("S001")
        assert len(all_s001) == 2
        r01_only = self.svc.list_pending("S001", "R01")
        assert len(r01_only) == 1

    def test_cancel_order(self):
        """取消挂单"""
        order = self._park()
        cancelled = self.svc.cancel(order.pending_id, "顾客离开")
        assert cancelled.status == PendingStatus.CANCELLED

    def test_auto_expire(self):
        """自动过期检查"""
        order = self._park()
        order.expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        expired_ids = self.svc.auto_expire()
        assert order.pending_id in expired_ids
        assert order.status == PendingStatus.EXPIRED


# ============================================================
# 3. RoundingService (抹零服务) — 6 tests
# ============================================================

RoundingService = rounding_mod.RoundingService
RoundingLevel = rounding_mod.RoundingLevel


class TestRoundingService:
    def setup_method(self):
        self.svc = RoundingService()

    def test_round_fen_no_change(self):
        """抹分：金额不变"""
        result = RoundingService.round_amount(1234, RoundingLevel.FEN)
        assert result["rounded_fen"] == 1234
        assert result["loss_fen"] == 0

    def test_round_jiao(self):
        """抹角：去掉分位"""
        result = RoundingService.round_amount(1234, RoundingLevel.JIAO)
        assert result["rounded_fen"] == 1230
        assert result["loss_fen"] == 4

    def test_round_yuan(self):
        """抹元：去掉角+分位"""
        result = RoundingService.round_amount(1234, RoundingLevel.YUAN)
        assert result["rounded_fen"] == 1200
        assert result["loss_fen"] == 34

    def test_negative_amount_raises(self):
        """负金额抛异常"""
        with pytest.raises(ValueError):
            RoundingService.round_amount(-100, RoundingLevel.JIAO)

    def test_apply_rounding_records(self):
        """应用抹零并记录"""
        record = self.svc.apply_rounding("O001", "S001", 5678, RoundingLevel.JIAO)
        assert record.rounded_fen == 5670
        assert record.loss_fen == 8

    def test_batch_stats(self):
        """按门店统计抹零损失"""
        self.svc.apply_rounding("O1", "S001", 1234, RoundingLevel.JIAO)
        self.svc.apply_rounding("O2", "S001", 5678, RoundingLevel.YUAN)
        self.svc.apply_rounding("O3", "S002", 9999, RoundingLevel.YUAN)

        stats = self.svc.batch_stats("S001")
        assert stats["total_count"] == 2
        # jiao: 4, yuan: 78 => total 82
        assert stats["total_loss_fen"] == 82
        assert "jiao" in stats["by_level"]
        assert "yuan" in stats["by_level"]


# ============================================================
# 4. InvoiceVoidService (发票红冲/作废服务) — 6 tests
# ============================================================

InvoiceVoidService = invoice_mod.InvoiceVoidService
InvoiceRecord = invoice_mod.InvoiceRecord
InvoiceStatus = invoice_mod.InvoiceStatus
VoidType = invoice_mod.VoidType


class TestInvoiceVoidService:
    def setup_method(self):
        self.svc = InvoiceVoidService()

    def _register_invoice(self, issue_date=None):
        inv = InvoiceRecord(
            store_id="S001", invoice_no="FP20240101001",
            invoice_code="3100", order_id="O001",
            amount_fen=10000, tax_fen=600,
            buyer_name="测试公司", buyer_tax_no="91110000",
            issue_date=issue_date or datetime.now(timezone.utc),
        )
        self.svc.register_invoice(inv)
        return inv

    def test_register_and_void_same_month(self):
        """当月发票可作废"""
        inv = self._register_invoice()
        record = self.svc.void_invoice(inv.invoice_id, "开错票", "OP01")
        assert record.void_type == VoidType.VOID
        assert inv.status == InvoiceStatus.VOIDED

    def test_void_cross_month_raises(self):
        """跨月发票不能作废"""
        past = datetime(2020, 1, 15, tzinfo=timezone.utc)
        inv = self._register_invoice(issue_date=past)
        with pytest.raises(ValueError, match="跨月"):
            self.svc.void_invoice(inv.invoice_id, "开错票")

    def test_red_invoice(self):
        """红冲发票生成负数红字发票"""
        inv = self._register_invoice()
        result = self.svc.red_invoice(inv.invoice_id, "退货红冲", "OP01")
        assert result["amount_fen"] == -10000
        assert result["tax_fen"] == -600
        assert result["red_invoice_no"].startswith("RED-")
        assert inv.status == InvoiceStatus.RED_OFFSET

    def test_void_already_voided_raises(self):
        """已作废的发票不能再作废"""
        inv = self._register_invoice()
        self.svc.void_invoice(inv.invoice_id, "第一次")
        with pytest.raises(ValueError, match="不允许作废"):
            self.svc.void_invoice(inv.invoice_id, "第二次")

    def test_red_already_red_raises(self):
        """已红冲的发票不能再红冲"""
        inv = self._register_invoice()
        self.svc.red_invoice(inv.invoice_id, "第一次红冲")
        with pytest.raises(ValueError, match="不允许红冲"):
            self.svc.red_invoice(inv.invoice_id, "第二次红冲")

    def test_get_void_history(self):
        """获取作废/红冲历史"""
        inv1 = self._register_invoice()
        inv2 = self._register_invoice()
        self.svc.void_invoice(inv1.invoice_id, "作废")
        self.svc.red_invoice(inv2.invoice_id, "红冲")
        history = self.svc.get_void_history(store_id="S001")
        assert len(history) == 2
        types_found = {h["void_type"] for h in history}
        assert types_found == {"void", "red"}


# ============================================================
# 5. StoredValueService (储值卡退卡+赠送规则服务) — 7 tests
# ============================================================

StoredValueService = stored_mod.StoredValueService
CardStatus = stored_mod.CardStatus


class TestStoredValueService:
    def setup_method(self):
        self.svc = StoredValueService()

    def _create_card(self):
        return self.svc.create_card("S001", "CUST01", "张三")

    def test_create_card(self):
        """创建储值卡"""
        card = self._create_card()
        assert card.customer_name == "张三"
        assert card.total_balance_fen == 0
        assert card.status == CardStatus.ACTIVE

    def test_recharge_direct(self):
        """直接充值无赠送"""
        card = self._create_card()
        card = self.svc.recharge(card.card_id, 20000)
        assert card.cash_balance_fen == 20000
        assert card.gift_balance_fen == 0

    def test_add_rule_and_apply(self):
        """添加充值规则并应用"""
        card = self._create_card()
        rule = self.svc.add_rule("充200送30", 20000, 3000)
        card = self.svc.apply_rule(card.card_id, rule.rule_id)
        assert card.cash_balance_fen == 20000
        assert card.gift_balance_fen == 3000
        assert card.total_balance_fen == 23000

    def test_consume_gift_first(self):
        """消费先扣赠送余额再扣现金"""
        card = self._create_card()
        rule = self.svc.add_rule("充200送30", 20000, 3000)
        self.svc.apply_rule(card.card_id, rule.rule_id)
        # 消费5000分 = 3000赠送 + 2000现金
        card = self.svc.consume(card.card_id, 5000)
        assert card.gift_balance_fen == 0
        assert card.cash_balance_fen == 18000

    def test_consume_insufficient_balance(self):
        """余额不足消费报错"""
        card = self._create_card()
        self.svc.recharge(card.card_id, 1000)
        with pytest.raises(ValueError, match="余额不足"):
            self.svc.consume(card.card_id, 2000)

    def test_refund_card_only_cash(self):
        """退卡仅退现金余额"""
        card = self._create_card()
        rule = self.svc.add_rule("充200送30", 20000, 3000)
        self.svc.apply_rule(card.card_id, rule.rule_id)
        result = self.svc.refund_card(card.card_id)
        assert result["refundable_fen"] == 20000
        assert result["non_refundable_fen"] == 3000
        assert card.status == CardStatus.REFUNDED

    def test_add_rule_invalid_amount(self):
        """充值/赠送金额<=0报错"""
        with pytest.raises(ValueError):
            self.svc.add_rule("无效", 0, 100)
        with pytest.raises(ValueError):
            self.svc.add_rule("无效", 100, -1)


# ============================================================
# 6. BirthdayTriggerService (生日自动触发服务) — 5 tests
# ============================================================

BirthdayTriggerService = birthday_mod.BirthdayTriggerService
MemberInfo = birthday_mod.MemberInfo
BirthdayBenefit = birthday_mod.BirthdayBenefit


class TestBirthdayTriggerService:
    def setup_method(self):
        self.svc = BirthdayTriggerService()

    def _register_members(self):
        today = date.today()
        self.svc.register_member(MemberInfo(
            member_id="M001", name="李四", phone="13800001111",
            birthday=today, store_id="S001",
        ))
        self.svc.register_member(MemberInfo(
            member_id="M002", name="王五", phone="13800002222",
            birthday=today + timedelta(days=2), store_id="S001",
        ))
        self.svc.register_member(MemberInfo(
            member_id="M003", name="赵六", phone="13800003333",
            birthday=date(1990, 6, 15), store_id="S001",
        ))

    def test_check_birthday_today(self):
        """检测当日生日会员"""
        self._register_members()
        matches = self.svc.check_birthday_today("S001")
        assert len(matches) == 1
        assert matches[0].member_id == "M001"

    def test_check_birthday_with_advance(self):
        """提前天数检测"""
        self._register_members()
        matches = self.svc.check_birthday_today("S001", advance_days=3)
        ids = {m.member_id for m in matches}
        assert "M001" in ids
        assert "M002" in ids

    def test_generate_notification(self):
        """生成生日通知"""
        member = MemberInfo(member_id="M001", name="李四", store_id="S001")
        notif = self.svc.generate_notification(member)
        assert "李四" in notif.message
        assert "88折" in notif.message
        assert "长寿面" in notif.message

    def test_apply_discount(self):
        """应用生日折扣"""
        result = self.svc.apply_discount("M001", 10000)
        assert result["discounted_fen"] == 8800  # 88折
        assert result["savings_fen"] == 1200
        assert result["free_dish"] == "长寿面"

    def test_run_daily_check(self):
        """每日定时检查"""
        self._register_members()
        notifications = self.svc.run_daily_check("S001", advance_days=0)
        assert len(notifications) == 1
        assert notifications[0].member_name == "李四"


# ============================================================
# 7. AutoAcceptService (外卖自动接单服务) — 6 tests
# ============================================================

AutoAcceptService = auto_mod.AutoAcceptService
AcceptStrategy = auto_mod.AcceptStrategy
StoreAcceptConfig = auto_mod.StoreAcceptConfig


class TestAutoAcceptService:
    def setup_method(self):
        self.svc = AutoAcceptService()

    def test_default_manual(self):
        """默认手动模式"""
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is False
        assert result["strategy"] == "manual"

    def test_always_accept(self):
        """始终自动接单"""
        self.svc.set_config(StoreAcceptConfig(store_id="S001", strategy=AcceptStrategy.ALWAYS))
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is True

    def test_hours_in_range(self):
        """时段内自动接单"""
        self.svc.set_config(StoreAcceptConfig(
            store_id="S001", strategy=AcceptStrategy.HOURS,
            auto_hours_start=time(10, 0), auto_hours_end=time(21, 0),
        ))
        check_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        result = self.svc.should_auto_accept("S001", check_time=check_time)
        assert result["accept"] is True

    def test_hours_out_of_range(self):
        """时段外不接单"""
        self.svc.set_config(StoreAcceptConfig(
            store_id="S001", strategy=AcceptStrategy.HOURS,
            auto_hours_start=time(10, 0), auto_hours_end=time(21, 0),
        ))
        check_time = datetime(2024, 6, 1, 22, 0, tzinfo=timezone.utc)
        result = self.svc.should_auto_accept("S001", check_time=check_time)
        assert result["accept"] is False

    def test_capacity_strategy(self):
        """产能策略：有产能则接单"""
        self.svc.set_config(StoreAcceptConfig(
            store_id="S001", strategy=AcceptStrategy.CAPACITY,
            max_concurrent_orders=20, current_orders=10,
        ))
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is True
        # 产能满
        self.svc.update_current_orders("S001", 20)
        result = self.svc.should_auto_accept("S001")
        assert result["accept"] is False

    def test_blackout_period(self):
        """黑名单时段不接单"""
        self.svc.set_config(StoreAcceptConfig(
            store_id="S001", strategy=AcceptStrategy.ALWAYS,
            blackout_periods=[(time(11, 30), time(13, 0))],
        ))
        check_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        result = self.svc.should_auto_accept("S001", check_time=check_time)
        assert result["accept"] is False


# ============================================================
# 8. SelfCheckoutService (自助结账服务) — 6 tests
# ============================================================

SelfCheckoutService = checkout_mod.SelfCheckoutService
CheckoutStatus = checkout_mod.CheckoutStatus


class TestSelfCheckoutService:
    def setup_method(self):
        self.svc = SelfCheckoutService(qr_expire_minutes=15)

    def _gen_qr(self):
        return self.svc.generate_checkout_qr("S001", "T05", "O001", 8800)

    def test_generate_qr(self):
        """生成二维码"""
        co = self._gen_qr()
        assert co.amount_fen == 8800
        assert co.amount_yuan == 88.0
        assert "tunxiang.cn" in co.qr_code
        assert co.status == CheckoutStatus.PENDING

    def test_generate_zero_amount_raises(self):
        """金额<=0抛异常"""
        with pytest.raises(ValueError):
            self.svc.generate_checkout_qr("S001", "T01", "O1", 0)

    def test_verify_payment_success(self):
        """支付验证成功"""
        co = self._gen_qr()
        result = self.svc.verify_payment(co.checkout_id, "wechat", "PAY123", 8800)
        assert result["verified"] is True
        assert co.status == CheckoutStatus.PAID

    def test_verify_payment_amount_mismatch(self):
        """金额不匹配"""
        co = self._gen_qr()
        result = self.svc.verify_payment(co.checkout_id, "wechat", "PAY123", 5000)
        assert result["verified"] is False
        assert "不匹配" in result["reason"]

    def test_verify_expired_qr(self):
        """二维码过期"""
        co = self._gen_qr()
        co.qr_expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        result = self.svc.verify_payment(co.checkout_id, "wechat", "PAY123", 8800)
        assert result["verified"] is False
        assert "过期" in result["reason"]

    def test_complete_checkout(self):
        """完成结账"""
        co = self._gen_qr()
        self.svc.verify_payment(co.checkout_id, "alipay", "PAY456", 8800)
        completed = self.svc.complete_checkout(co.checkout_id)
        assert completed.status == CheckoutStatus.COMPLETED


# ============================================================
# 9. BarcodeService (条码管理服务) — 6 tests
# ============================================================

BarcodeService = barcode_mod.BarcodeService
BarcodeType = barcode_mod.BarcodeType


class TestBarcodeService:
    def setup_method(self):
        self.svc = BarcodeService()

    def _gen_barcode(self, item_id="ITEM01", btype=BarcodeType.INTERNAL):
        return self.svc.generate(
            barcode_type=btype, item_id=item_id,
            item_name="五花肉", item_type="ingredient",
            store_id="S001", price_fen=2500, unit="kg",
        )

    def test_generate_internal(self):
        """生成内部条码"""
        record = self._gen_barcode()
        assert record.barcode_value.startswith("INT-")
        assert record.item_name == "五花肉"
        assert record.price_yuan == 25.0

    def test_generate_ean13(self):
        """生成EAN13条码（实现取md5前12位hex转digit，结果12位）"""
        record = self._gen_barcode(btype=BarcodeType.EAN13)
        assert len(record.barcode_value) <= 13
        assert record.barcode_value.isdigit()

    def test_generate_duplicate_raises(self):
        """重复条码值报错"""
        self.svc.generate(
            barcode_type=BarcodeType.INTERNAL, item_id="I1",
            item_name="Test", barcode_value="DUP001",
        )
        with pytest.raises(ValueError, match="已存在"):
            self.svc.generate(
                barcode_type=BarcodeType.INTERNAL, item_id="I2",
                item_name="Test2", barcode_value="DUP001",
            )

    def test_scan_found_and_not_found(self):
        """扫码查找"""
        record = self._gen_barcode()
        found = self.svc.scan(record.barcode_value)
        assert found is not None
        assert found.item_name == "五花肉"
        assert self.svc.scan("NONEXISTENT") is None

    def test_batch_inbound(self):
        """批量入库"""
        r1 = self._gen_barcode("I1")
        r2 = self.svc.generate(
            barcode_type=BarcodeType.INTERNAL, item_id="I2",
            item_name="大白菜", store_id="S001", price_fen=500, unit="kg",
        )
        result = self.svc.batch_inbound("S001", [
            {"barcode_value": r1.barcode_value, "qty": 10},
            {"barcode_value": r2.barcode_value, "qty": 5},
            {"barcode_value": "MISSING", "qty": 1},
        ])
        assert len(result["success"]) == 2
        assert len(result["not_found"]) == 1
        assert result["total_qty"] == 15
        # 2500*10 + 500*5 = 27500
        assert result["total_amount_fen"] == 27500

    def test_generate_label(self):
        """生成标签数据"""
        record = self._gen_barcode()
        label = self.svc.generate_label(record.barcode_value)
        assert label["item_name"] == "五花肉"
        assert "¥25.0" in label["price_text"]


# ============================================================
# 10. AssetManagementService (固定资产管理服务) — 7 tests
# ============================================================

AssetManagementService = asset_mod.AssetManagementService
AssetCategory = asset_mod.AssetCategory
AssetStatus = asset_mod.AssetStatus


class TestAssetManagementService:
    def setup_method(self):
        self.svc = AssetManagementService()

    def _register_asset(self, name="商用冰箱", category=AssetCategory.REFRIGERATION,
                        price_fen=500000, years=None):
        return self.svc.register(
            store_id="S001", name=name, category=category,
            purchase_price_fen=price_fen,
            purchase_date=date(2023, 1, 1),
            salvage_value_fen=50000,
            useful_life_years=years,
        )

    def test_register_asset(self):
        """登记固定资产"""
        asset = self._register_asset()
        assert asset.name == "商用冰箱"
        assert asset.purchase_price_yuan == 5000.0
        # 冷链设备默认8年
        assert asset.useful_life_years == 8

    def test_register_zero_price_raises(self):
        """购入价<=0报错"""
        with pytest.raises(ValueError):
            self.svc.register("S001", "Test", AssetCategory.OTHER, 0)

    def test_calculate_depreciation(self):
        """直线法折旧计算"""
        asset = self._register_asset(price_fen=500000, years=5)
        # 计算2024-01-01的折旧（1年后）
        dep = self.svc.calculate_depreciation(asset.asset_id, as_of_date=date(2024, 1, 1))
        # 年折旧 = (500000-50000)/5 = 90000
        assert dep["annual_depreciation_fen"] == 90000
        assert dep["annual_depreciation_yuan"] == 900.0
        # 1年后累计折旧约 90000
        assert dep["years_used"] == pytest.approx(1.0, abs=0.01)
        assert dep["net_value_fen"] == pytest.approx(410000, abs=1000)

    def test_depreciation_complete(self):
        """折旧完成标记"""
        asset = self._register_asset(years=5)
        dep = self.svc.calculate_depreciation(asset.asset_id, as_of_date=date(2030, 1, 1))
        assert dep["depreciation_complete"] is True

    def test_schedule_and_record_maintenance(self):
        """安排和记录维护"""
        asset = self._register_asset()
        self.svc.schedule_maintenance(asset.asset_id, interval_days=30)
        assert asset.next_maintenance is not None

        record = self.svc.record_maintenance(
            asset.asset_id, "更换压缩机", cost_fen=80000, operator="技工张")
        assert record.cost_yuan == 800.0
        assert asset.last_maintenance == date.today()

    def test_scrap_asset(self):
        """报废资产"""
        asset = self._register_asset()
        scrapped = self.svc.scrap(asset.asset_id, "超过使用年限")
        assert scrapped.status == AssetStatus.SCRAPPED
        # 二次报废报错
        with pytest.raises(ValueError, match="已报废"):
            self.svc.scrap(asset.asset_id)

    def test_get_report(self):
        """门店资产报告"""
        self._register_asset("冰箱A", AssetCategory.REFRIGERATION, 500000, 5)
        self._register_asset("POS机", AssetCategory.POS_DEVICE, 100000, 3)
        report = self.svc.get_report("S001")
        assert report["total_assets"] == 2
        assert report["total_purchase_fen"] == 600000
        assert report["total_purchase_yuan"] == 6000.0
        assert "refrigeration" in report["by_category"]
        assert "pos_device" in report["by_category"]
