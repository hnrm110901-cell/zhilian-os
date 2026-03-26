"""
顾客海鲜自选流程服务测试
"""

import pytest

from src.services.seafood_selection_service import (
    SeafoodSelectionFlow,
    SelectionStatus,
    TankInfo,
)


@pytest.fixture
def flow():
    svc = SeafoodSelectionFlow()
    # 注册测试鱼缸
    svc.register_tank(TankInfo(
        tank_id="T001", species="波士顿龙虾", available_qty=20,
        unit_price_fen=15000, unit_price_yuan=150.00,
        cooking_methods=["清蒸", "蒜蓉"], status="正常",
    ))
    svc.register_tank(TankInfo(
        tank_id="T002", species="基围虾", available_qty=50,
        unit_price_fen=6800, unit_price_yuan=68.00,
        cooking_methods=["白灼", "椒盐"], status="正常",
    ))
    svc.register_tank(TankInfo(
        tank_id="T003", species="石斑鱼", available_qty=0,
        unit_price_fen=12000, unit_price_yuan=120.00,
        cooking_methods=["清蒸"], status="补货中",
    ))
    return svc


class TestStartSelection:
    def test_start_returns_session_id(self, flow):
        result = flow.start_selection("A01")
        assert "session_id" in result
        assert result["table_code"] == "A01"
        assert result["status"] == "browsing"

    def test_start_with_customer_id(self, flow):
        result = flow.start_selection("A02", customer_id="C001")
        sid = result["session_id"]
        status = flow.get_selection_status(sid)
        assert status["customer_id"] == "C001"


class TestBrowseTanks:
    def test_browse_shows_available_only(self, flow):
        result = flow.start_selection("A01")
        sid = result["session_id"]
        tanks = flow.browse_tanks(sid)
        assert tanks["total_available"] == 2  # T003 库存0且补货中
        species_list = [t["species"] for t in tanks["tanks"]]
        assert "石斑鱼" not in species_list

    def test_browse_invalid_session(self, flow):
        result = flow.browse_tanks("nonexistent")
        assert "error" in result


class TestSelectItem:
    def test_select_success(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        result = flow.select_item(sid, "T001", "波士顿龙虾", 2)
        assert "item_id" in result
        assert result["quantity"] == 2
        assert "称重" in result["message"]

    def test_select_insufficient_stock(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        result = flow.select_item(sid, "T001", "波士顿龙虾", 999)
        assert "error" in result
        assert "库存不足" in result["error"]

    def test_select_zero_quantity(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        result = flow.select_item(sid, "T001", "波士顿龙虾", 0)
        assert "error" in result

    def test_select_nonexistent_tank(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        result = flow.select_item(sid, "T999", "未知", 1)
        assert "error" in result


class TestWeighItem:
    def test_weigh_success(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        item = flow.select_item(sid, "T001", "波士顿龙虾", 1)
        item_id = item["item_id"]

        result = flow.weigh_item(sid, item_id, 800, "SCALE001")
        assert result["weight_g"] == 800
        # 800g = 1.6斤，单价15000分/斤 → 24000分 = 240元
        assert result["total_price_fen"] == 24000
        assert result["total_price_yuan"] == 240.0
        assert "recommended_cooking" in result

    def test_weigh_zero_weight(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        item = flow.select_item(sid, "T001", "波士顿龙虾", 1)
        result = flow.weigh_item(sid, item["item_id"], 0, "SCALE001")
        assert "error" in result


class TestCookingMethod:
    def test_choose_method_success(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        item = flow.select_item(sid, "T001", "波士顿龙虾", 1)
        flow.weigh_item(sid, item["item_id"], 750, "S01")
        result = flow.choose_cooking_method(sid, item["item_id"], "清蒸")
        assert result["cooking_method"] == "清蒸"

    def test_choose_method_before_weigh(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        item = flow.select_item(sid, "T001", "波士顿龙虾", 1)
        result = flow.choose_cooking_method(sid, item["item_id"], "清蒸")
        assert "error" in result
        assert "称重" in result["error"]


class TestConfirmSelection:
    def test_full_flow_confirm(self, flow):
        """完整流程：选鱼→称重→做法→确认"""
        sid = flow.start_selection("A01")["session_id"]

        # 选第一条
        item1 = flow.select_item(sid, "T001", "波士顿龙虾", 1)
        flow.weigh_item(sid, item1["item_id"], 800, "S01")
        flow.choose_cooking_method(sid, item1["item_id"], "清蒸")

        # 选第二条
        item2 = flow.select_item(sid, "T002", "基围虾", 5)
        flow.weigh_item(sid, item2["item_id"], 500, "S01")
        flow.choose_cooking_method(sid, item2["item_id"], "白灼")

        # 确认
        result = flow.confirm_selection(sid)
        assert result["status"] == "confirmed"
        assert result["items_count"] == 2
        assert result["total_price_fen"] > 0
        assert result["total_price_yuan"] == round(result["total_price_fen"] / 100, 2)
        assert len(result["order_items"]) == 2

    def test_confirm_incomplete_fails(self, flow):
        """未完成称重/做法时确认失败"""
        sid = flow.start_selection("A01")["session_id"]
        flow.select_item(sid, "T001", "波士顿龙虾", 1)
        result = flow.confirm_selection(sid)
        assert "error" in result or "incomplete_items" in result

    def test_confirm_empty_selection(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        result = flow.confirm_selection(sid)
        assert "error" in result


class TestCancelSelection:
    def test_cancel_restores_stock(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        flow.select_item(sid, "T001", "波士顿龙虾", 3)
        # 库存从20减到17
        tanks = flow.browse_tanks(sid)
        lobster_tank = [t for t in tanks["tanks"] if t["tank_id"] == "T001"][0]
        assert lobster_tank["available_qty"] == 17

        # 取消后恢复
        flow.cancel_selection(sid)
        sid2 = flow.start_selection("A02")["session_id"]
        tanks2 = flow.browse_tanks(sid2)
        lobster_tank2 = [t for t in tanks2["tanks"] if t["tank_id"] == "T001"][0]
        assert lobster_tank2["available_qty"] == 20

    def test_cancel_confirmed_fails(self, flow):
        """已确认的不能取消"""
        sid = flow.start_selection("A01")["session_id"]
        item = flow.select_item(sid, "T001", "波士顿龙虾", 1)
        flow.weigh_item(sid, item["item_id"], 800, "S01")
        flow.choose_cooking_method(sid, item["item_id"], "清蒸")
        flow.confirm_selection(sid)
        result = flow.cancel_selection(sid)
        assert "error" in result


class TestGetSelectionStatus:
    def test_status_reflects_progress(self, flow):
        sid = flow.start_selection("A01")["session_id"]
        status = flow.get_selection_status(sid)
        assert status["status"] == "browsing"
        assert status["items_count"] == 0

        flow.select_item(sid, "T001", "波士顿龙虾", 1)
        status = flow.get_selection_status(sid)
        assert status["items_count"] == 1

    def test_status_invalid_session(self, flow):
        result = flow.get_selection_status("bad-id")
        assert "error" in result
