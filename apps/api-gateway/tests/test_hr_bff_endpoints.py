"""Tests for HR BFF endpoints (SM + HQ).

All DB/service calls are mocked — no real PostgreSQL needed.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.main import app
from src.core.database import get_db
from src.core.dependencies import get_current_active_user


def make_mock_user():
    user = MagicMock()
    user.id = "user-1"
    user.store_id = "S001"
    return user


def make_mock_session():
    return AsyncMock()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: make_mock_session()
    app.dependency_overrides[get_current_active_user] = lambda: make_mock_user()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSmHRBff:
    """SM HR BFF endpoint tests."""

    def test_sm_bff_returns_required_fields(self, client):
        """GET /api/v1/hr/bff/sm/{store_id} returns all required top-level fields."""
        with patch("src.agents.hr_agent.HRAgentV1") as MockAgent, \
             patch("src.services.hr.staffing_service.StaffingService") as MockStaffing:
            # Mock HRAgent diagnose
            mock_diag = MagicMock()
            mock_diag.high_risk_persons = [{"person_id": "p1", "risk_score": 0.9}]
            mock_diag.recommendations = [{"action": "1-on-1面谈"}]
            MockAgent.return_value.diagnose = AsyncMock(return_value=mock_diag)

            # Mock StaffingService
            mock_staffing = AsyncMock()
            mock_staffing.diagnose_staffing.return_value = {
                "peak_hours": [12, 13],
                "understaffed_hours": [12],
                "overstaffed_hours": [],
                "estimated_savings_yuan": 0.0,
                "confidence": 0.75,
                "analysis_date": "2026-03-18",
                "fused_demand": {},
                "total_active_staff": 8,
                "recommended_staff": 9,
                "recommendation_text": "12点需补1人",
            }
            MockStaffing.return_value = mock_staffing

            resp = client.get("/api/v1/hr/bff/sm/S001")

        assert resp.status_code == 200
        body = resp.json()
        assert "store_id" in body
        assert "retention" in body
        assert "staffing_today" in body
        assert "skill_gaps" in body
        assert "pending_actions_count" in body

    def test_sm_bff_partial_failure_returns_null_section(self, client):
        """If staffing service raises, staffing_today is null and other sections still return."""
        with patch("src.agents.hr_agent.HRAgentV1") as MockAgent, \
             patch("src.services.hr.staffing_service.StaffingService") as MockStaffing:
            mock_diag = MagicMock()
            mock_diag.high_risk_persons = []
            mock_diag.recommendations = []
            MockAgent.return_value.diagnose = AsyncMock(return_value=mock_diag)

            # StaffingService raises
            mock_staffing = AsyncMock()
            mock_staffing.diagnose_staffing.side_effect = Exception("DB unavailable")
            MockStaffing.return_value = mock_staffing

            resp = client.get("/api/v1/hr/bff/sm/S001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["staffing_today"] is None
        assert "retention" in body  # Other sections still present


class TestHqHRBff:
    """HQ HR BFF endpoint tests."""

    def test_hq_bff_returns_required_fields(self, client):
        """GET /api/v1/hr/bff/hq/{org_node_id} returns all required top-level fields."""
        mock_session = make_mock_session()
        # Mock DB queries for headcount, heatmap, knowledge health
        mock_session.execute.return_value.scalar.return_value = 42
        mock_session.execute.return_value.fetchall.return_value = []

        app.dependency_overrides[get_db] = lambda: mock_session

        resp = client.get("/api/v1/hr/bff/hq/org-node-1")

        assert resp.status_code == 200
        body = resp.json()
        assert "org_node_id" in body
        assert "as_of" in body
        assert "headcount" in body
        assert "turnover_heatmap" in body
        assert "knowledge_health" in body

    def test_hq_bff_partial_failure_returns_null_section(self, client):
        """HQ BFF handles DB error gracefully — null per section."""
        mock_session = make_mock_session()
        mock_session.execute.side_effect = Exception("DB error")
        app.dependency_overrides[get_db] = lambda: mock_session

        resp = client.get("/api/v1/hr/bff/hq/org-node-1")

        assert resp.status_code == 200
        body = resp.json()
        assert "org_node_id" in body
        assert body.get("headcount") is None  # DB error → null section
