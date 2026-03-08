"""
Workforce 人力链路集成测试（mock DB + service）

覆盖：
1) 客流预测 -> 排班建议 -> 企微推送链路
2) 店长确认闭环
3) 预算读取/写入接口行为
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("WECHAT_CORP_ID", "test_corp")
os.environ.setdefault("WECHAT_CORP_SECRET", "test_secret")
os.environ.setdefault("WECHAT_AGENT_ID", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-workforce-pipeline-32!!")

from src.api.workforce import (  # noqa: E402
    LaborBudgetUpsertRequest,
    StaffingAdviceConfirmRequest,
    _parse_iso_date,
    _parse_yyyymm,
    confirm_staffing_advice,
    get_labor_budget,
    upsert_labor_budget,
)
from src.services.workforce_push_service import WorkforcePushService  # noqa: E402


def _result_with_row(row):
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _mock_user(user_id: str = "u001"):
    user = MagicMock()
    user.id = user_id
    return user


class TestWorkforcePushPipeline:
    @pytest.mark.asyncio
    async def test_forecast_to_push_insert_path(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _result_with_row(None),  # schedules
                _result_with_row(None),  # existing advice
                _result_with_row(None),  # insert
                _result_with_row(None),  # update push_sent_at
            ]
        )
        forecast = {
            "daily_peak_headcount": 9,
            "periods": {
                "morning": {
                    "predicted_customer_count": 60,
                    "total_headcount_needed": 7,
                    "position_requirements": {"waiter": 3},
                    "reason_1": "早高峰上升",
                    "confidence_score": 0.7,
                },
                "lunch": {
                    "predicted_customer_count": 100,
                    "total_headcount_needed": 9,
                    "position_requirements": {"waiter": 4},
                    "reason_2": "午市历史均值高",
                    "confidence_score": 0.8,
                },
                "dinner": {
                    "predicted_customer_count": 90,
                    "total_headcount_needed": 8,
                    "position_requirements": {"waiter": 4},
                    "reason_3": "晚市节假日系数提升",
                    "confidence_score": 0.9,
                },
            },
        }
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value=forecast,
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "wf_1"},
            ),
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S001",
                db=db,
            )

        assert result["store_id"] == "S001"
        assert result["recommended_headcount"] == 9
        assert result["message_status"] == "sent"

    @pytest.mark.asyncio
    async def test_forecast_to_push_update_path(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _result_with_row(MagicMock(total_employees="12")),  # schedules
                _result_with_row(MagicMock(id="a1")),               # existing advice
                _result_with_row(None),                              # update
                _result_with_row(None),                              # update push_sent_at
            ]
        )
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value={
                    "daily_peak_headcount": 10,
                    "periods": {"morning": {}, "lunch": {}, "dinner": {}},
                },
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "wf_2"},
            ),
        ):
            result = await WorkforcePushService.push_daily_staffing_advice(
                store_id="S002",
                db=db,
                recipient_user_id="mgr_002",
            )
        assert result["recommended_headcount"] == 10
        assert result["current_headcount"] == 12
        assert result["estimated_saving_yuan"] == 400.0

    @pytest.mark.asyncio
    async def test_forecast_failure_breaks_pipeline(self):
        db = AsyncMock()
        with patch(
            "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
            new_callable=AsyncMock,
            side_effect=RuntimeError("forecast failed"),
        ):
            with pytest.raises(RuntimeError, match="forecast failed"):
                await WorkforcePushService.push_daily_staffing_advice(
                    store_id="S003",
                    db=db,
                )

    @pytest.mark.asyncio
    async def test_wechat_failure_breaks_pipeline_before_push_sent_update(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _result_with_row(None),
                _result_with_row(None),
                _result_with_row(None),
            ]
        )
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value={"daily_peak_headcount": 8, "periods": {"morning": {}, "lunch": {}, "dinner": {}}},
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                side_effect=RuntimeError("wechat down"),
            ),
        ):
            with pytest.raises(RuntimeError, match="wechat down"):
                await WorkforcePushService.push_daily_staffing_advice(
                    store_id="S004",
                    db=db,
                )
        assert db.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_default_recipient_is_store_prefixed(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _result_with_row(None),
                _result_with_row(None),
                _result_with_row(None),
                _result_with_row(None),
            ]
        )
        with (
            patch(
                "src.services.workforce_push_service.LaborDemandService.forecast_all_periods",
                new_callable=AsyncMock,
                return_value={"daily_peak_headcount": 7, "periods": {"morning": {}, "lunch": {}, "dinner": {}}},
            ),
            patch(
                "src.services.workforce_push_service.wechat_service.send_decision_card",
                new_callable=AsyncMock,
                return_value={"status": "sent", "message_id": "wf_3"},
            ) as mock_send,
        ):
            await WorkforcePushService.push_daily_staffing_advice(store_id="S005", db=db)

        assert mock_send.await_args.kwargs["to_user_id"] == "store_S005"


class TestWorkforceConfirmLoop:
    @pytest.mark.asyncio
    async def test_confirm_staffing_advice_confirmed_happy_path(self):
        db = AsyncMock()
        advice_row = MagicMock()
        advice_row.id = "advice-001"
        advice_row.created_at = datetime.utcnow() - timedelta(minutes=15)
        db.execute = AsyncMock(
            side_effect=[
                _result_with_row(advice_row),  # select advice
                _result_with_row(None),        # update advice
                _result_with_row(None),        # insert confirmation
            ]
        )
        db.commit = AsyncMock()
        body = StaffingAdviceConfirmRequest(
            advice_date="2026-03-09",
            meal_period="all_day",
            action="confirmed",
        )
        resp = await confirm_staffing_advice(
            store_id="S001",
            body=body,
            db=db,
            user=_mock_user("manager-1"),
        )
        assert resp["ok"] is True
        assert resp["status"] == "confirmed"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_staffing_advice_modified_requires_count(self):
        db = AsyncMock()
        body = StaffingAdviceConfirmRequest(
            advice_date="2026-03-09",
            meal_period="all_day",
            action="modified",
            modified_headcount=None,
        )
        with pytest.raises(HTTPException) as exc:
            await confirm_staffing_advice(
                store_id="S001",
                body=body,
                db=db,
                user=_mock_user(),
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_staffing_advice_invalid_meal_period(self):
        db = AsyncMock()
        body = StaffingAdviceConfirmRequest(
            advice_date="2026-03-09",
            meal_period="invalid",
            action="confirmed",
        )
        with pytest.raises(HTTPException) as exc:
            await confirm_staffing_advice(
                store_id="S001",
                body=body,
                db=db,
                user=_mock_user(),
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_staffing_advice_invalid_action(self):
        db = AsyncMock()
        body = StaffingAdviceConfirmRequest(
            advice_date="2026-03-09",
            meal_period="all_day",
            action="noop",
        )
        with pytest.raises(HTTPException) as exc:
            await confirm_staffing_advice(
                store_id="S001",
                body=body,
                db=db,
                user=_mock_user(),
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_staffing_advice_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with_row(None))
        body = StaffingAdviceConfirmRequest(
            advice_date="2026-03-09",
            meal_period="all_day",
            action="confirmed",
        )
        with pytest.raises(HTTPException) as exc:
            await confirm_staffing_advice(
                store_id="S001",
                body=body,
                db=db,
                user=_mock_user(),
            )
        assert exc.value.status_code == 404


class TestLaborBudgetApi:
    @pytest.mark.asyncio
    async def test_get_labor_budget_when_missing(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with_row(None))
        resp = await get_labor_budget(store_id="S001", month="2026-03", db=db, _=_mock_user())
        assert resp["exists"] is False
        assert resp["budget_period"] == "2026-03"

    @pytest.mark.asyncio
    async def test_get_labor_budget_when_exists(self):
        db = AsyncMock()
        row = MagicMock()
        row.store_id = "S001"
        row.budget_period = "2026-03"
        row.budget_type = "monthly"
        row.target_labor_cost_rate = 25.5
        row.max_labor_cost_yuan = 80000
        row.daily_budget_yuan = 2800
        row.alert_threshold_pct = 90
        row.approved_by = "manager-1"
        row.is_active = True
        db.execute = AsyncMock(return_value=_result_with_row(row))
        resp = await get_labor_budget(store_id="S001", month="2026-03", db=db, _=_mock_user())
        assert resp["exists"] is True
        assert resp["target_labor_cost_rate"] == 25.5
        assert resp["max_labor_cost_yuan"] == 80000.0

    @pytest.mark.asyncio
    async def test_get_labor_budget_invalid_month(self):
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await get_labor_budget(store_id="S001", month="2026-13", db=db, _=_mock_user())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upsert_labor_budget_commits(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with_row(None))
        db.commit = AsyncMock()
        body = LaborBudgetUpsertRequest(
            month="2026-03",
            target_labor_cost_rate=26.0,
            max_labor_cost_yuan=90000,
            daily_budget_yuan=3000,
            alert_threshold_pct=92,
            is_active=True,
        )
        resp = await upsert_labor_budget(
            store_id="S001",
            body=body,
            db=db,
            user=_mock_user("manager-2"),
        )
        assert resp["ok"] is True
        db.commit.assert_awaited_once()


class TestWorkforceValidationHelpers:
    def test_parse_iso_date_ok(self):
        d = _parse_iso_date("2026-03-09", "date")
        assert str(d) == "2026-03-09"

    def test_parse_iso_date_invalid(self):
        with pytest.raises(HTTPException) as exc:
            _parse_iso_date("2026/03/09", "date")
        assert exc.value.status_code == 400

    def test_parse_yyyymm_ok(self):
        y, m = _parse_yyyymm("2026-03")
        assert y == 2026 and m == 3

    def test_parse_yyyymm_invalid(self):
        with pytest.raises(HTTPException) as exc:
            _parse_yyyymm("2026-00")
        assert exc.value.status_code == 400

