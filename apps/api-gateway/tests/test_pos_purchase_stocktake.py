"""
Phase 2.2 功能平权完整测试

覆盖：
  1. PosTerminalService: 开单/加菜/删菜/折扣/结账/作废 (15 tests)
  2. PurchaseWorkbenchService: 创建PO/提交/确认/收货/对账 (12 tests)
  3. MobileStocktakeService: 创建盘点/计数/差异/审批 (13 tests)
"""

import os

for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from src.services.pos_terminal_service import (
    PosTerminalService,
    BillStatus,
    PaymentMethod,
    DiscountType,
)
from src.services.purchase_workbench_service import (
    PurchaseWorkbenchService,
    POStatus,
    ReceiveItem,
)
from src.services.mobile_stocktake_service import (
    MobileStocktakeService,
    StocktakeStatus,
    StocktakeScope,
)


# ═══════════════════════════════════════════════════════════════════════════════
# PosTerminalService Tests (15)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPosTerminal:

    def test_open_bill(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        assert bill.status == BillStatus.OPEN
        assert bill.store_id == "S001"
        assert bill.table_number == "A3"

    def test_add_item(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        item = svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        assert item.dish_name == "剁椒鱼头"
        assert item.subtotal_fen == 15800

    def test_add_multiple_items(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        svc.add_item(bill.bill_id, "D002", "酸菜鱼", 1, 8800)
        updated = svc.calculate_bill(bill.bill_id)
        assert updated.subtotal_fen == 24600
        assert updated.item_count == 2

    def test_add_item_quantity(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        item = svc.add_item(bill.bill_id, "D001", "米饭", 3, 300)
        assert item.subtotal_fen == 900

    def test_remove_item(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        item = svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        result = svc.remove_item(bill.bill_id, item.item_id)
        assert result is True
        summary = svc.calculate_bill(bill.bill_id)
        assert summary.item_count == 0

    def test_remove_nonexistent_item(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        with pytest.raises(ValueError, match="菜品不存在"):
            svc.remove_item(bill.bill_id, "fake-item")

    def test_apply_percentage_discount(self):
        """85折"""
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 10000)
        summary = svc.apply_discount(bill.bill_id, DiscountType.PERCENTAGE, 85)
        assert summary.discount_fen == 1500  # 10000 * 0.15
        assert summary.total_fen == 8500

    def test_apply_fixed_discount(self):
        """减2000分（¥20）"""
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 10000)
        summary = svc.apply_discount(bill.bill_id, DiscountType.FIXED_AMOUNT, 2000)
        assert summary.discount_fen == 2000
        assert summary.total_fen == 8000

    def test_settle_bill(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        result = svc.settle_bill(bill.bill_id, PaymentMethod.WECHAT, 15800)
        assert result.success is True
        assert result.total_fen == 15800
        assert result.change_fen == 0

    def test_settle_with_change(self):
        """现金支付找零"""
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        result = svc.settle_bill(bill.bill_id, PaymentMethod.CASH, 20000)
        assert result.success is True
        assert result.change_fen == 4200

    def test_settle_insufficient_payment(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        with pytest.raises(ValueError, match="支付金额不足"):
            svc.settle_bill(bill.bill_id, PaymentMethod.CASH, 10000)

    def test_void_bill(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        result = svc.void_bill(bill.bill_id, "客人取消")
        assert result is True
        detail = svc.get_bill_detail(bill.bill_id)
        assert detail.bill.status == BillStatus.VOIDED

    def test_cannot_add_to_settled_bill(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        svc.settle_bill(bill.bill_id, PaymentMethod.WECHAT, 15800)
        with pytest.raises(ValueError):
            svc.add_item(bill.bill_id, "D002", "酸菜鱼", 1, 8800)

    def test_get_active_bills(self):
        svc = PosTerminalService()
        svc.open_bill("S001", "A1", "W001")
        svc.open_bill("S001", "A2", "W001")
        svc.open_bill("S002", "B1", "W002")
        active = svc.get_active_bills("S001")
        assert len(active) == 2

    def test_get_bill_detail(self):
        svc = PosTerminalService()
        bill = svc.open_bill("S001", "A3", "W001")
        svc.add_item(bill.bill_id, "D001", "剁椒鱼头", 1, 15800)
        detail = svc.get_bill_detail(bill.bill_id)
        assert detail is not None
        assert detail.bill.bill_id == bill.bill_id
        assert detail.summary.item_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# PurchaseWorkbenchService Tests (12)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPurchaseWorkbench:

    def _create_po(self, svc: PurchaseWorkbenchService) -> str:
        po = svc.create_purchase_order(
            store_id="S001",
            supplier_id="SUP001",
            supplier_name="张记蔬菜",
            items=[
                {"ingredient_id": "ING001", "ingredient_name": "五花肉",
                 "unit": "kg", "ordered_qty": 50, "unit_price_fen": 3500},
                {"ingredient_id": "ING002", "ingredient_name": "青椒",
                 "unit": "kg", "ordered_qty": 20, "unit_price_fen": 800},
            ],
        )
        return po.order_id

    def test_create_po(self):
        svc = PurchaseWorkbenchService()
        po = svc.create_purchase_order(
            store_id="S001",
            supplier_id="SUP001",
            supplier_name="张记蔬菜",
            items=[
                {"ingredient_id": "ING001", "ingredient_name": "五花肉",
                 "unit": "kg", "ordered_qty": 50, "unit_price_fen": 3500},
            ],
        )
        assert po.status == POStatus.DRAFT
        assert po.total_ordered_fen == 175000  # 50 * 3500

    def test_submit_po(self):
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        po = svc.submit_order(order_id)
        assert po.status == POStatus.SUBMITTED

    def test_supplier_confirm(self):
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        svc.submit_order(order_id)
        po = svc.supplier_confirm(order_id, confirmed_items=[
            {"item_id": po_item_id, "confirmed_qty": qty}
            for po_item_id, qty in [
                (svc._orders[order_id].items[0].item_id, 50),
                (svc._orders[order_id].items[1].item_id, 18),
            ]
        ])
        assert po.status == POStatus.CONFIRMED
        assert po.items[1].confirmed_qty == 18

    def _confirm_and_receive(self, svc, order_id, receive_qtys=None):
        """辅助：确认+收货"""
        po = svc._orders[order_id]
        svc.supplier_confirm(order_id, [
            {"item_id": po.items[0].item_id, "confirmed_qty": 50},
            {"item_id": po.items[1].item_id, "confirmed_qty": 20},
        ])
        if receive_qtys is None:
            receive_qtys = [(po.items[0].item_id, 50), (po.items[1].item_id, 20)]
        items = [ReceiveItem(item_id=iid, received_qty=qty) for iid, qty in receive_qtys]
        return svc.receive_goods(order_id, items)

    def test_receive_goods_full(self):
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        svc.submit_order(order_id)
        result = self._confirm_and_receive(svc, order_id)
        assert result.fully_received is True
        assert svc._orders[order_id].status == POStatus.RECEIVED

    def test_receive_goods_partial(self):
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        svc.submit_order(order_id)
        po = svc._orders[order_id]
        svc.supplier_confirm(order_id, [
            {"item_id": po.items[0].item_id, "confirmed_qty": 50},
            {"item_id": po.items[1].item_id, "confirmed_qty": 20},
        ])
        items = [ReceiveItem(item_id=po.items[0].item_id, received_qty=30)]
        result = svc.receive_goods(order_id, items)
        assert result.fully_received is False
        assert svc._orders[order_id].status == POStatus.PARTIALLY_RECEIVED

    def test_reconcile_clean(self):
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        svc.submit_order(order_id)
        self._confirm_and_receive(svc, order_id)
        result = svc.reconcile_order(order_id)
        assert result.is_clean is True
        assert result.variance_fen == 0

    def test_reconcile_with_price_variance(self):
        """收全量但实际单价与下单不同，对账应检出价格差异"""
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        svc.submit_order(order_id)
        po = svc._orders[order_id]
        svc.supplier_confirm(order_id, [
            {"item_id": po.items[0].item_id, "confirmed_qty": 50},
            {"item_id": po.items[1].item_id, "confirmed_qty": 20},
        ])
        # 收全量但五花肉实际单价涨了（3500→4000）
        svc.receive_goods(order_id, [
            ReceiveItem(item_id=po.items[0].item_id, received_qty=50, unit_price_fen=4000),
            ReceiveItem(item_id=po.items[1].item_id, received_qty=20),
        ])
        result = svc.reconcile_order(order_id)
        # 金额差异：50*(4000-3500)=25000分
        assert result.is_clean is False or result.variance_fen != 0

    def test_cannot_submit_non_draft(self):
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        svc.submit_order(order_id)
        with pytest.raises(ValueError, match="不允许执行"):
            svc.submit_order(order_id)

    def test_get_suggested_orders(self):
        svc = PurchaseWorkbenchService()
        suggestions = svc.get_suggested_orders("S001")
        assert isinstance(suggestions, list)

    def test_get_supplier_performance(self):
        svc = PurchaseWorkbenchService()
        perf = svc.get_supplier_performance("SUP001")
        assert perf is not None
        assert perf.supplier_id == "SUP001"

    def test_full_po_lifecycle(self):
        """完整采购流程：创建→提交→确认→收货→对账"""
        svc = PurchaseWorkbenchService()
        order_id = self._create_po(svc)
        assert svc._orders[order_id].status == POStatus.DRAFT

        svc.submit_order(order_id)
        assert svc._orders[order_id].status == POStatus.SUBMITTED

        self._confirm_and_receive(svc, order_id)
        assert svc._orders[order_id].status == POStatus.RECEIVED

        result = svc.reconcile_order(order_id)
        assert result.is_clean is True
        assert svc._orders[order_id].status == POStatus.RECONCILED

    def test_po_total_calculation(self):
        svc = PurchaseWorkbenchService()
        po = svc.create_purchase_order(
            store_id="S001",
            supplier_id="SUP001",
            supplier_name="张记蔬菜",
            items=[
                {"ingredient_id": "ING001", "ingredient_name": "五花肉",
                 "unit": "kg", "ordered_qty": 10, "unit_price_fen": 3500},
                {"ingredient_id": "ING002", "ingredient_name": "青椒",
                 "unit": "kg", "ordered_qty": 5, "unit_price_fen": 800},
            ],
        )
        assert po.total_ordered_fen == 39000  # 10*3500 + 5*800


# ═══════════════════════════════════════════════════════════════════════════════
# MobileStocktakeService Tests (13)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMobileStocktake:

    def test_create_stocktake_full(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL, created_by="店长")
        assert st.status == StocktakeStatus.IN_PROGRESS
        assert st.scope == StocktakeScope.FULL

    def test_create_stocktake_partial(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.PARTIAL, category="蔬菜")
        assert st.category == "蔬菜"

    def test_add_count(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        record = svc.add_count(
            st.stocktake_id,
            ingredient_id="ING001",
            ingredient_name="五花肉",
            system_qty=50.0,
            counted_qty=48.0,
            unit="kg",
            unit_cost_fen=3500,
        )
        assert record.variance == -2.0
        assert record.variance_fen == -7000  # -2 * 3500
        assert record.needs_investigation is False  # 4% < 5%

    def test_count_needs_investigation(self):
        """差异率 > 5% 需要调查"""
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        record = svc.add_count(
            st.stocktake_id,
            ingredient_id="ING001",
            ingredient_name="五花肉",
            system_qty=100.0,
            counted_qty=90.0,  # 10% variance
            unit="kg",
            unit_cost_fen=3500,
        )
        assert record.needs_investigation is True

    def test_count_exact_match(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        record = svc.add_count(
            st.stocktake_id,
            ingredient_id="ING001",
            ingredient_name="五花肉",
            system_qty=50.0,
            counted_qty=50.0,
            unit="kg",
            unit_cost_fen=3500,
        )
        assert record.variance == 0.0
        assert record.needs_investigation is False

    def test_batch_count(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        result = svc.batch_count(st.stocktake_id, [
            {"ingredient_id": "ING001", "ingredient_name": "五花肉",
             "system_qty": 50, "counted_qty": 48, "unit": "kg", "unit_cost_fen": 3500},
            {"ingredient_id": "ING002", "ingredient_name": "青椒",
             "system_qty": 20, "counted_qty": 20, "unit": "kg", "unit_cost_fen": 800},
            {"ingredient_id": "ING003", "ingredient_name": "辣椒",
             "system_qty": 10, "counted_qty": 10, "unit": "kg", "unit_cost_fen": 1200},
        ])
        assert result.success_count == 3
        assert result.failed_count == 0

    def test_calculate_variance(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        svc.add_count(st.stocktake_id, "ING001", "五花肉", 50, 48, "kg", 3500)
        svc.add_count(st.stocktake_id, "ING002", "青椒", 20, 20, "kg", 800)
        report = svc.calculate_variance(st.stocktake_id)
        assert report.total_items == 2
        assert report.matched_items == 1
        assert report.variance_items == 1

    def test_variance_report_cost_impact(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        svc.add_count(st.stocktake_id, "ING001", "五花肉", 50, 45, "kg", 3500)  # -5kg
        report = svc.calculate_variance(st.stocktake_id)
        assert report.total_variance_fen == -17500  # -5 * 3500

    def test_get_variance_summary(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        svc.add_count(st.stocktake_id, "ING001", "五花肉", 50, 45, "kg", 3500)
        svc.add_count(st.stocktake_id, "ING002", "青椒", 20, 22, "kg", 800)  # 盘盈
        summary = svc.get_variance_summary(st.stocktake_id)
        assert summary is not None
        assert summary.negative_variance_fen < 0  # 盘亏
        assert summary.positive_variance_fen > 0  # 盘盈

    def test_approve_stocktake(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        svc.add_count(st.stocktake_id, "ING001", "五花肉", 50, 50, "kg", 3500)
        result = svc.approve_stocktake(st.stocktake_id, "MGR001")
        assert result.status == StocktakeStatus.APPROVED

    def test_cannot_approve_empty_stocktake(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        with pytest.raises(ValueError, match="没有盘点记录"):
            svc.approve_stocktake(st.stocktake_id, "MGR001")

    def test_count_with_location(self):
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        record = svc.add_count(
            st.stocktake_id, "ING001", "五花肉", 50, 48, "kg", 3500,
            location="冷库A", note="有2kg临近过期",
        )
        assert record.location == "冷库A"
        assert record.note == "有2kg临近过期"

    def test_system_qty_zero_variance(self):
        """系统库存为0时差异率处理"""
        svc = MobileStocktakeService()
        st = svc.create_stocktake("S001", StocktakeScope.FULL)
        record = svc.add_count(
            st.stocktake_id, "ING001", "五花肉", 0, 5, "kg", 3500,
        )
        # 系统0实盘5，差异率应为1.0（100%），需要调查
        assert record.variance_rate == 1.0
        assert record.needs_investigation is True
