"""Tests for HRAgent v1 (B级 rule-based)."""
import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.agents.hr_agent import HRAgentV1, HRDiagnosis


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_diagnose_retention_risk(mock_session):
    """Intent 'retention_risk' calls RetentionRiskService.scan_store."""
    agent = HRAgentV1()

    with patch("src.agents.hr_agent.RetentionRiskService") as MockRRS:
        mock_rrs = AsyncMock()
        # scan_store returns (high_risk_list, total_scanned)
        mock_rrs.scan_store.return_value = (
            [
                {
                    "assignment_id": str(uuid.uuid4()),
                    "person_name": "张三",
                    "risk_score": 0.85,
                    "risk_factors": {"new_hire": True},
                }
            ],
            1,
        )
        MockRRS.return_value = mock_rrs

        with patch("src.agents.hr_agent.HrKnowledgeService") as MockKS:
            mock_ks = AsyncMock()
            mock_ks.query_rules.return_value = [
                {"rule_type": "alert", "category": "turnover",
                 "action": {"recommend": "mentor_assign"}, "confidence": 0.8}
            ]
            MockKS.return_value = mock_ks

            # Mock session.execute for org_node_id lookup
            mock_session.execute = AsyncMock()
            org_result = MagicMock()
            org_result.scalar_one_or_none.return_value = "ORG_NODE_001"
            mock_session.execute.return_value = org_result

            diagnosis = await agent.diagnose(
                "retention_risk",
                store_id="STORE001",
                session=mock_session,
            )

    assert isinstance(diagnosis, HRDiagnosis)
    assert diagnosis.intent == "retention_risk"
    assert len(diagnosis.high_risk_persons) == 1
    assert diagnosis.high_risk_persons[0]["person_name"] == "张三"
    assert len(diagnosis.recommendations) >= 1


@pytest.mark.asyncio
async def test_diagnose_skill_gaps(mock_session):
    """Intent 'skill_gaps' calls SkillGapService.analyze_store."""
    agent = HRAgentV1()

    with patch("src.agents.hr_agent.SkillGapService") as MockSGS:
        mock_sgs = AsyncMock()
        mock_sgs.analyze_store.return_value = [
            {
                "person_id": str(uuid.uuid4()),
                "achieved_skills": ["服务沟通"],
                "next_recommended": {
                    "skill_name": "高级服务",
                    "estimated_revenue_lift": 500.00,
                },
                "total_potential_yuan": 500.00,
            }
        ]
        MockSGS.return_value = mock_sgs

        # Mock session.execute for org_node_id lookup
        mock_session.execute = AsyncMock()
        org_result = MagicMock()
        org_result.scalar_one_or_none.return_value = "ORG_NODE_001"
        mock_session.execute.return_value = org_result

        diagnosis = await agent.diagnose(
            "skill_gaps",
            store_id="STORE001",
            session=mock_session,
        )

    assert diagnosis.intent == "skill_gaps"
    assert len(diagnosis.recommendations) >= 1
    # Recommendations should include yuan impact
    assert any(
        r.get("expected_yuan", 0) > 0 for r in diagnosis.recommendations
    )


@pytest.mark.asyncio
async def test_diagnose_unknown_intent(mock_session):
    """Unknown intent returns error diagnosis."""
    agent = HRAgentV1()
    diagnosis = await agent.diagnose(
        "unknown_intent",
        store_id="STORE001",
        session=mock_session,
    )
    assert diagnosis.intent == "unknown_intent"
    assert "不支持" in diagnosis.summary


@pytest.mark.asyncio
async def test_diagnose_retention_empty_store(mock_session):
    """Empty store returns diagnosis with no high-risk persons."""
    agent = HRAgentV1()

    with patch("src.agents.hr_agent.RetentionRiskService") as MockRRS:
        mock_rrs = AsyncMock()
        mock_rrs.scan_store.return_value = ([], 0)  # (high_risk_list, total_scanned)
        MockRRS.return_value = mock_rrs

        with patch("src.agents.hr_agent.HrKnowledgeService") as MockKS:
            mock_ks = AsyncMock()
            mock_ks.query_rules.return_value = []
            MockKS.return_value = mock_ks

            # Mock session.execute for org_node_id lookup
            mock_session.execute = AsyncMock()
            org_result = MagicMock()
            org_result.scalar_one_or_none.return_value = "ORG_NODE_001"
            mock_session.execute.return_value = org_result

            diagnosis = await agent.diagnose(
                "retention_risk",
                store_id="STORE001",
                session=mock_session,
            )

    assert diagnosis.high_risk_persons == []
    assert "无高风险" in diagnosis.summary or "0" in diagnosis.summary


@pytest.mark.asyncio
async def test_agent_execute_interface(mock_session):
    """HRAgentV1.execute() follows BaseAgent interface."""
    agent = HRAgentV1()

    with patch.object(agent, "diagnose", return_value=HRDiagnosis(
        intent="retention_risk",
        store_id="STORE001",
        summary="扫描完成",
        recommendations=[],
        high_risk_persons=[],
        generated_at=datetime.utcnow(),
    )):
        with patch("src.agents.hr_agent.AsyncSessionLocal") as MockASL:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockASL.return_value = mock_ctx

            response = await agent.execute(
                "retention_risk",
                {"store_id": "STORE001"},
            )

    assert response.success is True
    assert response.data["intent"] == "retention_risk"
