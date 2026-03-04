"""
DecisionHub API 单元测试

覆盖：
  - get_top3_decisions：Top3 决策查询（mock DecisionPriorityEngine）
  - trigger_decision_push：推送触发（mock DecisionPushService）
  - list_pending_decisions：待审批列表（mock DB）
  - get_store_scenario：场景识别（mock ScenarioMatcher）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime

from src.api.decision_hub import (
    get_top3_decisions,
    trigger_decision_push,
    list_pending_decisions,
    get_store_scenario,
    TriggerPushRequest,
)


# ── 共用 fixture ──────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id = "user-001"
    return u


def _make_decision(rank=1, saving=5000.0):
    return {
        "rank":                  rank,
        "title":                 "紧急补货鸡腿",
        "action":                "今日17:00前补货50kg",
        "source":                "inventory",
        "expected_saving_yuan":  saving,
        "expected_cost_yuan":    800.0,
        "net_benefit_yuan":      saving - 800.0,
        "confidence_pct":        85.0,
        "urgency_hours":         4.0,
        "execution_difficulty":  "low",
        "decision_window_label": "今日",
        "priority_score":        92.5,
    }


# ── get_top3_decisions ────────────────────────────────────────────────────────

class TestGetTop3Decisions:
    @pytest.mark.asyncio
    async def test_returns_decisions_with_correct_structure(self):
        db   = AsyncMock()
        user = _mock_user()
        decisions = [_make_decision(1, 5000.0), _make_decision(2, 3000.0)]

        with patch(
            "src.api.decision_hub.DecisionPriorityEngine",
        ) as MockEngine:
            instance = MockEngine.return_value
            instance.get_top3 = AsyncMock(return_value=decisions)

            result = await get_top3_decisions(
                store_id="S001",
                monthly_revenue_yuan=100_000.0,
                current_user=user,
                db=db,
            )

        assert result["store_id"]   == "S001"
        assert result["count"]      == 2
        assert len(result["decisions"]) == 2
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_empty_decisions_returns_count_zero(self):
        db   = AsyncMock()
        user = _mock_user()

        with patch("src.api.decision_hub.DecisionPriorityEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.get_top3 = AsyncMock(return_value=[])

            result = await get_top3_decisions(
                store_id="S002",
                monthly_revenue_yuan=0.0,
                current_user=user,
                db=db,
            )

        assert result["count"] == 0
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_engine_failure_raises_500(self):
        from fastapi import HTTPException
        db   = AsyncMock()
        user = _mock_user()

        with patch("src.api.decision_hub.DecisionPriorityEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.get_top3 = AsyncMock(side_effect=RuntimeError("DB连接超时"))

            with pytest.raises(HTTPException) as exc_info:
                await get_top3_decisions(
                    store_id="S003",
                    monthly_revenue_yuan=0.0,
                    current_user=user,
                    db=db,
                )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_engine_receives_correct_store_id(self):
        db   = AsyncMock()
        user = _mock_user()

        with patch("src.api.decision_hub.DecisionPriorityEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.get_top3 = AsyncMock(return_value=[])

            await get_top3_decisions(
                store_id="S999",
                monthly_revenue_yuan=50_000.0,
                current_user=user,
                db=db,
            )

        MockEngine.assert_called_once_with(store_id="S999")


# ── trigger_decision_push ─────────────────────────────────────────────────────

class TestTriggerDecisionPush:
    @pytest.mark.asyncio
    async def test_morning_push_type_calls_correct_method(self):
        db   = AsyncMock()
        user = _mock_user()
        req  = TriggerPushRequest(store_id="S001", push_type="morning", monthly_revenue_yuan=80_000.0)

        with patch("src.api.decision_hub.DecisionPushService") as MockPS:
            MockPS.push_morning_decisions = AsyncMock(
                return_value={"messages_sent": 1, "decisions_count": 3}
            )

            result = await trigger_decision_push(req, current_user=user, db=db)

        MockPS.push_morning_decisions.assert_awaited_once()
        assert result["success"]    is True
        assert result["push_type"]  == "morning"

    @pytest.mark.asyncio
    async def test_evening_push_type_calls_correct_method(self):
        db   = AsyncMock()
        user = _mock_user()
        req  = TriggerPushRequest(store_id="S001", push_type="evening")

        with patch("src.api.decision_hub.DecisionPushService") as MockPS:
            MockPS.push_evening_recap = AsyncMock(
                return_value={"messages_sent": 1, "decisions_count": 2}
            )

            result = await trigger_decision_push(req, current_user=user, db=db)

        MockPS.push_evening_recap.assert_awaited_once()
        assert result["push_type"] == "evening"

    @pytest.mark.asyncio
    async def test_invalid_push_type_raises_400(self):
        from fastapi import HTTPException
        db   = AsyncMock()
        user = _mock_user()
        req  = TriggerPushRequest(store_id="S001", push_type="invalid_type")

        with pytest.raises(HTTPException) as exc_info:
            await trigger_decision_push(req, current_user=user, db=db)

        assert exc_info.value.status_code == 400
        assert "push_type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_push_service_failure_raises_500(self):
        from fastapi import HTTPException
        db   = AsyncMock()
        user = _mock_user()
        req  = TriggerPushRequest(store_id="S001", push_type="noon")

        with patch("src.api.decision_hub.DecisionPushService") as MockPS:
            MockPS.push_noon_anomaly = AsyncMock(side_effect=Exception("微信API超时"))

            with pytest.raises(HTTPException) as exc_info:
                await trigger_decision_push(req, current_user=user, db=db)

        assert exc_info.value.status_code == 500


# ── list_pending_decisions ────────────────────────────────────────────────────

class TestListPendingDecisions:
    def _make_record(self, store_id="S001", saving=3000.0, confidence=0.85):
        r = MagicMock()
        r.id             = "dec-001"
        r.store_id       = store_id
        r.decision_type  = "purchase"
        r.ai_suggestion  = {"action": "补货鸡腿", "expected_saving_yuan": saving}
        r.ai_confidence  = confidence
        r.created_at     = datetime(2026, 3, 1, 8, 0, 0)
        return r

    @pytest.mark.asyncio
    async def test_returns_pending_decisions(self):
        db   = AsyncMock()
        user = _mock_user()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self._make_record("S001", 3000.0, 0.85),
            self._make_record("S002", 2000.0, 0.70),
        ]
        db.execute = AsyncMock(return_value=mock_result)

        result = await list_pending_decisions(
            store_id=None, limit=20, current_user=user, db=db
        )

        assert result["total"] == 2
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_items_contain_yuan_fields(self):
        db   = AsyncMock()
        user = _mock_user()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self._make_record("S001", 5000.0, 0.9),
        ]
        db.execute = AsyncMock(return_value=mock_result)

        result = await list_pending_decisions(
            store_id="S001", limit=20, current_user=user, db=db
        )

        item = result["items"][0]
        assert "expected_saving_yuan" in item
        assert item["expected_saving_yuan"] == 5000.0
        assert "confidence_pct" in item
        assert item["confidence_pct"] == 90.0  # 0.9 * 100

    @pytest.mark.asyncio
    async def test_empty_result_returns_zero_total(self):
        db   = AsyncMock()
        user = _mock_user()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await list_pending_decisions(
            store_id="S999", limit=10, current_user=user, db=db
        )

        assert result["total"] == 0
        assert result["items"] == []


# ── get_store_scenario ────────────────────────────────────────────────────────

class TestGetStoreScenario:
    def _scenario_info(self, scenario_type="high_cost"):
        return {
            "store_id":       "S001",
            "scenario_type":  scenario_type,
            "scenario_label": "成本超标期",
            "metrics":        {
                "cost_rate_pct": 38.5,
                "revenue_yuan":  30000.0,
            },
            "as_of": "2026-03-01",
        }

    @pytest.mark.asyncio
    async def test_returns_scenario_with_similar_cases(self):
        db   = AsyncMock()
        user = _mock_user()
        similar = [
            {"case_id": "c1", "similarity": 0.92, "outcome": "success"},
        ]

        with (
            patch(
                "src.api.decision_hub.ScenarioMatcher.identify_current_scenario",
                new=AsyncMock(return_value=self._scenario_info()),
            ),
            patch(
                "src.api.decision_hub.ScenarioMatcher.find_similar_cases",
                new=AsyncMock(return_value=similar),
            ),
        ):
            result = await get_store_scenario(
                store_id="S001", as_of=None, current_user=user, db=db
            )

        assert result["scenario_type"]  == "high_cost"
        assert result["store_id"]       == "S001"
        assert result["similar_cases"]  == similar

    @pytest.mark.asyncio
    async def test_scenario_failure_raises_500(self):
        from fastapi import HTTPException
        db   = AsyncMock()
        user = _mock_user()

        with patch(
            "src.api.decision_hub.ScenarioMatcher.identify_current_scenario",
            new=AsyncMock(side_effect=RuntimeError("DB超时")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_store_scenario(
                    store_id="S001", as_of=None, current_user=user, db=db
                )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_scenario_passes_correct_metrics_to_find_similar(self):
        db   = AsyncMock()
        user = _mock_user()
        scenario = self._scenario_info("high_waste")

        mock_find = AsyncMock(return_value=[])
        with (
            patch(
                "src.api.decision_hub.ScenarioMatcher.identify_current_scenario",
                new=AsyncMock(return_value=scenario),
            ),
            patch(
                "src.api.decision_hub.ScenarioMatcher.find_similar_cases",
                new=mock_find,
            ),
        ):
            await get_store_scenario(
                store_id="S001", as_of=date(2026, 3, 1), current_user=user, db=db
            )

        mock_find.assert_awaited_once()
        call_kwargs = mock_find.call_args.kwargs
        assert call_kwargs["scenario_type"] == "high_waste"
        assert call_kwargs["cost_rate_pct"] == 38.5
