"""
海鲜进货价波动预警服务测试
"""

import pytest

from src.services.price_fluctuation_service import (
    PriceFluctuationService,
    AnomalyResult,
    TrendResult,
)


@pytest.fixture
def service():
    return PriceFluctuationService()


def _seed_prices(service, species="波士顿龙虾", base=15000, count=10, supplier="SUP01"):
    """填充价格历史数据"""
    for i in range(count):
        service.record_price(
            species=species,
            supplier_id=supplier,
            price_fen=base + i * 100,  # 缓慢上涨
            record_date=f"2026-03-{10 + i:02d}",
        )


class TestRecordPrice:
    def test_record_success(self, service):
        record = service.record_price("波士顿龙虾", "SUP01", 15000, "2026-03-20")
        assert record.species == "波士顿龙虾"
        assert record.price_fen == 15000
        assert record.price_yuan == 150.0

    def test_record_negative_price_raises(self, service):
        with pytest.raises(ValueError):
            service.record_price("波士顿龙虾", "SUP01", -100)

    def test_record_default_date(self, service):
        record = service.record_price("鲈鱼", "SUP01", 5000)
        assert record.date is not None

    def test_multiple_records_stored(self, service):
        service.record_price("鲈鱼", "SUP01", 5000, "2026-03-20")
        service.record_price("鲈鱼", "SUP01", 5200, "2026-03-21")
        assert len(service._price_history["鲈鱼"]) == 2


class TestDetectAnomaly:
    def test_normal_price_no_anomaly(self, service):
        """正常价格不触发异常"""
        history = [15000, 15100, 14900, 15050, 14950, 15000]
        result = service.detect_anomaly("波士顿龙虾", 15050, history)
        assert result.is_anomaly is False
        assert result.direction == "正常"

    def test_high_price_anomaly(self, service):
        """异常高价触发偏高"""
        history = [15000, 15100, 14900, 15050, 14950, 15000, 15100, 14900]
        result = service.detect_anomaly("波士顿龙虾", 20000, history)
        assert result.is_anomaly is True
        assert result.direction == "偏高"

    def test_low_price_anomaly(self, service):
        """异常低价触发偏低"""
        history = [15000, 15100, 14900, 15050, 14950, 15000, 15100, 14900]
        result = service.detect_anomaly("波士顿龙虾", 10000, history)
        assert result.is_anomaly is True
        assert result.direction == "偏低"

    def test_insufficient_data(self, service):
        """数据不足不判断异常"""
        result = service.detect_anomaly("鲈鱼", 5000, [5000, 5100])
        assert result.is_anomaly is False
        assert "数据不足" in result.severity

    def test_fen_yuan_dual_return(self, service):
        """同时返回分和元"""
        history = [15000] * 5
        result = service.detect_anomaly("波士顿龙虾", 15000, history)
        assert result.latest_price_yuan == 150.0
        assert result.mean_price_yuan == 150.0


class TestCalculateTrend:
    def test_upward_trend(self, service):
        """上涨趋势识别"""
        history = [
            {"date": f"2026-03-{i:02d}", "price_fen": 10000 + i * 500}
            for i in range(1, 11)
        ]
        result = service.calculate_trend("基围虾", history, 10)
        assert result.trend == "上涨"
        assert result.change_pct > 0

    def test_downward_trend(self, service):
        """下跌趋势识别"""
        history = [
            {"date": f"2026-03-{i:02d}", "price_fen": 20000 - i * 500}
            for i in range(1, 11)
        ]
        result = service.calculate_trend("帝王蟹", history, 10)
        assert result.trend == "下跌"
        assert result.change_pct < 0

    def test_stable_trend(self, service):
        """平稳趋势识别"""
        history = [
            {"date": f"2026-03-{i:02d}", "price_fen": 15000}
            for i in range(1, 11)
        ]
        result = service.calculate_trend("鲍鱼", history, 10)
        assert result.trend == "平稳"

    def test_empty_history(self, service):
        result = service.calculate_trend("未知", [], 10)
        assert result.trend == "数据不足"

    def test_min_max_correct(self, service):
        history = [
            {"date": "2026-03-01", "price_fen": 10000},
            {"date": "2026-03-02", "price_fen": 20000},
            {"date": "2026-03-03", "price_fen": 15000},
        ]
        result = service.calculate_trend("测试", history, 7)
        assert result.min_price_fen == 10000
        assert result.max_price_fen == 20000
        assert result.min_price_yuan == 100.0
        assert result.max_price_yuan == 200.0


class TestGenerateAlert:
    def test_anomaly_generates_alert(self, service):
        anomaly = AnomalyResult(
            species="波士顿龙虾", is_anomaly=True,
            latest_price_fen=20000, latest_price_yuan=200.0,
            mean_price_fen=15000, mean_price_yuan=150.0,
            std_dev_fen=500.0, deviation_sigma=3.5,
            direction="偏高", severity="显著",
        )
        alert = service.generate_alert("波士顿龙虾", anomaly, monthly_volume=200)
        assert alert is not None
        assert alert.alert_type == "异常偏高"
        # 差价5000分 × 200斤 = 1000000分 = 10000元
        assert alert.impact_estimate_fen == 5000 * 200
        assert alert.impact_estimate_yuan == 10000.0

    def test_no_anomaly_no_alert(self, service):
        anomaly = AnomalyResult(
            species="鲈鱼", is_anomaly=False,
            latest_price_fen=5000, latest_price_yuan=50.0,
            mean_price_fen=5000, mean_price_yuan=50.0,
            std_dev_fen=100.0, deviation_sigma=0.0,
            direction="正常", severity="正常",
        )
        alert = service.generate_alert("鲈鱼", anomaly)
        assert alert is None


class TestPriceDashboard:
    def test_dashboard_with_data(self, service):
        _seed_prices(service, "波士顿龙虾", 15000, 10)
        dashboards = service.get_price_dashboard(["波士顿龙虾"], 30)
        assert len(dashboards) == 1
        d = dashboards[0]
        assert d.species == "波士顿龙虾"
        assert d.latest_price_fen > 0
        assert d.latest_price_yuan > 0
        assert len(d.price_history) == 10

    def test_dashboard_no_data(self, service):
        dashboards = service.get_price_dashboard(["不存在"], 30)
        assert dashboards[0].trend == "无数据"

    def test_supplier_comparison(self, service):
        """多供应商比价"""
        service.record_price("鲈鱼", "SUP01", 5000, "2026-03-20")
        service.record_price("鲈鱼", "SUP02", 4800, "2026-03-20")
        dashboards = service.get_price_dashboard(["鲈鱼"], 30)
        assert len(dashboards[0].supplier_comparison) == 2
        # 便宜的排前面
        assert dashboards[0].supplier_comparison[0]["avg_price_fen"] <= 5000


class TestRecommendPurchaseTiming:
    def test_downtrend_wait(self, service):
        """下跌趋势建议等待"""
        trend = TrendResult(
            species="帝王蟹", trend="下跌", change_pct=-15.0, period_days=10,
            start_price_fen=20000, start_price_yuan=200.0,
            end_price_fen=17000, end_price_yuan=170.0,
            avg_price_fen=18500, avg_price_yuan=185.0,
            min_price_fen=17000, min_price_yuan=170.0,
            max_price_fen=20000, max_price_yuan=200.0,
            volatility=5.0,
        )
        advice = service.recommend_purchase_timing("帝王蟹", trend)
        assert advice.recommendation == "等待观望"
        assert advice.potential_saving_fen > 0

    def test_uptrend_buy_now(self, service):
        """上涨趋势建议立即采购"""
        trend = TrendResult(
            species="波士顿龙虾", trend="上涨", change_pct=12.0, period_days=10,
            start_price_fen=15000, start_price_yuan=150.0,
            end_price_fen=16800, end_price_yuan=168.0,
            avg_price_fen=15900, avg_price_yuan=159.0,
            min_price_fen=15000, min_price_yuan=150.0,
            max_price_fen=16800, max_price_yuan=168.0,
            volatility=4.0,
        )
        advice = service.recommend_purchase_timing("波士顿龙虾", trend)
        assert advice.recommendation == "立即采购"

    def test_stable_normal(self, service):
        """平稳趋势正常采购"""
        trend = TrendResult(
            species="鲈鱼", trend="平稳", change_pct=0.5, period_days=10,
            start_price_fen=5000, start_price_yuan=50.0,
            end_price_fen=5025, end_price_yuan=50.25,
            avg_price_fen=5012, avg_price_yuan=50.12,
            min_price_fen=4980, min_price_yuan=49.80,
            max_price_fen=5050, max_price_yuan=50.50,
            volatility=0.5,
        )
        advice = service.recommend_purchase_timing("鲈鱼", trend)
        assert advice.recommendation == "正常采购"

    def test_no_data_default(self, service):
        """无数据时给默认建议"""
        advice = service.recommend_purchase_timing("未知品种")
        assert advice.recommendation == "正常采购"
        assert advice.confidence < 0.5
