"""Tests for HrKnowledgeService."""
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.services.hr.knowledge_service import HrKnowledgeService


def _mock_scalars_all(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _mock_fetchall(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_query_rules_all(mock_session):
    """Query all active rules."""
    rule = MagicMock()
    rule._mapping = {
        "id": uuid.uuid4(),
        "rule_type": "sop",
        "category": "turnover",
        "condition": {"tenure_days_lt": 90},
        "action": {"recommend": "mentor_assign"},
        "confidence": 0.85,
    }
    mock_session.execute = AsyncMock(return_value=_mock_fetchall([rule]))

    svc = HrKnowledgeService(session=mock_session)
    rules = await svc.query_rules()

    assert len(rules) == 1
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_rules_with_category_filter(mock_session):
    """Filter rules by category."""
    mock_session.execute = AsyncMock(return_value=_mock_fetchall([]))

    svc = HrKnowledgeService(session=mock_session)
    rules = await svc.query_rules(category="scheduling")

    assert rules == []
    # Verify category filter was used in query
    call_args = mock_session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    assert params.get("category") == "scheduling"


@pytest.mark.asyncio
async def test_get_skills_for_person(mock_session):
    """Get achieved skill names for a person."""
    person_id = uuid.uuid4()
    row1 = MagicMock()
    row1.skill_name = "服务沟通"
    row2 = MagicMock()
    row2.skill_name = "库存管理"
    mock_session.execute = AsyncMock(return_value=_mock_fetchall([row1, row2]))

    svc = HrKnowledgeService(session=mock_session)
    skills = await svc.get_skills_for_person(person_id)

    assert skills == ["服务沟通", "库存管理"]


@pytest.mark.asyncio
async def test_get_next_skill_for_person(mock_session):
    """Returns highest-revenue-lift unachieved skill in category."""
    person_id = uuid.uuid4()

    call_count = 0
    async def fake_execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        sql_text = getattr(stmt, 'text', str(stmt))
        # First call: get achieved skill IDs
        if "person_achievements" in sql_text:
            return _mock_scalars_all([])
        # Second call: get unskilled nodes ordered by revenue lift
        if "skill_nodes" in sql_text:
            node = MagicMock()
            node._mapping = {
                "id": uuid.uuid4(),
                "skill_name": "高级服务",
                "estimated_revenue_lift": 500.00,
                "category": "service",
            }
            return _mock_fetchall([node])
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = HrKnowledgeService(session=mock_session)
    result = await svc.get_next_skill_for_person(person_id, target_category="service")

    assert result is not None
    assert result["skill_name"] == "高级服务"


@pytest.mark.asyncio
async def test_get_next_skill_all_achieved(mock_session):
    """Returns None when all skills in category are achieved."""
    person_id = uuid.uuid4()
    node_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "person_achievements" in sql_text:
            return _mock_scalars_all([node_id])
        if "skill_nodes" in sql_text:
            return _mock_fetchall([])  # no unskilled nodes left
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = HrKnowledgeService(session=mock_session)
    result = await svc.get_next_skill_for_person(person_id, target_category="service")

    assert result is None
