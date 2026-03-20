"""帕累托寻优器 + HPI爆品评分 + 伪爆品鉴别 测试"""
import os
import pytest
from datetime import date

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from src.services.pareto_optimizer_service import (
    DishCandidate, ParetoOptimizerService,
    dominates, find_pareto_front, compute_weighted_score,
    normalize_score, invert_complexity, label_solution, describe_tradeoff,
    DEFAULT_WEIGHTS,
)
from src.services.hit_potential_service import (
    DishPerformance, HitPotentialService,
    compute_hpi, grade_hpi, detect_fake_hit,
    calc_order_rate, calc_repurchase_rate, calc_margin_hit,
    calc_low_return, calc_efficiency, calc_ticket_lift,
)


# ═══════════════════════════════════════════════════════════════
#  帕累托寻优器测试
# ═══════════════════════════════════════════════════════════════

class TestParetoBasics:

    def test_normalize_score(self):
        assert normalize_score(50) == 0.5
        assert normalize_score(0) == 0.0
        assert normalize_score(100) == 1.0
        assert normalize_score(120) == 1.0  # 上限截断

    def test_invert_complexity(self):
        assert invert_complexity(20) == 80
        assert invert_complexity(100) == 0
        assert invert_complexity(0) == 100

    def test_dominates_clear_winner(self):
        a = DishCandidate("a", "菜A", 90, 80, 20, 85, 70)
        b = DishCandidate("b", "菜B", 70, 60, 50, 60, 50)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_dominates_no_domination(self):
        """各有优势，互不支配"""
        a = DishCandidate("a", "菜A", 90, 50, 30, 80, 60)  # 口味好但毛利低
        b = DishCandidate("b", "菜B", 60, 85, 30, 80, 60)  # 毛利好但口味差
        assert dominates(a, b) is False
        assert dominates(b, a) is False

    def test_find_pareto_front(self):
        c1 = DishCandidate("1", "口味型", 95, 55, 40, 70, 80)
        c2 = DishCandidate("2", "利润型", 60, 85, 25, 80, 50)
        c3 = DishCandidate("3", "平衡型", 75, 70, 30, 75, 65)
        c4 = DishCandidate("4", "劣势型", 50, 50, 60, 50, 40)  # 被支配

        front = find_pareto_front([c1, c2, c3, c4])
        front_ids = {c.candidate_id for c in front}
        assert "4" not in front_ids  # 劣势型被支配
        assert "1" in front_ids
        assert "2" in front_ids

    def test_empty_candidates(self):
        assert find_pareto_front([]) == []


class TestParetoService:

    def setup_method(self):
        self.svc = ParetoOptimizerService()
        self.candidates = [
            DishCandidate("1", "剁椒鱼头", 92, 62, 45, 75, 85,
                          bom_cost_yuan=28, suggested_price_yuan=78),
            DishCandidate("2", "小炒黄牛肉", 85, 75, 30, 80, 60,
                          bom_cost_yuan=22, suggested_price_yuan=88),
            DishCandidate("3", "松露蒸蛋", 78, 82, 15, 55, 70,
                          bom_cost_yuan=12, suggested_price_yuan=68),
            DishCandidate("4", "凉拌折耳根", 65, 88, 10, 90, 45,
                          bom_cost_yuan=5, suggested_price_yuan=38),
            DishCandidate("5", "失败菜", 30, 30, 80, 30, 20,
                          bom_cost_yuan=35, suggested_price_yuan=48),
        ]

    def test_optimize_returns_sorted(self):
        results = self.svc.optimize(self.candidates, top_n=3)
        assert len(results) == 3
        assert results[0].rank == 1
        assert results[0].weighted_score >= results[1].weighted_score

    def test_optimize_labels_unique(self):
        results = self.svc.optimize(self.candidates, top_n=5)
        # 至少应有不同的标签
        labels = {r.label for r in results}
        assert len(labels) >= 2

    def test_optimize_with_custom_weights(self):
        """偏好毛利时，高毛利方案排名靠前"""
        margin_weights = {"F": 0.1, "M": 0.6, "X": 0.1, "S": 0.1, "R": 0.1}
        results = self.svc.optimize(self.candidates, weights=margin_weights, top_n=3)
        # 前两名应该是毛利率高的
        top2_margins = [r.candidate.margin_pct for r in results[:2]]
        assert min(top2_margins) >= 75  # 凉拌折耳根88 或 松露蒸蛋82

    def test_optimize_tradeoff_description(self):
        results = self.svc.optimize(self.candidates, top_n=3)
        for r in results:
            assert r.tradeoff_description  # 非空
            assert "突出" in r.tradeoff_description

    def test_optimize_dimension_scores(self):
        results = self.svc.optimize(self.candidates, top_n=1)
        ds = results[0].dimension_scores
        assert "F_flavor" in ds
        assert "M_margin" in ds
        assert "X_complexity" in ds
        assert "S_supply" in ds
        assert "R_repurchase" in ds

    def test_build_candidate(self):
        c = self.svc.build_candidate_from_cost_model(
            dish_name="测试菜", recipe_version_id="rv_001",
            bom_cost_yuan=20, suggested_price_yuan=68,
            prep_steps=6, skill_level=3, equipment_count=2,
            supply_availability=90, substitute_count=3,
            category_repurchase_rate=35, flavor_score=80,
        )
        assert c.margin_pct == pytest.approx(70.6, abs=1)
        assert 0 <= c.complexity_score <= 100
        assert 0 <= c.supply_score <= 100


# ═══════════════════════════════════════════════════════════════
#  HPI 爆品评分测试
# ═══════════════════════════════════════════════════════════════

class TestHPICalc:

    def test_order_rate_high(self):
        p = DishPerformance("d1", "菜A", "b1", total_orders=100, dish_order_count=15)
        assert calc_order_rate(p) == pytest.approx(100, abs=50)  # 15% 点单率

    def test_order_rate_zero(self):
        p = DishPerformance("d1", "菜A", "b1", total_orders=0)
        assert calc_order_rate(p) == 0.0

    def test_repurchase_rate(self):
        p = DishPerformance("d1", "菜A", "b1", unique_customers=100, repeat_customers=30)
        assert calc_repurchase_rate(p) == 100.0  # 30% = 满分

    def test_margin_hit_good(self):
        p = DishPerformance("d1", "菜A", "b1",
                            revenue_yuan=100, cost_yuan=30, target_margin_pct=65)
        assert calc_margin_hit(p) == 100.0  # 70% > 65%

    def test_margin_hit_bad(self):
        p = DishPerformance("d1", "菜A", "b1",
                            revenue_yuan=100, cost_yuan=60, target_margin_pct=65)
        assert calc_margin_hit(p) == 10.0  # 40% << 65%

    def test_low_return_excellent(self):
        p = DishPerformance("d1", "菜A", "b1", dish_order_count=200, return_count=2)
        assert calc_low_return(p) == 100.0  # 1%

    def test_grade_hpi(self):
        assert grade_hpi(85) == "爆品苗子"
        assert grade_hpi(65) == "潜力股"
        assert grade_hpi(45) == "平庸品"
        assert grade_hpi(30) == "失败品"


class TestHPIService:

    def setup_method(self):
        self.svc = HitPotentialService()

    def test_evaluate_hit(self):
        perf = DishPerformance(
            "d1", "剁椒鱼头", "b1", period_days=7,
            launch_date=date(2026, 3, 10),
            total_orders=500, dish_order_count=80,
            unique_customers=60, repeat_customers=20,
            positive_feedback_count=15, total_feedback_count=18,
            return_count=1, complaint_count=0,
            revenue_yuan=6240, cost_yuan=1800, target_margin_pct=65,
            avg_ticket_with_dish=120, avg_ticket_without_dish=95,
            avg_prep_time_minutes=12, target_prep_time_minutes=15,
        )
        result = self.svc.evaluate(perf)
        assert result.hpi_score >= 70
        assert result.grade in ("爆品苗子", "潜力股")
        assert not result.is_fake_hit
        assert result.days_since_launch is not None

    def test_evaluate_failure(self):
        perf = DishPerformance(
            "d2", "失败菜", "b1", period_days=7,
            total_orders=500, dish_order_count=5,
            unique_customers=5, repeat_customers=0,
            positive_feedback_count=1, total_feedback_count=5,
            return_count=2, complaint_count=1,
            revenue_yuan=190, cost_yuan=120, target_margin_pct=65,
        )
        result = self.svc.evaluate(perf)
        assert result.hpi_score < 40
        assert result.grade == "失败品"


# ═══════════════════════════════════════════════════════════════
#  伪爆品鉴别测试
# ═══════════════════════════════════════════════════════════════

class TestFakeHit:

    def test_genuine_hit(self):
        perf = DishPerformance(
            "d1", "真爆品", "b1",
            dish_order_count=200, unique_customers=150, repeat_customers=50,
            revenue_yuan=15600, cost_yuan=4500, target_margin_pct=65,
            return_count=3, complaint_count=1,
            discount_order_count=30, full_price_order_count=170,
        )
        is_fake, reasons = detect_fake_hit(perf)
        assert not is_fake
        assert len(reasons) == 0

    def test_discount_dependent(self):
        perf = DishPerformance(
            "d2", "折扣依赖品", "b1",
            dish_order_count=200, unique_customers=150, repeat_customers=8,
            revenue_yuan=15600, cost_yuan=9000, target_margin_pct=65,
            return_count=25, complaint_count=0,
            discount_order_count=160, full_price_order_count=40,
        )
        is_fake, reasons = detect_fake_hit(perf)
        assert is_fake  # 折扣依赖 + 低毛利 + 高退菜 + 低复购 = 4个命中
        assert len(reasons) >= 2
        assert any("折扣" in r for r in reasons)

    def test_low_margin_fake(self):
        perf = DishPerformance(
            "d3", "赔钱赚吆喝", "b1",
            dish_order_count=300, unique_customers=200, repeat_customers=5,
            revenue_yuan=12000, cost_yuan=8000, target_margin_pct=65,
            return_count=5, complaint_count=0,
            discount_order_count=200, full_price_order_count=100,
        )
        is_fake, reasons = detect_fake_hit(perf)
        assert is_fake
        assert any("毛利" in r for r in reasons)

    def test_batch_evaluate_with_fake(self):
        svc = HitPotentialService()
        perfs = [
            DishPerformance("d1", "真爆品", "b1",
                            total_orders=500, dish_order_count=80,
                            unique_customers=60, repeat_customers=20,
                            positive_feedback_count=15, total_feedback_count=18,
                            return_count=1, revenue_yuan=6240, cost_yuan=1800,
                            discount_order_count=10, full_price_order_count=70),
            DishPerformance("d2", "伪爆品", "b1",
                            total_orders=500, dish_order_count=100,
                            unique_customers=80, repeat_customers=3,
                            positive_feedback_count=5, total_feedback_count=20,
                            return_count=15, revenue_yuan=5000, cost_yuan=3500,
                            discount_order_count=80, full_price_order_count=20),
        ]
        results = svc.batch_evaluate(perfs, sort_by="fake_first")
        assert results[0].is_fake_hit  # 伪爆品排第一
