"""
MenuRanker 服务层单元测试

覆盖：
- _calc_trend_score: 零基准、上升趋势、下降趋势、边界归一化
- _calc_margin_score: 零价格、全毛利、部分毛利
- _calc_stock_score: 充裕库存、不足库存、临界比率
- _calc_time_slot_score: 午市/晚市/早市/非高峰
- _calc_low_refund_score: 零退单、10%退单、超高退单截断
- _generate_highlight: 各因子触发条件
- DishScore.compute_total: 加权公式验证
- rank(): 无DB返回空列表；Redis缓存命中走缓存路径
- invalidate_cache(): 有/无Redis均不抛异常
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from src.services.menu_ranker import MenuRanker, _current_time_slot
from src.models.menu_rank import DishScore, RankedDish


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ranker(db=None, redis=None) -> MenuRanker:
    return MenuRanker(db_session=db, redis_client=redis)


def _dish(**kwargs):
    """构造菜品数据字典，提供合理默认值"""
    defaults = {
        "dish_id": "D001",
        "dish_name": "测试菜品",
        "price": 50.0,
        "cost": 20.0,
        "current_stock": 30,
        "min_stock": 10,
        "recent_sales": 20,
        "prev_sales": 10,
        "refund_rate": 0.02,
        "lunch_sales_pct": 0.6,
        "dinner_sales_pct": 0.3,
    }
    defaults.update(kwargs)
    return defaults


def _scored_dish(**kwargs) -> DishScore:
    d = _dish(**kwargs)
    r = _ranker()
    return DishScore(
        dish_id=d["dish_id"],
        dish_name=d["dish_name"],
        trend_score=r._calc_trend_score(d),
        margin_score=r._calc_margin_score(d),
        stock_score=r._calc_stock_score(d),
        time_slot_score=r._calc_time_slot_score(d, "lunch"),
        low_refund_score=r._calc_low_refund_score(d),
    ).compute_total()


# ---------------------------------------------------------------------------
# _calc_trend_score
# ---------------------------------------------------------------------------

class TestCalcTrendScore:
    def test_zero_prev_sales_returns_midpoint(self):
        r = _ranker()
        assert r._calc_trend_score(_dish(prev_sales=0)) == 0.5

    def test_positive_trend_above_midpoint(self):
        r = _ranker()
        score = r._calc_trend_score(_dish(recent_sales=20, prev_sales=10))
        assert score > 0.5

    def test_negative_trend_below_midpoint(self):
        r = _ranker()
        score = r._calc_trend_score(_dish(recent_sales=5, prev_sales=10))
        assert score < 0.5

    def test_score_clamped_to_one(self):
        r = _ranker()
        score = r._calc_trend_score(_dish(recent_sales=10000, prev_sales=1))
        assert score == 1.0

    def test_score_clamped_to_zero(self):
        r = _ranker()
        score = r._calc_trend_score(_dish(recent_sales=0, prev_sales=100))
        assert score == 0.0

    def test_equal_sales_returns_midpoint(self):
        r = _ranker()
        score = r._calc_trend_score(_dish(recent_sales=10, prev_sales=10))
        assert score == 0.5


# ---------------------------------------------------------------------------
# _calc_margin_score
# ---------------------------------------------------------------------------

class TestCalcMarginScore:
    def test_zero_price_returns_default(self):
        r = _ranker()
        assert r._calc_margin_score(_dish(price=0)) == 0.3

    def test_full_margin_returns_one(self):
        r = _ranker()
        assert r._calc_margin_score(_dish(price=100, cost=0)) == 1.0

    def test_half_margin(self):
        r = _ranker()
        score = r._calc_margin_score(_dish(price=100, cost=50))
        assert abs(score - 0.5) < 1e-9

    def test_negative_cost_does_not_exceed_one(self):
        r = _ranker()
        score = r._calc_margin_score(_dish(price=50, cost=-10))
        assert score <= 1.0

    def test_cost_exceeds_price_returns_zero(self):
        r = _ranker()
        score = r._calc_margin_score(_dish(price=30, cost=50))
        assert score == 0.0


# ---------------------------------------------------------------------------
# _calc_stock_score
# ---------------------------------------------------------------------------

class TestCalcStockScore:
    def test_ample_stock_returns_one(self):
        r = _ranker()
        assert r._calc_stock_score(_dish(current_stock=300, min_stock=10)) == 1.0

    def test_exactly_3x_min_returns_one(self):
        r = _ranker()
        assert r._calc_stock_score(_dish(current_stock=30, min_stock=10)) == 1.0

    def test_half_min_returns_zero(self):
        r = _ranker()
        assert r._calc_stock_score(_dish(current_stock=5, min_stock=10)) == 0.0

    def test_zero_min_stock_returns_one(self):
        r = _ranker()
        assert r._calc_stock_score(_dish(current_stock=0, min_stock=0)) == 1.0

    def test_between_half_and_3x_is_partial(self):
        r = _ranker()
        score = r._calc_stock_score(_dish(current_stock=15, min_stock=10))
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# _calc_time_slot_score
# ---------------------------------------------------------------------------

class TestCalcTimeSlotScore:
    def test_lunch_uses_lunch_pct(self):
        r = _ranker()
        dish = _dish(lunch_sales_pct=0.7)
        assert r._calc_time_slot_score(dish, "lunch") == pytest.approx(0.7)

    def test_dinner_uses_dinner_pct(self):
        r = _ranker()
        dish = _dish(dinner_sales_pct=0.8)
        assert r._calc_time_slot_score(dish, "dinner") == pytest.approx(0.8)

    def test_off_peak_returns_fixed_value(self):
        r = _ranker()
        assert r._calc_time_slot_score(_dish(), "off_peak") == 0.3

    def test_breakfast_returns_fixed_default(self):
        r = _ranker()
        score = r._calc_time_slot_score(_dish(), "breakfast")
        assert score == 0.3  # breakfast_sales_pct not in dish → default 0.3


# ---------------------------------------------------------------------------
# _calc_low_refund_score
# ---------------------------------------------------------------------------

class TestCalcLowRefundScore:
    def test_zero_refund_returns_one(self):
        r = _ranker()
        assert r._calc_low_refund_score(_dish(refund_rate=0.0)) == 1.0

    def test_ten_percent_refund_returns_zero(self):
        r = _ranker()
        assert r._calc_low_refund_score(_dish(refund_rate=0.1)) == pytest.approx(0.0)

    def test_five_percent_refund_returns_half(self):
        r = _ranker()
        assert r._calc_low_refund_score(_dish(refund_rate=0.05)) == pytest.approx(0.5)

    def test_high_refund_clamped_to_zero(self):
        r = _ranker()
        assert r._calc_low_refund_score(_dish(refund_rate=0.5)) == 0.0


# ---------------------------------------------------------------------------
# _generate_highlight
# ---------------------------------------------------------------------------

class TestGenerateHighlight:
    def test_high_trend_returns_rising_label(self):
        r = _ranker()
        score = _scored_dish(recent_sales=100, prev_sales=10)
        score.trend_score = 0.9
        assert r._generate_highlight(score, _dish()) == "销量持续上升"

    def test_high_margin_returns_margin_label(self):
        r = _ranker()
        score = _scored_dish()
        score.trend_score = 0.5
        score.margin_score = 0.85
        assert r._generate_highlight(score, _dish()) == "高毛利推荐"

    def test_high_stock_returns_stock_label(self):
        r = _ranker()
        score = _scored_dish()
        score.trend_score = 0.5
        score.margin_score = 0.5
        score.stock_score = 0.95
        assert r._generate_highlight(score, _dish()) == "库存充足"

    def test_high_low_refund_returns_satisfaction_label(self):
        r = _ranker()
        score = _scored_dish()
        score.trend_score = 0.5
        score.margin_score = 0.5
        score.stock_score = 0.5
        score.low_refund_score = 0.95
        assert r._generate_highlight(score, _dish()) == "顾客满意度高"

    def test_average_scores_returns_none(self):
        r = _ranker()
        score = _scored_dish()
        score.trend_score = 0.5
        score.margin_score = 0.5
        score.stock_score = 0.5
        score.low_refund_score = 0.5
        assert r._generate_highlight(score, _dish()) is None


# ---------------------------------------------------------------------------
# DishScore.compute_total
# ---------------------------------------------------------------------------

class TestDishScoreComputeTotal:
    def test_all_zero_scores_total_zero(self):
        s = DishScore(dish_id="D1", dish_name="测试",
                      trend_score=0, margin_score=0, stock_score=0,
                      time_slot_score=0, low_refund_score=0).compute_total()
        assert s.total_score == 0.0

    def test_all_one_scores_total_one(self):
        s = DishScore(dish_id="D1", dish_name="测试",
                      trend_score=1, margin_score=1, stock_score=1,
                      time_slot_score=1, low_refund_score=1).compute_total()
        assert s.total_score == 1.0

    def test_weights_sum_to_one(self):
        # 验证：0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.0
        assert 0.30 + 0.25 + 0.20 + 0.15 + 0.10 == pytest.approx(1.0)

    def test_explicit_calculation(self):
        s = DishScore(dish_id="D1", dish_name="测试",
                      trend_score=0.8, margin_score=0.6, stock_score=0.4,
                      time_slot_score=0.5, low_refund_score=0.9).compute_total()
        expected = round(0.8 * 0.30 + 0.6 * 0.25 + 0.4 * 0.20 + 0.5 * 0.15 + 0.9 * 0.10, 4)
        assert s.total_score == expected


# ---------------------------------------------------------------------------
# MenuRanker.rank() — no DB
# ---------------------------------------------------------------------------

class TestRankNoDb:
    @pytest.mark.asyncio
    async def test_no_db_returns_empty_list(self):
        r = _ranker()
        result = await r.rank("STORE_001")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_db_with_limit_returns_empty_list(self):
        r = _ranker()
        result = await r.rank("STORE_001", limit=5)
        assert result == []


# ---------------------------------------------------------------------------
# MenuRanker.rank() — Redis cache hit
# ---------------------------------------------------------------------------

class TestRankCacheHit:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self):
        cached = [RankedDish(
            rank=1, dish_id="D001", dish_name="红烧肉",
            score=DishScore(dish_id="D001", dish_name="红烧肉",
                            trend_score=0.9, margin_score=0.8,
                            stock_score=0.7, time_slot_score=0.6,
                            low_refund_score=1.0, total_score=0.83),
        )]
        raw = json.dumps([d.model_dump() for d in cached], default=str)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=raw)

        r = _ranker(redis=redis_mock)
        result = await r.rank("STORE_001", limit=5)

        assert len(result) == 1
        assert result[0].dish_id == "D001"
        redis_mock.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_respects_limit(self):
        cached = [
            RankedDish(rank=i, dish_id=f"D00{i}", dish_name=f"菜品{i}",
                       score=DishScore(dish_id=f"D00{i}", dish_name=f"菜品{i}",
                                       total_score=0.5))
            for i in range(1, 6)
        ]
        raw = json.dumps([d.model_dump() for d in cached], default=str)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=raw)

        r = _ranker(redis=redis_mock)
        result = await r.rank("STORE_001", limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# MenuRanker.invalidate_cache()
# ---------------------------------------------------------------------------

class TestInvalidateCache:
    @pytest.mark.asyncio
    async def test_invalidate_with_redis_calls_delete(self):
        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()
        r = _ranker(redis=redis_mock)
        await r.invalidate_cache("STORE_001")
        redis_mock.delete.assert_awaited_once_with("menu_rank:STORE_001")

    @pytest.mark.asyncio
    async def test_invalidate_without_redis_does_not_raise(self):
        r = _ranker()
        await r.invalidate_cache("STORE_001")  # should not raise
