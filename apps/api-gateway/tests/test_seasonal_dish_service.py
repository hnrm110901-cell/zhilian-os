"""
季节性菜品自动上下架服务测试
"""

import pytest
from datetime import date

from src.services.seasonal_dish_service import (
    SeasonalDishService,
    SeasonConfig,
)


@pytest.fixture
def service():
    return SeasonalDishService()


class TestCheckSeasonalAvailability:
    def test_lobster_available_in_summer(self, service):
        """小龙虾在7月应当季"""
        result = service.check_seasonal_availability("SD001", date(2026, 7, 15))
        assert result["available"] is True
        assert result["is_in_season"] is True
        assert result["dish_name"] == "小龙虾"

    def test_lobster_unavailable_in_winter(self, service):
        """小龙虾在1月不当季"""
        result = service.check_seasonal_availability("SD001", date(2026, 1, 15))
        assert result["available"] is False
        assert "非当季" in result["reason"]

    def test_cross_year_season(self, service):
        """腊味合蒸（11-2月）跨年测试"""
        # 12月应该当季
        result = service.check_seasonal_availability("SD005", date(2026, 12, 15))
        assert result["is_in_season"] is True
        # 1月也应该当季
        result = service.check_seasonal_availability("SD005", date(2026, 1, 15))
        assert result["is_in_season"] is True
        # 6月不当季
        result = service.check_seasonal_availability("SD005", date(2026, 6, 15))
        assert result["is_in_season"] is False

    def test_nonexistent_dish(self, service):
        result = service.check_seasonal_availability("NOPE", date(2026, 6, 1))
        assert result["available"] is False
        assert "未找到" in result["reason"]

    def test_price_in_result(self, service):
        """结果包含价格（fen+yuan）"""
        result = service.check_seasonal_availability("SD001", date(2026, 7, 1))
        assert result["price_fen"] == 8800
        assert result["price_yuan"] == 88.00


class TestUpcomingSeasonalChanges:
    def test_changes_in_range(self, service):
        """30天内能检测到变更"""
        # 4月15日，5月1日小龙虾将上架（16天后）
        changes = service.get_upcoming_seasonal_changes(date(2026, 4, 15), 30)
        dish_names = [c.dish_name for c in changes]
        actions = {c.dish_name: c.action for c in changes}
        # 春笋在4月结束，5月1日下架
        assert "春笋" in dish_names
        assert actions["春笋"] == "下架"

    def test_no_changes_short_range(self, service):
        """非常短的前瞻期可能无变更"""
        changes = service.get_upcoming_seasonal_changes(date(2026, 7, 15), 1)
        # 7月中旬前后通常没有变更
        # 这里只验证不报错
        assert isinstance(changes, list)

    def test_changes_sorted_by_days(self, service):
        changes = service.get_upcoming_seasonal_changes(date(2026, 4, 1), 60)
        if len(changes) >= 2:
            assert changes[0].days_until <= changes[1].days_until


class TestAutoToggleDishes:
    def test_toggle_summer_dishes(self, service):
        """7月：小龙虾/冬瓜/秋葵应上架"""
        results = service.auto_toggle_dishes(current_date=date(2026, 7, 1))
        actions = {r.dish_name: r.action for r in results}
        assert actions["小龙虾"] == "上架"
        assert actions["冬瓜"] == "上架"
        assert actions["秋葵"] == "上架"
        # 大闸蟹7月不当季，不应上架
        assert actions["大闸蟹"] != "上架"

    def test_toggle_idempotent(self, service):
        """连续执行两次，第二次应该全部无变化"""
        service.auto_toggle_dishes(current_date=date(2026, 7, 1))
        results2 = service.auto_toggle_dishes(current_date=date(2026, 7, 1))
        changed = [r for r in results2 if r.action != "无变化"]
        assert len(changed) == 0

    def test_toggle_with_custom_config(self, service):
        """自定义配置也能正确处理"""
        custom = [SeasonConfig(
            dish_id="CUSTOM01", dish_name="测试菜", start_month=3, end_month=5,
        )]
        results = service.auto_toggle_dishes(custom, date(2026, 4, 1))
        assert results[0].action == "上架"


class TestSeasonalCalendar:
    def test_calendar_has_12_months(self, service):
        calendar = service.get_seasonal_calendar(2026)
        assert len(calendar) == 12

    def test_july_has_summer_dishes(self, service):
        calendar = service.get_seasonal_calendar(2026)
        july = calendar[6]  # 0-indexed
        assert july.month == 7
        assert "小龙虾" in july.available_dishes
        assert "冬瓜" in july.available_dishes

    def test_january_has_winter_dishes(self, service):
        calendar = service.get_seasonal_calendar(2026)
        jan = calendar[0]
        assert "腊味合蒸" in jan.available_dishes


class TestNotifyUpcomingChange:
    def test_urgent_notification(self, service):
        """3天内变更生成高紧急度通知"""
        from src.services.seasonal_dish_service import SeasonalChange
        changes = [
            SeasonalChange("SD001", "小龙虾", "上架", "2026-05-01", 2, "进入当季"),
        ]
        notifications = service.notify_upcoming_change(changes, "湘菜馆")
        assert len(notifications) == 1
        assert notifications[0].urgency == "高"
        assert "紧急" in notifications[0].title
        assert "店长" in notifications[0].notify_roles

    def test_no_changes_no_notifications(self, service):
        notifications = service.notify_upcoming_change([], "测试店")
        assert len(notifications) == 0
