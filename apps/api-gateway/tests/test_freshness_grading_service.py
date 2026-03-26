"""
海鲜新鲜度分级服务测试
覆盖等级计算、剩余时间、折扣建议、下架判定、批量检查、看板统计
"""

import pytest
from datetime import datetime, timedelta, timezone

from src.services.freshness_grading_service import (
    FreshnessGrade,
    SeafoodCategory,
    StorageType,
    calculate_grade,
    get_remaining_hours,
    should_discount,
    should_remove,
    batch_grade_check,
    get_freshness_dashboard,
    _get_effective_decay_rate,
    _elapsed_hours,
)


# ──────────────────── 辅助工具 ────────────────────

def _make_time(hours_ago: float, now: datetime = None) -> datetime:
    """构造 hours_ago 小时前的时间"""
    if now is None:
        now = datetime.now(timezone.utc)
    return now - timedelta(hours=hours_ago)


NOW = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)


# ──────────────────── calculate_grade 测试 ────────────────────

class TestCalculateGrade:
    """等级计算测试"""

    def test_chilled_fresh_within_6h_is_A(self):
        """冰鲜+冷藏，3小时前到货 → A级（基准衰减=1.0×0.6=0.6，有效1.8h<6h）"""
        arrival = _make_time(3.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.CHILLED, StorageType.CHILLED, NOW)
        assert grade == FreshnessGrade.A

    def test_chilled_ambient_24h_is_C(self):
        """冰鲜+常温，24小时 → 有效时间=24×1.0×1.5=36h → C级(24-48h)"""
        arrival = _make_time(24.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.CHILLED, StorageType.AMBIENT, NOW)
        assert grade == FreshnessGrade.C

    def test_live_water_tank_5h_is_A(self):
        """活鲜+水箱，5小时 → 有效时间=5×2.0×0.5=5h → A级(<6h)"""
        arrival = _make_time(5.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.LIVE, StorageType.WATER_TANK, NOW)
        assert grade == FreshnessGrade.A

    def test_live_ambient_4h_is_B(self):
        """活鲜+常温，4小时 → 有效时间=4×2.0×1.0=8h → B级(6-24h)"""
        arrival = _make_time(4.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.LIVE, StorageType.AMBIENT, NOW)
        assert grade == FreshnessGrade.B

    def test_frozen_in_freezer_100h_still_B(self):
        """冷冻+冷冻存储，100小时 → 有效时间=100×0.3×0.5=15h → B级(6-24h)"""
        arrival = _make_time(100.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.FROZEN, StorageType.FROZEN, NOW)
        assert grade == FreshnessGrade.B

    def test_frozen_ambient_long_time_is_E(self):
        """冷冻+常温，200小时 → 有效时间=200×0.3×2.5=150h → E级(>72h)"""
        arrival = _make_time(200.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.FROZEN, StorageType.AMBIENT, NOW)
        assert grade == FreshnessGrade.E

    def test_live_ambient_40h_is_E(self):
        """活鲜+常温，40小时 → 有效时间=40×2.0×1.0=80h → E级(>72h)"""
        arrival = _make_time(40.0, NOW)
        grade = calculate_grade(arrival, SeafoodCategory.LIVE, StorageType.AMBIENT, NOW)
        assert grade == FreshnessGrade.E

    def test_just_arrived_is_A(self):
        """刚到货 → A级"""
        grade = calculate_grade(NOW, SeafoodCategory.CHILLED, StorageType.CHILLED, NOW)
        assert grade == FreshnessGrade.A

    def test_string_category_works(self):
        """支持字符串类型的品类参数"""
        arrival = _make_time(3.0, NOW)
        grade = calculate_grade(arrival, "chilled", "chilled", NOW)
        assert grade == FreshnessGrade.A


# ──────────────────── get_remaining_hours 测试 ────────────────────

class TestGetRemainingHours:
    """剩余时间计算测试"""

    def test_just_arrived_has_full_remaining(self):
        """刚到货的冰鲜+冷藏，A级剩余时间=6/(1.0×0.6)=10h"""
        remaining = get_remaining_hours(NOW, SeafoodCategory.CHILLED, StorageType.CHILLED, now=NOW)
        assert remaining == 10.0

    def test_expired_returns_zero(self):
        """过期品剩余时间为0"""
        arrival = _make_time(200.0, NOW)
        remaining = get_remaining_hours(arrival, SeafoodCategory.FROZEN, StorageType.AMBIENT, now=NOW)
        assert remaining == 0.0

    def test_remaining_decreases_over_time(self):
        """时间越长，剩余时间越少"""
        r1 = get_remaining_hours(_make_time(1.0, NOW), SeafoodCategory.CHILLED, StorageType.CHILLED, now=NOW)
        r2 = get_remaining_hours(_make_time(5.0, NOW), SeafoodCategory.CHILLED, StorageType.CHILLED, now=NOW)
        assert r1 > r2


# ──────────────────── should_discount 测试 ────────────────────

class TestShouldDiscount:
    """折扣建议测试"""

    def test_grade_A_no_discount(self):
        disc, pct = should_discount(FreshnessGrade.A)
        assert disc is False
        assert pct is None

    def test_grade_C_discount_90(self):
        disc, pct = should_discount(FreshnessGrade.C)
        assert disc is True
        assert pct == 90

    def test_grade_D_discount_70(self):
        disc, pct = should_discount(FreshnessGrade.D)
        assert disc is True
        assert pct == 70

    def test_grade_E_no_discount_should_remove(self):
        """E级不打折（应下架）"""
        disc, pct = should_discount(FreshnessGrade.E)
        assert disc is False
        assert pct is None


# ──────────────────── should_remove 测试 ────────────────────

class TestShouldRemove:
    """下架判定测试"""

    def test_grade_E_must_remove(self):
        assert should_remove(FreshnessGrade.E) is True

    def test_grade_D_not_removed(self):
        assert should_remove(FreshnessGrade.D) is False

    def test_grade_A_not_removed(self):
        assert should_remove(FreshnessGrade.A) is False


# ──────────────────── batch_grade_check 测试 ────────────────────

class TestBatchGradeCheck:
    """批量检查测试"""

    def test_batch_with_multiple_items(self):
        """批量检查多个品项"""
        items = [
            {
                "item_id": "SF001",
                "arrival_time": _make_time(2.0, NOW),
                "category": "chilled",
                "storage_type": "chilled",
                "unit_price_fen": 5000,  # ¥50.00
            },
            {
                "item_id": "SF002",
                "arrival_time": _make_time(40.0, NOW),
                "category": "live",
                "storage_type": "ambient",
                "unit_price_fen": 8000,  # ¥80.00
            },
        ]
        results = batch_grade_check(items, NOW)
        assert len(results) == 2
        assert results[0]["grade"] == "A"
        assert results[0]["should_discount"] is False
        assert results[1]["grade"] == "E"
        assert results[1]["should_remove"] is True

    def test_batch_with_invalid_item(self):
        """缺少必要字段时返回错误而非崩溃"""
        items = [
            {"item_id": "BAD01"},  # 缺少必要字段
        ]
        results = batch_grade_check(items, NOW)
        assert len(results) == 1
        assert "error" in results[0]

    def test_batch_discount_price_calculation(self):
        """折扣品计算折后价格（金额单位 fen）"""
        items = [
            {
                "item_id": "SF003",
                "arrival_time": _make_time(24.0, NOW),
                "category": "chilled",
                "storage_type": "ambient",  # 有效36h → C级 → 9折
                "unit_price_fen": 10000,
            },
        ]
        results = batch_grade_check(items, NOW)
        assert results[0]["grade"] == "C"
        assert results[0]["discounted_price_fen"] == 9000  # 10000 * 90%


# ──────────────────── get_freshness_dashboard 测试 ────────────────────

class TestFreshnessDashboard:
    """看板统计测试"""

    def test_dashboard_grouping(self):
        """看板按等级分组统计"""
        items = [
            {"item_id": "A1", "arrival_time": _make_time(1.0, NOW), "category": "chilled", "storage_type": "chilled"},
            {"item_id": "A2", "arrival_time": _make_time(2.0, NOW), "category": "chilled", "storage_type": "chilled"},
            {"item_id": "E1", "arrival_time": _make_time(40.0, NOW), "category": "live", "storage_type": "ambient"},
        ]
        dashboard = get_freshness_dashboard(items, NOW)
        assert dashboard["total"] == 3
        assert dashboard["by_grade"]["A"]["count"] == 2
        assert dashboard["by_grade"]["E"]["count"] == 1
        assert dashboard["summary"]["fresh_count"] == 2
        assert dashboard["summary"]["expired_count"] == 1

    def test_dashboard_alerts_for_expired(self):
        """E级品项生成告警"""
        items = [
            {"item_id": "E1", "arrival_time": _make_time(40.0, NOW), "category": "live", "storage_type": "ambient"},
        ]
        dashboard = get_freshness_dashboard(items, NOW)
        assert len(dashboard["alerts"]) == 1
        assert dashboard["alerts"][0]["alert_type"] == "过期下架"
        assert dashboard["alerts"][0]["action"] == "立即下架"

    def test_empty_items_returns_valid_structure(self):
        """空列表返回有效结构"""
        dashboard = get_freshness_dashboard([], NOW)
        assert dashboard["total"] == 0
        assert dashboard["summary"]["fresh_rate"] == 0.0


# ──────────────────── 内部函数测试 ────────────────────

class TestInternalHelpers:
    """内部辅助函数测试"""

    def test_effective_decay_rate_live_water_tank(self):
        rate = _get_effective_decay_rate("live", "water_tank")
        assert rate == 2.0 * 0.5  # 1.0

    def test_elapsed_hours_naive_datetime(self):
        """无时区的 datetime 视为 UTC"""
        naive_arrival = datetime(2026, 3, 26, 10, 0, 0)
        naive_now = datetime(2026, 3, 26, 13, 0, 0)
        elapsed = _elapsed_hours(naive_arrival, naive_now)
        assert elapsed == 3.0

    def test_elapsed_hours_future_arrival_returns_zero(self):
        """到货时间在未来返回0"""
        future = NOW + timedelta(hours=5)
        elapsed = _elapsed_hours(future, NOW)
        assert elapsed == 0.0
