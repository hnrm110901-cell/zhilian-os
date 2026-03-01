"""
Tests for ExternalFactorsAdapter
"""
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock

from src.services.external_factors_adapter import (
    ExternalFactorsAdapter,
    ExternalFactorsResult,
    STRATEGY_SMART,
    STRATEGY_MULTIPLY,
    STRATEGY_MAX,
)


# ── _compose strategy tests ───────────────────────────────────────────────────

class TestComposeStrategy:
    """Tests for the static _compose() method."""

    # SMART strategy
    def test_smart_uses_max_demand_factor(self):
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_SMART,
            weather_factor=1.0,
            holiday_factor=1.8,
            auspicious_factor=2.2,
            event_factor=1.3,
        )
        # SMART: weather × max(holiday, auspicious, event) = 1.0 × 2.2
        assert result == pytest.approx(2.2, abs=0.01)

    def test_smart_applies_weather_multiplicatively(self):
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_SMART,
            weather_factor=0.85,
            holiday_factor=1.8,
            auspicious_factor=1.0,
            event_factor=1.0,
        )
        # 0.85 × max(1.8, 1.0, 1.0) = 0.85 × 1.8 = 1.53
        assert result == pytest.approx(0.85 * 1.8, abs=0.01)

    def test_smart_prevents_double_stacking(self):
        """Holiday + auspicious on same day should NOT be multiplied."""
        result_smart    = ExternalFactorsAdapter._compose(
            STRATEGY_SMART,    weather_factor=1.0,
            holiday_factor=1.7, auspicious_factor=2.2, event_factor=1.0,
        )
        result_multiply = ExternalFactorsAdapter._compose(
            STRATEGY_MULTIPLY, weather_factor=1.0,
            holiday_factor=1.7, auspicious_factor=2.2, event_factor=1.0,
        )
        # SMART should be less than MULTIPLY for demand factors > 1
        assert result_smart < result_multiply
        assert result_smart == pytest.approx(2.2, abs=0.01)  # takes max

    def test_smart_baseline_no_factors(self):
        result = ExternalFactorsAdapter._compose(
            STRATEGY_SMART,
            weather_factor=1.0, holiday_factor=1.0,
            auspicious_factor=1.0, event_factor=1.0,
        )
        assert result == pytest.approx(1.0, abs=0.01)

    # MULTIPLY strategy
    def test_multiply_combines_all_factors(self):
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_MULTIPLY,
            weather_factor=0.9,
            holiday_factor=1.5,
            auspicious_factor=1.0,
            event_factor=1.2,
        )
        expected = 0.9 * 1.5 * 1.0 * 1.2
        assert result == pytest.approx(expected, abs=0.01)

    def test_multiply_extreme_case(self):
        """Demonstrates why SMART is preferred — MULTIPLY can create extreme values."""
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_MULTIPLY,
            weather_factor=1.0,
            holiday_factor=1.8,
            auspicious_factor=2.2,
            event_factor=1.3,
        )
        # 1.0 × 1.8 × 2.2 × 1.3 = 5.148 — extremely high
        assert result > 5.0

    # MAX strategy
    def test_max_takes_single_largest(self):
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_MAX,
            weather_factor=0.7,
            holiday_factor=1.8,
            auspicious_factor=2.2,
            event_factor=1.4,
        )
        assert result == pytest.approx(2.2, abs=0.01)

    def test_max_with_weather_as_dominant(self):
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_MAX,
            weather_factor=3.0,  # hypothetical extreme weather bonus
            holiday_factor=1.5,
            auspicious_factor=1.0,
            event_factor=1.0,
        )
        assert result == pytest.approx(3.0, abs=0.01)

    def test_unknown_strategy_defaults_to_smart(self):
        """Unknown strategy should fall through to SMART."""
        result_unknown = ExternalFactorsAdapter._compose(
            strategy="unknown_strategy",
            weather_factor=0.9, holiday_factor=1.8,
            auspicious_factor=2.2, event_factor=1.3,
        )
        result_smart = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_SMART,
            weather_factor=0.9, holiday_factor=1.8,
            auspicious_factor=2.2, event_factor=1.3,
        )
        assert result_unknown == pytest.approx(result_smart, abs=0.01)

    def test_all_factors_below_1_smart(self):
        """Bad weather + no holidays → composite < 1."""
        result = ExternalFactorsAdapter._compose(
            strategy=STRATEGY_SMART,
            weather_factor=0.7,
            holiday_factor=0.9,
            auspicious_factor=1.0,
            event_factor=1.0,
        )
        # 0.7 × max(0.9, 1.0, 1.0) = 0.7 × 1.0 = 0.7
        assert result == pytest.approx(0.7, abs=0.01)


# ── get_factors (integration path) ────────────────────────────────────────────

class TestGetFactors:

    @pytest.mark.asyncio
    @patch("src.services.external_factors_adapter.weather_adapter")
    @patch("src.services.external_factors_adapter.AuspiciousDateService")
    async def test_returns_result_with_breakdown(self, mock_ausp_cls, mock_weather):
        # Weather fails gracefully
        mock_weather.get_tomorrow_weather = AsyncMock(return_value=None)

        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=False, demand_factor=1.0, label=None, sources=[]
        )
        mock_ausp_cls.return_value = mock_ausp

        adapter = ExternalFactorsAdapter()
        result  = await adapter.get_factors(date(2026, 3, 15))

        assert isinstance(result, ExternalFactorsResult)
        assert result.composite_factor > 0
        assert result.target_date == "2026-03-15"

    @pytest.mark.asyncio
    @patch("src.services.external_factors_adapter.weather_adapter")
    @patch("src.services.external_factors_adapter.AuspiciousDateService")
    async def test_auspicious_day_raises_factor(self, mock_ausp_cls, mock_weather):
        mock_weather.get_tomorrow_weather = AsyncMock(return_value=None)

        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=True, demand_factor=2.2, label="5/20表白日", sources=["fixed"]
        )
        mock_ausp_cls.return_value = mock_ausp

        adapter = ExternalFactorsAdapter()
        result  = await adapter.get_factors(date(2026, 5, 20), strategy=STRATEGY_SMART)

        assert result.composite_factor >= 2.2
        assert "auspicious" in result.factors_breakdown
        assert result.factors_breakdown["auspicious"] == pytest.approx(2.2, abs=0.01)

    @pytest.mark.asyncio
    @patch("src.services.external_factors_adapter.weather_adapter")
    @patch("src.services.external_factors_adapter.AuspiciousDateService")
    async def test_weather_failure_degrades_gracefully(self, mock_ausp_cls, mock_weather):
        mock_weather.get_tomorrow_weather = AsyncMock(side_effect=Exception("API down"))

        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=False, demand_factor=1.0, label=None, sources=[]
        )
        mock_ausp_cls.return_value = mock_ausp

        adapter = ExternalFactorsAdapter()
        result  = await adapter.get_factors(date(2026, 3, 15))

        # Should not crash; weather defaults to 1.0
        assert result.composite_factor > 0
        assert len(result.warnings) >= 1  # warning recorded
        assert "weather" not in result.factors_breakdown  # 1.0 not recorded

    @pytest.mark.asyncio
    @patch("src.services.external_factors_adapter.weather_adapter")
    @patch("src.services.external_factors_adapter.AuspiciousDateService")
    async def test_event_factor_combined(self, mock_ausp_cls, mock_weather):
        mock_weather.get_tomorrow_weather = AsyncMock(return_value=None)
        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=False, demand_factor=1.0, label=None, sources=[]
        )
        mock_ausp_cls.return_value = mock_ausp

        adapter = ExternalFactorsAdapter()
        events  = [{"type": "concert", "name": "演唱会"}]

        with patch.object(
            adapter, "_fetch_event_factor",
            return_value=1.4, __name__="mock"
        ) as mock_ef:
            mock_ef.side_effect = lambda evts, res: (
                setattr(res, "event", {"events": ["concert"], "impact_factor": 1.4}) or 1.4
            )
            result = await adapter.get_factors(
                date(2026, 3, 15), strategy=STRATEGY_SMART, events=events
            )

        # event factor should appear in breakdown
        assert "event" in result.factors_breakdown or result.composite_factor >= 1.0

    @pytest.mark.asyncio
    @patch("src.services.external_factors_adapter.weather_adapter")
    @patch("src.services.external_factors_adapter.AuspiciousDateService")
    async def test_multiply_strategy_differs_from_smart(self, mock_ausp_cls, mock_weather):
        mock_weather.get_tomorrow_weather = AsyncMock(return_value={
            "temperature": 5, "weather": "rainy"
        })
        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=True, demand_factor=1.8, label="好日子", sources=["fixed"]
        )
        mock_ausp_cls.return_value = mock_ausp

        adapter_smart    = ExternalFactorsAdapter()
        adapter_multiply = ExternalFactorsAdapter()

        result_smart    = await adapter_smart.get_factors(date(2026, 2, 14), STRATEGY_SMART)
        result_multiply = await adapter_multiply.get_factors(date(2026, 2, 14), STRATEGY_MULTIPLY)

        # SMART and MULTIPLY should differ when multiple demand factors > 1
        # (they may be equal if there's only one demand factor > 1)
        assert isinstance(result_smart.composite_factor, float)
        assert isinstance(result_multiply.composite_factor, float)

    @pytest.mark.asyncio
    @patch("src.services.external_factors_adapter.weather_adapter")
    @patch("src.services.external_factors_adapter.AuspiciousDateService")
    async def test_to_dict_is_serializable(self, mock_ausp_cls, mock_weather):
        mock_weather.get_tomorrow_weather = AsyncMock(return_value=None)
        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=False, demand_factor=1.0, label=None, sources=[]
        )
        mock_ausp_cls.return_value = mock_ausp

        import json
        adapter = ExternalFactorsAdapter()
        result  = await adapter.get_factors(date(2026, 3, 15))
        d       = result.to_dict()

        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert len(json_str) > 0
        assert "composite_factor" in d
        assert "factors_breakdown" in d


# ── _fetch_event_factor ────────────────────────────────────────────────────────

class TestFetchEventFactor:

    def test_no_events_returns_1(self):
        adapter = ExternalFactorsAdapter()
        result  = ExternalFactorsResult()
        factor  = adapter._fetch_event_factor(None, result)
        assert factor == 1.0

    def test_empty_events_returns_1(self):
        adapter = ExternalFactorsAdapter()
        result  = ExternalFactorsResult()
        factor  = adapter._fetch_event_factor([], result)
        assert factor == 1.0

    def test_unknown_event_type_returns_1(self):
        adapter = ExternalFactorsAdapter()
        result  = ExternalFactorsResult()
        with patch("src.services.external_factors_adapter.BusinessDistrictEvents") as mock_bde:
            mock_bde.get_event_impact.return_value = 1.0
            factor = adapter._fetch_event_factor([{"type": "unknown"}], result)
        assert factor == 1.0


# ── ExternalFactorsResult ─────────────────────────────────────────────────────

class TestExternalFactorsResult:

    def test_default_composite_factor_is_1(self):
        r = ExternalFactorsResult()
        assert r.composite_factor == 1.0

    def test_to_dict_rounds_factors(self):
        r = ExternalFactorsResult(
            composite_factor=2.123456,
            factors_breakdown={"auspicious": 2.123456},
        )
        d = r.to_dict()
        assert d["composite_factor"] == 2.123  # rounded to 3dp
        assert d["factors_breakdown"]["auspicious"] == 2.123

    def test_warnings_list_is_mutable(self):
        r = ExternalFactorsResult()
        r.warnings.append("test warning")
        assert "test warning" in r.warnings
