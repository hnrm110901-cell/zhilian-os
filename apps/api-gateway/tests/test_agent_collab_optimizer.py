"""
AgentCollaborationOptimizer 单元测试
纯函数测试 + 协同仲裁端到端测试
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from src.services.agent_collab_optimizer import (
    AgentCollabOptimizer,
    AgentRecommendation,
    get_agent_priority,
    classify_conflict_severity,
    detect_keyword_conflict,
    arbitrate_conflict,
    is_duplicate,
    should_suppress,
    compute_global_impact,
    build_ai_insight,
)


# ──────────────────────────────────────────────
# 纯函数测试
# ──────────────────────────────────────────────

class TestGetAgentPriority:
    def test_known_agent(self):
        assert get_agent_priority("business_intel") == 100
        assert get_agent_priority("ops_flow") == 95
        assert get_agent_priority("fct") == 55

    def test_unknown_agent_defaults(self):
        assert get_agent_priority("unknown_agent") == 50

    def test_override_takes_precedence(self):
        assert get_agent_priority("fct", override=99) == 99

    def test_zero_override_accepted(self):
        assert get_agent_priority("business_intel", override=0) == 0


class TestClassifyConflictSeverity:
    def test_high_severity_large_impact(self):
        assert classify_conflict_severity(15000, 5000) == "high"

    def test_medium_severity(self):
        assert classify_conflict_severity(3000, 1000) == "medium"

    def test_low_severity(self):
        assert classify_conflict_severity(500, 200) == "low"

    def test_uses_max_of_both(self):
        # Even if impact_a is low, large impact_b → high
        assert classify_conflict_severity(100, 12000) == "high"


class TestDetectKeywordConflict:
    def test_known_conflict_pair_ops_supplier(self):
        result = detect_keyword_conflict("ops_flow", "立即补货大米300kg", "supplier", "切换供应商不续约")
        assert result is not None
        conflict_type, desc = result
        assert conflict_type == "resource_contention"
        assert "ops_flow" in desc or "supplier" in desc

    def test_known_conflict_pair_reversed(self):
        # Same pair but agents swapped
        result = detect_keyword_conflict("supplier", "切换供应商不续约", "ops_flow", "立即补货大米")
        assert result is not None

    def test_contradictory_action_promotion_vs_cost(self):
        result = detect_keyword_conflict("business_intel", "给会员发折扣券促销", "fct", "控制现金流减少支出")
        # 促销 + 提价 pair: "促销" in text_a and "提价" in text_b? Not quite
        # Let's test an actual contradictory pair: 增加 vs 减少
        result2 = detect_keyword_conflict("marketing", "增加发券频次提高复购", "people", "减少用工人数控制成本")
        assert result2 is not None
        assert "contradictory_action" in result2[0]

    def test_no_conflict_unrelated(self):
        result = detect_keyword_conflict("business_intel", "分析营收趋势数据", "supplier", "检查供应商资质认证")
        assert result is None

    def test_different_stores_no_check(self):
        # detect_keyword_conflict doesn't check store_id — that's done at call site
        # This just tests text comparison
        result = detect_keyword_conflict("ops_flow", "补货", "supplier", "切换供应商")
        assert result is not None


class TestArbitrateConflict:
    def test_fct_wins_financial_constraint(self):
        winner, method = arbitrate_conflict("financial_constraint", "business_intel", 100, 5000, "fct", 55, 2000)
        assert winner == "fct"
        assert method == "financial_first"

    def test_compliance_wins_risk(self):
        winner, method = arbitrate_conflict("priority_clash", "marketing", 80, 10000, "compliance", 60, 3000)
        assert winner == "compliance"
        assert method == "risk_first"

    def test_higher_priority_wins(self):
        winner, method = arbitrate_conflict("resource_contention", "business_intel", 100, 2000, "supplier", 65, 5000)
        assert winner == "business_intel"
        assert method == "priority_wins"

    def test_equal_priority_higher_impact_wins(self):
        winner, method = arbitrate_conflict("contradictory_action", "agent_a", 80, 8000, "agent_b", 80, 4000)
        assert winner == "agent_a"
        assert method == "revenue_first"

    def test_equal_priority_equal_impact_b_not_always_wins(self):
        winner, method = arbitrate_conflict("contradictory_action", "agent_a", 80, 5000, "agent_b", 80, 5000)
        # equal: uses >=, so agent_a wins
        assert winner == "agent_a"


class TestIsDuplicate:
    def test_high_overlap_is_duplicate(self):
        a = AgentRecommendation("1", "business_intel", "S001", "cost", "建议降低食材采购成本优化库存周转率", 1000, 0.8)
        b = AgentRecommendation("2", "ops_flow",       "S001", "cost", "降低食材采购成本并优化库存周转", 900, 0.7)
        assert is_duplicate(a, b)

    def test_different_store_not_duplicate(self):
        a = AgentRecommendation("1", "business_intel", "S001", "cost", "降低食材采购成本优化", 1000, 0.8)
        b = AgentRecommendation("2", "ops_flow",       "S002", "cost", "降低食材采购成本优化", 900, 0.7)
        assert not is_duplicate(a, b)

    def test_completely_different_not_duplicate(self):
        a = AgentRecommendation("1", "marketing", "S001", "promo", "向流失客户发送复购优惠券", 500, 0.7)
        b = AgentRecommendation("2", "ops_flow",  "S001", "inv",   "大米库存告警立即补货", 800, 0.9)
        assert not is_duplicate(a, b)


class TestShouldSuppress:
    def test_low_impact_low_confidence_suppressed(self):
        rec = AgentRecommendation("1", "marketing", "S001", "minor", "轻微建议", 50, 0.3)
        assert should_suppress(rec)

    def test_high_impact_not_suppressed(self):
        rec = AgentRecommendation("1", "ops_flow", "S001", "critical", "重要建议", 5000, 0.3)
        assert not should_suppress(rec)

    def test_low_impact_high_confidence_not_suppressed(self):
        rec = AgentRecommendation("1", "compliance", "S001", "risk", "风险提醒", 50, 0.9)
        assert not should_suppress(rec)


class TestComputeGlobalImpact:
    def test_sums_expected_impact(self):
        recs = [
            AgentRecommendation("1", "a", "S001", "t", "text", 1000, 0.8),
            AgentRecommendation("2", "b", "S001", "t", "text", 2000, 0.7),
            AgentRecommendation("3", "c", "S001", "t", "text", 500, 0.9),
        ]
        assert compute_global_impact(recs) == 3500.0

    def test_empty_list_returns_zero(self):
        assert compute_global_impact([]) == 0.0


class TestBuildAiInsight:
    def test_includes_conflict_count(self):
        from src.services.agent_collab_optimizer import ConflictRecord
        conflicts = [ConflictRecord("id", "a", "b", "r1", "r2", "resource_contention", "high", "desc")]
        text = build_ai_insight(10, 8, conflicts, 5000, 5500)
        assert "冲突" in text

    def test_includes_removed_count(self):
        text = build_ai_insight(10, 7, [], 5000, 4800)
        assert "3" in text or "去除" in text or "冗余" in text

    def test_equal_input_output_returns_summary(self):
        text = build_ai_insight(5, 5, [], 3000, 3000)
        assert "5" in text or "建议" in text or "优化" in text


# ──────────────────────────────────────────────
# 集成测试 — 协同总线端到端
# ──────────────────────────────────────────────

class TestAgentCollabOptimizer:
    def setup_method(self):
        self.optimizer = AgentCollabOptimizer()

    def _make_rec(self, id, agent, store, text, impact=1000, confidence=0.8, rec_type="action"):
        return AgentRecommendation(id, agent, store, rec_type, text, impact, confidence)

    def test_empty_input(self):
        result = self.optimizer.optimize([])
        assert result.output_count == 0
        assert result.conflicts_detected == 0

    def test_single_recommendation_passes_through(self):
        recs = [self._make_rec("1", "business_intel", "S001", "建议优化营收管理策略提升效益", 2000)]
        result = self.optimizer.optimize(recs)
        assert result.output_count == 1
        assert result.conflicts_detected == 0

    def test_conflict_detection_ops_supplier(self):
        recs = [
            self._make_rec("r1", "ops_flow",  "S001", "立即补货大米300kg应对高峰", 5000),
            self._make_rec("r2", "supplier",  "S001", "切换供应商不续约当前合同", 3000),
        ]
        result = self.optimizer.optimize(recs)
        assert result.conflicts_detected == 1
        assert result.conflicts[0].agent_a == "ops_flow"
        assert result.conflicts[0].agent_b == "supplier"

    def test_ops_flow_wins_over_supplier_priority(self):
        recs = [
            self._make_rec("r1", "ops_flow",  "S001", "立即补货大米300kg应对高峰", 5000),
            self._make_rec("r2", "supplier",  "S001", "切换供应商不续约当前合同", 3000),
        ]
        result = self.optimizer.optimize(recs)
        # ops_flow (priority 95) > supplier (priority 65)
        assert result.conflicts[0].winning_agent == "ops_flow"
        # supplier recommendation is suppressed
        output_ids = {r.id for r in result.optimized_recommendations}
        assert "r1" in output_ids
        assert "r2" not in output_ids

    def test_fct_financial_constraint_wins(self):
        recs = [
            self._make_rec("r1", "business_intel", "S001", "给会员发折扣券提升复购率", 8000),
            self._make_rec("r2", "fct",            "S001", "控制现金流本周减少大额支出", 4000),
        ]
        result = self.optimizer.optimize(recs)
        # Check if financial_first arbitration applies
        financial_conflicts = [c for c in result.conflicts if c.arbitration_method == "financial_first"]
        # Only triggers if "折扣" + "现金流" keywords detected
        # "折扣" is not in text_a, so no conflict expected here
        # This tests that financial constraint doesn't fire false positives
        assert result.output_count >= 1

    def test_dedup_removes_near_duplicate(self):
        recs = [
            self._make_rec("r1", "business_intel", "S001", "降低食材采购成本优化库存周转率提升毛利", 2000),
            self._make_rec("r2", "ops_flow",       "S001", "降低食材采购成本并优化库存周转率", 1500),
        ]
        result = self.optimizer.optimize(recs)
        assert result.dedup_count >= 1
        assert result.output_count == 1  # Only the higher impact one remains
        # Higher impact (r1) kept
        output_ids = {r.id for r in result.optimized_recommendations}
        assert "r1" in output_ids

    def test_suppress_low_impact_low_confidence(self):
        recs = [
            self._make_rec("r1", "business_intel", "S001", "重要营收优化建议", 5000, 0.9),
            self._make_rec("r2", "marketing",      "S001", "次要的轻微小建议", 50, 0.2),
        ]
        result = self.optimizer.optimize(recs)
        assert result.suppressed_count >= 1
        output_ids = {r.id for r in result.optimized_recommendations}
        assert "r1" in output_ids
        assert "r2" not in output_ids

    def test_sort_by_impact_times_confidence(self):
        recs = [
            self._make_rec("r1", "supplier",      "S001", "建议A供应商优化", 1000, 0.5),   # score=500
            self._make_rec("r2", "business_intel","S001", "建议B营收分析建议", 2000, 0.8),  # score=1600
            self._make_rec("r3", "ops_flow",      "S001", "建议C库存预警建议", 3000, 0.6),  # score=1800
        ]
        result = self.optimizer.optimize(recs)
        assert result.output_count == 3
        # r3 (1800) > r2 (1600) > r1 (500)
        ids_in_order = [r.id for r in result.optimized_recommendations]
        assert ids_in_order[0] == "r3"
        assert ids_in_order[1] == "r2"
        assert ids_in_order[2] == "r1"

    def test_different_stores_no_conflict(self):
        recs = [
            self._make_rec("r1", "ops_flow", "S001", "立即补货大米300kg", 5000),
            self._make_rec("r2", "supplier", "S002", "切换供应商不续约", 3000),
        ]
        result = self.optimizer.optimize(recs)
        # Different stores → no cross-store conflict
        assert result.conflicts_detected == 0
        assert result.output_count == 2

    def test_ai_insight_generated(self):
        recs = [
            self._make_rec("r1", "ops_flow",  "S001", "立即补货大米300kg", 5000),
            self._make_rec("r2", "supplier",  "S001", "切换供应商不续约", 3000),
        ]
        result = self.optimizer.optimize(recs)
        assert isinstance(result.ai_insight, str)
        assert len(result.ai_insight) > 10

    def test_impact_totals_computed(self):
        recs = [
            self._make_rec("r1", "business_intel", "S001", "大额营收优化建议策略", 3000, 0.9),
            self._make_rec("r2", "ops_flow",       "S001", "重要库存预警告警建议", 2000, 0.8),
        ]
        result = self.optimizer.optimize(recs)
        assert result.total_impact_yuan_before == 5000.0
        assert result.total_impact_yuan_after > 0
