"""
私域运营Agent单元测试
覆盖：RFM分层、信号感知、旅程引擎、四象限、差评处理、execute分发
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# base_agent lives in apps/api-gateway/src/core
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent.parent.parent.parent / "apps" / "api-gateway" / "src" / "core"),
)

import pytest
from agent import (
    PrivateDomainAgent,
    RFMLevel,
    StoreQuadrant,
    SignalType,
    JourneyType,
    JourneyStatus,
)


@pytest.fixture
def agent():
    return PrivateDomainAgent(store_id="S001")


# ─────────────────────────── RFM 分层 ───────────────────────────

class TestClassifyRFM:
    def test_s1_high_value(self, agent):
        assert agent._classify_rfm(recency_days=5, frequency=3, monetary=15000) == RFMLevel.S1.value

    def test_s2_potential(self, agent):
        assert agent._classify_rfm(recency_days=20, frequency=1, monetary=5000) == RFMLevel.S2.value

    def test_s3_dormant(self, agent):
        assert agent._classify_rfm(recency_days=45, frequency=0, monetary=0) == RFMLevel.S3.value

    def test_s4_churn_warning(self, agent):
        assert agent._classify_rfm(recency_days=75, frequency=0, monetary=0) == RFMLevel.S4.value

    def test_s5_churned(self, agent):
        assert agent._classify_rfm(recency_days=100, frequency=0, monetary=0) == RFMLevel.S5.value

    def test_boundary_s1_exact_threshold(self, agent):
        # 恰好满足 S1 条件
        result = agent._classify_rfm(
            recency_days=30,
            frequency=agent.s1_min_frequency,
            monetary=agent.s1_min_monetary,
        )
        assert result == RFMLevel.S1.value

    def test_boundary_s3_day60(self, agent):
        assert agent._classify_rfm(recency_days=60, frequency=0, monetary=0) == RFMLevel.S3.value

    def test_boundary_s4_day90(self, agent):
        assert agent._classify_rfm(recency_days=90, frequency=0, monetary=0) == RFMLevel.S4.value


# ─────────────────────────── 流失风险分 ───────────────────────────

class TestChurnRisk:
    def test_recent_active_low_risk(self, agent):
        score = agent._calculate_churn_risk(recency_days=3, frequency=5)
        assert score < 0.3

    def test_long_absent_high_risk(self, agent):
        score = agent._calculate_churn_risk(recency_days=90, frequency=0)
        assert score >= 0.7

    def test_score_range(self, agent):
        for r in range(0, 120, 10):
            for f in range(0, 10, 2):
                score = agent._calculate_churn_risk(r, f)
                assert 0.0 <= score <= 1.0

    def test_higher_frequency_lowers_risk(self, agent):
        low_freq = agent._calculate_churn_risk(recency_days=30, frequency=0)
        high_freq = agent._calculate_churn_risk(recency_days=30, frequency=8)
        assert high_freq < low_freq


# ─────────────────────────── 动态标签 ───────────────────────────

class TestDynamicTags:
    def test_high_spend_tag(self, agent):
        c = {"monetary": agent.s1_min_monetary * 3, "frequency": 1, "recency_days": 5, "avg_order_time": 12}
        tags = agent._infer_dynamic_tags(c)
        assert "高消费" in tags

    def test_high_frequency_tag(self, agent):
        c = {"monetary": 1000, "frequency": 5, "recency_days": 5, "avg_order_time": 12}
        tags = agent._infer_dynamic_tags(c)
        assert "高频" in tags

    def test_recent_active_tag(self, agent):
        c = {"monetary": 1000, "frequency": 1, "recency_days": 3, "avg_order_time": 12}
        tags = agent._infer_dynamic_tags(c)
        assert "近期活跃" in tags

    def test_lunch_preference_tag(self, agent):
        c = {"monetary": 1000, "frequency": 1, "recency_days": 20, "avg_order_time": 12}
        tags = agent._infer_dynamic_tags(c)
        assert "午餐偏好" in tags

    def test_dinner_preference_tag(self, agent):
        c = {"monetary": 1000, "frequency": 1, "recency_days": 20, "avg_order_time": 19}
        tags = agent._infer_dynamic_tags(c)
        assert "晚餐偏好" in tags

    def test_default_tag_when_no_match(self, agent):
        c = {"monetary": 500, "frequency": 0, "recency_days": 50, "avg_order_time": 9}
        tags = agent._infer_dynamic_tags(c)
        assert tags == ["普通用户"]


# ─────────────────────────── 四象限 ───────────────────────────

class TestStoreQuadrant:
    @pytest.mark.asyncio
    async def test_benchmark_high_penetration_low_competition(self, agent):
        result = await agent.calculate_store_quadrant(
            competition_density=2.0,
            member_count=400,
            estimated_population=1000,
        )
        assert result["quadrant"] == StoreQuadrant.BENCHMARK.value
        assert "strategy" in result

    @pytest.mark.asyncio
    async def test_defensive_high_penetration_high_competition(self, agent):
        result = await agent.calculate_store_quadrant(
            competition_density=8.0,
            member_count=400,
            estimated_population=1000,
        )
        assert result["quadrant"] == StoreQuadrant.DEFENSIVE.value

    @pytest.mark.asyncio
    async def test_potential_low_penetration_low_competition(self, agent):
        result = await agent.calculate_store_quadrant(
            competition_density=2.0,
            member_count=50,
            estimated_population=1000,
        )
        assert result["quadrant"] == StoreQuadrant.POTENTIAL.value

    @pytest.mark.asyncio
    async def test_breakthrough_low_penetration_high_competition(self, agent):
        result = await agent.calculate_store_quadrant(
            competition_density=8.0,
            member_count=50,
            estimated_population=1000,
        )
        assert result["quadrant"] == StoreQuadrant.BREAKTHROUGH.value

    @pytest.mark.asyncio
    async def test_penetration_rate_calculated_correctly(self, agent):
        result = await agent.calculate_store_quadrant(
            competition_density=2.0,
            member_count=300,
            estimated_population=1000,
        )
        assert result["member_penetration"] == pytest.approx(0.3, abs=0.001)

    @pytest.mark.asyncio
    async def test_zero_population_no_division_error(self, agent):
        result = await agent.calculate_store_quadrant(
            competition_density=0.0,
            member_count=0,
            estimated_population=0,
        )
        assert "quadrant" in result


# ─────────────────────────── 旅程引擎 ───────────────────────────

class TestJourneyEngine:
    @pytest.mark.asyncio
    async def test_trigger_new_customer_journey(self, agent):
        record = await agent.trigger_journey(JourneyType.NEW_CUSTOMER.value, "C001")
        assert record["journey_type"] == JourneyType.NEW_CUSTOMER.value
        assert record["customer_id"] == "C001"
        assert record["store_id"] == "S001"
        assert record["status"] == JourneyStatus.RUNNING.value
        assert record["total_steps"] == 4
        assert record["current_step"] == 1
        assert record["journey_id"].startswith("JRN_NEW_CUSTOMER_C001")

    @pytest.mark.asyncio
    async def test_trigger_vip_retention_journey(self, agent):
        record = await agent.trigger_journey(JourneyType.VIP_RETENTION.value, "C002")
        assert record["total_steps"] == 4

    @pytest.mark.asyncio
    async def test_trigger_reactivation_journey(self, agent):
        record = await agent.trigger_journey(JourneyType.REACTIVATION.value, "C003")
        assert record["total_steps"] == 3

    @pytest.mark.asyncio
    async def test_trigger_review_repair_journey(self, agent):
        record = await agent.trigger_journey(JourneyType.REVIEW_REPAIR.value, "C004")
        assert record["total_steps"] == 4

    @pytest.mark.asyncio
    async def test_get_journeys_all(self, agent):
        journeys = await agent.get_journeys()
        assert len(journeys) > 0

    @pytest.mark.asyncio
    async def test_get_journeys_filter_by_status(self, agent):
        running = await agent.get_journeys(status=JourneyStatus.RUNNING.value)
        for j in running:
            assert j["status"] == JourneyStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_get_journeys_completed_filter(self, agent):
        completed = await agent.get_journeys(status=JourneyStatus.COMPLETED.value)
        for j in completed:
            assert j["status"] == JourneyStatus.COMPLETED.value


# ─────────────────────────── 信号感知 ───────────────────────────

class TestSignalDetection:
    @pytest.mark.asyncio
    async def test_detect_signals_returns_list(self, agent):
        signals = await agent.detect_signals()
        assert isinstance(signals, list)
        assert len(signals) <= 20

    @pytest.mark.asyncio
    async def test_signals_have_required_fields(self, agent):
        signals = await agent.detect_signals()
        for s in signals:
            assert "signal_id" in s
            assert "signal_type" in s
            assert "store_id" in s
            assert s["store_id"] == "S001"

    @pytest.mark.asyncio
    async def test_churn_risk_signals_detected(self, agent):
        signals = await agent.detect_signals()
        types = {s["signal_type"] for s in signals}
        assert SignalType.CHURN_RISK.value in types

    @pytest.mark.asyncio
    async def test_get_signals_filter_by_type(self, agent):
        signals = await agent.get_signals(signal_type=SignalType.CHURN_RISK.value)
        for s in signals:
            assert s["signal_type"] == SignalType.CHURN_RISK.value

    @pytest.mark.asyncio
    async def test_get_signals_limit(self, agent):
        signals = await agent.get_signals(limit=5)
        assert len(signals) <= 5


# ─────────────────────────── RFM 分析 ───────────────────────────

class TestAnalyzeRFM:
    @pytest.mark.asyncio
    async def test_analyze_rfm_returns_segments(self, agent):
        segments = await agent.analyze_rfm(30)
        assert len(segments) == 50

    @pytest.mark.asyncio
    async def test_segments_have_valid_rfm_levels(self, agent):
        valid_levels = {l.value for l in RFMLevel}
        segments = await agent.analyze_rfm(30)
        for s in segments:
            assert s["rfm_level"] in valid_levels

    @pytest.mark.asyncio
    async def test_segments_risk_score_in_range(self, agent):
        segments = await agent.analyze_rfm(30)
        for s in segments:
            assert 0.0 <= s["risk_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_get_churn_risks_subset_of_rfm(self, agent):
        all_segments = await agent.analyze_rfm(30)
        churn_risks = await agent.get_churn_risks()
        churn_ids = {s["customer_id"] for s in churn_risks}
        all_ids = {s["customer_id"] for s in all_segments}
        assert churn_ids.issubset(all_ids)

    @pytest.mark.asyncio
    async def test_churn_risks_are_s3_s4_s5_or_high_risk(self, agent):
        churn_risks = await agent.get_churn_risks()
        for s in churn_risks:
            assert s["rfm_level"] in ("S3", "S4", "S5") or s["risk_score"] >= 0.6


# ─────────────────────────── 差评处理 ───────────────────────────

class TestBadReviewProcessing:
    @pytest.mark.asyncio
    async def test_process_bad_review_with_customer(self, agent):
        result = await agent.process_bad_review(
            review_id="REV001",
            customer_id="C001",
            rating=1,
            content="菜品太咸",
        )
        assert result["handled"] is True
        assert result["journey_triggered"] is True
        assert result["journey_id"] is not None
        assert result["compensation_issued"] is True  # rating <= 2

    @pytest.mark.asyncio
    async def test_process_bad_review_without_customer(self, agent):
        result = await agent.process_bad_review(
            review_id="REV002",
            customer_id=None,
            rating=2,
            content="服务慢",
        )
        assert result["handled"] is True
        assert result["journey_triggered"] is False

    @pytest.mark.asyncio
    async def test_process_review_rating_3_no_compensation(self, agent):
        result = await agent.process_bad_review(
            review_id="REV003",
            customer_id="C002",
            rating=3,
            content="一般",
        )
        assert result["compensation_issued"] is False


# ─────────────────────────── execute 分发 ───────────────────────────

class TestExecuteDispatch:
    @pytest.mark.asyncio
    async def test_execute_get_dashboard(self, agent):
        resp = await agent.execute("get_dashboard", {})
        assert resp.success is True
        assert resp.data is not None
        assert "store_id" in resp.data

    @pytest.mark.asyncio
    async def test_execute_analyze_rfm(self, agent):
        resp = await agent.execute("analyze_rfm", {"days": 30})
        assert resp.success is True
        assert isinstance(resp.data, list)

    @pytest.mark.asyncio
    async def test_execute_detect_signals(self, agent):
        resp = await agent.execute("detect_signals", {})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_execute_calculate_store_quadrant(self, agent):
        resp = await agent.execute("calculate_store_quadrant", {
            "competition_density": 3.0,
            "member_count": 200,
            "estimated_population": 800,
        })
        assert resp.success is True
        assert "quadrant" in resp.data

    @pytest.mark.asyncio
    async def test_execute_trigger_journey(self, agent):
        resp = await agent.execute("trigger_journey", {
            "journey_type": JourneyType.NEW_CUSTOMER.value,
            "customer_id": "C999",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_execute_get_churn_risks(self, agent):
        resp = await agent.execute("get_churn_risks", {})
        assert resp.success is True
        assert isinstance(resp.data, list)

    @pytest.mark.asyncio
    async def test_execute_unsupported_action(self, agent):
        resp = await agent.execute("nonexistent_action", {})
        assert resp.success is False
        assert resp.error is not None

    @pytest.mark.asyncio
    async def test_execute_process_bad_review(self, agent):
        resp = await agent.execute("process_bad_review", {
            "review_id": "REV_TEST",
            "customer_id": "C001",
            "rating": 1,
            "content": "测试差评",
        })
        assert resp.success is True
        assert resp.data["handled"] is True


# ─────────────────────────── 看板 ───────────────────────────

class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_fields(self, agent):
        dashboard = await agent.get_dashboard()
        assert dashboard["store_id"] == "S001"
        assert "total_members" in dashboard
        assert "active_members" in dashboard
        assert "rfm_distribution" in dashboard
        assert "pending_signals" in dashboard
        assert "running_journeys" in dashboard
        assert "monthly_repurchase_rate" in dashboard
        assert "churn_risk_count" in dashboard
        assert "bad_review_count" in dashboard
        assert "store_quadrant" in dashboard
        assert "roi_estimate" in dashboard

    @pytest.mark.asyncio
    async def test_dashboard_repurchase_rate_range(self, agent):
        dashboard = await agent.get_dashboard()
        assert 0.0 <= dashboard["monthly_repurchase_rate"] <= 1.0

    @pytest.mark.asyncio
    async def test_dashboard_active_lte_total(self, agent):
        dashboard = await agent.get_dashboard()
        assert dashboard["active_members"] <= dashboard["total_members"]

    @pytest.mark.asyncio
    async def test_dashboard_rfm_distribution_sums_to_total(self, agent):
        dashboard = await agent.get_dashboard()
        dist_sum = sum(dashboard["rfm_distribution"].values())
        assert dist_sum == dashboard["total_members"]
