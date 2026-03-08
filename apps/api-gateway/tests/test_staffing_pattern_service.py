from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-staffing-pattern-32!!")

from src.services.staffing_pattern_service import (  # noqa: E402
    StaffingPatternService,
    infer_day_type,
)


def _result_with_rows(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _result_with_row(row):
    result = MagicMock()
    result.fetchone.return_value = row
    return result


class TestStaffingPatternService:
    def test_infer_day_type(self):
        assert infer_day_type(date(2026, 3, 9)) == "weekday"
        assert infer_day_type(date(2026, 3, 8)) == "weekend"

    @pytest.mark.asyncio
    async def test_learn_from_history_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with_rows([]))
        resp = await StaffingPatternService.learn_from_history(
            store_id="S001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 8),
            db=db,
        )
        assert resp["stored_count"] == 0
        assert resp["patterns"] == []

    @pytest.mark.asyncio
    async def test_learn_from_history_success(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        rows = [
            SimpleNamespace(
                schedule_date=date(2026, 3, 2),
                shift_type="morning",
                position="waiter",
                start_time="08:00",
                end_time="14:00",
                required_count=3,
                actual_labor_cost_rate=24.5,
            ),
            SimpleNamespace(
                schedule_date=date(2026, 3, 2),
                shift_type="morning",
                position="cashier",
                start_time="08:00",
                end_time="14:00",
                required_count=1,
                actual_labor_cost_rate=24.5,
            ),
            SimpleNamespace(
                schedule_date=date(2026, 3, 3),
                shift_type="morning",
                position="waiter",
                start_time="08:00",
                end_time="14:00",
                required_count=2,
                actual_labor_cost_rate=30.0,
            ),
        ]
        db.execute = AsyncMock(
            side_effect=[
                _result_with_rows(rows),
                _result_with_row(None),
            ]
        )
        resp = await StaffingPatternService.learn_from_history(
            store_id="S001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 8),
            db=db,
        )
        assert resp["stored_count"] >= 1
        assert len(resp["patterns"]) >= 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_best_pattern_none(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with_row(None))
        pattern = await StaffingPatternService.get_best_pattern(
            store_id="S001",
            target_date=date(2026, 3, 8),
            db=db,
        )
        assert pattern is None

    @pytest.mark.asyncio
    async def test_build_shifts_from_best_pattern(self):
        db = AsyncMock()
        row = SimpleNamespace(
            pattern_name="weekend_all_day_template",
            day_type="weekend",
            meal_period="all_day",
            shifts_template=[
                {"shift_type": "morning", "position": "waiter", "required_count": 2, "start": "08:00", "end": "14:00"}
            ],
            sample_days=6,
            avg_labor_cost_rate=23.1,
            performance_score=76.9,
        )
        employees = [
            SimpleNamespace(id="E001", skills=["waiter"], is_active=True),
            SimpleNamespace(id="E002", skills=["waiter"], is_active=True),
        ]
        db.execute = AsyncMock(return_value=_result_with_row(row))
        with patch(
            "src.services.staffing_pattern_service.EmployeeRepository.get_by_store",
            new_callable=AsyncMock,
            return_value=employees,
        ):
            shifts = await StaffingPatternService.build_shifts_from_best_pattern(
                store_id="S001",
                target_date=date(2026, 3, 8),
                db=db,
            )
        assert len(shifts) == 2
        assert shifts[0]["position"] == "waiter"
