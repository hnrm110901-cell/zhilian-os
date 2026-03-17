"""Tests for HR knowledge seed loader — uses mocks for speed."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_load_rules_inserts_correct_count():
    """Loader should insert exactly as many rules as are in the JSON file."""
    from src.services.hr.seed_service import HrSeedService

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    sample_rules = [
        {"rule_type": "alert", "category": "turnover",
         "condition": {}, "action": {}, "confidence": 0.8}
    ] * 3

    with patch.object(HrSeedService, "_load_json",
                      return_value=sample_rules):
        service = HrSeedService(mock_session)
        count = await service.load_rules(skip_if_exists=False)

    assert count == 3
    # 1 TRUNCATE + 3 inserts = 4 execute calls when skip_if_exists=False
    assert mock_session.execute.call_count == 4


@pytest.mark.asyncio
async def test_load_skills_inserts_correct_count():
    from src.services.hr.seed_service import HrSeedService

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    sample_skills = [
        {"skill_name": f"Skill {i}", "category": "service"}
        for i in range(5)
    ]

    with patch.object(HrSeedService, "_load_json",
                      return_value=sample_skills):
        service = HrSeedService(mock_session)
        count = await service.load_skills(skip_if_exists=False)

    assert count == 5


@pytest.mark.asyncio
async def test_load_rules_skips_when_exists():
    """skip_if_exists=True should not insert if rules already exist."""
    from src.services.hr.seed_service import HrSeedService

    mock_session = AsyncMock()
    # Simulate: COUNT(*) returns 10 (already seeded)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 10
    mock_session.execute = AsyncMock(return_value=mock_result)

    service = HrSeedService(mock_session)
    count = await service.load_rules(skip_if_exists=True)

    assert count == 0  # No inserts performed
