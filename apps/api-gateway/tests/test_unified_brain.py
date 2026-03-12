"""
Unified Brain 单元测试

覆盖：
  - generate_candidates: 各维度生成/不生成
  - _score_candidate: 得分计算
  - pick_top_decision: 选最优/无决策
  - format_push_message: 格式验证
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
from src.services.unified_brain import (
    ActionCard, BrainInput,
    generate_candidates, pick_top_decision,
    _score_candidate, format_push_message,
)


def _ctx(**overrides) -> BrainInput:
    defaults = dict(store_id="S001", date="2026-03-12")
    defaults.update(overrides)
    return BrainInput(**defaults)


class TestScoreCandidate:
    def test_critical_higher(self):
        c = ActionCard("t", "a", 1000, 80, "src", "critical")
        w = ActionCard("t", "a", 1000, 80, "src", "warning")
        assert _score_candidate(c) > _score_candidate(w)

    def test_higher_saving(self):
        a = ActionCard("t", "a", 5000, 70, "src", "warning")
        b = ActionCard("t", "a", 1000, 70, "src", "warning")
        assert _score_candidate(a) > _score_candidate(b)

    def test_higher_confidence(self):
        a = ActionCard("t", "a", 1000, 90, "src", "warning")
        b = ActionCard("t", "a", 1000, 50, "src", "warning")
        assert _score_candidate(a) > _score_candidate(b)

    def test_zero_saving(self):
        c = ActionCard("t", "a", 0, 80, "src", "critical")
        assert _score_candidate(c) == 0


class TestGenerateCandidates:
    def test_no_issues(self):
        ctx = _ctx()
        assert generate_candidates(ctx) == []

    def test_cost_overrun(self):
        ctx = _ctx(cost_variance_pct=3.0, cost_saving_yuan=12000, cost_top_factor="用量超标")
        candidates = generate_candidates(ctx)
        assert len(candidates) == 1
        assert candidates[0].source == "cost_truth"

    def test_labor_overrun(self):
        ctx = _ctx(labor_cost_rate=30.0, labor_target_rate=25.0, labor_saving_yuan=5000)
        candidates = generate_candidates(ctx)
        assert any(c.source == "labor_analysis" for c in candidates)

    def test_inventory_critical(self):
        ctx = _ctx(
            critical_inventory_count=2,
            inventory_items=[{"name": "鲈鱼"}, {"name": "五花肉"}],
            inventory_risk_yuan=8000,
        )
        candidates = generate_candidates(ctx)
        inv = [c for c in candidates if c.source == "inventory_alert"]
        assert len(inv) == 1
        assert inv[0].severity == "critical"
        assert inv[0].deadline_hours == 4

    def test_waste_high(self):
        ctx = _ctx(waste_rate_pct=5.0, waste_target_pct=3.0, waste_top_item="鲈鱼", waste_saving_yuan=4000)
        candidates = generate_candidates(ctx)
        assert any(c.source == "waste_guard" for c in candidates)

    def test_revenue_drop(self):
        ctx = _ctx(revenue_change_pct=-20, revenue_yesterday_yuan=20000)
        candidates = generate_candidates(ctx)
        assert any(c.source == "revenue_analysis" for c in candidates)

    def test_revenue_drop_small_ignored(self):
        ctx = _ctx(revenue_change_pct=-10, revenue_yesterday_yuan=20000)
        candidates = generate_candidates(ctx)
        assert not any(c.source == "revenue_analysis" for c in candidates)

    def test_multiple_candidates(self):
        ctx = _ctx(
            cost_variance_pct=3.5, cost_saving_yuan=12000,
            labor_cost_rate=31.0, labor_target_rate=25.0, labor_saving_yuan=5000,
            waste_rate_pct=5.5, waste_target_pct=3.0, waste_top_item="鱼", waste_saving_yuan=4000,
        )
        candidates = generate_candidates(ctx)
        assert len(candidates) == 3


class TestPickTopDecision:
    def test_picks_highest_score(self):
        ctx = _ctx(
            cost_variance_pct=3.5, cost_saving_yuan=12000, cost_top_factor="usage",
            waste_rate_pct=5.0, waste_target_pct=3.0, waste_top_item="鱼", waste_saving_yuan=2000,
        )
        card = pick_top_decision(ctx)
        assert card is not None
        # cost saving 12000 × 0.75 × 2.0=18000 > waste 2000 × 0.70 × 1.5=2100
        assert card.source == "cost_truth"

    def test_inventory_wins_when_critical(self):
        ctx = _ctx(
            cost_variance_pct=2.5, cost_saving_yuan=5000,
            critical_inventory_count=3,
            inventory_items=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
            inventory_risk_yuan=15000,
        )
        card = pick_top_decision(ctx)
        assert card is not None
        assert card.source == "inventory_alert"

    def test_no_decision_when_ok(self):
        ctx = _ctx()
        assert pick_top_decision(ctx) is None


class TestFormatPushMessage:
    def test_contains_key_fields(self):
        card = ActionCard("成本超标", "检查切配", 12800, 75, "test", "critical")
        msg = format_push_message(card, cumulative_saving_yuan=18400)
        assert "成本超标" in msg
        assert "检查切配" in msg
        assert "12,800" in msg
        assert "75%" in msg
        assert "18,400" in msg

    def test_no_cumulative(self):
        card = ActionCard("测试", "操作", 1000, 60, "t", "warning")
        msg = format_push_message(card, 0)
        assert "累计" not in msg
