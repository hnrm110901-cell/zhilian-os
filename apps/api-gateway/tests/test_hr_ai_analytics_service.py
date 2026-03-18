"""Tests for WF-8 CompensationFairnessService + WF-9 TalentHealthService."""
from unittest.mock import AsyncMock

import pytest

from src.services.hr.compensation_fairness_service import CompensationFairnessService
from src.services.hr.talent_health_service import TalentHealthService

pytestmark = pytest.mark.asyncio

_MOCK_SESSION = AsyncMock()


# ── CompensationFairnessService ──────────────────────────────────────

class TestCompensationFairnessService:
    svc = CompensationFairnessService()

    async def test_analyze_store_empty(self):
        result = await self.svc.analyze_store([], _MOCK_SESSION)
        assert result["employee_count"] == 0
        assert result["anomalies"] == []
        assert result["avg_salary_yuan"] == 0

    async def test_analyze_store_flags_low_pay(self):
        employees = [
            {"person_id": "p1", "role": "server", "salary_yuan": 2500, "tenure_months": 6},
        ]
        result = await self.svc.analyze_store(employees, _MOCK_SESSION)
        assert result["anomaly_count"] == 1
        anomaly = result["anomalies"][0]
        assert anomaly["risk"] == "low_pay"
        assert anomaly["person_id"] == "p1"
        assert anomaly["deviation_pct"] < 0

    async def test_analyze_store_flags_high_pay(self):
        employees = [
            {"person_id": "p2", "role": "chef", "salary_yuan": 10000, "tenure_months": 24},
        ]
        result = await self.svc.analyze_store(employees, _MOCK_SESSION)
        assert result["anomaly_count"] == 1
        anomaly = result["anomalies"][0]
        assert anomaly["risk"] == "high_pay"
        assert anomaly["deviation_pct"] > 0

    async def test_analyze_store_normal_no_anomalies(self):
        employees = [
            {"person_id": "p3", "role": "server", "salary_yuan": 4000, "tenure_months": 12},
            {"person_id": "p4", "role": "chef", "salary_yuan": 6000, "tenure_months": 18},
        ]
        result = await self.svc.analyze_store(employees, _MOCK_SESSION)
        assert result["anomaly_count"] == 0
        assert result["avg_salary_yuan"] == 5000.0

    async def test_flag_anomalies_returns_list(self):
        employees = [
            {"person_id": "p1", "role": "server", "salary_yuan": 2000},
            {"person_id": "p2", "role": "chef", "salary_yuan": 6000},
        ]
        anomalies = await self.svc.flag_anomalies(employees, _MOCK_SESSION)
        assert isinstance(anomalies, list)
        assert len(anomalies) == 1
        assert anomalies[0]["person_id"] == "p1"

    async def test_market_benchmark_server(self):
        result = await self.svc.market_benchmark("服务员")
        assert result["role_key"] == "server"
        assert result["p50"] == 4000

    async def test_market_benchmark_unknown_returns_default(self):
        result = await self.svc.market_benchmark("收银员")
        assert result["role_key"] == "default"
        assert result["p50"] == 4500


# ── TalentHealthService ─────────────────────────────────────────────

class TestTalentHealthService:
    svc = TalentHealthService()

    async def test_score_store_zero_staff(self):
        result = await self.svc.score_store(
            {"org_node_id": "s1", "total_staff": 0}, _MOCK_SESSION
        )
        assert result["health_score"] == 0
        assert result["skill_coverage"] == 0

    async def test_score_store_healthy(self):
        data = {
            "org_node_id": "s2",
            "store_name": "旗舰店",
            "total_staff": 20,
            "turnover_count_90d": 1,
            "avg_skill_count": 4,
            "target_skill_count": 5,
            "avg_tenure_months": 18,
            "new_hire_count_90d": 2,
        }
        result = await self.svc.score_store(data, _MOCK_SESSION)
        assert result["health_score"] > 60
        assert result["risk_level"] in ("low", "medium")

    async def test_score_store_high_turnover_low_score(self):
        data = {
            "org_node_id": "s3",
            "store_name": "问题店",
            "total_staff": 10,
            "turnover_count_90d": 8,
            "avg_skill_count": 1,
            "target_skill_count": 5,
            "avg_tenure_months": 3,
            "new_hire_count_90d": 7,
        }
        result = await self.svc.score_store(data, _MOCK_SESSION)
        assert result["health_score"] < 50
        assert result["risk_level"] == "high"
        assert result["stability_index"] < 30

    async def test_hq_dashboard_multiple_stores(self):
        stores = [
            {
                "org_node_id": "s1", "store_name": "好店",
                "total_staff": 20, "turnover_count_90d": 1,
                "avg_skill_count": 4, "target_skill_count": 5,
                "avg_tenure_months": 18, "new_hire_count_90d": 2,
            },
            {
                "org_node_id": "s2", "store_name": "差店",
                "total_staff": 10, "turnover_count_90d": 8,
                "avg_skill_count": 1, "target_skill_count": 5,
                "avg_tenure_months": 3, "new_hire_count_90d": 7,
            },
        ]
        result = await self.svc.hq_dashboard(stores, _MOCK_SESSION)
        assert result["store_count"] == 2
        assert result["risk_store_count"] >= 1
        assert len(result["all_scores"]) == 2
        # sorted ascending by health_score
        assert result["all_scores"][0]["health_score"] <= result["all_scores"][1]["health_score"]

    async def test_talent_flow_matrix(self):
        transfers = [
            {"from_store": "A", "to_store": "B", "count": 3},
            {"from_store": "A", "to_store": "C", "count": 2},
            {"from_store": "B", "to_store": "A", "count": 1},
        ]
        result = await self.svc.talent_flow_matrix(transfers, _MOCK_SESSION)
        assert result["total_transfers"] == 6
        assert result["flow_matrix"]["A"]["B"] == 3
        assert result["top_sources"][0][0] == "A"
        assert result["top_sources"][0][1] == 5
