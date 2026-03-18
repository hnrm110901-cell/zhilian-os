"""Tests for StaffingService — WF-2 staffing health analysis.

All tests mock AsyncSession + Redis. No real PostgreSQL required.
"""
import json
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.setex = MagicMock()
    return r


def _make_execute(orders_data, metrics_data, shifts_data):
    """Build side_effect that dispatches based on SQL keywords."""
    def _row(hour, count):
        r = MagicMock()
        r.hour = hour
        r.order_count = float(count)
        r.avg_count = float(count)
        r.headcount = int(count)
        return r

    async def fake_execute(stmt, params=None):
        sql = str(stmt).lower()
        result = MagicMock()
        # Recent orders: contains "/ 7" division
        if "/ 7" in sql:
            result.fetchall.return_value = [_row(h, c) for h, c in orders_data]
        # Historical avg: contains avg_count alias (DOW-based query)
        elif "avg_count" in sql:
            result.fetchall.return_value = [_row(h, c) for h, c in metrics_data]
        elif "shifts" in sql:
            result.fetchall.return_value = [_row(h, c) for h, c in shifts_data]
        else:
            result.fetchall.return_value = []
        return result
    return fake_execute


@pytest.mark.asyncio
async def test_output_has_all_required_fields(mock_session, mock_redis):
    """Output contains all spec §3.3 required keys."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute([], [], [])
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    for key in ("store_id", "analysis_date", "peak_hours", "understaffed_hours",
                "overstaffed_hours", "recommended_headcount", "estimated_savings_yuan",
                "confidence", "data_freshness"):
        assert key in result, f"Missing: {key}"


@pytest.mark.asyncio
async def test_peak_hours_detected(mock_session, mock_redis):
    """peak_hours contains hours where fused demand > mean + 1σ."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[(9, 3), (10, 4), (11, 5), (12, 20), (13, 18), (17, 4), (18, 22), (19, 19)],
        metrics_data=[(9, 3.0), (10, 4.0), (11, 5.0), (12, 18.0), (13, 16.0), (17, 4.0), (18, 20.0), (19, 17.0)],
        shifts_data=[(9, 2), (10, 2), (12, 3), (18, 3)],
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert len(result["peak_hours"]) > 0
    assert 12 in result["peak_hours"] or 18 in result["peak_hours"]


@pytest.mark.asyncio
async def test_savings_yuan_positive_when_overstaffed(mock_session, mock_redis):
    """estimated_savings_yuan > 0 when actual headcount >> recommended."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[(h, 2) for h in range(9, 21)],
        metrics_data=[(h, 2.0) for h in range(9, 21)],
        shifts_data=[(h, 10) for h in range(9, 21)],   # massively overstaffed
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["estimated_savings_yuan"] > 0


@pytest.mark.asyncio
async def test_both_empty_returns_zero_confidence(mock_session, mock_redis):
    """Both data sources empty => confidence == 0.0, no crash."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute([], [], [])
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["confidence"] == 0.0
    assert result["peak_hours"] == []
    assert result["estimated_savings_yuan"] == 0.0


@pytest.mark.asyncio
async def test_orders_empty_falls_back_to_metrics(mock_session, mock_redis):
    """No recent orders => falls back to metrics only, confidence > 0, no crash."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[],
        metrics_data=[(12, 15.0), (18, 12.0)],
        shifts_data=[(12, 4), (18, 3)],
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["confidence"] > 0.0
    assert isinstance(result["peak_hours"], list)


@pytest.mark.asyncio
async def test_redis_cache_hit_skips_db(mock_session, mock_redis):
    """Cached result returned without hitting DB."""
    from src.services.hr.staffing_service import StaffingService

    cached = {
        "store_id": "STORE001", "analysis_date": "2026-03-18",
        "peak_hours": [12, 18], "understaffed_hours": [], "overstaffed_hours": [],
        "recommended_headcount": {"12": 5}, "estimated_savings_yuan": 0.0,
        "confidence": 0.75, "data_freshness": {},
    }
    mock_redis.get.return_value = json.dumps(cached).encode()

    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["peak_hours"] == [12, 18]
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_understaffed_hours_detected(mock_session, mock_redis):
    """Hours where actual headcount < recommended are in understaffed_hours."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[(12, 30)],   # very high demand at noon
        metrics_data=[(12, 25.0)],
        shifts_data=[(12, 1)],    # only 1 person on shift
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert 12 in result["understaffed_hours"]
