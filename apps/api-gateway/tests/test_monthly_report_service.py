"""
MonthlyReportService 单元测试

覆盖：
  - build_executive_summary：高管摘要生成（纯函数）
  - build_weekly_trend_chart：ECharts 数据构建（纯函数）
  - render_html_report：HTML 包含关键字段（纯函数）
  - MonthlyReportService.generate：完整报告 JSON（mock DB）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.monthly_report_service import (
    MonthlyReportService,
    build_executive_summary,
    build_weekly_trend_chart,
    render_html_report,
)


# ── build_executive_summary ──────────────────────────────────────────────────

class TestBuildExecutiveSummary:
    def _make_story(self, cost_pct=30.0, status="ok", revenue=3_000_000,
                    saving=5000.0, adoption=75.0, waste=120_000):
        return {
            "store_id":  "S001",
            "period_label": "2026年3月",
            "cost_metrics": {
                "revenue_yuan":       revenue / 100,
                "actual_cost_pct":    cost_pct,
                "cost_rate_status":   status,
                "waste_cost_yuan":    waste / 100,
                "waste_pct":          round(waste / revenue * 100, 2),
            },
            "decision_summary": {
                "approved":           3,
                "total":              4,
                "adoption_rate_pct":  adoption,
                "total_saving_yuan":  saving,
            },
            "narrative": "本月经营稳定。",
        }

    def test_contains_period_label(self):
        story = self._make_story()
        summary = build_executive_summary(story)
        assert summary["period"] == "2026年3月"

    def test_revenue_yuan_passed_through(self):
        story = self._make_story(revenue=3_000_000)
        summary = build_executive_summary(story)
        assert summary["revenue_yuan"] == 30000.0  # 3_000_000 / 100

    def test_critical_status_triggers_warning_headline(self):
        story = self._make_story(status="critical", cost_pct=42.0)
        summary = build_executive_summary(story)
        assert "超标" in summary["headline"] or "⚠️" in summary["headline"]

    def test_saving_triggers_positive_headline(self):
        story = self._make_story(status="ok", saving=8000.0)
        summary = build_executive_summary(story)
        assert "8000" in summary["headline"] or "节省" in summary["headline"]

    def test_adoption_rate_included(self):
        story = self._make_story(adoption=80.0)
        summary = build_executive_summary(story)
        assert summary["decision_adoption_pct"] == 80.0


# ── build_weekly_trend_chart ─────────────────────────────────────────────────

class TestBuildWeeklyTrendChart:
    def _weekly_trend(self):
        return [
            {"week_start": "2026-03-01", "actual_cost_pct": 28.0, "revenue_yuan": 10000.0, "cost_rate_status": "ok"},
            {"week_start": "2026-03-08", "actual_cost_pct": 33.0, "revenue_yuan": 11000.0, "cost_rate_status": "warning"},
            {"week_start": "2026-03-15", "actual_cost_pct": 42.0, "revenue_yuan": 9000.0,  "cost_rate_status": "critical"},
            {"week_start": "2026-03-22", "actual_cost_pct": 29.0, "revenue_yuan": 12000.0, "cost_rate_status": "ok"},
        ]

    def test_x_axis_contains_all_weeks(self):
        chart = build_weekly_trend_chart(self._weekly_trend())
        assert len(chart["x_axis"]) == 4

    def test_cost_rate_data_matches_input(self):
        chart = build_weekly_trend_chart(self._weekly_trend())
        assert chart["cost_rate_data"][1] == 33.0

    def test_point_colors_match_status(self):
        chart = build_weekly_trend_chart(self._weekly_trend())
        assert chart["point_colors"][0] == "#52c41a"   # ok → green
        assert chart["point_colors"][1] == "#faad14"   # warning → orange
        assert chart["point_colors"][2] == "#f5222d"   # critical → red

    def test_revenue_data_included(self):
        chart = build_weekly_trend_chart(self._weekly_trend())
        assert chart["revenue_data"][0] == 10000.0

    def test_empty_trend_returns_empty_lists(self):
        chart = build_weekly_trend_chart([])
        assert chart["x_axis"] == []
        assert chart["cost_rate_data"] == []


# ── render_html_report ───────────────────────────────────────────────────────

class TestRenderHtmlReport:
    def _make_inputs(self):
        exec_sum = {
            "headline":              "✅ 本月节省 ¥5000",
            "revenue_yuan":          30000.0,
            "actual_cost_pct":       30.5,
            "cost_rate_status":      "ok",
            "waste_cost_yuan":       1200.0,
            "decision_adoption_pct": 75.0,
            "total_saving_yuan":     5000.0,
            "decisions_approved":    3,
            "decisions_total":       4,
            "narrative":             "本月运营良好。",
            "period":                "2026年3月",
        }
        top3 = [
            {"action": "紧急补货鸡腿", "expected_saving_yuan": 2000.0, "outcome": "success"},
        ]
        weekly_chart = {
            "x_axis":          ["2026-03-01", "2026-03-08"],
            "cost_rate_data":  [28.0, 33.0],
            "revenue_data":    [10000.0, 11000.0],
            "point_colors":    ["#52c41a", "#faad14"],
        }
        return exec_sum, top3, weekly_chart

    def test_html_contains_store_id(self):
        es, top3, chart = self._make_inputs()
        html = render_html_report("S001", 2026, 3, es, top3, chart)
        assert "S001" in html

    def test_html_contains_period_label(self):
        es, top3, chart = self._make_inputs()
        html = render_html_report("S001", 2026, 3, es, top3, chart)
        assert "2026年3月" in html

    def test_html_contains_revenue(self):
        es, top3, chart = self._make_inputs()
        html = render_html_report("S001", 2026, 3, es, top3, chart)
        assert "30,000" in html or "30000" in html

    def test_html_contains_decision_action(self):
        es, top3, chart = self._make_inputs()
        html = render_html_report("S001", 2026, 3, es, top3, chart)
        assert "紧急补货鸡腿" in html

    def test_html_contains_week_data(self):
        es, top3, chart = self._make_inputs()
        html = render_html_report("S001", 2026, 3, es, top3, chart)
        assert "2026-03-01" in html
        assert "28.0%" in html

    def test_html_is_valid_string(self):
        es, top3, chart = self._make_inputs()
        html = render_html_report("S001", 2026, 3, es, top3, chart)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html


# ── MonthlyReportService.generate ───────────────────────────────────────────

class TestMonthlyReportServiceGenerate:
    def _make_monthly_story_mock(self):
        return {
            "store_id":    "S001",
            "year":        2026,
            "month":       3,
            "period":      "monthly",
            "period_label": "2026年3月",
            "cost_metrics": {
                "revenue_fen":        3_000_000,
                "revenue_yuan":       30000.0,
                "actual_cost_fen":    900_000,
                "actual_cost_yuan":   9000.0,
                "actual_cost_pct":    30.0,
                "waste_cost_fen":     120_000,
                "waste_cost_yuan":    1200.0,
                "waste_pct":          4.0,
                "cost_rate_status":   "ok",
                "cost_rate_label":    "正常",
            },
            "decision_summary": {
                "total":              5,
                "approved":           4,
                "rejected":           1,
                "successful":         3,
                "adoption_rate_pct":  80.0,
                "total_saving_yuan":  8000.0,
            },
            "top3_decisions": [
                {"action": "补货鸡腿", "expected_saving_yuan": 3000.0, "outcome": "success", "status": "APPROVED"},
            ],
            "weekly_trend": [
                {"week_start": "2026-03-01", "revenue_yuan": 7000.0, "actual_cost_pct": 29.0, "cost_rate_status": "ok"},
                {"week_start": "2026-03-08", "revenue_yuan": 8000.0, "actual_cost_pct": 31.0, "cost_rate_status": "warning"},
                {"week_start": "2026-03-15", "revenue_yuan": 7500.0, "actual_cost_pct": 30.0, "cost_rate_status": "ok"},
                {"week_start": "2026-03-22", "revenue_yuan": 7500.0, "actual_cost_pct": 30.0, "cost_rate_status": "ok"},
            ],
            "narrative": "2026年3月，门店 S001 食材成本率为 30.0%（正常）。",
            "generated_at": "2026-04-01T00:00:00",
        }

    @pytest.mark.asyncio
    async def test_generate_returns_complete_structure(self):
        db = AsyncMock()
        with patch(
            "src.services.monthly_report_service.CaseStoryGenerator.generate_monthly_story",
            new=AsyncMock(return_value=self._make_monthly_story_mock()),
        ):
            report = await MonthlyReportService.generate("S001", 2026, 3, db)

        assert "executive_summary" in report
        assert "weekly_trend_chart" in report
        assert "top3_decisions" in report
        assert "cost_metrics" in report

    @pytest.mark.asyncio
    async def test_executive_summary_contains_yuan_fields(self):
        db = AsyncMock()
        with patch(
            "src.services.monthly_report_service.CaseStoryGenerator.generate_monthly_story",
            new=AsyncMock(return_value=self._make_monthly_story_mock()),
        ):
            report = await MonthlyReportService.generate("S001", 2026, 3, db)

        es = report["executive_summary"]
        assert "revenue_yuan" in es
        assert "total_saving_yuan" in es

    @pytest.mark.asyncio
    async def test_generate_html_returns_string(self):
        db = AsyncMock()
        with patch(
            "src.services.monthly_report_service.CaseStoryGenerator.generate_monthly_story",
            new=AsyncMock(return_value=self._make_monthly_story_mock()),
        ):
            html = await MonthlyReportService.generate_html("S001", 2026, 3, db)

        assert isinstance(html, str)
        assert "S001" in html
        assert "2026年3月" in html
