from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.shift_fairness_service import (
    ShiftFairnessService,
    compute_employee_unfavorable_ratio,
    compute_fairness_index,
    compute_gini,
    find_consecutive_worst_employees,
    is_unfavorable_shift,
)


def test_is_unfavorable_shift_by_type():
    assert is_unfavorable_shift("night", time(10, 0)) is True
    assert is_unfavorable_shift("closing", time(10, 0)) is True


def test_is_unfavorable_shift_by_early_start():
    assert is_unfavorable_shift("morning", time(7, 30)) is True
    assert is_unfavorable_shift("morning", time(9, 0)) is False


def test_compute_employee_unfavorable_ratio_empty():
    assert compute_employee_unfavorable_ratio([]) == 0.0


def test_compute_employee_unfavorable_ratio_mixed():
    records = [
        {"shift_type": "night", "start_time": time(18, 0)},
        {"shift_type": "morning", "start_time": time(9, 0)},
        {"shift_type": "morning", "start_time": time(7, 30)},
    ]
    assert compute_employee_unfavorable_ratio(records) == 0.6667


def test_compute_gini_edge_cases():
    assert compute_gini([]) == 0.0
    assert compute_gini([0, 0, 0]) == 0.0


def test_compute_gini_non_zero():
    assert compute_gini([1, 1, 1]) == 0.0
    assert compute_gini([0, 0, 1]) > 0.0


def test_compute_fairness_index():
    assert compute_fairness_index([]) == 100.0
    assert compute_fairness_index([0.5, 0.5, 0.5]) == 100.0
    assert compute_fairness_index([0.0, 0.0, 1.0]) < 100.0


def test_find_consecutive_worst_employees():
    weekly = [
        {"E1": 3, "E2": 1},
        {"E1": 2, "E2": 2},
        {"E1": 4, "E2": 1},
    ]
    assert find_consecutive_worst_employees(weekly, min_weeks=3) == ["E1"]


def test_find_consecutive_worst_employees_none():
    weekly = [
        {"E1": 2, "E2": 3},
        {"E1": 2, "E2": 1},
        {"E1": 1, "E2": 4},
    ]
    assert find_consecutive_worst_employees(weekly, min_weeks=3) == []


@pytest.mark.asyncio
async def test_get_monthly_shift_fairness():
    db = AsyncMock()
    result_obj = MagicMock()
    result_obj.all.return_value = [
        ("E1", "night", time(18, 0), date(2026, 3, 1)),
        ("E1", "morning", time(9, 0), date(2026, 3, 2)),
        ("E2", "morning", time(9, 0), date(2026, 3, 1)),
        ("E2", "morning", time(7, 30), date(2026, 3, 2)),
    ]
    db.execute = AsyncMock(return_value=result_obj)

    service = ShiftFairnessService()
    data = await service.get_monthly_shift_fairness("S1", 2026, 3, db)

    assert data["store_id"] == "S1"
    assert data["total_employees"] == 2
    assert 0 <= data["fairness_index"] <= 100
    assert data["employee_stats"][0]["employee_id"] in {"E1", "E2"}


@pytest.mark.asyncio
async def test_get_monthly_shift_fairness_no_rows():
    db = AsyncMock()
    result_obj = MagicMock()
    result_obj.all.return_value = []
    db.execute = AsyncMock(return_value=result_obj)

    service = ShiftFairnessService()
    data = await service.get_monthly_shift_fairness("S1", 2026, 3, db)

    assert data["total_employees"] == 0
    assert data["fairness_index"] == 100.0


@pytest.mark.asyncio
async def test_detect_unfair_assignment_alerts_high_risk():
    db = AsyncMock()
    result_obj = MagicMock()
    result_obj.all.return_value = [
        ("E1", "night", time(18, 0), date(2026, 2, 9)),
        ("E1", "night", time(18, 0), date(2026, 2, 16)),
        ("E1", "night", time(18, 0), date(2026, 2, 23)),
        ("E2", "morning", time(9, 0), date(2026, 2, 9)),
    ]
    db.execute = AsyncMock(return_value=result_obj)

    service = ShiftFairnessService()
    data = await service.detect_unfair_assignment_alerts(
        store_id="S1",
        end_date=date(2026, 3, 1),
        db=db,
        lookback_weeks=3,
    )

    assert data["high_risk_employees"] == ["E1"]
    assert len(data["weekly_unfavorable_counts"]) >= 3


@pytest.mark.asyncio
async def test_detect_unfair_assignment_alerts_no_high_risk():
    db = AsyncMock()
    result_obj = MagicMock()
    result_obj.all.return_value = [
        ("E1", "night", time(18, 0), date(2026, 2, 9)),
        ("E2", "night", time(18, 0), date(2026, 2, 16)),
        ("E1", "night", time(18, 0), date(2026, 2, 23)),
    ]
    db.execute = AsyncMock(return_value=result_obj)

    service = ShiftFairnessService()
    data = await service.detect_unfair_assignment_alerts(
        store_id="S1",
        end_date=date(2026, 3, 1),
        db=db,
        lookback_weeks=3,
    )

    assert data["high_risk_employees"] == []
