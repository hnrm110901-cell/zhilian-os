"""
KPIAlertService 单元测试

覆盖：
  - classify_alert：纯函数阈值分类
  - build_alert_message：告警文本构建（Rule 7 合规）
  - KPIAlertService.check_store：单店检查（mock FoodCostService + KPI DB）
  - KPIAlertService.run_all_stores：多店汇总（mock 子调用）
  - KPIAlertService.run_and_notify：完整流程（mock send_alert）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from src.services.kpi_alert_service import (
    KPIAlertService,
    classify_alert,
    build_alert_message,
)


# ── classify_alert ────────────────────────────────────────────────────────────

class TestClassifyAlert:
    def test_ok_below_warning(self):
        assert classify_alert(28.0, 32.0, 35.0) == "ok"

    def test_warning_at_threshold(self):
        assert classify_alert(32.0, 32.0, 35.0) == "warning"

    def test_warning_between_thresholds(self):
        assert classify_alert(33.5, 32.0, 35.0) == "warning"

    def test_critical_at_threshold(self):
        assert classify_alert(35.0, 32.0, 35.0) == "critical"

    def test_critical_above_threshold(self):
        assert classify_alert(40.0, 32.0, 35.0) == "critical"

    def test_exact_ok_boundary(self):
        assert classify_alert(31.9, 32.0, 35.0) == "ok"


# ── build_alert_message ───────────────────────────────────────────────────────

class TestBuildAlertMessage:
    def _call(self, status="critical"):
        return build_alert_message(
            store_id="S001",
            actual_pct=37.0,
            warning_threshold=32.0,
            critical_threshold=35.0,
            actual_cost_yuan=12000.0,
            top_ingredients=[
                {"name": "鸡腿", "cost_yuan": 4000.0},
                {"name": "猪肉", "cost_yuan": 3000.0},
            ],
            status=status,
        )

    def test_contains_store_id(self):
        assert "S001" in self._call()

    def test_critical_has_warning_emoji(self):
        msg = self._call("critical")
        assert "🚨" in msg

    def test_warning_has_warning_emoji(self):
        msg = self._call("warning")
        assert "⚠️" in msg

    def test_contains_yuan_amount(self):
        msg = self._call()
        assert "¥" in msg
        assert "12,000" in msg or "12000" in msg

    def test_contains_top_ingredient(self):
        assert "鸡腿" in self._call()

    def test_contains_action_suggestion(self):
        msg = self._call()
        assert "建议" in msg or "AI" in msg


# ── KPIAlertService.check_store ───────────────────────────────────────────────

class TestCheckStore:
    def _make_variance(self, actual_pct=33.0):
        return {
            "actual_cost_pct":  actual_pct,
            "actual_cost_fen":  900_000,
            "top_ingredients":  [{"name": "鸡腿", "cost_yuan": 4000.0}],
        }

    @pytest.mark.asyncio
    async def test_warning_status_sets_needs_alert(self):
        db = AsyncMock()
        thresholds = {"warning": 32.0, "critical": 35.0}

        with patch(
            "src.services.kpi_alert_service.FoodCostService.get_store_food_cost_variance",
            new=AsyncMock(return_value=self._make_variance(33.0)),
        ):
            result = await KPIAlertService.check_store(
                store_id="S001", db=db, thresholds=thresholds
            )

        assert result["status"] == "warning"
        assert result["needs_alert"] is True

    @pytest.mark.asyncio
    async def test_ok_status_not_alert(self):
        db = AsyncMock()
        thresholds = {"warning": 32.0, "critical": 35.0}

        with patch(
            "src.services.kpi_alert_service.FoodCostService.get_store_food_cost_variance",
            new=AsyncMock(return_value=self._make_variance(28.0)),
        ):
            result = await KPIAlertService.check_store(
                store_id="S001", db=db, thresholds=thresholds
            )

        assert result["status"] == "ok"
        assert result["needs_alert"] is False

    @pytest.mark.asyncio
    async def test_critical_above_threshold(self):
        db = AsyncMock()
        thresholds = {"warning": 32.0, "critical": 35.0}

        with patch(
            "src.services.kpi_alert_service.FoodCostService.get_store_food_cost_variance",
            new=AsyncMock(return_value=self._make_variance(38.5)),
        ):
            result = await KPIAlertService.check_store(
                store_id="S001", db=db, thresholds=thresholds
            )

        assert result["status"] == "critical"
        assert result["actual_cost_pct"] == 38.5

    @pytest.mark.asyncio
    async def test_result_contains_yuan_field(self):
        db = AsyncMock()
        thresholds = {"warning": 32.0, "critical": 35.0}

        with patch(
            "src.services.kpi_alert_service.FoodCostService.get_store_food_cost_variance",
            new=AsyncMock(return_value=self._make_variance(33.0)),
        ):
            result = await KPIAlertService.check_store(
                store_id="S001", db=db, thresholds=thresholds
            )

        assert "actual_cost_yuan" in result
        assert result["actual_cost_yuan"] == 9000.0  # 900_000 / 100


# ── KPIAlertService.run_all_stores ────────────────────────────────────────────

class TestRunAllStores:
    @pytest.mark.asyncio
    async def test_alerts_counted_correctly(self):
        db = AsyncMock()

        # 2 stores: one warning, one ok
        async def mock_check(store_id, db, thresholds, lookback_days=7):
            if store_id == "S001":
                return {"store_id": "S001", "status": "warning", "needs_alert": True,
                        "actual_cost_pct": 33.0, "actual_cost_yuan": 9000.0,
                        "warning_threshold": 32.0, "critical_threshold": 35.0,
                        "top_ingredients": []}
            return {"store_id": "S002", "status": "ok", "needs_alert": False,
                    "actual_cost_pct": 28.0, "actual_cost_yuan": 7000.0,
                    "warning_threshold": 32.0, "critical_threshold": 35.0,
                    "top_ingredients": []}

        with (
            patch.object(KPIAlertService, "_get_food_cost_thresholds",
                         new=AsyncMock(return_value={"warning": 32.0, "critical": 35.0})),
            patch.object(KPIAlertService, "_get_active_store_ids",
                         new=AsyncMock(return_value=["S001", "S002"])),
            patch.object(KPIAlertService, "check_store", side_effect=mock_check),
        ):
            result = await KPIAlertService.run_all_stores(db=db)

        assert result["total"] == 2
        assert result["alert_count"] == 1
        assert result["ok_count"] == 1
        assert result["alerts"][0]["store_id"] == "S001"

    @pytest.mark.asyncio
    async def test_failed_store_does_not_crash_run(self):
        db = AsyncMock()

        async def mock_check(store_id, db, thresholds, lookback_days=7):
            if store_id == "S_BAD":
                raise RuntimeError("DB timeout")
            return {"store_id": "S001", "status": "ok", "needs_alert": False,
                    "actual_cost_pct": 28.0, "actual_cost_yuan": 7000.0,
                    "warning_threshold": 32.0, "critical_threshold": 35.0,
                    "top_ingredients": []}

        with (
            patch.object(KPIAlertService, "_get_food_cost_thresholds",
                         new=AsyncMock(return_value={"warning": 32.0, "critical": 35.0})),
            patch.object(KPIAlertService, "_get_active_store_ids",
                         new=AsyncMock(return_value=["S001", "S_BAD"])),
            patch.object(KPIAlertService, "check_store", side_effect=mock_check),
        ):
            result = await KPIAlertService.run_all_stores(db=db)

        # Should not raise; failed store is skipped
        assert result["total"] == 2
        assert result["ok_count"] == 1


# ── KPIAlertService.run_and_notify ────────────────────────────────────────────

class TestRunAndNotify:
    @pytest.mark.asyncio
    async def test_sends_alert_for_warning_stores(self):
        db = AsyncMock()

        summary = {
            "total": 1, "alert_count": 1, "ok_count": 0,
            "alerts": [{"store_id": "S001", "status": "warning",
                        "needs_alert": True, "actual_cost_pct": 33.0,
                        "actual_cost_yuan": 9000.0,
                        "warning_threshold": 32.0, "critical_threshold": 35.0,
                        "top_ingredients": []}],
        }
        mock_send = AsyncMock(return_value={"success": True})

        with (
            patch.object(KPIAlertService, "run_all_stores",
                         new=AsyncMock(return_value=summary)),
            patch.object(KPIAlertService, "send_alert", mock_send),
        ):
            result = await KPIAlertService.run_and_notify(db=db)

        mock_send.assert_awaited_once()
        assert result["sent_count"] == 1
        assert result["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_no_alerts_sends_nothing(self):
        db = AsyncMock()

        summary = {"total": 3, "alert_count": 0, "ok_count": 3, "alerts": []}
        mock_send = AsyncMock()

        with (
            patch.object(KPIAlertService, "run_all_stores",
                         new=AsyncMock(return_value=summary)),
            patch.object(KPIAlertService, "send_alert", mock_send),
        ):
            result = await KPIAlertService.run_and_notify(db=db)

        mock_send.assert_not_awaited()
        assert result["sent_count"] == 0
