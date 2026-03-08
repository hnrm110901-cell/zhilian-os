"""
LaborDemandService 单元测试
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.labor_demand_service import (
    LaborDemandService,
    _build_result,
    _dict_to_json_str,
    _period_hours,
    _pg_dow,
    _weekday_cn,
    apply_micro_event_adjustment,
    compute_momentum_factor,
    compute_position_requirements,
    compute_volatility_penalty,
    get_holiday_weight,
)


class TestPureFunctions:
    def test_compute_position_requirements_minimum_floor(self):
        result = compute_position_requirements(1, "lunch")
        assert result["waiter"] >= 2
        assert result["chef"] >= 1
        assert result["cashier"] >= 1
        assert result["manager"] == 1

    def test_compute_position_requirements_manager_threshold(self):
        low = compute_position_requirements(80, "dinner")
        high = compute_position_requirements(81, "dinner")
        assert low["manager"] == 1
        assert high["manager"] == 2

    def test_compute_position_requirements_unknown_period_fallback_to_lunch(self):
        result = compute_position_requirements(54, "late_night")
        # lunch waiter ratio=18, min=2 -> ceil(54/18)=3
        assert result["waiter"] == 3

    def test_get_holiday_weight_known_holiday(self):
        weight, label = get_holiday_weight(date(2026, 1, 1))
        assert weight == 1.20
        assert "元旦" in label

    def test_get_holiday_weight_weekend_non_holiday(self):
        # 2026-03-07 是周六
        weight, label = get_holiday_weight(date(2026, 3, 7))
        assert weight == 1.10
        assert label == "周末"

    def test_get_holiday_weight_weekday_non_holiday(self):
        # 2026-03-09 是周一
        weight, label = get_holiday_weight(date(2026, 3, 9))
        assert weight == 1.00
        assert label == "工作日"

    def test_period_hours_mapping(self):
        assert _period_hours("morning") == (6, 11)
        assert _period_hours("lunch") == (11, 15)
        assert _period_hours("dinner") == (17, 22)
        assert _period_hours("all_day") == (6, 23)

    def test_period_hours_default(self):
        assert _period_hours("unknown") == (6, 23)

    def test_pg_dow_conversion(self):
        assert _pg_dow(0) == 1  # Mon -> 1
        assert _pg_dow(6) == 0  # Sun -> 0

    def test_weekday_cn(self):
        assert _weekday_cn(0) == "周一"
        assert _weekday_cn(6) == "周日"

    def test_dict_to_json_str_with_chinese(self):
        s = _dict_to_json_str({"门店": "上海店"})
        assert "上海店" in s

    def test_build_result_has_expected_fields(self):
        result = _build_result(
            store_id="S001",
            forecast_date=date(2026, 3, 9),
            meal_period="lunch",
            predicted_customers=88,
            confidence=0.7233,
            weather_score=1.02,
            holiday_weight=1.10,
            hist_avg=80,
            reason_1="r1",
            reason_2="r2",
            reason_3="r3",
            basis="statistical",
            model_version="v1.0-stat",
        )
        assert result["store_id"] == "S001"
        assert result["forecast_date"] == "2026-03-09"
        assert result["meal_period"] == "lunch"
        assert result["confidence_score"] == 0.723
        assert result["basis"] == "statistical"
        assert result["total_headcount_needed"] == sum(result["position_requirements"].values())

    def test_compute_momentum_factor_normal(self):
        factor = compute_momentum_factor([110, 120, 100], [100, 100, 100])
        assert factor == 1.1

    def test_compute_momentum_factor_clamped(self):
        factor_high = compute_momentum_factor([300, 300, 300], [100, 100, 100])
        factor_low = compute_momentum_factor([10, 10, 10], [100, 100, 100])
        assert factor_high == 1.15
        assert factor_low == 0.85

    def test_compute_momentum_factor_empty(self):
        assert compute_momentum_factor([], [1, 2, 3]) == 1.0

    def test_compute_volatility_penalty(self):
        low_vol = compute_volatility_penalty([100, 101, 99, 100, 100])
        high_vol = compute_volatility_penalty([20, 200, 30, 180, 25, 170])
        assert low_vol >= high_vol
        assert 0.9 <= high_vol <= 1.0

    def test_apply_micro_event_adjustment(self):
        adjusted = apply_micro_event_adjustment(100, 1.1, 0.95)
        assert adjusted == pytest.approx(104.5)


class TestServiceRouting:
    @pytest.mark.asyncio
    async def test_forecast_invalid_meal_period_raises(self):
        with pytest.raises(ValueError):
            await LaborDemandService.forecast(
                store_id="S001",
                forecast_date=date(2026, 3, 9),
                meal_period="invalid",
                db=None,
            )

    @pytest.mark.asyncio
    async def test_forecast_route_rule_based_and_upsert(self):
        mock_result = {"basis": "rule_based", "predicted_customer_count": 10, "total_headcount_needed": 3, "confidence_score": 0.4}
        db = AsyncMock()
        with (
            patch.object(LaborDemandService, "_get_history_days", new_callable=AsyncMock, return_value=3),
            patch.object(LaborDemandService, "_rule_based", new_callable=AsyncMock, return_value=mock_result),
            patch.object(LaborDemandService, "_upsert_forecast", new_callable=AsyncMock) as mock_upsert,
        ):
            result = await LaborDemandService.forecast(
                store_id="S001",
                forecast_date=date(2026, 3, 9),
                meal_period="lunch",
                db=db,
                save=True,
            )
        assert result["basis"] == "rule_based"
        mock_upsert.assert_awaited_once_with(mock_result, db)

    @pytest.mark.asyncio
    async def test_forecast_route_statistical(self):
        with (
            patch.object(LaborDemandService, "_get_history_days", new_callable=AsyncMock, return_value=20),
            patch.object(LaborDemandService, "_statistical", new_callable=AsyncMock, return_value={"basis": "statistical", "predicted_customer_count": 11, "total_headcount_needed": 4, "confidence_score": 0.65}),
        ):
            result = await LaborDemandService.forecast(
                store_id="S001",
                forecast_date=date(2026, 3, 9),
                meal_period="dinner",
                db=AsyncMock(),
                save=False,
            )
        assert result["basis"] == "statistical"

    @pytest.mark.asyncio
    async def test_forecast_route_weighted(self):
        with (
            patch.object(LaborDemandService, "_get_history_days", new_callable=AsyncMock, return_value=80),
            patch.object(LaborDemandService, "_weighted_historical", new_callable=AsyncMock, return_value={"basis": "weighted", "predicted_customer_count": 12, "total_headcount_needed": 5, "confidence_score": 0.82}),
        ):
            result = await LaborDemandService.forecast(
                store_id="S001",
                forecast_date=date(2026, 3, 9),
                meal_period="morning",
                db=AsyncMock(),
                save=False,
            )
        assert result["basis"] == "weighted"

    @pytest.mark.asyncio
    async def test_forecast_all_periods_aggregate(self):
        side = [
            {"total_headcount_needed": 5},
            {"total_headcount_needed": 8},
            {"total_headcount_needed": 7},
        ]
        with patch.object(LaborDemandService, "forecast", new_callable=AsyncMock, side_effect=side):
            result = await LaborDemandService.forecast_all_periods(
                store_id="S001",
                forecast_date=date(2026, 3, 9),
                db=AsyncMock(),
                save=True,
                weather_score=1.0,
            )
        assert result["daily_peak_headcount"] == 8
        assert result["daily_total_headcount_slots"] == 20
        assert set(result["periods"].keys()) == {"morning", "lunch", "dinner"}


class TestInternalDbPaths:
    @pytest.mark.asyncio
    async def test_get_history_days_with_none_db(self):
        days = await LaborDemandService._get_history_days("S001", None)
        assert days == 0

    @pytest.mark.asyncio
    async def test_get_history_days_db_exception_returns_zero(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        days = await LaborDemandService._get_history_days("S001", db)
        assert days == 0

    @pytest.mark.asyncio
    async def test_get_history_days_success(self):
        db = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 42
        db.execute = AsyncMock(return_value=scalar_result)
        days = await LaborDemandService._get_history_days("S001", db)
        assert days == 42

    @pytest.mark.asyncio
    async def test_upsert_forecast_commits(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=None)
        db.commit = AsyncMock()
        payload = _build_result(
            store_id="S001",
            forecast_date=date(2026, 3, 9),
            meal_period="lunch",
            predicted_customers=50,
            confidence=0.7,
            weather_score=1.0,
            holiday_weight=1.0,
            hist_avg=45,
            reason_1="a",
            reason_2="b",
            reason_3="c",
            basis="statistical",
            model_version="v1.0-stat",
        )
        await LaborDemandService._upsert_forecast(payload, db)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_forecast_rollback_and_raise(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("insert failed"))
        db.rollback = AsyncMock()
        payload = _build_result(
            store_id="S001",
            forecast_date=date(2026, 3, 9),
            meal_period="lunch",
            predicted_customers=50,
            confidence=0.7,
            weather_score=1.0,
            holiday_weight=1.0,
            hist_avg=45,
            reason_1="a",
            reason_2="b",
            reason_3="c",
            basis="statistical",
            model_version="v1.0-stat",
        )
        with pytest.raises(RuntimeError, match="insert failed"):
            await LaborDemandService._upsert_forecast(payload, db)
        db.rollback.assert_awaited_once()
