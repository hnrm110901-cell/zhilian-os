"""
推荐引擎单元测试
Tests for IntelligentRecommendationEngine

覆盖：
  - recommend_dishes: 正常推荐、top_k 边界、空菜品列表
  - optimize_pricing: 高峰定价、低峰定价、库存驱动定价
  - generate_marketing_campaign: acquisition / retention 目标
  - 评分公式权重之和验证（CF + CB + Context + Business = 1.0）
"""
import os
import sys

# ── 设置最小化测试环境变量，防止 AgentService 初始化失败 ──────────────────────
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

# ── 阻断 agent_service 全局初始化（不需要真实 Agent 启动）───────────────────
from unittest.mock import MagicMock as _MM
if "src.services.agent_service" not in sys.modules:
    sys.modules["src.services.agent_service"] = _MM()

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.recommendation_engine import (
    IntelligentRecommendationEngine,
    DishRecommendation,
    PricingRecommendation,
    MarketingCampaign,
    PricingStrategy,
    RecommendationType,
)


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def make_engine(db=None):
    """创建引擎实例，默认使用 MagicMock DB。"""
    return IntelligentRecommendationEngine(db=db or MagicMock())


def make_dish(dish_id="d1", name="测试菜", price=30.0, profit_margin=0.5,
              category="正餐", tags=None):
    return {
        "dish_id": dish_id,
        "name": name,
        "price": price,
        "profit_margin": profit_margin,
        "category": category,
        "tags": tags or [],
    }


# ── recommend_dishes ──────────────────────────────────────────────────────────

class TestRecommendDishes:

    @pytest.mark.asyncio
    async def test_normal_recommendation_returns_list(self):
        """正常流程：返回推荐列表，长度 <= top_k。"""
        engine = make_engine()
        dishes = [make_dish(f"d{i}", f"菜{i}") for i in range(10)]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=0.6)),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=5)

        assert isinstance(result, list)
        assert len(result) <= 5
        for rec in result:
            assert isinstance(rec, DishRecommendation)
            assert 0.0 <= rec.score <= 1.0

    @pytest.mark.asyncio
    async def test_top_k_boundary_returns_at_most_k(self):
        """top_k 边界：无论菜品多少，结果不超过 top_k。"""
        engine = make_engine()
        dishes = [make_dish(f"d{i}") for i in range(20)]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=0.5)),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=3)

        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_empty_dish_list_returns_empty(self):
        """空菜品列表时返回空结果。"""
        engine = make_engine()

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=[])),
        ):
            result = await engine.recommend_dishes("C001", "S001")

        assert result == []

    @pytest.mark.asyncio
    async def test_recently_ordered_dishes_are_skipped(self):
        """最近下单过的菜品应被跳过。"""
        engine = make_engine()
        dishes = [make_dish("d1"), make_dish("d2")]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            # 所有菜品都最近点过
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=True)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=0.8)),
        ):
            result = await engine.recommend_dishes("C001", "S001")

        assert result == []

    @pytest.mark.asyncio
    async def test_recommendations_sorted_by_score_descending(self):
        """推荐结果按得分降序排列。"""
        engine = make_engine()
        dishes = [make_dish(f"d{i}", profit_margin=0.1 * i) for i in range(5)]
        cf_scores = [0.9, 0.1, 0.5, 0.3, 0.7]
        cf_iter = iter(cf_scores)

        async def mock_cf(customer_id, dish_id):
            return next(cf_iter)

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=mock_cf),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=5)

        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)


# ── 评分公式权重验证 ──────────────────────────────────────────────────────────

class TestScoringFormula:

    def test_weight_env_vars_sum_to_one(self):
        """CF + CB + Context + Business 默认权重之和应等于 1.0。"""
        cf_w  = float(os.getenv("RECOMMEND_CF_WEIGHT", "0.3"))
        cb_w  = float(os.getenv("RECOMMEND_CB_WEIGHT", "0.3"))
        ctx_w = float(os.getenv("RECOMMEND_CONTEXT_WEIGHT", "0.2"))
        biz_w = float(os.getenv("RECOMMEND_BUSINESS_WEIGHT", "0.2"))
        assert abs(cf_w + cb_w + ctx_w + biz_w - 1.0) < 1e-9

    def test_content_based_score_with_no_history(self):
        """无历史订单时 CB 得分应为 0.5（中性）。"""
        engine = make_engine()
        score = engine._content_based_score([], make_dish(tags=["辣", "热菜"]))
        assert score == 0.5

    def test_context_score_time_boost_breakfast(self):
        """早餐时段早餐品类得分应高于基准。"""
        engine = make_engine()
        dish = make_dish(category="早餐")
        base = engine._context_score(dish, {"hour": 5})    # 非早餐时段
        boosted = engine._context_score(dish, {"hour": 7})  # 早餐时段
        assert boosted > base

    def test_business_score_high_margin(self):
        """高利润率菜品 business_score 应高于低利润率。"""
        engine = make_engine()
        low  = engine._business_score(make_dish(profit_margin=0.1), "S001")
        high = engine._business_score(make_dish(profit_margin=0.9), "S001")
        assert high > low


# ── optimize_pricing ──────────────────────────────────────────────────────────

class TestOptimizePricing:

    def _make_dish_data(self, price=50.0, inventory=100):
        return {
            "dish_id": "d1",
            "name": "招牌菜",
            "price": price,
            "profit_margin": 0.6,
            "category": "正餐",
            "tags": [],
            "inventory": inventory,
            "sales_velocity": 10.0,
        }

    @pytest.mark.asyncio
    async def test_peak_hour_pricing_increases_price(self):
        """高峰时段定价应推荐涨价。"""
        engine = make_engine()
        dish_data = self._make_dish_data()

        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 12, "is_peak": True}
            )

        assert isinstance(result, PricingRecommendation)
        assert result.strategy == PricingStrategy.PEAK_HOUR
        assert result.recommended_price >= result.current_price

    @pytest.mark.asyncio
    async def test_off_peak_pricing_decreases_price(self):
        """低峰时段定价应推荐降价促销（hour > 20 触发 OFF_PEAK 策略）。"""
        engine = make_engine()
        dish_data = self._make_dish_data()

        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 21}  # >20 → OFF_PEAK
            )

        assert isinstance(result, PricingRecommendation)
        assert result.strategy == PricingStrategy.OFF_PEAK
        assert result.recommended_price <= result.current_price

    @pytest.mark.asyncio
    async def test_inventory_based_pricing_for_high_stock(self):
        """高库存场景应触发库存定价策略（inventory_level 为 float > 0.8）。"""
        engine = make_engine()
        dish_data = self._make_dish_data(inventory=500)

        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 14, "inventory_level": 0.9}  # float 0.9 > 0.8
            )

        assert isinstance(result, PricingRecommendation)
        assert result.strategy == PricingStrategy.INVENTORY_BASED

    @pytest.mark.asyncio
    async def test_pricing_recommendation_has_required_fields(self):
        """返回对象包含所有必填字段。"""
        engine = make_engine()
        dish_data = self._make_dish_data()

        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing("S001", "d1")

        assert result.dish_id == "d1"
        assert result.current_price > 0
        assert isinstance(result.reason, str) and result.reason


# ── generate_marketing_campaign ───────────────────────────────────────────────

class TestGenerateMarketingCampaign:

    def _mock_segment_methods(self, engine, dishes=None):
        dishes = dishes if dishes is not None else [make_dish(f"d{i}") for i in range(3)]
        segment_data = {"size": 500, "avg_order_value": 80.0, "conversion_base": 0.15}

        engine._identify_target_segment = MagicMock(return_value="high_value")
        engine._get_segment_data = MagicMock(return_value=segment_data)
        engine._select_promotion_dishes = AsyncMock(return_value=dishes)
        engine._calculate_optimal_discount = MagicMock(return_value=0.15)
        engine._estimate_conversion_rate = MagicMock(return_value=0.20)
        engine._estimate_campaign_revenue = MagicMock(return_value=5000.0)
        engine._calculate_campaign_duration = MagicMock(return_value=7)
        engine._generate_campaign_reason = MagicMock(return_value="拉新活动：高价值用户专属折扣")

    @pytest.mark.asyncio
    async def test_acquisition_campaign(self):
        """新客获取目标应生成有效营销方案。"""
        engine = make_engine()
        self._mock_segment_methods(engine)

        result = await engine.generate_marketing_campaign(
            "S001", objective="acquisition", budget=2000.0
        )

        assert isinstance(result, MarketingCampaign)
        assert result.campaign_id.startswith("campaign_S001_")
        assert 0 < result.discount_rate < 1.0
        assert result.expected_revenue > 0
        assert result.duration_days > 0

    @pytest.mark.asyncio
    async def test_retention_campaign(self):
        """老客留存目标应选择合适的 segment 并生成方案。"""
        engine = make_engine()
        self._mock_segment_methods(engine)
        engine._identify_target_segment = MagicMock(return_value="lapsed")

        result = await engine.generate_marketing_campaign(
            "S001", objective="retention", budget=1000.0, target_segment="lapsed"
        )

        assert isinstance(result, MarketingCampaign)
        assert result.target_segment == "lapsed"
        assert len(result.dish_ids) > 0

    @pytest.mark.asyncio
    async def test_campaign_with_no_promoted_dishes_returns_empty_ids(self):
        """无可推广菜品时 dish_ids 应为空列表。"""
        engine = make_engine()
        self._mock_segment_methods(engine, dishes=[])

        result = await engine.generate_marketing_campaign(
            "S001", objective="acquisition", budget=500.0
        )

        assert result.dish_ids == []

    @pytest.mark.asyncio
    async def test_campaign_reason_is_non_empty(self):
        """营销方案理由字段不应为空。"""
        engine = make_engine()
        self._mock_segment_methods(engine)

        result = await engine.generate_marketing_campaign("S001", "acquisition", 1000.0)

        assert isinstance(result.reason, str) and len(result.reason) > 0


# ── 评分公式更详尽验证 ──────────────────────────────────────────────────────

class TestScoringFormulaDetailed:

    @pytest.mark.asyncio
    async def test_final_score_is_weighted_sum(self):
        """最终得分应严格等于 0.3*CF + 0.3*CB + 0.2*CTX + 0.2*BIZ。"""
        engine = make_engine()
        cf, cb, ctx, biz = 0.8, 0.6, 0.9, 0.4
        dishes = [make_dish("d1", profit_margin=0.5, tags=["辣"])]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=cf)),
            patch.object(engine, "_content_based_score", return_value=cb),
            patch.object(engine, "_context_score", return_value=ctx),
            patch.object(engine, "_business_score", return_value=biz),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=1)

        expected = 0.3 * cf + 0.3 * cb + 0.2 * ctx + 0.2 * biz
        assert len(result) == 1
        assert abs(result[0].score - expected) < 1e-9

    @pytest.mark.asyncio
    async def test_score_clipped_at_one(self):
        """所有子分数最大值时，最终得分不超过 1.0（加权和 ≤ 1.0）。"""
        engine = make_engine()
        dishes = [make_dish("d1")]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=1.0)),
            patch.object(engine, "_content_based_score", return_value=1.0),
            patch.object(engine, "_context_score", return_value=1.0),
            patch.object(engine, "_business_score", return_value=1.0),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=1)

        # 0.3+0.3+0.2+0.2 = 1.0 exactly
        assert result[0].score <= 1.0

    def test_content_based_score_with_matching_tags(self):
        """历史订单标签与菜品标签重合时，CB 得分应高于 0.5。"""
        engine = make_engine()
        history = [
            {"dish_id": "d1", "tags": ["辣", "热菜"]},
            {"dish_id": "d2", "tags": ["辣"]},
        ]
        dish = make_dish(tags=["辣", "热菜"])
        score = engine._content_based_score(history, dish)
        assert score > 0.5

    def test_content_based_score_no_tag_overlap(self):
        """历史订单标签与菜品标签完全不重合时，CB 得分仍为 0.4 基线。"""
        engine = make_engine()
        history = [{"dish_id": "d1", "tags": ["清淡"]}]
        dish = make_dish(tags=["辣"])
        score = engine._content_based_score(history, dish)
        assert abs(score - 0.4) < 1e-9

    def test_context_score_lunch_boost(self):
        """午餐时段正餐品类得分应高于基准。"""
        engine = make_engine()
        dish = make_dish(category="正餐")
        base = engine._context_score(dish, {"hour": 16})   # 非午餐
        boosted = engine._context_score(dish, {"hour": 12})  # 午餐
        assert boosted > base

    def test_context_score_weather_cold_hot_dish(self):
        """寒冷天气下热菜得分应提升。"""
        engine = make_engine()
        dish = make_dish(tags=["hot"])
        base = engine._context_score(dish, {"hour": 12, "weather": ""})
        cold = engine._context_score(dish, {"hour": 12, "weather": "cold"})
        assert cold > base

    @pytest.mark.asyncio
    async def test_confidence_is_min_of_cf_cb(self):
        """推荐结果的 confidence 应等于 min(cf_score, cb_score)。"""
        engine = make_engine()
        cf, cb = 0.7, 0.4
        dishes = [make_dish("d1")]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=cf)),
            patch.object(engine, "_content_based_score", return_value=cb),
            patch.object(engine, "_context_score", return_value=0.5),
            patch.object(engine, "_business_score", return_value=0.5),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=1)

        assert abs(result[0].confidence - min(cf, cb)) < 1e-9

    @pytest.mark.asyncio
    async def test_estimated_profit_equals_margin_times_price(self):
        """estimated_profit 应等于 profit_margin × price。"""
        engine = make_engine()
        dishes = [make_dish("d1", price=80.0, profit_margin=0.35)]

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=0.5)),
        ):
            result = await engine.recommend_dishes("C001", "S001", top_k=1)

        assert abs(result[0].estimated_profit - 80.0 * 0.35) < 1e-9


# ── 定价策略详细验证 ──────────────────────────────────────────────────────────

class TestPricingStrategyDetailed:

    @pytest.mark.asyncio
    async def test_demand_based_pricing_strategy(self):
        """非高峰非低谷时段且库存正常应触发 DEMAND_BASED 策略。"""
        engine = make_engine()
        dish_data = {
            "dish_id": "d1", "name": "招牌菜", "price": 50.0,
            "profit_margin": 0.6, "category": "正餐", "tags": [],
            "inventory": 100, "sales_velocity": 10.0,
        }
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 15}  # 15:00 非高峰
            )
        assert result.strategy == PricingStrategy.DEMAND_BASED

    @pytest.mark.asyncio
    async def test_demand_based_high_demand_increases_price(self):
        """高需求 (demand_level=0.9) 下 DEMAND_BASED 定价应涨价。"""
        engine = make_engine()
        dish_data = {"dish_id": "d1", "price": 50.0, "profit_margin": 0.6}
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 15, "demand_level": 0.9}
            )
        # 0.9 + 0.2*0.9 = 1.08 → 50*1.08 = 54.0
        assert result.recommended_price > result.current_price

    @pytest.mark.asyncio
    async def test_inventory_based_pricing_reduces_price(self):
        """库存过高 (>0.8) 时应降价促销。"""
        engine = make_engine()
        dish_data = {"dish_id": "d1", "price": 100.0, "profit_margin": 0.5}
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 14, "inventory_level": 0.95}
            )
        assert result.strategy == PricingStrategy.INVENTORY_BASED
        assert result.recommended_price < result.current_price

    @pytest.mark.asyncio
    async def test_peak_pricing_ratio_approximately_12_percent(self):
        """高峰定价默认涨幅约 12%。"""
        engine = make_engine()
        dish_data = {"dish_id": "d1", "price": 100.0, "profit_margin": 0.5}
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 12, "is_peak": True}
            )
        assert abs(result.recommended_price - 112.0) < 1.0

    @pytest.mark.asyncio
    async def test_off_peak_pricing_reduces_by_15_percent(self):
        """低峰定价默认降幅约 15%。"""
        engine = make_engine()
        dish_data = {"dish_id": "d1", "price": 100.0, "profit_margin": 0.5}
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing(
                "S001", "d1", context={"hour": 22}
            )
        assert abs(result.recommended_price - 85.0) < 1.0

    @pytest.mark.asyncio
    async def test_price_change_pct_is_correct(self):
        """price_change_pct 应等于 (推荐价-原价)/原价。"""
        engine = make_engine()
        dish_data = {"dish_id": "d1", "price": 50.0, "profit_margin": 0.5}
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            result = await engine.optimize_pricing("S001", "d1", context={"hour": 12})
        expected_pct = (result.recommended_price - 50.0) / 50.0
        assert abs(result.price_change_pct - expected_pct) < 1e-9


# ── 推荐理由生成 ──────────────────────────────────────────────────────────────

class TestRecommendationReason:

    def test_high_cf_score_includes_similar_customers(self):
        """CF 高分时理由应包含'相似顾客'。"""
        engine = make_engine()
        reason = engine._generate_recommendation_reason(
            make_dish(), cf_score=0.9, cb_score=0.1, context_score=0.1, business_score=0.1
        )
        assert "相似顾客" in reason

    def test_all_low_scores_returns_default_reason(self):
        """所有子分数都低时返回默认理由'为您精选'。"""
        engine = make_engine()
        reason = engine._generate_recommendation_reason(
            make_dish(), cf_score=0.3, cb_score=0.3, context_score=0.3, business_score=0.3
        )
        assert reason == "为您精选"

    def test_multiple_high_scores_joins_reasons(self):
        """多个子分数都高时理由应包含多个原因。"""
        engine = make_engine()
        reason = engine._generate_recommendation_reason(
            make_dish(), cf_score=0.9, cb_score=0.9, context_score=0.1, business_score=0.9
        )
        assert "、" in reason  # Chinese comma separator
        assert "相似顾客" in reason
        assert "口味偏好" in reason
