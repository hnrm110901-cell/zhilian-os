"""
BehaviorScoreEngine 单元测试

覆盖：
  - 纯函数：compute_adoption_rate / compute_execution_accuracy /
            compute_total_saving / _classify_adoption / _roi_label
  - 集成：BehaviorScoreEngine.get_store_report（mock DB）
         BehaviorScoreEngine.get_system_roi_summary（mock）
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONTHLY_SYSTEM_COST_YUAN", "2000")

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.behavior_score_engine import (
    BehaviorScoreEngine,
    _classify_adoption,
    _roi_label,
    compute_adoption_rate,
    compute_execution_accuracy,
    compute_total_saving,
)


# ════════════════════════════════════════════════════════════════════════════════
# 测试夹具
# ════════════════════════════════════════════════════════════════════════════════

def _decision(status="pending", outcome="", saving=500.0):
    return {
        "decision_status": status,
        "outcome": outcome,
        "ai_suggestion": {"expected_saving_yuan": saving},
        "expected_saving_yuan": saving,
    }


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数测试
# ════════════════════════════════════════════════════════════════════════════════

class TestComputeAdoptionRate:
    def test_empty_returns_zero(self):
        assert compute_adoption_rate([]) == 0.0

    def test_all_adopted(self):
        decs = [_decision("approved"), _decision("executed"), _decision("modified")]
        assert compute_adoption_rate(decs) == 1.0

    def test_none_adopted(self):
        decs = [_decision("pending"), _decision("rejected")]
        assert compute_adoption_rate(decs) == 0.0

    def test_partial_adoption(self):
        decs = [_decision("approved"), _decision("rejected"), _decision("pending")]
        rate = compute_adoption_rate(decs)
        assert abs(rate - 1/3) < 0.001

    def test_status_case_insensitive(self):
        decs = [_decision("APPROVED"), _decision("EXECUTED")]
        assert compute_adoption_rate(decs) == 1.0


class TestComputeExecutionAccuracy:
    def test_empty_returns_zero(self):
        assert compute_execution_accuracy([]) == 0.0

    def test_no_adopted_returns_zero(self):
        decs = [_decision("pending"), _decision("rejected")]
        assert compute_execution_accuracy(decs) == 0.0

    def test_all_adopted_with_feedback(self):
        decs = [
            _decision("approved", "success"),
            _decision("executed", "partial"),
        ]
        assert compute_execution_accuracy(decs) == 1.0

    def test_partial_feedback(self):
        decs = [
            _decision("approved", "success"),   # has feedback
            _decision("approved", ""),           # no feedback yet
        ]
        acc = compute_execution_accuracy(decs)
        assert abs(acc - 0.5) < 0.001

    def test_failure_counts_as_feedback(self):
        # failure = 有反馈（即使失败），应计入 feedback_count
        decs = [_decision("approved", "failure")]
        assert compute_execution_accuracy(decs) == 1.0


class TestComputeTotalSaving:
    def test_only_adopted_counted(self):
        decs = [
            _decision("approved", saving=300.0),
            _decision("rejected", saving=500.0),   # 拒绝不计入
            _decision("pending",  saving=200.0),   # 待审批不计入
        ]
        assert compute_total_saving(decs) == 300.0

    def test_multiple_adopted(self):
        decs = [
            _decision("approved",  saving=100.0),
            _decision("executed",  saving=200.0),
            _decision("modified",  saving=150.0),
        ]
        assert compute_total_saving(decs) == 450.0

    def test_empty_returns_zero(self):
        assert compute_total_saving([]) == 0.0

    def test_fallback_to_top_level_field(self):
        # ai_suggestion 为空时从顶层字段取值
        d = {"decision_status": "approved", "ai_suggestion": {}, "expected_saving_yuan": 400.0, "outcome": ""}
        assert compute_total_saving([d]) == 400.0


class TestClassifyAdoption:
    def test_high(self):
        assert _classify_adoption(75.0) == "high"
        assert _classify_adoption(70.0) == "high"

    def test_medium(self):
        assert _classify_adoption(50.0) == "medium"
        assert _classify_adoption(40.0) == "medium"

    def test_low(self):
        assert _classify_adoption(39.9) == "low"
        assert _classify_adoption(0.0) == "low"


class TestRoiLabel:
    def test_excellent(self):
        assert _roi_label(10.0) == "优秀"
        assert _roi_label(15.0) == "优秀"

    def test_good(self):
        assert _roi_label(5.0) == "良好"
        assert _roi_label(9.9) == "良好"

    def test_break_even(self):
        assert _roi_label(1.0) == "持平"
        assert _roi_label(4.9) == "持平"

    def test_needs_improvement(self):
        assert _roi_label(0.5) == "待提升"
        assert _roi_label(0.0) == "待提升"


# ════════════════════════════════════════════════════════════════════════════════
# 集成测试（mock DB）
# ════════════════════════════════════════════════════════════════════════════════

def _make_orm_record(status="approved", outcome="success", saving=800.0):
    r = MagicMock()
    r.id = "d001"
    r.store_id = "S001"
    r.decision_type = "purchase_suggestion"
    r.decision_status = MagicMock()
    r.decision_status.value = status
    r.outcome = MagicMock()
    r.outcome.value = outcome
    r.ai_suggestion = {"expected_saving_yuan": saving}
    r.approved_at = datetime(2026, 3, 5, 9, 0)
    r.created_at  = datetime(2026, 3, 5, 8, 0)
    return r


@pytest.mark.asyncio
async def test_get_store_report_basic_structure():
    """get_store_report 返回所有必需字段"""
    db = AsyncMock()
    records = [
        _make_orm_record("approved", "success", 500.0),
        _make_orm_record("rejected", "", 300.0),
        _make_orm_record("pending", "", 200.0),
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    db.execute = AsyncMock(return_value=mock_result)

    report = await BehaviorScoreEngine.get_store_report(
        store_id="S001",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        db=db,
    )

    assert report["store_id"] == "S001"
    assert report["total_sent"] == 3
    assert report["total_adopted"] == 1
    assert report["total_rejected"] == 1
    assert abs(report["adoption_rate_pct"] - 33.3) < 0.1
    assert report["total_saving_yuan"] == 500.0
    assert "execution_accuracy_pct" in report
    assert "adoption_level" in report


@pytest.mark.asyncio
async def test_get_store_report_empty_db():
    """无记录时返回全零结构"""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    report = await BehaviorScoreEngine.get_store_report(
        store_id="S001",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        db=db,
    )

    assert report["total_sent"] == 0
    assert report["adoption_rate_pct"] == 0.0
    assert report["total_saving_yuan"] == 0.0


@pytest.mark.asyncio
async def test_get_system_roi_summary_aggregates():
    """get_system_roi_summary 汇总所有门店，ROI 倍数正确"""
    store_a = MagicMock()
    store_a.id = "SA"
    store_b = MagicMock()
    store_b.id = "SB"

    db = AsyncMock()
    stores_result = MagicMock()
    stores_result.scalars.return_value.all.return_value = [store_a, store_b]
    db.execute = AsyncMock(return_value=stores_result)

    async def mock_store_report(store_id, start_date, end_date, db):
        return {
            "total_sent":        10,
            "total_adopted":     7,
            "adoption_rate_pct": 70.0,
            "total_saving_yuan": 5000.0,
        }

    with patch.object(BehaviorScoreEngine, "get_store_report", side_effect=mock_store_report):
        roi = await BehaviorScoreEngine.get_system_roi_summary(
            brand_id="B001",
            month=date(2026, 3, 1),
            db=db,
        )

    # 2 stores × ¥2000/store = ¥4000 monthly cost
    # total_saving = ¥10000 → ROI = 10000/4000 = 2.5
    assert roi["store_count"] == 2
    assert roi["total_saving_yuan"] == 10000.0
    assert roi["monthly_cost_yuan"] == 4000.0
    assert abs(roi["roi_multiple"] - 2.5) < 0.01
    assert roi["roi_label"] == "持平"


@pytest.mark.asyncio
async def test_get_system_roi_summary_skips_failed_store():
    """单店报告失败时静默跳过"""
    store_a = MagicMock(); store_a.id = "SA"
    store_b = MagicMock(); store_b.id = "SB"

    db = AsyncMock()
    stores_result = MagicMock()
    stores_result.scalars.return_value.all.return_value = [store_a, store_b]
    db.execute = AsyncMock(return_value=stores_result)

    async def mock_store_report(store_id, start_date, end_date, db):
        if store_id == "SB":
            raise RuntimeError("DB 超时")
        return {"total_sent": 5, "total_adopted": 4, "adoption_rate_pct": 80.0, "total_saving_yuan": 2000.0}

    with patch.object(BehaviorScoreEngine, "get_store_report", side_effect=mock_store_report):
        roi = await BehaviorScoreEngine.get_system_roi_summary(
            brand_id="B001",
            month=date(2026, 3, 1),
            db=db,
        )

    # 只有 SA 被计入
    assert roi["store_count"] == 1
    assert roi["total_saving_yuan"] == 2000.0
