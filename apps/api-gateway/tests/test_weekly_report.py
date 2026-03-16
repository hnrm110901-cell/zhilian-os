"""
周报聚合服务单元测试
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from src.services.weekly_report_service import WeeklyReportService


def _make_daily_report(
    report_date,
    total_revenue=100000,  # ¥1000.00
    order_count=50,
    customer_count=40,
    avg_order_value=2000,  # ¥20.00
    task_completion_rate=85.0,
    inventory_alert_count=2,
    service_issue_count=1,
):
    d = MagicMock()
    d.report_date = report_date
    d.total_revenue = total_revenue
    d.order_count = order_count
    d.customer_count = customer_count
    d.avg_order_value = avg_order_value
    d.task_completion_rate = task_completion_rate
    d.inventory_alert_count = inventory_alert_count
    d.service_issue_count = service_issue_count
    return d


class TestAggregate:
    """测试 _aggregate 方法"""

    def test_empty_reports(self):
        svc = WeeklyReportService()
        result = svc._aggregate([])
        assert result["total_revenue_yuan"] == 0
        assert result["total_orders"] == 0
        assert result["avg_daily_revenue_yuan"] == 0

    def test_single_day(self):
        svc = WeeklyReportService()
        reports = [_make_daily_report(date(2026, 3, 10), total_revenue=500000, order_count=100, customer_count=80)]
        result = svc._aggregate(reports)
        assert result["total_revenue_yuan"] == 5000.0
        assert result["total_orders"] == 100
        assert result["total_customers"] == 80
        assert result["avg_daily_revenue_yuan"] == 5000.0
        assert result["avg_order_value_yuan"] == 50.0

    def test_seven_days(self):
        svc = WeeklyReportService()
        reports = [
            _make_daily_report(
                date(2026, 3, d),
                total_revenue=100000 * d,  # 递增
                order_count=50,
                customer_count=40,
            )
            for d in range(10, 17)
        ]
        result = svc._aggregate(reports)
        # sum(100000*10 + ... + 100000*16) = 100000 * (10+11+...+16) = 100000 * 91 = 9100000分
        assert result["total_revenue_yuan"] == 91000.0
        assert result["total_orders"] == 350  # 50 * 7
        assert result["total_customers"] == 280  # 40 * 7
        assert result["avg_daily_revenue_yuan"] == 13000.0  # 91000 / 7

    def test_none_values_treated_as_zero(self):
        svc = WeeklyReportService()
        d = _make_daily_report(date(2026, 3, 10))
        d.total_revenue = None
        d.order_count = None
        d.customer_count = None
        d.task_completion_rate = None
        d.inventory_alert_count = None
        d.service_issue_count = None
        result = svc._aggregate([d])
        assert result["total_revenue_yuan"] == 0
        assert result["total_orders"] == 0
        assert result["avg_order_value_yuan"] == 0


class TestWeekOverWeek:
    """测试 _week_over_week 方法"""

    def test_growth(self):
        svc = WeeklyReportService()
        this_week = {"total_revenue_yuan": 10000, "total_orders": 500, "total_customers": 400}
        prev_week = {"total_revenue_yuan": 8000, "total_orders": 400, "total_customers": 300}
        wow = svc._week_over_week(this_week, prev_week)
        assert wow["revenue_pct"] == 25.0
        assert wow["orders_pct"] == 25.0
        assert wow["customers_pct"] == pytest.approx(33.3, abs=0.1)

    def test_decline(self):
        svc = WeeklyReportService()
        this_week = {"total_revenue_yuan": 8000, "total_orders": 400, "total_customers": 300}
        prev_week = {"total_revenue_yuan": 10000, "total_orders": 500, "total_customers": 400}
        wow = svc._week_over_week(this_week, prev_week)
        assert wow["revenue_pct"] == -20.0
        assert wow["orders_pct"] == -20.0
        assert wow["customers_pct"] == -25.0

    def test_prev_zero_returns_none(self):
        svc = WeeklyReportService()
        this_week = {"total_revenue_yuan": 10000, "total_orders": 500, "total_customers": 400}
        prev_week = {"total_revenue_yuan": 0, "total_orders": 0, "total_customers": 0}
        wow = svc._week_over_week(this_week, prev_week)
        assert wow["revenue_pct"] is None
        assert wow["orders_pct"] is None


class TestBuildSummary:
    """测试 _build_summary 方法"""

    def test_summary_contains_key_info(self):
        svc = WeeklyReportService()
        agg = {
            "total_revenue_yuan": 50000.0,
            "total_orders": 350,
            "total_customers": 280,
            "avg_daily_revenue_yuan": 7142.86,
            "avg_order_value_yuan": 142.86,
            "total_inventory_alerts": 3,
        }
        wow = {"revenue_pct": 12.5, "orders_pct": 8.0, "customers_pct": 5.0}
        summary = svc._build_summary(agg, wow, date(2026, 3, 10), date(2026, 3, 16))

        assert "周报" in summary
        assert "50,000.00" in summary
        assert "350" in summary
        assert "280" in summary
        assert "↑12.5%" in summary
        assert "库存预警 3 次" in summary

    def test_summary_no_wow_when_none(self):
        svc = WeeklyReportService()
        agg = {
            "total_revenue_yuan": 10000.0,
            "total_orders": 100,
            "total_customers": 80,
            "avg_daily_revenue_yuan": 1428.57,
            "avg_order_value_yuan": 100.0,
            "total_inventory_alerts": 0,
        }
        wow = {"revenue_pct": None, "orders_pct": None, "customers_pct": None}
        summary = svc._build_summary(agg, wow, date(2026, 3, 10), date(2026, 3, 16))
        assert "环比" not in summary
        assert "库存预警" not in summary

    def test_summary_decline_arrow(self):
        svc = WeeklyReportService()
        agg = {
            "total_revenue_yuan": 8000.0,
            "total_orders": 100,
            "total_customers": 80,
            "avg_daily_revenue_yuan": 1142.86,
            "avg_order_value_yuan": 80.0,
            "total_inventory_alerts": 0,
        }
        wow = {"revenue_pct": -5.5, "orders_pct": -3.0, "customers_pct": -2.0}
        summary = svc._build_summary(agg, wow, date(2026, 3, 10), date(2026, 3, 16))
        assert "↓5.5%" in summary
