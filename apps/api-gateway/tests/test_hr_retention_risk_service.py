"""Tests for RetentionRiskService."""
import os
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.services.hr.retention_risk_service import RetentionRiskService


def _mock_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _mock_fetchall(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _mock_scalars_all(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_compute_risk_new_hire_no_achievements(mock_session):
    """New hire (<90 days) with no achievements → higher risk."""
    assignment_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        # start_date query
        if "start_date" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(date.today() - timedelta(days=30))
        # achievement count
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(0)
        # person_id lookup
        if "person_id" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        # existing retention signal
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    score = await svc.compute_risk_for_assignment(assignment_id, session=mock_session)

    # new_hire(0.2) + no_achievements(0.2) + baseline(0.3) = 0.7
    assert 0.6 <= score <= 0.8


@pytest.mark.asyncio
async def test_compute_risk_veteran_with_skills(mock_session):
    """Veteran (>90 days) with achievements → lower risk."""
    assignment_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "start_date" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(date.today() - timedelta(days=200))
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(3)
        if "person_id" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    score = await svc.compute_risk_for_assignment(assignment_id, session=mock_session)

    # baseline(0.3) only, no new_hire, has achievements
    assert 0.2 <= score <= 0.4


@pytest.mark.asyncio
async def test_compute_risk_with_existing_signal(mock_session):
    """Existing retention signal blends into score."""
    assignment_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "start_date" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(date.today() - timedelta(days=200))
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(2)
        if "person_id" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(0.6)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    score = await svc.compute_risk_for_assignment(assignment_id, session=mock_session)

    # baseline(0.3) + existing_signal(0.6 * 0.5 = 0.3) = 0.6
    assert 0.5 <= score <= 0.7


@pytest.mark.asyncio
async def test_scan_store_returns_high_risk(mock_session):
    """scan_store returns list of high-risk assignments."""
    org_node_id = "ORG_NODE_001"
    assignment_id = uuid.uuid4()
    person_id = uuid.uuid4()

    assignment_row = MagicMock()
    assignment_row.id = assignment_id
    assignment_row.person_id = person_id
    assignment_row.start_date = date.today() - timedelta(days=30)

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        # Fetch active assignments for store
        if "employment_assignments" in sql_text and "org_node_id" in sql_text and "SELECT" in sql_text and "INSERT" not in sql_text and "UPDATE" not in sql_text:
            if "start_date" in sql_text and "COUNT" not in sql_text and "person_id" not in sql_text:
                return _mock_scalar_one_or_none(assignment_row.start_date)
            if "person_id" in sql_text and "COUNT" not in sql_text:
                return _mock_scalar_one_or_none(person_id)
            return _mock_fetchall([assignment_row])
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(0)
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        # INSERT/UPDATE retention_signals
        if "retention_signals" in sql_text:
            return MagicMock()
        # person name lookup
        if "persons" in sql_text:
            return _mock_scalar_one_or_none("张三")
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    high_risk, total_scanned = await svc.scan_store(org_node_id)

    assert isinstance(high_risk, list)
    assert isinstance(total_scanned, int)


@pytest.mark.asyncio
@patch("src.services.hr.retention_risk_service.wechat_service")
async def test_run_wf1_pushes_wechat(mock_wechat, mock_session):
    """WF-1 pushes WeChat alerts for high-risk employees."""
    org_node_id = "ORG_NODE_001"

    # Patch scan_store to return (high_risk_list, total_scanned)
    svc = RetentionRiskService(session=mock_session)

    with patch.object(svc, "scan_store", return_value=(
        [{"assignment_id": str(uuid.uuid4()), "person_name": "张三",
          "risk_score": 0.85, "risk_factors": {"new_hire": True}}],
        3,  # 3 total active assignments scanned, 1 is high-risk
    )):
        result = await svc.run_wf1_for_store(org_node_id)

    assert result["high_risk"] == 1
    assert result["scanned"] == 3
    mock_wechat.send_text_message.assert_called_once()
