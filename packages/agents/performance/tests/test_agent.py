"""
PerformanceAgent 单元测试
覆盖全部 6 个 action 和关键辅助函数
"""
import pytest
from src.agent import (
    PerformanceAgent,
    ROLE_CONFIG,
    COMMISSION_RULES,
    DEFAULT_TARGETS,
    LOWER_IS_BETTER,
    _achievement,
    _compute_rule_amount,
    _detect_role,
    _detect_action,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    return PerformanceAgent(store_id="STORE001")


@pytest.fixture
def store_manager_metrics():
    """店长典型指标值（单位：分 or 小数）"""
    return {
        "revenue":          32_000_000,   # ¥320,000 → 超额 ~6.7%
        "profit":           0.58,
        "labor_efficiency": 520_000,
        "satisfaction":     4.6,
        "food_safety":      1.0,
        "waste_rate":       0.04,
    }


@pytest.fixture
def waiter_metrics():
    return {
        "avg_per_table":   17_000,    # 超额 ¥20/桌
        "add_order_rate":  0.35,
        "good_review_rate": 0.92,
        "attendance":      0.98,
        "order_count":     200,
    }


@pytest.fixture
def delivery_metrics():
    return {
        "order_count":    250,         # 101–300 tier
        "on_time_rate":   0.96,        # ≥ 95%，触发准时奖
        "bad_review_rate": 0.02,
    }


# ── 辅助函数测试 ──────────────────────────────────────────────────────────────

class TestAchievement:
    def test_normal_metric_above_target(self):
        ach = _achievement(110, 100, "revenue")
        assert ach == 1.1

    def test_normal_metric_below_target(self):
        ach = _achievement(80, 100, "revenue")
        assert round(ach, 4) == 0.8

    def test_lower_is_better_below_target(self):
        # waste_rate: target=0.05, value=0.04 → 0.05/0.04 = 1.25
        ach = _achievement(0.04, 0.05, "waste_rate")
        assert round(ach, 4) == 1.25

    def test_lower_is_better_above_target(self):
        # waste_rate: target=0.05, value=0.08 → 0.05/0.08 = 0.625
        ach = _achievement(0.08, 0.05, "waste_rate")
        assert round(ach, 4) == 0.625

    def test_caps_at_2(self):
        ach = _achievement(500, 100, "revenue")
        assert ach == 2.0

    def test_zero_target_returns_zero(self):
        ach = _achievement(10, 0, "complaint")
        assert ach == 0.0

    def test_all_lower_is_better_metrics_present(self):
        for mid in LOWER_IS_BETTER:
            # 确保不抛异常
            ach = _achievement(1, 1, mid)
            assert ach == 1.0


class TestComputeRuleAmount:
    def test_achievement_bonus_triggered(self):
        rule = {
            "name": "test", "type": "achievement_bonus",
            "metric": "revenue", "threshold": 0.80, "fixed_fen": 200_000,
        }
        result = _compute_rule_amount(rule, {}, {"revenue": 0.95}, None)
        assert result == 200_000

    def test_achievement_bonus_not_triggered(self):
        rule = {
            "name": "test", "type": "achievement_bonus",
            "metric": "revenue", "threshold": 0.80, "fixed_fen": 200_000,
        }
        result = _compute_rule_amount(rule, {}, {"revenue": 0.70}, None)
        assert result == 0

    def test_count_commission(self):
        rule = {
            "name": "会员开卡", "type": "count_commission",
            "metric": "member_card", "per_unit_fen": 500,
        }
        result = _compute_rule_amount(rule, {"member_card": 60}, {}, None)
        assert result == 30_000  # 60 × 500

    def test_rate_on_value(self):
        rule = {
            "name": "储值提成", "type": "rate_on_value",
            "metric": "stored_value", "rate": 0.01,
        }
        result = _compute_rule_amount(rule, {"stored_value": 1_000_000}, {}, None)
        assert result == 10_000  # 1_000_000 × 0.01

    def test_below_threshold_triggered(self):
        rule = {
            "name": "退菜奖", "type": "below_threshold",
            "metric": "return_rate", "threshold": 0.02, "fixed_fen": 20_000,
        }
        result = _compute_rule_amount(rule, {"return_rate": 0.01}, {}, None)
        assert result == 20_000

    def test_below_threshold_not_triggered(self):
        rule = {
            "name": "退菜奖", "type": "below_threshold",
            "metric": "return_rate", "threshold": 0.02, "fixed_fen": 20_000,
        }
        result = _compute_rule_amount(rule, {"return_rate": 0.03}, {}, None)
        assert result == 0

    def test_tiered_count_first_tier(self):
        rule = {
            "name": "单量提成", "type": "tiered_count",
            "metric": "order_count",
            "tiers": [(100, 100), (300, 150), (9999, 200)],
        }
        result = _compute_rule_amount(rule, {"order_count": 80}, {}, None)
        assert result == 8_000  # 80 × 100

    def test_tiered_count_second_tier(self):
        rule = {
            "name": "单量提成", "type": "tiered_count",
            "metric": "order_count",
            "tiers": [(100, 100), (300, 150), (9999, 200)],
        }
        result = _compute_rule_amount(rule, {"order_count": 250}, {}, None)
        assert result == 37_500  # 250 × 150

    def test_score_coefficient(self):
        rule = {
            "name": "绩效系数", "type": "score_coefficient",
            "metric": "ALL", "base_salary_fen": 500_000, "coeff_scale": 0.20,
        }
        result = _compute_rule_amount(rule, {}, {}, 1.0)
        assert result == 100_000  # 500_000 × 1.0 × 0.20

    def test_cross_store_returns_none(self):
        rule = {"name": "跨店奖", "type": "cross_store", "metric": None}
        result = _compute_rule_amount(rule, {}, {}, None)
        assert result is None

    def test_missing_metric_returns_none(self):
        rule = {
            "name": "test", "type": "achievement_bonus",
            "metric": "revenue", "threshold": 0.80, "fixed_fen": 200_000,
        }
        result = _compute_rule_amount(rule, {}, {}, None)  # no achievements
        assert result is None

    def test_penalty_on_rate(self):
        rule = {
            "name": "差评扣减", "type": "penalty_on_rate",
            "metric": "bad_review_rate", "count_metric": "order_count",
            "per_unit_fen": -1_000,
        }
        # 差评率 5%，200 单 → 差评 10 条 → -10 × 1000 = -10000
        result = _compute_rule_amount(
            rule,
            {"bad_review_rate": 0.05, "order_count": 200},
            {},
            None,
        )
        assert result == -10_000

    def test_saving_bonus(self):
        rule = {
            "name": "损耗节约奖", "type": "saving_bonus",
            "metric": "waste_rate", "base_target": 0.05, "coeff_fen": 50_000,
        }
        # 实际 3%，节约 2% → 2 × 50_000 = 100_000
        result = _compute_rule_amount(rule, {"waste_rate": 0.03}, {}, None)
        assert result == 100_000


class TestNLDetect:
    def test_detect_role_store_manager(self):
        assert _detect_role("店长的提成怎么算") == "store_manager"

    def test_detect_role_waiter(self):
        assert _detect_role("服务员的绩效") == "waiter"

    def test_detect_role_kitchen(self):
        assert _detect_role("后厨损耗率") == "kitchen"
        assert _detect_role("厨师出餐量") == "kitchen"

    def test_detect_role_delivery(self):
        assert _detect_role("外卖单量") == "delivery"

    def test_detect_role_none(self):
        assert _detect_role("所有岗位配置") is None

    def test_detect_action_commission(self):
        assert _detect_action("提成多少钱") == "commission"

    def test_detect_action_performance(self):
        assert _detect_action("绩效得分") == "performance"

    def test_detect_action_explain(self):
        assert _detect_action("请解释一下") == "explain"

    def test_detect_action_default(self):
        assert _detect_action("不明白的话") == "config"


# ── PerformanceAgent action 测试 ──────────────────────────────────────────────

class TestGetRoleConfig:
    @pytest.mark.asyncio
    async def test_all_roles(self, agent):
        resp = await agent.execute("get_role_config", {})
        assert resp.success is True
        data = resp.data
        assert "roles" in data
        assert len(data["roles"]) == 6

    @pytest.mark.asyncio
    async def test_specific_role(self, agent):
        resp = await agent.execute("get_role_config", {"role_id": "store_manager"})
        assert resp.success is True
        data = resp.data
        assert data["role_id"] == "store_manager"
        assert data["role_name"] == "店长"
        assert len(data["metrics"]) > 0
        assert len(data["commission_rules"]) > 0

    @pytest.mark.asyncio
    async def test_all_roles_have_config(self, agent):
        for role_id in ROLE_CONFIG:
            resp = await agent.execute("get_role_config", {"role_id": role_id})
            assert resp.success is True
            assert resp.data["role_id"] == role_id

    @pytest.mark.asyncio
    async def test_invalid_role(self, agent):
        resp = await agent.execute("get_role_config", {"role_id": "unknown_role"})
        assert resp.success is True
        assert "error" in resp.data
        assert "available" in resp.data


class TestCalculatePerformance:
    @pytest.mark.asyncio
    async def test_store_manager_full_metrics(self, agent, store_manager_metrics):
        resp = await agent.execute("calculate_performance", {
            "role_id": "store_manager",
            "metric_values": store_manager_metrics,
            "period": "2026-02",
        })
        assert resp.success is True
        data = resp.data
        assert data["role_id"] == "store_manager"
        assert data["total_score"] is not None
        assert 0 < data["total_score"] <= 2.0
        assert len(data["metrics"]) == len(ROLE_CONFIG["store_manager"]["metrics"])

    @pytest.mark.asyncio
    async def test_empty_metric_values(self, agent):
        resp = await agent.execute("calculate_performance", {
            "role_id": "waiter",
            "metric_values": {},
        })
        assert resp.success is True
        assert resp.data["total_score"] is None
        for m in resp.data["metrics"]:
            assert m["achievement_rate"] is None

    @pytest.mark.asyncio
    async def test_partial_metric_values(self, agent):
        resp = await agent.execute("calculate_performance", {
            "role_id": "kitchen",
            "metric_values": {"serve_time": 12.0},  # only one metric
        })
        assert resp.success is True
        # total_score should be computed from the partial data
        assert resp.data["total_score"] is not None

    @pytest.mark.asyncio
    async def test_invalid_role_id(self, agent):
        resp = await agent.execute("calculate_performance", {"role_id": "invalid"})
        assert resp.success is True
        assert "error" in resp.data

    @pytest.mark.asyncio
    async def test_all_roles_compute(self, agent):
        for role_id in ROLE_CONFIG:
            resp = await agent.execute("calculate_performance", {"role_id": role_id})
            assert resp.success is True
            assert resp.data["role_id"] == role_id

    @pytest.mark.asyncio
    async def test_waste_rate_lower_is_better(self, agent):
        """损耗率低于目标 → 达成率 > 1"""
        resp = await agent.execute("calculate_performance", {
            "role_id": "store_manager",
            "metric_values": {"waste_rate": 0.03},  # target=0.05 → ach=1.67
        })
        metric = next(m for m in resp.data["metrics"] if m["metric_id"] == "waste_rate")
        assert metric["achievement_rate"] > 1.0


class TestCalculateCommission:
    @pytest.mark.asyncio
    async def test_store_manager_excess_commission(self, agent, store_manager_metrics):
        resp = await agent.execute("calculate_commission", {
            "role_id": "store_manager",
            "metric_values": store_manager_metrics,
            "period": "2026-02",
        })
        assert resp.success is True
        data = resp.data
        assert data["role_id"] == "store_manager"
        assert data["total_commission_fen"] is not None
        assert data["total_commission_yuan"] is not None
        # 月度目标达成奖应触发（revenue 达成 > 80%）
        award = next(r for r in data["rule_results"] if "月度目标达成奖" in r["name"])
        assert award["amount_fen"] == 200_000

    @pytest.mark.asyncio
    async def test_cashier_count_commission(self, agent):
        resp = await agent.execute("calculate_commission", {
            "role_id": "cashier",
            "metric_values": {"member_card": 40, "stored_value": 2_000_000},
        })
        assert resp.success is True
        data = resp.data
        card_rule = next(r for r in data["rule_results"] if "开卡" in r["name"])
        assert card_rule["amount_fen"] == 40 * 500  # 40 × ¥5

    @pytest.mark.asyncio
    async def test_delivery_tiered_commission(self, agent, delivery_metrics):
        resp = await agent.execute("calculate_commission", {
            "role_id": "delivery",
            "metric_values": delivery_metrics,
        })
        assert resp.success is True
        data = resp.data
        # 250 单 → 150 分/单
        tier_rule = next(r for r in data["rule_results"] if "单量" in r["name"])
        assert tier_rule["amount_fen"] == 250 * 150

    @pytest.mark.asyncio
    async def test_kitchen_saving_bonus(self, agent):
        resp = await agent.execute("calculate_commission", {
            "role_id": "kitchen",
            "metric_values": {"waste_rate": 0.03, "order_count": 200},
        })
        assert resp.success is True
        saving_rule = next(r for r in resp.data["rule_results"] if "节约" in r["name"])
        # (5% - 3%) × 100 × ¥500/1% = 100_000 fen
        assert saving_rule["amount_fen"] == 100_000

    @pytest.mark.asyncio
    async def test_delivery_on_time_bonus(self, agent, delivery_metrics):
        resp = await agent.execute("calculate_commission", {
            "role_id": "delivery",
            "metric_values": delivery_metrics,  # on_time_rate=0.96 ≥ 0.95
        })
        ontime_rule = next(r for r in resp.data["rule_results"] if "准时" in r["name"])
        assert ontime_rule["amount_fen"] == 20_000

    @pytest.mark.asyncio
    async def test_commission_total_is_sum_of_rules(self, agent):
        resp = await agent.execute("calculate_commission", {
            "role_id": "cashier",
            "metric_values": {"member_card": 30, "stored_value": 500_000},
        })
        data = resp.data
        expected_total = sum(
            r["amount_fen"] for r in data["rule_results"] if r["amount_fen"] is not None
        )
        assert data["total_commission_fen"] == expected_total

    @pytest.mark.asyncio
    async def test_invalid_role(self, agent):
        resp = await agent.execute("calculate_commission", {"role_id": "bad"})
        assert resp.success is True
        assert "error" in resp.data


class TestGetPerformanceReport:
    @pytest.mark.asyncio
    async def test_empty_role_results(self, agent):
        resp = await agent.execute("get_performance_report", {
            "store_id": "STORE001",
            "period": "2026-02",
            "role_results": [],
        })
        assert resp.success is True
        data = resp.data
        assert data["summary"]["roles_counted"] == 0
        assert data["summary"]["avg_total_score"] is None
        assert data["summary"]["total_commission_fen"] == 0

    @pytest.mark.asyncio
    async def test_with_injected_role_results(self, agent):
        role_results = [
            {"role_id": "store_manager", "total_score": 1.1, "total_commission_fen": 300_000},
            {"role_id": "waiter",        "total_score": 0.9, "total_commission_fen": 15_000},
        ]
        resp = await agent.execute("get_performance_report", {
            "store_id": "STORE001",
            "period": "2026-02",
            "role_results": role_results,
        })
        assert resp.success is True
        data = resp.data
        assert data["summary"]["roles_counted"] == 2
        assert data["summary"]["total_commission_fen"] == 315_000
        assert data["summary"]["avg_total_score"] == pytest.approx(1.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_generated_at_present(self, agent):
        resp = await agent.execute("get_performance_report", {})
        assert resp.success is True
        assert "generated_at" in resp.data


class TestExplainRule:
    @pytest.mark.asyncio
    async def test_list_all_rules_for_role(self, agent):
        resp = await agent.execute("explain_rule", {"role_id": "store_manager"})
        assert resp.success is True
        data = resp.data
        assert "rules" in data
        assert len(data["rules"]) == len(COMMISSION_RULES["store_manager"])

    @pytest.mark.asyncio
    async def test_explain_specific_rule(self, agent):
        resp = await agent.execute("explain_rule", {
            "role_id": "store_manager",
            "rule_name": "月度目标达成奖",
        })
        assert resp.success is True
        data = resp.data
        assert "steps" in data
        assert "desc" in data
        assert len(data["steps"]) > 0

    @pytest.mark.asyncio
    async def test_explain_tiered_rule(self, agent):
        resp = await agent.execute("explain_rule", {
            "role_id": "delivery",
            "rule_name": "单量提成",
        })
        assert resp.success is True
        assert "steps" in resp.data

    @pytest.mark.asyncio
    async def test_invalid_role(self, agent):
        resp = await agent.execute("explain_rule", {"role_id": "nobody"})
        assert resp.success is True
        assert "error" in resp.data

    @pytest.mark.asyncio
    async def test_rule_not_found(self, agent):
        resp = await agent.execute("explain_rule", {
            "role_id": "waiter",
            "rule_name": "不存在的规则",
        })
        assert resp.success is True
        assert "error" in resp.data
        assert "available" in resp.data

    @pytest.mark.asyncio
    async def test_all_roles_explain(self, agent):
        for role_id in COMMISSION_RULES:
            resp = await agent.execute("explain_rule", {"role_id": role_id})
            assert resp.success is True


class TestNLQuery:
    @pytest.mark.asyncio
    async def test_store_manager_commission(self, agent):
        resp = await agent.execute("nl_query", {
            "question": "店长本月提成多少钱",
            "metric_values": {"revenue": 32_000_000},
        })
        assert resp.success is True
        # dispatch → calculate_commission
        assert "rule_results" in resp.data

    @pytest.mark.asyncio
    async def test_waiter_performance(self, agent):
        resp = await agent.execute("nl_query", {
            "question": "服务员绩效得分是多少",
            "metric_values": {"avg_per_table": 16_000},
        })
        assert resp.success is True
        assert "metrics" in resp.data

    @pytest.mark.asyncio
    async def test_kitchen_config(self, agent):
        resp = await agent.execute("nl_query", {
            "question": "后厨岗位有哪些指标",
        })
        assert resp.success is True
        assert "metrics" in resp.data or "roles" in resp.data

    @pytest.mark.asyncio
    async def test_explain_dispatch(self, agent):
        resp = await agent.execute("nl_query", {
            "question": "解释一下提成计算方式",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_empty_question(self, agent):
        resp = await agent.execute("nl_query", {"question": ""})
        assert resp.success is True
        assert "error" in resp.data


class TestInvalidAction:
    @pytest.mark.asyncio
    async def test_unsupported_action(self, agent):
        resp = await agent.execute("fly_to_moon", {})
        assert resp.success is False
        assert "不支持" in resp.error

    def test_supported_actions_list(self, agent):
        actions = agent.get_supported_actions()
        assert "get_role_config" in actions
        assert "calculate_performance" in actions
        assert "calculate_commission" in actions
        assert "get_performance_report" in actions
        assert "explain_rule" in actions
        assert "nl_query" in actions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
