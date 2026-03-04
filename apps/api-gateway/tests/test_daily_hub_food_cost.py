"""
Daily Hub 食材成本集成测试

覆盖 DailyHubService._get_yesterday_review 中的食材成本分析分支：
  1. 成本正常（ok）    — 不追加告警
  2. 成本偏高（warning）— 追加 🟡 告警
  3. 成本严重超标（critical）— 追加 🔴 告警
  4. 无 DB 传入       — 跳过分析，food_cost=None，不报错
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.daily_hub_service import DailyHubService
from src.services.food_cost_service import FoodCostService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_report(alerts=None):
    r = MagicMock()
    r.total_revenue = 80000
    r.order_count   = 200
    r.health_score  = 88.0
    r.highlights    = ["午市满座"]
    r.alerts        = list(alerts or [])
    return r


def _make_fc_data(actual_pct, theoretical_pct, variance_pct, status):
    return {
        "actual_pct":      actual_pct,
        "theoretical_pct": theoretical_pct,
        "variance_pct":    variance_pct,
        "variance_status": status,
        "top_ingredients": [],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestYesterdayReviewFoodCost:

    @pytest.mark.asyncio
    async def test_food_cost_ok_no_alert(self):
        """成本差异 < 2%（ok）— 不追加任何食材告警"""
        db = AsyncMock()
        report  = _make_report()
        fc_data = _make_fc_data(22.0, 21.5, 0.5, "ok")

        with patch(
            "src.services.daily_report_service.daily_report_service"
        ) as mock_drs, patch.object(
            FoodCostService,
            "get_store_food_cost_variance",
            new_callable=AsyncMock,
            return_value=fc_data,
        ):
            mock_drs.generate_daily_report = AsyncMock(return_value=report)
            svc    = DailyHubService()
            result = await svc._get_yesterday_review("S001", date(2026, 2, 1), db=db)

        assert result["food_cost"] is not None
        assert result["food_cost"]["variance_status"] == "ok"
        # 不应有食材告警（不含 emoji）
        food_alerts = [a for a in result["alerts"] if "食材" in a]
        assert food_alerts == []

    @pytest.mark.asyncio
    async def test_food_cost_warning_appends_alert(self):
        """成本差异 2-5%（warning）— 追加 🟡 警告"""
        db = AsyncMock()
        report  = _make_report()
        fc_data = _make_fc_data(25.5, 22.0, 3.5, "warning")

        with patch(
            "src.services.daily_report_service.daily_report_service"
        ) as mock_drs, patch.object(
            FoodCostService,
            "get_store_food_cost_variance",
            new_callable=AsyncMock,
            return_value=fc_data,
        ):
            mock_drs.generate_daily_report = AsyncMock(return_value=report)
            svc    = DailyHubService()
            result = await svc._get_yesterday_review("S001", date(2026, 2, 1), db=db)

        assert result["food_cost"]["variance_status"] == "warning"
        assert any("🟡" in a for a in result["alerts"])
        assert any("25.5" in a for a in result["alerts"])

    @pytest.mark.asyncio
    async def test_food_cost_critical_appends_alert(self):
        """成本差异 ≥ 5%（critical）— 追加 🔴 告警，优先级高"""
        db = AsyncMock()
        report  = _make_report(alerts=["备货不足"])  # 已有其他告警
        fc_data = _make_fc_data(38.0, 22.0, 16.0, "critical")

        with patch(
            "src.services.daily_report_service.daily_report_service"
        ) as mock_drs, patch.object(
            FoodCostService,
            "get_store_food_cost_variance",
            new_callable=AsyncMock,
            return_value=fc_data,
        ):
            mock_drs.generate_daily_report = AsyncMock(return_value=report)
            svc    = DailyHubService()
            result = await svc._get_yesterday_review("S001", date(2026, 2, 1), db=db)

        assert result["food_cost"]["variance_status"] == "critical"
        # 原有告警仍保留
        assert "备货不足" in result["alerts"]
        # 食材严重超标告警已追加
        assert any("🔴" in a for a in result["alerts"])
        assert any("38.0" in a for a in result["alerts"])

    @pytest.mark.asyncio
    async def test_no_db_skips_food_cost_gracefully(self):
        """不传 db 时跳过食材分析，food_cost=None，不报错"""
        report = _make_report()

        with patch(
            "src.services.daily_report_service.daily_report_service"
        ) as mock_drs:
            mock_drs.generate_daily_report = AsyncMock(return_value=report)
            svc    = DailyHubService()
            result = await svc._get_yesterday_review("S001", date(2026, 2, 1), db=None)

        assert result["food_cost"] is None
        # 没有任何食材告警
        food_alerts = [a for a in result["alerts"] if "食材" in a]
        assert food_alerts == []

    @pytest.mark.asyncio
    async def test_food_cost_failure_does_not_break_review(self):
        """食材成本查询失败时，昨日复盘仍正常返回，food_cost=None"""
        db     = AsyncMock()
        report = _make_report()

        with patch(
            "src.services.daily_report_service.daily_report_service"
        ) as mock_drs, patch.object(
            FoodCostService,
            "get_store_food_cost_variance",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB 连接超时"),
        ):
            mock_drs.generate_daily_report = AsyncMock(return_value=report)
            svc    = DailyHubService()
            result = await svc._get_yesterday_review("S001", date(2026, 2, 1), db=db)

        # 主数据完整返回
        assert result["total_revenue"] == 80000
        assert result["order_count"]   == 200
        # food_cost 降级为 None
        assert result["food_cost"] is None
