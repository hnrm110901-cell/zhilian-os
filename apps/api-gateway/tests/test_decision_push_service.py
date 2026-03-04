"""
DecisionPushService 单元测试

覆盖：
  - _format_card_description：Top3 卡片描述格式化
  - _format_anomaly_description：午推异常描述
  - _format_prebattle_description：战前推备战描述
  - _format_evening_description：晚推回顾描述
  - push_morning_decisions：晨推逻辑（mock engine + wechat）
  - push_noon_anomaly：午推仅在有异常时推送
  - push_prebattle_decisions：战前推仅在有库存决策时推送
  - push_evening_recap：晚推待批数+决策结合
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.decision_push_service import (
    DecisionPushService,
    _format_card_description,
    _format_anomaly_description,
    _format_prebattle_description,
    _format_evening_description,
)


# ── 测试数据 ──────────────────────────────────────────────────────────────────

def _make_decision(
    rank=1,
    title="测试决策",
    action="执行行动",
    source="inventory",
    saving=1000.0,
    confidence_pct=85.0,
    urgency_hours=2.0,
    difficulty="easy",
):
    return {
        "rank": rank,
        "title": title,
        "action": action,
        "source": source,
        "expected_saving_yuan": saving,
        "expected_cost_yuan": 100.0,
        "net_benefit_yuan": saving - 100.0,
        "confidence_pct": confidence_pct,
        "urgency_hours": urgency_hours,
        "execution_difficulty": difficulty,
        "decision_window_label": "08:00晨推",
        "priority_score": 75.0,
        "context": {},
    }


# ── 纯函数测试 ─────────────────────────────────────────────────────────────────

class TestFormatCardDescription:
    def test_empty_returns_no_decision_text(self):
        result = _format_card_description([])
        assert "无高优先级决策" in result

    def test_single_decision_formatted(self):
        d = _make_decision(title="紧急补货：鸡腿", saving=500.0, confidence_pct=92.0)
        result = _format_card_description([d])
        assert "鸡腿" in result
        assert "¥500" in result
        assert "92%" in result

    def test_max_three_decisions(self):
        decs = [_make_decision(rank=i) for i in range(1, 6)]  # 5 个
        result = _format_card_description(decs)
        # 第4、5个不应出现
        assert result.count("测试决策") == 3

    def test_description_within_512_chars(self):
        decs = [_make_decision(title="A" * 80, action="B" * 80) for _ in range(3)]
        result = _format_card_description(decs)
        assert len(result) <= 512


class TestFormatAnomalyDescription:
    def test_no_waste_no_decisions_returns_normal(self):
        result = _format_anomaly_description(None, [])
        assert "无重大异常" in result

    def test_critical_waste_rate_shows_emoji(self):
        waste = {
            "waste_rate_pct": 7.2,
            "waste_rate_status": "critical",
            "total_waste_yuan": 3500.0,
            "top5": [{"item_name": "羊肉", "waste_cost_yuan": 1200.0, "action": "减少备量"}],
        }
        result = _format_anomaly_description(waste, [])
        assert "🔴" in result
        assert "7.2%" in result
        assert "羊肉" in result

    def test_warning_waste_shows_warning_emoji(self):
        waste = {
            "waste_rate_pct": 4.1,
            "waste_rate_status": "warning",
            "total_waste_yuan": 800.0,
            "top5": [],
        }
        result = _format_anomaly_description(waste, [])
        assert "⚠️" in result

    def test_ok_waste_suppressed(self):
        waste = {
            "waste_rate_pct": 1.5,
            "waste_rate_status": "ok",
            "total_waste_yuan": 200.0,
            "top5": [],
        }
        result = _format_anomaly_description(waste, [])
        # ok 状态不应出现损耗率行
        assert "1.5%" not in result


class TestFormatPrebattleDescription:
    def test_inventory_decision_highlighted(self):
        decs = [_make_decision(source="inventory", title="紧急补货：鸡腿")]
        result = _format_prebattle_description(decs, "北京店")
        assert "库存" in result
        assert "鸡腿" in result

    def test_no_decisions_shows_normal(self):
        result = _format_prebattle_description([], "广州店")
        assert "正常" in result

    def test_store_name_in_header(self):
        result = _format_prebattle_description([], "上海旗舰店")
        assert "上海旗舰店" in result


class TestFormatEveningDescription:
    def test_pending_approvals_shown(self):
        result = _format_evening_description([], pending_count=3)
        assert "3" in result
        assert "待审批" in result

    def test_total_saving_summed(self):
        decs = [_make_decision(saving=300.0), _make_decision(saving=700.0)]
        result = _format_evening_description(decs, pending_count=0)
        assert "¥1000" in result

    def test_nothing_pending_shows_ok(self):
        result = _format_evening_description([], pending_count=0)
        assert "正常" in result


# ── push_morning_decisions ───────────────────────────────────────────────────

class TestPushMorningDecisions:
    @pytest.mark.asyncio
    async def test_sends_card_when_decisions_exist(self):
        db  = AsyncMock()
        decisions = [_make_decision(rank=1, saving=2000.0)]

        with (
            patch(
                "src.services.decision_push_service.DecisionPriorityEngine",
                autospec=True,
            ) as MockEngine,
            patch(
                "src.services.decision_push_service.wechat_service",
            ) as mock_ws,
        ):
            instance = MockEngine.return_value
            instance.get_top3 = AsyncMock(return_value=decisions)
            mock_ws.send_decision_card = AsyncMock(
                return_value={"status": "sent", "message_id": "abc123"}
            )

            result = await DecisionPushService.push_morning_decisions(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is True
        assert result["decision_count"] == 1
        mock_ws.send_decision_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_send_when_no_decisions(self):
        db = AsyncMock()

        with (
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])
            result = await DecisionPushService.push_morning_decisions(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is False
        mock_ws.send_decision_card.assert_not_called()


# ── push_noon_anomaly ─────────────────────────────────────────────────────────

class TestPushNoonAnomaly:
    @pytest.mark.asyncio
    async def test_sends_when_waste_critical(self):
        db = AsyncMock()
        critical_waste = {
            "waste_rate_pct": 6.5, "waste_rate_status": "critical",
            "total_waste_yuan": 4000.0, "top5": [],
        }

        with (
            patch("src.services.decision_push_service.WasteGuardService") as MockWaste,
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockWaste.get_waste_rate_summary = AsyncMock(return_value=critical_waste)
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])
            mock_ws.send_decision_card = AsyncMock(
                return_value={"status": "sent", "message_id": "xyz"}
            )

            result = await DecisionPushService.push_noon_anomaly(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_no_send_when_all_ok(self):
        db = AsyncMock()
        ok_waste = {
            "waste_rate_pct": 1.0, "waste_rate_status": "ok",
            "total_waste_yuan": 100.0, "top5": [],
        }

        with (
            patch("src.services.decision_push_service.WasteGuardService") as MockWaste,
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockWaste.get_waste_rate_summary = AsyncMock(return_value=ok_waste)
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])

            result = await DecisionPushService.push_noon_anomaly(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is False
        mock_ws.send_decision_card.assert_not_called()


# ── push_prebattle_decisions ──────────────────────────────────────────────────

class TestPushPrebattleDecisions:
    @pytest.mark.asyncio
    async def test_sends_when_inventory_decision_exists(self):
        db  = AsyncMock()
        decisions = [_make_decision(source="inventory", urgency_hours=1.0)]

        with (
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=decisions)
            mock_ws.send_decision_card = AsyncMock(
                return_value={"status": "sent", "message_id": "pre1"}
            )

            result = await DecisionPushService.push_prebattle_decisions(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_no_send_when_only_low_urgency_food_cost(self):
        """仅有 food_cost 且 urgency_hours>4 时，战前推不发送。"""
        db  = AsyncMock()
        decisions = [_make_decision(source="food_cost", urgency_hours=10.0)]

        with (
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=decisions)

            result = await DecisionPushService.push_prebattle_decisions(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is False


# ── push_evening_recap ────────────────────────────────────────────────────────

class TestPushEveningRecap:
    @pytest.mark.asyncio
    async def test_sends_when_pending_approvals_exist(self):
        db  = AsyncMock()

        with (
            patch("src.services.decision_push_service._count_pending_approvals",
                  new_callable=AsyncMock, return_value=2),
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])
            mock_ws.send_decision_card = AsyncMock(
                return_value={"status": "sent", "message_id": "eve1"}
            )

            result = await DecisionPushService.push_evening_recap(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is True
        assert result["pending_approvals"] == 2

    @pytest.mark.asyncio
    async def test_no_send_when_nothing_pending_and_no_decisions(self):
        db = AsyncMock()

        with (
            patch("src.services.decision_push_service._count_pending_approvals",
                  new_callable=AsyncMock, return_value=0),
            patch("src.services.decision_push_service.DecisionPriorityEngine",
                  autospec=True) as MockEngine,
            patch("src.services.decision_push_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])

            result = await DecisionPushService.push_evening_recap(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss", db=db,
            )

        assert result["sent"] is False
        mock_ws.send_decision_card.assert_not_called()
