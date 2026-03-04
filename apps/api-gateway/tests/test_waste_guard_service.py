"""
WasteGuardService 单元测试

覆盖：
  - get_top5_waste：Top5 损耗食材 + 归因
  - get_waste_rate_summary：损耗率计算 + 状态分级 + 环比
  - get_bom_waste_deviation：BOM 偏差排名
  - get_full_waste_report：综合报告（组合调用）
  - _action_for_causes：根因 → 行动映射
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.waste_guard_service import (
    WasteGuardService,
    _action_for_causes,
    _DEFAULT_ACTION,
    _ROOT_CAUSE_ACTIONS,
)


# ── 纯函数测试 ─────────────────────────────────────────────────────────────────

class TestActionForCauses:
    def test_empty_list_returns_default(self):
        assert _action_for_causes([]) == _DEFAULT_ACTION

    def test_known_root_cause(self):
        causes = [{"root_cause": "staff_error", "event_type": "cooking_loss", "event_count": 3}]
        assert _action_for_causes(causes) == _ROOT_CAUSE_ACTIONS["staff_error"]

    def test_uses_first_cause_as_primary(self):
        causes = [
            {"root_cause": "over_prep",    "event_type": "over_prep", "event_count": 5},
            {"root_cause": "food_quality", "event_type": "spoilage",  "event_count": 2},
        ]
        assert _action_for_causes(causes) == _ROOT_CAUSE_ACTIONS["over_prep"]

    def test_unknown_root_cause_returns_default(self):
        causes = [{"root_cause": None, "event_type": None, "event_count": 1}]
        assert _action_for_causes(causes) == _DEFAULT_ACTION

    def test_event_type_used_when_root_cause_none(self):
        causes = [{"root_cause": None, "event_type": "spoilage", "event_count": 2}]
        assert _action_for_causes(causes) == _ROOT_CAUSE_ACTIONS["spoilage"]


# ── get_top5_waste ─────────────────────────────────────────────────────────────

class TestGetTop5Waste:
    def _make_db(self, top5_rows, total_fen, attr_rows=None):
        """构造返回固定数据的 AsyncMock db"""
        db = AsyncMock()
        call_count = 0

        async def execute_side_effect(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # SQL 1: top5 rows
                result.fetchall.return_value = top5_rows
            elif call_count == 2:
                # SQL 2: total waste
                result.scalar.return_value = total_fen
            else:
                # SQL 3: attribution
                result.fetchall.return_value = attr_rows or []
            return result

        db.execute = execute_side_effect
        return db

    @pytest.mark.asyncio
    async def test_empty_result(self):
        db = self._make_db(top5_rows=[], total_fen=0)
        result = await WasteGuardService.get_top5_waste(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["top5"] == []
        assert result["total_waste_yuan"] == 0.0

    @pytest.mark.asyncio
    async def test_single_item_ranked_first(self):
        row = MagicMock()
        row.item_id = "ITEM-001"
        row.item_name = "鸡腿"
        row.category = "meat"
        row.unit = "kg"
        row.waste_cost_fen = 15000   # ¥150
        row.waste_qty = 10.0

        db = self._make_db(top5_rows=[row], total_fen=15000)
        result = await WasteGuardService.get_top5_waste(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert len(result["top5"]) == 1
        item = result["top5"][0]
        assert item["rank"] == 1
        assert item["waste_cost_yuan"] == 150.0
        assert item["cost_share_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_cost_share_calculation(self):
        rows = []
        for i, cost in enumerate([6000, 3000, 1000], start=1):
            row = MagicMock()
            row.item_id = f"ITEM-{i:03d}"
            row.item_name = f"食材{i}"
            row.category = "vegetable"
            row.unit = "kg"
            row.waste_cost_fen = cost
            row.waste_qty = 5.0
            rows.append(row)

        db = self._make_db(top5_rows=rows, total_fen=10000)
        result = await WasteGuardService.get_top5_waste(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        shares = [item["cost_share_pct"] for item in result["top5"]]
        assert shares == [60.0, 30.0, 10.0]

    @pytest.mark.asyncio
    async def test_attribution_mapped_to_items(self):
        row = MagicMock()
        row.item_id = "ITEM-001"
        row.item_name = "羊肉"
        row.category = "meat"
        row.unit = "kg"
        row.waste_cost_fen = 20000
        row.waste_qty = 8.0

        attr_row = MagicMock()
        attr_row.ingredient_id = "ITEM-001"
        attr_row.root_cause = "over_prep"
        attr_row.event_type = "over_prep"
        attr_row.event_count = 4

        db = self._make_db(top5_rows=[row], total_fen=20000, attr_rows=[attr_row])
        result = await WasteGuardService.get_top5_waste(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        item = result["top5"][0]
        assert len(item["root_causes"]) == 1
        assert item["root_causes"][0]["root_cause"] == "over_prep"
        assert "备餐量" in item["action"]

    @pytest.mark.asyncio
    async def test_no_attribution_uses_default_action(self):
        row = MagicMock()
        row.item_id = "ITEM-001"
        row.item_name = "食材A"
        row.category = "dry_goods"
        row.unit = "kg"
        row.waste_cost_fen = 5000
        row.waste_qty = 2.0

        db = self._make_db(top5_rows=[row], total_fen=5000, attr_rows=[])
        result = await WasteGuardService.get_top5_waste(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["top5"][0]["action"] == _DEFAULT_ACTION


# ── get_waste_rate_summary ────────────────────────────────────────────────────

class TestGetWasteRateSummary:
    def _make_db(self, waste_fen, revenue_fen, prev_waste_fen=0):
        db = AsyncMock()
        call_count = 0

        async def execute_side_effect(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = waste_fen
            elif call_count == 2:
                result.scalar.return_value = revenue_fen
            else:
                result.scalar.return_value = prev_waste_fen
            return result

        db.execute = execute_side_effect
        return db

    @pytest.mark.asyncio
    async def test_zero_revenue_rate_is_zero(self):
        db = self._make_db(waste_fen=5000, revenue_fen=0)
        result = await WasteGuardService.get_waste_rate_summary(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["waste_rate_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_status_ok_below_3pct(self):
        # waste=¥200，revenue=¥10000 → 2%
        db = self._make_db(waste_fen=20000, revenue_fen=1000000)
        result = await WasteGuardService.get_waste_rate_summary(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["waste_rate_status"] == "ok"

    @pytest.mark.asyncio
    async def test_status_warning_3_to_5pct(self):
        # waste=¥400，revenue=¥10000 → 4%
        db = self._make_db(waste_fen=40000, revenue_fen=1000000)
        result = await WasteGuardService.get_waste_rate_summary(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["waste_rate_status"] == "warning"

    @pytest.mark.asyncio
    async def test_status_critical_above_5pct(self):
        # waste=¥600，revenue=¥10000 → 6%
        db = self._make_db(waste_fen=60000, revenue_fen=1000000)
        result = await WasteGuardService.get_waste_rate_summary(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["waste_rate_status"] == "critical"

    @pytest.mark.asyncio
    async def test_waste_change_calculated(self):
        # 本期¥300，上期¥200 → 增加¥100
        db = self._make_db(waste_fen=30000, revenue_fen=1000000, prev_waste_fen=20000)
        result = await WasteGuardService.get_waste_rate_summary(
            "S001", date(2026, 2, 1), date(2026, 2, 7), db
        )
        assert result["waste_change_yuan"] == 100.0

    @pytest.mark.asyncio
    async def test_no_prev_period_change_pct_is_none(self):
        db = self._make_db(waste_fen=30000, revenue_fen=1000000, prev_waste_fen=0)
        result = await WasteGuardService.get_waste_rate_summary(
            "S001", date(2026, 2, 1), date(2026, 2, 7), db
        )
        assert result["waste_change_pct"] is None


# ── get_bom_waste_deviation ───────────────────────────────────────────────────

class TestGetBomWasteDeviation:
    @pytest.mark.asyncio
    async def test_empty_returns_empty_items(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await WasteGuardService.get_bom_waste_deviation(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_variance_cost_yuan_conversion(self):
        row = MagicMock()
        row.ingredient_id = "ING-001"
        row.item_name = "羊肉"
        row.unit = "kg"
        row.unit_cost_fen = 3000   # ¥30/kg
        row.total_variance_qty = 5.0
        row.variance_cost_fen = 15000   # ¥150
        row.avg_variance_pct = 0.15     # 15%
        row.event_count = 7

        result_mock = MagicMock()
        result_mock.fetchall.return_value = [row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await WasteGuardService.get_bom_waste_deviation(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )
        item = result["items"][0]
        assert item["rank"] == 1
        assert item["variance_cost_yuan"] == 150.0
        assert item["avg_variance_pct"] == 15.0
        assert item["event_count"] == 7


# ── get_full_waste_report ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_waste_report_combines_all():
    """综合报告应包含 top5、bom_deviation 和 waste_rate_pct 字段"""
    with (
        patch.object(
            WasteGuardService, "get_top5_waste", new_callable=AsyncMock,
            return_value={"top5": [], "total_waste_yuan": 0.0},
        ) as mock_top5,
        patch.object(
            WasteGuardService, "get_waste_rate_summary", new_callable=AsyncMock,
            return_value={
                "waste_rate_pct": 2.5,
                "waste_rate_status": "warning",
                "waste_cost_yuan": 500.0,
                "waste_change_yuan": 50.0,
            },
        ),
        patch.object(
            WasteGuardService, "get_bom_waste_deviation", new_callable=AsyncMock,
            return_value={"items": []},
        ),
    ):
        db = AsyncMock()
        result = await WasteGuardService.get_full_waste_report(
            "S001", date(2026, 2, 1), date(2026, 2, 28), db
        )

    assert "top5" in result
    assert "bom_deviation" in result
    assert result["waste_rate_pct"] == 2.5
    assert result["waste_rate_status"] == "warning"
    assert result["total_waste_yuan"] == 500.0
