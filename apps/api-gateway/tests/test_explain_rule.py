"""
Tests for PerformanceAgent._explain_rule + _build_rule_explanation

Covers every commission rule type and the lookup/error paths.
"""
import os

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from src.agents.performance_agent import (
    PerformanceAgent, _build_rule_explanation, COMMISSION_RULE_CONFIG,
)


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    return PerformanceAgent()


def _rule(role: str, name: str) -> dict:
    return next(r for r in COMMISSION_RULE_CONFIG[role] if r["name"] == name)


# ── _build_rule_explanation ───────────────────────────────────────────────────

class TestBuildRuleExplanation:

    def test_achievement_bonus_steps(self):
        rule = _rule("waiter", "好评奖")
        exp  = _build_rule_explanation(rule)
        assert len(exp["calculation_steps"]) == 4
        assert "80%" in exp["calculation_steps"][2]
        assert "¥100" in exp["calculation_steps"][2]
        assert exp["applicable_data"]["threshold"] == "80%"
        assert "good_review_rate" in exp["applicable_data"]["required_metrics"]

    def test_excess_commission_steps(self):
        rule = _rule("store_manager", "超额提成 1-3%")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        assert len(steps) == 5
        assert "1%" in steps[3] and "3%" in steps[3]
        assert exp["applicable_data"]["rate_range"] == "1% – 3%"

    def test_score_coefficient_steps(self):
        rule = _rule("shift_manager", "月度绩效系数")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        assert len(steps) == 2
        assert "20%" in steps[1]
        assert exp["applicable_data"]["coeff_scale"] == "20%"

    def test_excess_linear_steps(self):
        rule = _rule("waiter", "桌均提成")
        exp  = _build_rule_explanation(rule)
        assert "超额" in exp["calculation_steps"][1]
        assert "avg_per_table" in exp["applicable_data"]["required_metrics"]

    def test_count_commission_steps(self):
        rule = _rule("kitchen", "出餐量奖")
        exp  = _build_rule_explanation(rule)
        assert "¥0.50/个" in exp["calculation_steps"][1]
        assert exp["applicable_data"]["per_unit"] == "¥0.50"

    def test_rate_on_count_steps(self):
        rule = _rule("waiter", "加单提成")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        assert any("比率" in s for s in steps)
        mets = exp["applicable_data"]["required_metrics"]
        assert "add_order_rate" in mets
        assert "order_count" in mets

    def test_rate_on_value_steps(self):
        rule = _rule("cashier", "储值/卡券销售提成(%)")
        exp  = _build_rule_explanation(rule)
        assert "1%" in exp["calculation_steps"][1]
        assert exp["applicable_data"]["rate"] == "1%"

    def test_below_threshold_steps(self):
        rule = _rule("kitchen", "退菜率低于阈值奖")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        assert len(steps) == 3
        assert "2.00%" in steps[1]
        assert "¥200" in steps[1]

    def test_saving_bonus_steps(self):
        rule = _rule("kitchen", "损耗节约奖")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        assert any("5.00%" in s for s in steps)
        assert exp["applicable_data"]["reward_per_pct"] == "¥500"

    def test_tiered_count_steps(self):
        rule = _rule("delivery", "单量提成(元/单或阶梯)")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        # Tiers: 1–100, 101–300, 301–∞
        assert any("1–100" in s for s in steps)
        assert any("101–300" in s for s in steps)
        assert any("∞" in s for s in steps)
        tiers = exp["applicable_data"]["tiers"]
        assert len(tiers) == 3
        assert tiers[0]["rate"] == "¥1.0/单"
        assert tiers[2]["rate"] == "¥2.0/单"

    def test_penalty_on_rate_steps(self):
        rule = _rule("delivery", "差评扣减")
        exp  = _build_rule_explanation(rule)
        steps = exp["calculation_steps"]
        assert any("扣减" in s for s in steps)
        assert "¥10" in steps[-1]
        mets = exp["applicable_data"]["required_metrics"]
        assert "bad_review_rate" in mets and "order_count" in mets

    def test_cross_store_steps(self):
        rule = _rule("store_manager", "季度综合排名奖")
        exp  = _build_rule_explanation(rule)
        assert any("汇总" in s for s in exp["calculation_steps"])


# ── _explain_rule lookup ──────────────────────────────────────────────────────

class TestExplainRule:

    @pytest.mark.asyncio
    async def test_exact_match_with_role(self, agent):
        r = await agent._explain_rule({"rule_id": "好评奖", "role_id": "waiter"})
        assert r["success"]
        d = r["data"]
        assert d["rule_id"]   == "好评奖"
        assert d["role_id"]   == "waiter"
        assert d["role_name"] == "服务员"
        assert d["type"]      == "achievement_bonus"
        assert isinstance(d["calculation_steps"], list)
        assert isinstance(d["applicable_data"],   dict)
        assert r["metadata"]["source"] == "config"

    @pytest.mark.asyncio
    async def test_substring_match_cross_role(self, agent):
        """Partial name returns the matching rule."""
        r = await agent._explain_rule({"rule_id": "差评扣减"})
        assert r["success"]
        assert r["data"]["role_id"] == "delivery"

    @pytest.mark.asyncio
    async def test_exact_beats_substring(self, agent):
        """When multiple matches, exact name wins."""
        r = await agent._explain_rule({"rule_id": "准时奖"})
        assert r["success"]
        assert r["data"]["rule_id"] == "准时奖"

    @pytest.mark.asyncio
    async def test_commission_id_used_as_fallback_key(self, agent):
        """commission_id accepted when rule_id absent."""
        r = await agent._explain_rule({"commission_id": "出餐量奖"})
        assert r["success"]
        assert r["data"]["role_id"] == "kitchen"

    @pytest.mark.asyncio
    async def test_not_found_returns_error_with_available_list(self, agent):
        r = await agent._explain_rule({"rule_id": "不存在的规则xyz"})
        assert not r["success"]
        assert "可用规则" in r["error"]

    @pytest.mark.asyncio
    async def test_missing_key_returns_error(self, agent):
        r = await agent._explain_rule({})
        assert not r["success"]
        assert r["data"] is None

    @pytest.mark.asyncio
    async def test_role_filter_prevents_cross_role_match(self, agent):
        """Searching 'single量提成' in waiter role should fail (it belongs to delivery)."""
        r = await agent._explain_rule({"rule_id": "单量提成", "role_id": "waiter"})
        assert not r["success"]

    @pytest.mark.asyncio
    async def test_calculation_steps_is_list_of_strings(self, agent):
        for rule_name in ["月度目标达成奖", "超额提成 1-3%", "月度绩效系数"]:
            r = await agent._explain_rule({"rule_id": rule_name})
            assert r["success"], f"Failed for {rule_name}: {r}"
            steps = r["data"]["calculation_steps"]
            assert isinstance(steps, list) and all(isinstance(s, str) for s in steps)

    @pytest.mark.asyncio
    async def test_applicable_data_required_metrics_present(self, agent):
        for role, rule_name in [
            ("store_manager", "月度目标达成奖"),
            ("cashier",       "会员开卡提成(元/张)"),
            ("delivery",      "差评扣减"),
        ]:
            r = await agent._explain_rule({"rule_id": rule_name, "role_id": role})
            assert r["success"], f"{rule_name}: {r}"
            mets = r["data"]["applicable_data"]["required_metrics"]
            assert isinstance(mets, list) and len(mets) >= 1

    @pytest.mark.asyncio
    async def test_all_configured_rules_are_explainable(self, agent):
        """Every rule in COMMISSION_RULE_CONFIG must return success with steps."""
        errors = []
        for role_id, rules in COMMISSION_RULE_CONFIG.items():
            for rule in rules:
                r = await agent._explain_rule({
                    "rule_id": rule["name"],
                    "role_id": role_id,
                })
                if not r["success"]:
                    errors.append(f"{role_id}/{rule['name']}: {r['error']}")
                elif not r["data"]["calculation_steps"]:
                    errors.append(f"{role_id}/{rule['name']}: empty steps")
        assert not errors, "\n".join(errors)
