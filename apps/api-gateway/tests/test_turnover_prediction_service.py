import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.turnover_prediction_service import (
    TurnoverPredictionService,
    compute_turnover_risk_score,
    estimate_replacement_cost,
    normalize_attendance_risk,
    normalize_consecutive_days_risk,
    normalize_fairness_risk,
    normalize_salary_volatility_risk,
    top_risk_factors,
)


def test_estimate_replacement_cost():
    assert estimate_replacement_cost(8000) == 4000.0
    assert estimate_replacement_cost(-100) == 0.0


def test_normalize_attendance_risk():
    assert normalize_attendance_risk(0) == 0.0
    assert normalize_attendance_risk(4) == 0.5
    assert normalize_attendance_risk(12) == 1.0


def test_normalize_fairness_risk():
    assert normalize_fairness_risk(100) == 0.0
    assert normalize_fairness_risk(70) == 0.3
    assert normalize_fairness_risk(-1) == 1.0


def test_normalize_consecutive_days_risk():
    assert normalize_consecutive_days_risk(6) == 0.0
    assert normalize_consecutive_days_risk(10) == 0.5
    assert normalize_consecutive_days_risk(20) == 1.0


def test_normalize_salary_volatility_risk():
    assert normalize_salary_volatility_risk(0.0) == 0.0
    assert normalize_salary_volatility_risk(0.15) == 0.5
    assert normalize_salary_volatility_risk(0.5) == 1.0


def test_compute_turnover_risk_score():
    score = compute_turnover_risk_score(
        {
            "attendance": 1.0,
            "fairness": 1.0,
            "consecutive_days": 1.0,
            "salary_volatility": 1.0,
        }
    )
    assert score == 1.0


def test_top_risk_factors():
    factors = top_risk_factors(
        {
            "attendance": 0.2,
            "fairness": 0.8,
            "consecutive_days": 0.6,
            "salary_volatility": 0.3,
        },
        top_n=2,
    )
    assert factors[0][0] == "fairness"
    assert len(factors) == 2


@pytest.mark.asyncio
async def test_predict_employee_turnover_high_risk_send_alert():
    service = TurnoverPredictionService()
    db = AsyncMock()

    employee = SimpleNamespace(
        id="E1",
        legacy_employee_id="E1",
        store_id="S1",
        name="张三",
        preferences={
            "attendance_anomaly_count": 8,
            "shift_fairness_score": 20,
            "consecutive_work_days": 14,
            "salary_volatility_rate": 0.25,
            "monthly_salary": 9000,
        },
    )

    manager_id = uuid.uuid4()
    store = SimpleNamespace(id="S1", manager_id=manager_id)

    db.get = AsyncMock(return_value=store)

    with patch("src.services.turnover_prediction_service.EmployeeRepository.get_by_id", new=AsyncMock(return_value=employee)):
        with patch("src.services.turnover_prediction_service.wechat_service.send_text_message", new=AsyncMock(return_value={"errcode": 0})) as mock_send:
            result = await service.predict_employee_turnover("E1", db)

    assert result["risk_score_90d"] > 0.7
    assert result["alert_sent"] is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_predict_employee_turnover_low_risk_no_alert():
    service = TurnoverPredictionService()
    db = AsyncMock()

    employee = SimpleNamespace(
        id="E2",
        legacy_employee_id="E2",
        store_id="S1",
        name="李四",
        preferences={
            "attendance_anomaly_count": 0,
            "shift_fairness_score": 95,
            "consecutive_work_days": 4,
            "salary_volatility_rate": 0.02,
            "monthly_salary": 7000,
        },
    )

    with patch("src.services.turnover_prediction_service.EmployeeRepository.get_by_id", new=AsyncMock(return_value=employee)):
        with patch("src.services.turnover_prediction_service.wechat_service.send_text_message", new=AsyncMock(return_value={"errcode": 0})) as mock_send:
            result = await service.predict_employee_turnover("E2", db)

    assert result["risk_score_90d"] < 0.7
    assert result["alert_sent"] is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_predict_employee_turnover_employee_not_found():
    service = TurnoverPredictionService()
    db = AsyncMock()

    with patch("src.services.turnover_prediction_service.EmployeeRepository.get_by_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError):
            await service.predict_employee_turnover("NOPE", db)
