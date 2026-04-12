"""
P2 Gap Services 测试
覆盖：SupplierStatementService, CentralKitchenService, SemiFinishedService,
      DishSOPService, FranchiseService
每个服务至少5个测试，共25+
"""

import os
import sys
import types
import importlib.util
from datetime import date, datetime, timezone

import pytest

# === 导入模式（按项目约定） ===
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


supplier_mod = _load("supplier_statement_service")
ck_mod = _load("central_kitchen_service")
semi_mod = _load("semi_finished_service")
sop_mod = _load("dish_sop_service")
franchise_mod = _load("franchise_service")

SupplierStatementService = supplier_mod.SupplierStatementService
PurchaseEntry = supplier_mod.PurchaseEntry
PaymentRecord = supplier_mod.PaymentRecord
ReconcileStatus = supplier_mod.ReconcileStatus

CentralKitchenService = ck_mod.CentralKitchenService
ProductionItem = ck_mod.ProductionItem
PlanStatus = ck_mod.PlanStatus
DeliveryStatus = ck_mod.DeliveryStatus

SemiFinishedService = semi_mod.SemiFinishedService
SemiFinishedIngredient = semi_mod.SemiFinishedIngredient
BatchStatus = semi_mod.BatchStatus

DishSOPService = sop_mod.DishSOPService
SOPStep = sop_mod.SOPStep

FranchiseService = franchise_mod.FranchiseService
FranchiseeStatus = franchise_mod.FranchiseeStatus
FeeType = franchise_mod.FeeType


# ============================================================
# SupplierStatementService 测试（6个）
# ============================================================

class TestSupplierStatementService:

    def _make_svc_with_data(self):
        svc = SupplierStatementService()
        svc.add_entry(PurchaseEntry(
            supplier_id="SUP001", store_id="S001", item_name="猪肉",
            qty=10, unit="kg", unit_price_fen=2000, amount_fen=20000,
            delivery_date=date(2026, 3, 10), invoice_no="INV001",
        ))
        svc.add_entry(PurchaseEntry(
            supplier_id="SUP001", store_id="S001", item_name="牛肉",
            qty=5, unit="kg", unit_price_fen=5000, amount_fen=25000,
            delivery_date=date(2026, 3, 15), invoice_no="INV002",
        ))
        svc.add_entry(PurchaseEntry(
            supplier_id="SUP002", store_id="S002", item_name="鸡蛋",
            qty=100, unit="个", unit_price_fen=50, amount_fen=5000,
            delivery_date=date(2026, 3, 12),
        ))
        svc.add_payment(PaymentRecord(
            supplier_id="SUP001", amount_fen=15000,
            payment_date=date(2026, 3, 20), method="bank_transfer",
        ))
        return svc

    def test_generate_statement_basic(self):
        """生成对账单基本功能"""
        svc = self._make_svc_with_data()
        stmt = svc.generate_statement("SUP001", date(2026, 3, 1), date(2026, 3, 31))
        assert stmt["supplier_id"] == "SUP001"
        assert stmt["summary"]["total_purchase_fen"] == 45000
        assert stmt["summary"]["total_purchase_yuan"] == 450.0
        assert stmt["summary"]["total_payment_fen"] == 15000
        assert stmt["summary"]["balance_fen"] == 30000
        assert stmt["summary"]["balance_yuan"] == 300.0
        assert stmt["summary"]["entry_count"] == 2

    def test_generate_statement_with_store_filter(self):
        """对账单按门店过滤"""
        svc = self._make_svc_with_data()
        stmt = svc.generate_statement("SUP001", date(2026, 3, 1), date(2026, 3, 31), store_id="S001")
        assert stmt["summary"]["entry_count"] == 2

    def test_generate_statement_empty_period(self):
        """空日期范围返回空对账单"""
        svc = self._make_svc_with_data()
        stmt = svc.generate_statement("SUP001", date(2026, 1, 1), date(2026, 1, 31))
        assert stmt["summary"]["total_purchase_fen"] == 0
        assert stmt["summary"]["entry_count"] == 0

    def test_get_payables(self):
        """应付账款汇总"""
        svc = self._make_svc_with_data()
        payables = svc.get_payables()
        # SUP001: 45000 - 15000 = 30000 应付
        # SUP002: 5000 - 0 = 5000 应付
        assert len(payables) == 2
        sup001 = next(p for p in payables if p["supplier_id"] == "SUP001")
        assert sup001["payable_fen"] == 30000
        assert sup001["payable_yuan"] == 300.0

    def test_get_payables_by_supplier(self):
        """按供应商查询应付"""
        svc = self._make_svc_with_data()
        payables = svc.get_payables(supplier_id="SUP002")
        assert len(payables) == 1
        assert payables[0]["payable_fen"] == 5000

    def test_reconcile_matched(self):
        """对账一致"""
        svc = self._make_svc_with_data()
        result = svc.reconcile("SUP001", 45000, date(2026, 3, 1), date(2026, 3, 31))
        assert result["status"] == ReconcileStatus.MATCHED.value
        assert result["difference_fen"] == 0

    def test_reconcile_disputed(self):
        """对账有差异"""
        svc = self._make_svc_with_data()
        result = svc.reconcile("SUP001", 40000, date(2026, 3, 1), date(2026, 3, 31))
        assert result["status"] == ReconcileStatus.DISPUTED.value
        assert result["difference_fen"] == 5000
        assert result["difference_yuan"] == 50.0


# ============================================================
# CentralKitchenService 测试（7个）
# ============================================================

class TestCentralKitchenService:

    def _make_items(self):
        return [
            ProductionItem(item_id="I001", item_name="卤牛肉", qty=50, unit="kg", cost_fen=3000),
            ProductionItem(item_id="I002", item_name="糖醋汁", qty=20, unit="L", cost_fen=500),
        ]

    def test_create_plan(self):
        """创建生产计划"""
        svc = CentralKitchenService()
        items = self._make_items()
        plan = svc.create_plan(date(2026, 3, 26), items, note="周四生产")
        assert plan.status == PlanStatus.DRAFT
        assert len(plan.items) == 2
        assert plan.note == "周四生产"
        # 50*3000 + 20*500 = 160000
        assert plan.total_cost_fen == 160000
        assert plan.total_cost_yuan == 1600.0

    def test_create_plan_empty_items_raises(self):
        """空生产项不允许"""
        svc = CentralKitchenService()
        with pytest.raises(ValueError, match="不能为空"):
            svc.create_plan(date(2026, 3, 26), [])

    def test_production_lifecycle(self):
        """生产计划完整生命周期：DRAFT -> CONFIRMED -> IN_PRODUCTION -> COMPLETED"""
        svc = CentralKitchenService()
        plan = svc.create_plan(date(2026, 3, 26), self._make_items())
        assert plan.status == PlanStatus.DRAFT

        plan = svc.schedule_production(plan.plan_id)
        assert plan.status == PlanStatus.CONFIRMED

        plan = svc.start_production(plan.plan_id)
        assert plan.status == PlanStatus.IN_PRODUCTION

        plan = svc.complete_production(plan.plan_id)
        assert plan.status == PlanStatus.COMPLETED

    def test_schedule_non_draft_raises(self):
        """非DRAFT状态不能排产"""
        svc = CentralKitchenService()
        plan = svc.create_plan(date(2026, 3, 26), self._make_items())
        svc.schedule_production(plan.plan_id)
        with pytest.raises(ValueError, match="不允许排产"):
            svc.schedule_production(plan.plan_id)

    def test_create_distribution_and_dispatch(self):
        """创建配送单并发车"""
        svc = CentralKitchenService()
        plan = svc.create_plan(date(2026, 3, 26), self._make_items())
        dist = svc.create_distribution(
            plan.plan_id, "S001", "尝在一起·五一店",
            [{"item_name": "卤牛肉", "qty": 10, "unit": "kg"}],
        )
        assert dist.status == DeliveryStatus.PENDING
        dist = svc.dispatch(dist.order_id, driver="张师傅")
        assert dist.status == DeliveryStatus.DISPATCHED
        assert dist.driver == "张师傅"
        assert dist.dispatched_at is not None

    def test_track_delivery(self):
        """追踪配送状态"""
        svc = CentralKitchenService()
        plan = svc.create_plan(date(2026, 3, 26), self._make_items())
        dist = svc.create_distribution(
            plan.plan_id, "S001", "尝在一起·五一店",
            [{"item_name": "卤牛肉", "qty": 10, "unit": "kg"}],
        )
        info = svc.track_delivery(dist.order_id)
        assert info["status"] == "pending"
        assert info["store_name"] == "尝在一起·五一店"
        assert info["items_count"] == 1

    def test_confirm_delivery(self):
        """确认收货"""
        svc = CentralKitchenService()
        plan = svc.create_plan(date(2026, 3, 26), self._make_items())
        dist = svc.create_distribution(
            plan.plan_id, "S001", "尝在一起·五一店",
            [{"item_name": "卤牛肉", "qty": 10, "unit": "kg"}],
        )
        svc.dispatch(dist.order_id, driver="张师傅")
        dist = svc.confirm_delivery(dist.order_id)
        assert dist.status == DeliveryStatus.DELIVERED
        assert dist.delivered_at is not None


# ============================================================
# SemiFinishedService 测试（6个）
# ============================================================

class TestSemiFinishedService:

    def _make_recipe_ingredients(self):
        return [
            SemiFinishedIngredient(
                ingredient_id="IG001", ingredient_name="猪肉",
                qty=5, unit="kg", cost_fen=2000,
            ),
            SemiFinishedIngredient(
                ingredient_id="IG002", ingredient_name="酱油",
                qty=1, unit="L", cost_fen=800,
            ),
        ]

    def test_create_recipe(self):
        """创建半成品配方"""
        svc = SemiFinishedService()
        recipe = svc.create_recipe(
            name="卤肉", recipe=self._make_recipe_ingredients(),
            standard_batch_qty=10, unit="份", shelf_life_hours=48,
        )
        assert recipe.name == "卤肉"
        assert recipe.standard_batch_qty == 10
        # 成本 = (2000*5 + 800*1) / 10 = 10800/10 = 1080
        assert recipe.unit_cost_fen == 1080
        assert recipe.unit_cost_yuan == 10.8

    def test_create_recipe_empty_raises(self):
        """空配方不允许"""
        svc = SemiFinishedService()
        with pytest.raises(ValueError, match="不能为空"):
            svc.create_recipe(name="空", recipe=[])

    def test_produce_batch(self):
        """生产批次"""
        svc = SemiFinishedService()
        recipe = svc.create_recipe(
            name="卤肉", recipe=self._make_recipe_ingredients(),
            standard_batch_qty=10, unit="份",
        )
        batch = svc.produce_batch(recipe.semi_id, qty=20, operator="厨师长")
        assert batch.produced_qty == 20
        assert batch.remaining_qty == 20
        assert batch.status == BatchStatus.IN_STOCK
        # 成本按比例: ratio=20/10=2, cost = (2000*5*2 + 800*1*2) = 21600
        assert batch.cost_fen == 21600

    def test_produce_batch_zero_qty_raises(self):
        """生产数量<=0报错"""
        svc = SemiFinishedService()
        recipe = svc.create_recipe(
            name="卤肉", recipe=self._make_recipe_ingredients(),
            standard_batch_qty=10, unit="份",
        )
        with pytest.raises(ValueError, match="大于0"):
            svc.produce_batch(recipe.semi_id, qty=0)

    def test_consume_in_order_fifo(self):
        """FIFO消耗半成品"""
        svc = SemiFinishedService()
        recipe = svc.create_recipe(
            name="卤肉", recipe=self._make_recipe_ingredients(),
            standard_batch_qty=10, unit="份",
        )
        batch1 = svc.produce_batch(recipe.semi_id, qty=5, operator="A")
        batch2 = svc.produce_batch(recipe.semi_id, qty=10, operator="B")

        result = svc.consume_in_order(recipe.semi_id, qty=7, order_id="ORD001")
        assert result["consumed_qty"] == 7
        assert result["shortage_qty"] == 0
        assert len(result["batches"]) == 2
        # 第一批全部消耗(5)，第二批消耗2
        assert result["batches"][0]["qty"] == 5
        assert result["batches"][1]["qty"] == 2
        # 验证batch1被标为DEPLETED
        assert svc._batches[batch1.batch_id].status == BatchStatus.DEPLETED

    def test_get_inventory(self):
        """获取半成品库存汇总"""
        svc = SemiFinishedService()
        recipe = svc.create_recipe(
            name="卤肉", recipe=self._make_recipe_ingredients(),
            standard_batch_qty=10, unit="份", store_id="S001",
        )
        svc.produce_batch(recipe.semi_id, qty=10, store_id="S001")
        svc.produce_batch(recipe.semi_id, qty=5, store_id="S001")

        inventory = svc.get_inventory(store_id="S001")
        assert len(inventory) == 1
        assert inventory[0]["name"] == "卤肉"
        assert inventory[0]["total_qty"] == 15
        assert inventory[0]["batch_count"] == 2
        assert "total_cost_yuan" in inventory[0]


# ============================================================
# DishSOPService 测试（6个）
# ============================================================

class TestDishSOPService:

    def _make_steps(self):
        return [
            SOPStep(description="热锅冷油", duration_seconds=30, temperature=180, tips="油温不宜过高"),
            SOPStep(description="下肉片翻炒", duration_seconds=60, tools=["锅铲"]),
            SOPStep(description="加酱汁焖煮", duration_seconds=180, temperature=100),
        ]

    def test_create_sop(self):
        """创建菜品SOP"""
        svc = DishSOPService()
        sop = svc.create_sop(
            dish_id="D001", dish_name="小炒肉",
            steps=self._make_steps(), difficulty="中等",
        )
        assert sop.dish_name == "小炒肉"
        assert len(sop.steps) == 3
        assert sop.total_time_seconds == 270
        assert sop.total_time_minutes == 4.5
        # 自动编号
        assert sop.steps[0].step_no == 1
        assert sop.steps[2].step_no == 3

    def test_create_sop_empty_steps_raises(self):
        """空步骤不允许"""
        svc = DishSOPService()
        with pytest.raises(ValueError, match="不能为空"):
            svc.create_sop(dish_id="D001", dish_name="空SOP", steps=[])

    def test_display_on_kds(self):
        """KDS展示数据"""
        svc = DishSOPService()
        svc.create_sop(dish_id="D001", dish_name="小炒肉", steps=self._make_steps())
        kds = svc.display_on_kds("D001")
        assert kds["has_sop"] is True
        assert kds["dish_name"] == "小炒肉"
        assert len(kds["steps"]) == 3
        # 30秒 < 120，显示为"30秒"
        assert kds["steps"][0]["time"] == "30秒"
        # 180秒 >= 120，显示为"3分钟"
        assert kds["steps"][2]["time"] == "3分钟"
        # 有温度的步骤
        assert kds["steps"][0]["temp"] == "180℃"

    def test_display_on_kds_no_sop(self):
        """无SOP菜品的KDS降级"""
        svc = DishSOPService()
        kds = svc.display_on_kds("NONEXIST")
        assert kds["has_sop"] is False
        assert kds["steps"] == []

    def test_update_step(self):
        """更新SOP步骤"""
        svc = DishSOPService()
        svc.create_sop(dish_id="D001", dish_name="小炒肉", steps=self._make_steps())
        sop = svc.update_step("D001", step_no=2, description="下五花肉翻炒", duration_seconds=90)
        assert sop.steps[1].description == "下五花肉翻炒"
        assert sop.steps[1].duration_seconds == 90
        assert sop.version == 2
        # 总耗时重新计算: 30 + 90 + 180 = 300
        assert sop.total_time_seconds == 300

    def test_add_step(self):
        """添加SOP步骤"""
        svc = DishSOPService()
        svc.create_sop(dish_id="D001", dish_name="小炒肉", steps=self._make_steps())
        new_step = SOPStep(description="装盘", duration_seconds=15)
        sop = svc.add_step("D001", new_step)
        assert len(sop.steps) == 4
        assert sop.steps[3].step_no == 4
        assert sop.steps[3].description == "装盘"
        assert sop.version == 2

    def test_list_all(self):
        """列出所有SOP"""
        svc = DishSOPService()
        svc.create_sop(dish_id="D001", dish_name="小炒肉", steps=self._make_steps())
        svc.create_sop(dish_id="D002", dish_name="辣椒炒肉",
                       steps=[SOPStep(description="炒", duration_seconds=60)])
        result = svc.list_all()
        assert len(result) == 2
        names = {r["dish_name"] for r in result}
        assert names == {"小炒肉", "辣椒炒肉"}


# ============================================================
# FranchiseService 测试（6个）
# ============================================================

class TestFranchiseService:

    def _register_default(self, svc):
        return svc.register(
            name="张三加盟店", contact_person="张三", phone="13800001111",
            store_ids=["S100", "S101"], region="长沙",
            royalty_rate=0.03, management_fee_fen=500000,
            marketing_rate=0.01, initial_fee_fen=10000000,
        )

    def test_register(self):
        """注册加盟商"""
        svc = FranchiseService()
        f = self._register_default(svc)
        assert f.name == "张三加盟店"
        assert f.status == FranchiseeStatus.ACTIVE
        assert len(f.store_ids) == 2
        assert f.royalty_rate == 0.03

    def test_calculate_royalty(self):
        """计算特许权使用费"""
        svc = FranchiseService()
        f = self._register_default(svc)
        svc.set_store_revenue("S100", "2026-03", 50000000)  # 50万
        svc.set_store_revenue("S101", "2026-03", 30000000)  # 30万
        fees = svc.calculate_royalty(f.franchisee_id, "2026-03")
        assert len(fees) == 3
        royalty = next(fee for fee in fees if fee.fee_type == FeeType.ROYALTY)
        # 总营业额 800000元 = 80000000分, 3% = 2400000分
        assert royalty.amount_fen == int(80000000 * 0.03)
        mgmt = next(fee for fee in fees if fee.fee_type == FeeType.MANAGEMENT)
        assert mgmt.amount_fen == 500000
        marketing = next(fee for fee in fees if fee.fee_type == FeeType.MARKETING)
        assert marketing.amount_fen == int(80000000 * 0.01)

    def test_calculate_royalty_suspended_raises(self):
        """暂停状态加盟商不能计算费用"""
        svc = FranchiseService()
        f = self._register_default(svc)
        svc.suspend(f.franchisee_id, reason="欠费")
        with pytest.raises(ValueError, match="状态异常"):
            svc.calculate_royalty(f.franchisee_id, "2026-03")

    def test_get_kpi_dashboard(self):
        """KPI面板"""
        svc = FranchiseService()
        f = self._register_default(svc)
        svc.set_store_revenue("S100", "2026-03", 50000000)
        svc.calculate_royalty(f.franchisee_id, "2026-03")
        dashboard = svc.get_kpi_dashboard(f.franchisee_id)
        assert dashboard["name"] == "张三加盟店"
        assert dashboard["store_count"] == 2
        assert dashboard["total_revenue_fen"] == 50000000
        assert dashboard["total_revenue_yuan"] == 500000.0
        assert dashboard["total_fees_fen"] > 0
        assert "unpaid_yuan" in dashboard

    def test_suspend_and_reactivate(self):
        """暂停和恢复加盟商"""
        svc = FranchiseService()
        f = self._register_default(svc)
        f = svc.suspend(f.franchisee_id, reason="合规检查")
        assert f.status == FranchiseeStatus.SUSPENDED
        f = svc.reactivate(f.franchisee_id)
        assert f.status == FranchiseeStatus.ACTIVE

    def test_terminate(self):
        """终止加盟商"""
        svc = FranchiseService()
        f = self._register_default(svc)
        f = svc.terminate(f.franchisee_id, reason="合同到期")
        assert f.status == FranchiseeStatus.TERMINATED
        # 再次终止应报错
        with pytest.raises(ValueError, match="已终止"):
            svc.terminate(f.franchisee_id)
