"""
海鲜损耗预测 AI 模型测试
"""

import pytest
from datetime import date

from src.services.seafood_loss_predictor import (
    SeafoodLossPredictor,
    _mean,
    _std,
    _simple_linear_regression,
)


@pytest.fixture
def predictor():
    return SeafoodLossPredictor()


# ── 辅助函数测试 ─────────────────────────────────────────────────────────


class TestHelperFunctions:
    def test_mean_normal(self):
        assert _mean([1.0, 2.0, 3.0]) == 2.0

    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_std_normal(self):
        result = _std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert 2.0 < result < 2.2  # 标准差约 2.14

    def test_std_single_value(self):
        assert _std([5.0]) == 0.0

    def test_linear_regression_positive_slope(self):
        slope, intercept = _simple_linear_regression(
            [1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]
        )
        assert abs(slope - 2.0) < 0.01
        assert abs(intercept - 0.0) < 0.01


# ── predict_daily_loss 测试 ──────────────────────────────────────────────


class TestPredictDailyLoss:
    def test_zero_stock_returns_zero(self, predictor):
        """库存为0时预测死亡数为0"""
        result = predictor.predict_daily_loss(
            species="波士顿龙虾", current_stock=0, season="summer",
            tank_temp=12.0, days_in_tank=1, historical_mortality_rates=[],
        )
        assert result.predicted_deaths == 0
        assert result.loss_amount_fen == 0
        assert result.risk_level == "低"

    def test_normal_prediction(self, predictor):
        """正常预测返回合理范围"""
        result = predictor.predict_daily_loss(
            species="波士顿龙虾", current_stock=100, season="7",
            tank_temp=12.0, days_in_tank=3,
            historical_mortality_rates=[0.005, 0.006, 0.007, 0.008],
            unit_price_fen=15000,
        )
        assert result.predicted_deaths >= 0
        assert result.predicted_deaths <= 100
        assert result.loss_amount_fen == result.predicted_deaths * 15000
        assert result.loss_amount_yuan == round(result.loss_amount_fen / 100, 2)
        assert result.confidence > 0.5

    def test_high_temp_increases_mortality(self, predictor):
        """高温偏离增加死亡率"""
        normal = predictor.predict_daily_loss(
            species="波士顿龙虾", current_stock=100, season="6",
            tank_temp=12.0, days_in_tank=1, historical_mortality_rates=[],
        )
        hot = predictor.predict_daily_loss(
            species="波士顿龙虾", current_stock=100, season="6",
            tank_temp=25.0, days_in_tank=1, historical_mortality_rates=[],
        )
        assert hot.mortality_rate >= normal.mortality_rate

    def test_longer_days_increases_mortality(self, predictor):
        """存放天数越长死亡率越高"""
        day1 = predictor.predict_daily_loss(
            species="基围虾", current_stock=200, season="6",
            tank_temp=20.0, days_in_tank=1, historical_mortality_rates=[],
        )
        day5 = predictor.predict_daily_loss(
            species="基围虾", current_stock=200, season="6",
            tank_temp=20.0, days_in_tank=5, historical_mortality_rates=[],
        )
        assert day5.mortality_rate > day1.mortality_rate

    def test_summer_higher_than_winter(self, predictor):
        """夏季死亡率高于冬季"""
        summer = predictor.predict_daily_loss(
            species="石斑鱼", current_stock=50, season="7",
            tank_temp=20.0, days_in_tank=1, historical_mortality_rates=[],
        )
        winter = predictor.predict_daily_loss(
            species="石斑鱼", current_stock=50, season="1",
            tank_temp=20.0, days_in_tank=1, historical_mortality_rates=[],
        )
        assert summer.factors["season_coeff"] > winter.factors["season_coeff"]

    def test_risk_level_classification(self, predictor):
        """风险等级分类正确"""
        result = predictor.predict_daily_loss(
            species="鲍鱼", current_stock=50, season="6",
            tank_temp=17.0, days_in_tank=1, historical_mortality_rates=[],
        )
        assert result.risk_level in ("低", "中", "高", "极高")

    def test_unknown_species_uses_default(self, predictor):
        """未知品种使用默认死亡率"""
        result = predictor.predict_daily_loss(
            species="未知鱼种", current_stock=100, season="6",
            tank_temp=18.0, days_in_tank=1, historical_mortality_rates=[],
        )
        assert result.predicted_deaths >= 0


# ── optimize_purchase_quantity 测试 ──────────────────────────────────────


class TestOptimizePurchaseQuantity:
    def test_sufficient_stock_no_purchase(self, predictor):
        """库存充足时不建议采购"""
        result = predictor.optimize_purchase_quantity(
            species="波士顿龙虾", daily_demand=5, current_stock=100,
            predicted_loss=1, lead_days=2, unit_price_fen=15000,
        )
        assert result.recommended_qty == 0
        assert "足够" in result.reasoning

    def test_low_stock_recommends_purchase(self, predictor):
        """库存不足时建议采购"""
        result = predictor.optimize_purchase_quantity(
            species="波士顿龙虾", daily_demand=10, current_stock=5,
            predicted_loss=2, lead_days=3, unit_price_fen=15000,
        )
        assert result.recommended_qty > 0
        assert result.cost_estimate_fen == result.recommended_qty * 15000
        assert result.cost_estimate_yuan == round(result.cost_estimate_fen / 100, 2)


# ── get_high_risk_species 测试 ───────────────────────────────────────────


class TestHighRiskSpecies:
    def test_returns_sorted_by_risk(self, predictor):
        """返回按风险排序的列表"""
        tank_data = [
            {"species": "鲍鱼", "current_stock": 50, "tank_temp": 17.0,
             "days_in_tank": 1, "unit_price_fen": 5000},
            {"species": "皮皮虾", "current_stock": 100, "tank_temp": 30.0,
             "days_in_tank": 5, "unit_price_fen": 8000},
        ]
        result = predictor.get_high_risk_species(tank_data)
        assert len(result) == 2
        # 皮皮虾（高温+长天数）风险应该更高
        assert result[0].risk_score >= result[1].risk_score

    def test_empty_stock_skipped(self, predictor):
        """库存为0的跳过"""
        tank_data = [
            {"species": "鲈鱼", "current_stock": 0, "tank_temp": 18.0,
             "days_in_tank": 1, "unit_price_fen": 3000},
        ]
        result = predictor.get_high_risk_species(tank_data)
        assert len(result) == 0


# ── generate_loss_report 测试 ────────────────────────────────────────────


class TestLossReport:
    def test_empty_records(self, predictor):
        """空记录生成基础报告"""
        report = predictor.generate_loss_report([], 7)
        assert report.total_deaths == 0
        assert report.total_loss_fen == 0
        assert report.worst_species == "无"

    def test_report_with_data(self, predictor):
        """有数据时正确汇总"""
        records = [
            {"species": "波士顿龙虾", "date": "2026-03-20", "deaths": 2, "loss_fen": 30000, "reason": "水质异常"},
            {"species": "波士顿龙虾", "date": "2026-03-21", "deaths": 3, "loss_fen": 45000, "reason": "水质异常"},
            {"species": "基围虾", "date": "2026-03-20", "deaths": 5, "loss_fen": 10000, "reason": "存放过久"},
        ]
        report = predictor.generate_loss_report(records, 7)
        assert report.total_deaths == 10
        assert report.total_loss_fen == 85000
        assert report.total_loss_yuan == 850.0
        assert len(report.by_species) == 2
        # 波士顿龙虾损耗金额更高，排第一
        assert report.by_species[0].species == "波士顿龙虾"
        assert report.worst_species == "波士顿龙虾"

    def test_report_suggestions_generated(self, predictor):
        """报告包含改进建议"""
        records = [
            {"species": "花甲", "date": "2026-03-20", "deaths": 10, "loss_fen": 5000, "reason": "水质异常"},
            {"species": "花甲", "date": "2026-03-21", "deaths": 12, "loss_fen": 6000, "reason": "水质异常"},
            {"species": "花甲", "date": "2026-03-22", "deaths": 15, "loss_fen": 7500, "reason": "水质异常"},
            {"species": "花甲", "date": "2026-03-23", "deaths": 18, "loss_fen": 9000, "reason": "水质异常"},
        ]
        report = predictor.generate_loss_report(records, 7)
        assert len(report.improvement_suggestions) > 0
