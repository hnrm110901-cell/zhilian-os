"""
DecisionPriorityEngine 单元测试

测试覆盖：
  - 纯函数：_hours_to_next_window / _score_* / compute_priority_score
  - 候选决策格式化：_format_decision
  - 集成：get_top3（mock DB + mock services）
"""
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.decision_priority_engine import (
    DecisionCandidate,
    DecisionPriorityEngine,
    _format_decision,
    _hours_to_next_window,
    _score_confidence,
    _score_execution,
    _score_financial,
    _score_urgency,
    compute_priority_score,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreFinancial:
    def test_zero_revenue_returns_zero(self):
        assert _score_financial(1000, 0) == 0.0

    def test_zero_saving_returns_zero(self):
        assert _score_financial(0, 100_000) == 0.0

    def test_capped_at_100(self):
        # 节省 = 月营收 → 理论上 10000 分，应被 cap 到 100
        assert _score_financial(100_000, 100_000) == 100.0

    def test_one_percent_monthly(self):
        # 节省1%月营收（100_000 × 1% = 1000）→ 1000 / 100_000 × 10000 = 100
        assert _score_financial(1000, 100_000) == 100.0

    def test_half_percent_monthly(self):
        # 节省0.5%月营收（500 / 100_000 × 10000 = 50）
        result = _score_financial(500, 100_000)
        assert result == 50.0


class TestScoreUrgency:
    def test_zero_hours_is_max(self):
        assert _score_urgency(0) == 100.0

    def test_negative_hours_clamped_to_max(self):
        assert _score_urgency(-1) == 100.0

    def test_12_hours(self):
        # 100 / (1+12) ≈ 7.69
        result = _score_urgency(12)
        assert abs(result - 7.69) < 0.1

    def test_urgency_decreases_with_hours(self):
        assert _score_urgency(1) > _score_urgency(4) > _score_urgency(12)


class TestScoreConfidence:
    def test_full_confidence(self):
        assert _score_confidence(1.0) == 100.0

    def test_zero_confidence(self):
        assert _score_confidence(0.0) == 0.0

    def test_80_percent(self):
        assert _score_confidence(0.80) == 80.0

    def test_clamp_above_one(self):
        assert _score_confidence(1.5) == 100.0


class TestScoreExecution:
    def test_easy_is_max(self):
        assert _score_execution("easy") == 100.0

    def test_medium_is_60(self):
        assert _score_execution("medium") == 60.0

    def test_hard_is_30(self):
        assert _score_execution("hard") == 30.0

    def test_unknown_defaults_to_60(self):
        assert _score_execution("unknown") == 60.0


class TestComputePriorityScore:
    def _make_candidate(self, saving=1000, cost=0, confidence=0.8, urgency=2.0, difficulty="easy"):
        return DecisionCandidate(
            title="test",
            action="test action",
            source="inventory",
            expected_saving_yuan=saving,
            expected_cost_yuan=cost,
            confidence=confidence,
            urgency_hours=urgency,
            execution_difficulty=difficulty,
            decision_window_label="17:30战前",
        )

    def test_score_is_between_0_and_100(self):
        c = self._make_candidate()
        score = compute_priority_score(c, monthly_revenue_yuan=100_000)
        assert 0.0 <= score <= 100.0

    def test_higher_saving_gives_higher_score(self):
        c_low  = self._make_candidate(saving=100)
        c_high = self._make_candidate(saving=5000)
        monthly_rev = 100_000
        assert compute_priority_score(c_high, monthly_rev) > compute_priority_score(c_low, monthly_rev)

    def test_lower_urgency_hours_gives_higher_score(self):
        c_urgent = self._make_candidate(urgency=0.5)
        c_later  = self._make_candidate(urgency=10.0)
        assert compute_priority_score(c_urgent) > compute_priority_score(c_later)

    def test_weights_sum_to_one(self):
        # 满分候选：saving=月营收，urgency=0，confidence=1.0，easy
        c = DecisionCandidate(
            title="max", action="max", source="inventory",
            expected_saving_yuan=100_000, expected_cost_yuan=0,
            confidence=1.0, urgency_hours=0.0,
            execution_difficulty="easy", decision_window_label="立即",
        )
        score = compute_priority_score(c, monthly_revenue_yuan=100_000)
        assert score == 100.0


class TestHoursToNextWindow:
    def test_returns_tuple(self):
        now = datetime(2026, 3, 4, 10, 0, 0)
        hours, label = _hours_to_next_window(now)
        assert isinstance(hours, float)
        assert isinstance(label, str)

    def test_before_first_window(self):
        # 7:00 → next window = 08:00，距离1小时
        now = datetime(2026, 3, 4, 7, 0, 0)
        hours, label = _hours_to_next_window(now)
        assert abs(hours - 1.0) < 0.01
        assert label == "08:00晨推"

    def test_between_windows(self):
        # 09:00 → next window = 12:00，距离3小时
        now = datetime(2026, 3, 4, 9, 0, 0)
        hours, label = _hours_to_next_window(now)
        assert abs(hours - 3.0) < 0.01
        assert label == "12:00午推"

    def test_after_last_window(self):
        # 22:00 → 所有今天窗口已过，next = 明天08:00
        now = datetime(2026, 3, 4, 22, 0, 0)
        hours, label = _hours_to_next_window(now)
        assert hours > 0
        assert label == "08:00晨推"


class TestFormatDecision:
    def test_output_has_required_fields(self):
        c = DecisionCandidate(
            title="补货：鸡腿",
            action="建议采购100kg",
            source="inventory",
            expected_saving_yuan=500.0,
            expected_cost_yuan=200.0,
            confidence=0.85,
            urgency_hours=2.0,
            execution_difficulty="easy",
            decision_window_label="17:30战前",
        )
        result = _format_decision(c, priority_score=75.0, rank=1)
        assert result["rank"] == 1
        assert result["expected_saving_yuan"] == 500.0
        assert result["expected_cost_yuan"] == 200.0
        assert result["net_benefit_yuan"] == 300.0
        assert result["confidence_pct"] == 85.0
        assert result["priority_score"] == 75.0


# ═══════════════════════════════════════════════════════════════════════════════
# 集成测试（mock DB）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_top3_returns_list():
    """get_top3 在无数据时返回空列表（不报错）"""
    engine = DecisionPriorityEngine(store_id="S001")
    db = AsyncMock()
    # inventory 查询返回空
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "src.services.decision_priority_engine.FoodCostService.get_store_food_cost_variance",
        new_callable=AsyncMock,
        return_value={"variance_status": "ok", "variance_pct": 0.0, "actual_cost_pct": 30.0,
                      "revenue_yuan": 0.0, "top_ingredients": []},
    ):
        result = await engine.get_top3(db=db, target_date=date(2026, 3, 4))

    assert isinstance(result, list)
    assert len(result) <= 3


@pytest.mark.asyncio
async def test_get_top3_inventory_candidate():
    """有库存告警时 get_top3 返回非空决策"""
    from src.models.inventory import InventoryStatus

    engine = DecisionPriorityEngine(store_id="S001")
    db = AsyncMock()

    # Mock InventoryItem（OUT_OF_STOCK）
    mock_item = MagicMock()
    mock_item.id = "ITEM-001"
    mock_item.name = "鸡腿"
    mock_item.status = InventoryStatus.OUT_OF_STOCK
    mock_item.current_quantity = 0.0
    mock_item.min_quantity = 50.0
    mock_item.unit_cost = 1500   # 15元/kg
    mock_item.unit = "kg"

    inv_result = MagicMock()
    inv_result.scalars.return_value.all.return_value = [mock_item]
    db.execute = AsyncMock(return_value=inv_result)

    with patch(
        "src.services.decision_priority_engine.FoodCostService.get_store_food_cost_variance",
        new_callable=AsyncMock,
        return_value={"variance_status": "ok", "variance_pct": 0.5, "actual_cost_pct": 31.0,
                      "revenue_yuan": 0.0, "top_ingredients": []},
    ):
        result = await engine.get_top3(db=db, target_date=date(2026, 3, 4))

    assert len(result) >= 1
    assert result[0]["source"] == "inventory"
    assert result[0]["expected_saving_yuan"] > 0


@pytest.mark.asyncio
async def test_get_top3_top3_limit():
    """即使有多个候选，最多只返回3条"""
    from src.models.inventory import InventoryStatus

    engine = DecisionPriorityEngine(store_id="S001")
    db = AsyncMock()

    # 返回5个库存告警
    mock_items = []
    for i in range(5):
        item = MagicMock()
        item.id = f"ITEM-{i:03d}"
        item.name = f"食材{i}"
        item.status = InventoryStatus.CRITICAL
        item.current_quantity = 5.0
        item.min_quantity = 50.0
        item.unit_cost = 1000
        item.unit = "kg"
        mock_items.append(item)

    inv_result = MagicMock()
    inv_result.scalars.return_value.all.return_value = mock_items
    db.execute = AsyncMock(return_value=inv_result)

    with patch(
        "src.services.decision_priority_engine.FoodCostService.get_store_food_cost_variance",
        new_callable=AsyncMock,
        return_value={"variance_status": "ok", "variance_pct": 0.0, "actual_cost_pct": 28.0,
                      "revenue_yuan": 0.0, "top_ingredients": []},
    ):
        result = await engine.get_top3(db=db, target_date=date(2026, 3, 4))

    assert len(result) <= 3


@pytest.mark.asyncio
async def test_get_top3_food_cost_critical():
    """食材成本差异为 critical 时触发相应决策"""
    engine = DecisionPriorityEngine(store_id="S001")
    db = AsyncMock()

    inv_result = MagicMock()
    inv_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=inv_result)

    with patch(
        "src.services.decision_priority_engine.FoodCostService.get_store_food_cost_variance",
        new_callable=AsyncMock,
        return_value={
            "variance_status": "critical",
            "variance_pct": 6.5,
            "actual_cost_pct": 40.0,
            "theoretical_pct": 33.5,
            "revenue_yuan": 7000.0,
            "top_ingredients": [
                {"item_id": "I1", "name": "羊肉", "usage_cost_fen": 80000, "usage_cost_yuan": 800.0},
            ],
        },
    ):
        result = await engine.get_top3(
            db=db,
            target_date=date(2026, 3, 4),
            monthly_revenue_yuan=30_000,
        )

    assert len(result) >= 1
    food_cost_decisions = [r for r in result if r["source"] == "food_cost"]
    assert len(food_cost_decisions) >= 1
    assert food_cost_decisions[0]["expected_saving_yuan"] > 0
