"""
WorkforcePushService 单元测试
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.workforce_push_service import WorkforcePushService


def _make_forecast(daily_peak_headcount: int = 10):
    return {
        "daily_peak_headcount": daily_peak_headcount,
        "periods": {
            "morning": {
                "predicted_customer_count": 80,
                "total_headcount_needed": 8,
                "position_requirements": {"waiter": 4, "chef": 2, "cashier": 1, "manager": 1},
                "reason_1": "早高峰客流提升",
                "confidence_score": 0.7,
            },
            "lunch": {
                "predicted_customer_count": 120,
                "total_headcount_needed": 10,
                "position_requirements": {"waiter": 5, "chef": 3, "cashier": 1, "manager": 1},
                "reason_2": "午市历史同类日较高",
                "confidence_score": 0.8,
            },
            "dinner": {
                "predicted_customer_count": 100,
                "total_headcount_needed": 9,
                "position_requirements": {"waiter": 5, "chef": 2, "cashier": 1, "manager": 1},
                "reason_3": "晚市节假日权重提升",
                "confidence_score": 0.9,
            },
        },
    }


def _mock_result(row):
    result = MagicMock()
    result.fetchone.return_value = row
    return result


class TestFormatStaffingRecommendation:
    def test_contains_core_fields(self):
        result = WorkforcePushService._format_staffing_recommendation(
            store_name="上海店",
            target_date=date(2026, 3, 9),
            forecast=_make_forecast(10),
            recommended_headcount=10,
            current_headcount=8,
            estimated_saving_yuan=400.0,
        )
        assert "上海店" in result
        assert "明日客流预测：300 人" in result
        assert "建议排班：10 人" in result
        assert "差值 +2" in result
        assert "预计节省：¥400" in result

    def test_omits_delta_when_current_missing(self):
        result = WorkforcePushService._format_staffing_recommendation(
            store_name="北京店",
            target_date=date(2026, 3, 9),
            forecast=_make_forecast(10),
            recommended_headcount=10,
            current_headcount=None,
            estimated_saving_yuan=0.0,
        )
        assert "当前已排" not in result

    def test_truncates_to_510_chars(self):
        fc = _make_forecast(10)
        fc["periods"]["morning"]["reason_1"] = "A" * 500
        fc["periods"]["lunch"]["reason_2"] = "B" * 500
        fc["periods"]["dinner"]["reason_3"] = "C" * 500
        result = WorkforcePushService._format_staffing_recommendation(
            store_name="深圳店",
            target_date=date(2026, 3, 9),
            forecast=fc,
            recommended_headcount=10,
            current_headcount=8,
            estimated_saving_yuan=100.0,
        )
        assert len(result) <= 510


class TestPushDailyStaffingAdvice:
    @pytest.mark.asyncio
    async def test_calls_forecast_with_expected_args(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
            ]
        )
        target_date = date(2026, 3, 9)
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=_make_forecast(8),
            ) as mock_forecast,
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "mx"},
            ),
        ):
            await WorkforcePushService.push_daily_staffing_advice(
                store_id="S000",
                db=db,
                target_date=target_date,
            )

        mock_forecast.assert_awaited_once()
        kwargs = mock_forecast.await_args.kwargs
        assert kwargs["store_id"] == "S000"
        assert kwargs["forecast_date"] == target_date
        assert kwargs["save"] is True
        assert kwargs["weather_score"] == 1.0

    @pytest.mark.asyncio
    async def test_insert_branch_with_default_recipient(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(None),  # schedules
                _mock_result(None),  # existing staffing_advice
                _mock_result(None),  # insert staffing_advice
                _mock_result(None),  # update push_sent_at
            ]
        )
        mock_card = {"status": "sent", "message_id": "m1"}
        target_date = date(2026, 3, 9)

        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=_make_forecast(10),
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value=mock_card,
            ) as mock_send,
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S001",
                db=db,
                store_name="上海店",
                target_date=target_date,
            )

        assert result["store_id"] == "S001"
        assert result["advice_date"] == "2026-03-09"
        assert result["message_status"] == "sent"
        assert result["current_headcount"] is None
        assert result["estimated_saving_yuan"] == 0.0
        assert db.execute.await_count == 4
        assert mock_send.await_args.kwargs["to_user_id"] == "store_S001"

    @pytest.mark.asyncio
    async def test_update_branch_with_custom_recipient_and_overspend(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(MagicMock(total_employees="6")),       # schedules
                _mock_result(MagicMock(id="advice-1")),             # existing staffing_advice
                _mock_result(None),                                  # update existing
                _mock_result(None),                                  # update push_sent_at
            ]
        )
        target_date = date(2026, 3, 9)
        forecast = _make_forecast(10)

        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=forecast,
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "m2"},
            ) as mock_send,
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S002",
                db=db,
                store_name="广州店",
                recipient_user_id="manager_002",
                target_date=target_date,
            )

        assert result["current_headcount"] == 6
        assert result["recommended_headcount"] == 10
        assert result["estimated_saving_yuan"] == 0.0
        assert mock_send.await_args.kwargs["to_user_id"] == "manager_002"

    @pytest.mark.asyncio
    async def test_saving_computation_when_recommended_lower_than_current(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(MagicMock(total_employees="12")),
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
            ]
        )
        target_date = date(2026, 3, 9)

        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=_make_forecast(10),
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "m3"},
            ),
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S003",
                db=db,
                target_date=target_date,
            )

        # delta = 10 - 12 = -2 -> saving = 400 (默认 200/人天)
        assert result["estimated_saving_yuan"] == 400.0

    @pytest.mark.asyncio
    async def test_non_integer_total_employees_falls_back_to_none(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(MagicMock(total_employees="N/A")),
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
            ]
        )

        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=_make_forecast(9),
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "m4"},
            ),
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S004",
                db=db,
                target_date=date(2026, 3, 9),
            )

        assert result["current_headcount"] is None

    @pytest.mark.asyncio
    async def test_action_url_contains_store_and_date(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
            ]
        )
        target_date = date(2026, 3, 9)
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=_make_forecast(8),
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "m5"},
            ) as mock_send,
        ):
            await WorkforcePushService.push_daily_staffing_advice(
                store_id="S005",
                db=db,
                target_date=target_date,
            )
        action_url = mock_send.await_args.kwargs["action_url"]
        assert "store_id=S005" in action_url
        assert "date=2026-03-09" in action_url

    @pytest.mark.asyncio
    async def test_respects_custom_avg_wage_env_for_saving(self, monkeypatch):
        monkeypatch.setenv("L8_AVG_WAGE_PER_DAY", "300")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_result(MagicMock(total_employees="12")),
                _mock_result(None),
                _mock_result(None),
                _mock_result(None),
            ]
        )
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=_make_forecast(10),
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "m6"},
            ),
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S006",
                db=db,
                target_date=date(2026, 3, 9),
            )
        assert result["estimated_saving_yuan"] == 600.0
