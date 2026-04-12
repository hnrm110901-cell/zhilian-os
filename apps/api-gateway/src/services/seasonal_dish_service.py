"""
季节性菜品自动上下架服务（Seasonal Dish Service）

核心功能：
- 季节菜品配置管理
- 当季可用性检查
- 未来 N 天上下架变更预测
- 批量自动上下架
- 全年季节菜品日历
- 上下架预告通知

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


@dataclass
class SeasonConfig:
    """季节菜品配置"""
    dish_id: str
    dish_name: str
    start_month: int  # 开始月份（含）
    end_month: int    # 结束月份（含）
    regions: List[str] = field(default_factory=lambda: ["全国"])
    price_fen: int = 0  # 参考价（分）
    price_yuan: float = 0.0
    category: str = "时令"
    notes: str = ""


@dataclass
class SeasonalChange:
    """上下架变更"""
    dish_id: str
    dish_name: str
    action: str  # 上架/下架
    change_date: str  # YYYY-MM-DD
    days_until: int
    reason: str


@dataclass
class ToggleResult:
    """上下架执行结果"""
    dish_id: str
    dish_name: str
    action: str  # 上架/下架/无变化
    previous_status: str
    new_status: str
    reason: str


@dataclass
class CalendarMonth:
    """日历月份数据"""
    month: int
    month_name: str
    available_dishes: List[str]
    upcoming_on: List[str]   # 本月将上架的
    upcoming_off: List[str]  # 本月将下架的


@dataclass
class ChangeNotification:
    """变更通知"""
    title: str
    content: str
    changes: List[Dict[str, str]]
    urgency: str  # 高/中/低
    notify_roles: List[str]


# ── 预置季节菜品配置 ─────────────────────────────────────────────────────

DEFAULT_SEASONAL_DISHES: List[SeasonConfig] = [
    SeasonConfig(
        dish_id="SD001", dish_name="小龙虾",
        start_month=5, end_month=9,
        regions=["全国"], price_fen=8800, price_yuan=88.00,
        category="时令招牌", notes="夏季爆款，需提前备货",
    ),
    SeasonConfig(
        dish_id="SD002", dish_name="大闸蟹",
        start_month=9, end_month=12,
        regions=["全国"], price_fen=16800, price_yuan=168.00,
        category="时令招牌", notes="阳澄湖产地直供",
    ),
    SeasonConfig(
        dish_id="SD003", dish_name="春笋",
        start_month=3, end_month=4,
        regions=["华东", "华中", "华南"], price_fen=3800, price_yuan=38.00,
        category="时令蔬菜", notes="新鲜现挖，保鲜期短",
    ),
    SeasonConfig(
        dish_id="SD004", dish_name="冬瓜",
        start_month=6, end_month=9,
        regions=["全国"], price_fen=1800, price_yuan=18.00,
        category="时令蔬菜", notes="消暑必备",
    ),
    SeasonConfig(
        dish_id="SD005", dish_name="腊味合蒸",
        start_month=11, end_month=2,
        regions=["湖南", "湖北"], price_fen=6800, price_yuan=68.00,
        category="时令招牌", notes="湖南传统腊味，冬季限定",
    ),
    SeasonConfig(
        dish_id="SD006", dish_name="荠菜馄饨",
        start_month=2, end_month=4,
        regions=["华东", "华中"], price_fen=2800, price_yuan=28.00,
        category="时令小吃", notes="早春时鲜",
    ),
    SeasonConfig(
        dish_id="SD007", dish_name="秋葵",
        start_month=6, end_month=9,
        regions=["全国"], price_fen=2200, price_yuan=22.00,
        category="时令蔬菜", notes="白灼/凉拌均可",
    ),
    SeasonConfig(
        dish_id="SD008", dish_name="糖炒板栗",
        start_month=9, end_month=12,
        regions=["全国"], price_fen=1500, price_yuan=15.00,
        category="时令小吃", notes="秋季零食",
    ),
]

MONTH_NAMES = {
    1: "一月", 2: "二月", 3: "三月", 4: "四月",
    5: "五月", 6: "六月", 7: "七月", 8: "八月",
    9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
}


class SeasonalDishService:
    """
    季节性菜品自动上下架服务

    管理菜品的季节性上下架，支持跨年月份范围。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(service="seasonal_dish")
        # 菜品配置：dish_id → SeasonConfig
        self._configs: Dict[str, SeasonConfig] = {}
        # 当前上架状态：dish_id → bool（True=上架）
        self._dish_status: Dict[str, bool] = {}

        # 加载预置配置
        for cfg in DEFAULT_SEASONAL_DISHES:
            self._configs[cfg.dish_id] = cfg

    def add_config(self, config: SeasonConfig) -> None:
        """添加或更新季节菜品配置"""
        self._configs[config.dish_id] = config
        self._logger.info("季节菜品配置更新", dish=config.dish_name)

    def get_configs(self) -> List[SeasonConfig]:
        """获取所有配置"""
        return list(self._configs.values())

    # ── 核心方法 ──────────────────────────────────────────────────────────

    def check_seasonal_availability(
        self,
        dish_id: str,
        current_date: Optional[date] = None,
        region: str = "全国",
    ) -> Dict[str, Any]:
        """
        检查菜品是否当季可用

        Args:
            dish_id: 菜品ID
            current_date: 当前日期（默认today）
            region: 地区
        """
        if current_date is None:
            current_date = date.today()

        config = self._configs.get(dish_id)
        if config is None:
            return {
                "dish_id": dish_id,
                "available": False,
                "reason": "未找到该菜品的季节配置",
            }

        month = current_date.month
        is_in_season = self._is_in_season(month, config.start_month, config.end_month)

        # 地区检查
        region_match = "全国" in config.regions or region in config.regions

        available = is_in_season and region_match

        # 计算距离下一个季节变更的天数
        if is_in_season:
            # 距下架还有多少天
            end_date = self._month_end_date(current_date.year, config.end_month)
            days_remaining = (end_date - current_date).days
            if days_remaining < 0:
                # 跨年的情况
                end_date = self._month_end_date(current_date.year + 1, config.end_month)
                days_remaining = (end_date - current_date).days
            next_change = f"距下架还有 {days_remaining} 天"
        else:
            # 距上架还有多少天
            start_date = date(current_date.year, config.start_month, 1)
            if start_date <= current_date:
                start_date = date(current_date.year + 1, config.start_month, 1)
            days_until = (start_date - current_date).days
            next_change = f"距上架还有 {days_until} 天"

        reason = ""
        if not is_in_season:
            reason = f"非当季（上架月份：{config.start_month}-{config.end_month}月）"
        elif not region_match:
            reason = f"该地区（{region}）不在供应范围内"

        return {
            "dish_id": dish_id,
            "dish_name": config.dish_name,
            "available": available,
            "is_in_season": is_in_season,
            "region_match": region_match,
            "season_range": f"{config.start_month}月-{config.end_month}月",
            "next_change": next_change,
            "reason": reason,
            "price_fen": config.price_fen,
            "price_yuan": config.price_yuan,
        }

    def get_upcoming_seasonal_changes(
        self,
        current_date: Optional[date] = None,
        lookahead_days: int = 30,
    ) -> List[SeasonalChange]:
        """
        获取未来 N 天的上下架变更

        Args:
            current_date: 当前日期
            lookahead_days: 前瞻天数
        """
        if current_date is None:
            current_date = date.today()

        changes: List[SeasonalChange] = []
        end_date = current_date + timedelta(days=lookahead_days)

        for config in self._configs.values():
            # 检查上架日期（start_month的1号）
            for year in (current_date.year, current_date.year + 1):
                on_date = date(year, config.start_month, 1)
                if current_date < on_date <= end_date:
                    days_until = (on_date - current_date).days
                    changes.append(SeasonalChange(
                        dish_id=config.dish_id,
                        dish_name=config.dish_name,
                        action="上架",
                        change_date=on_date.isoformat(),
                        days_until=days_until,
                        reason=f"进入当季（{config.start_month}-{config.end_month}月）",
                    ))

            # 检查下架日期（end_month的最后一天+1 → 即下个月1号）
            for year in (current_date.year, current_date.year + 1):
                off_date = self._next_month_first(year, config.end_month)
                if current_date < off_date <= end_date:
                    days_until = (off_date - current_date).days
                    changes.append(SeasonalChange(
                        dish_id=config.dish_id,
                        dish_name=config.dish_name,
                        action="下架",
                        change_date=off_date.isoformat(),
                        days_until=days_until,
                        reason=f"季节结束（{config.start_month}-{config.end_month}月）",
                    ))

        # 按日期排序
        changes.sort(key=lambda c: c.days_until)

        self._logger.info(
            "查询上下架变更",
            lookahead_days=lookahead_days,
            changes_count=len(changes),
        )
        return changes

    def auto_toggle_dishes(
        self,
        dishes_config: Optional[List[SeasonConfig]] = None,
        current_date: Optional[date] = None,
    ) -> List[ToggleResult]:
        """
        批量自动上下架

        Args:
            dishes_config: 菜品配置列表（为空则用内部配置）
            current_date: 当前日期
        """
        if current_date is None:
            current_date = date.today()

        configs = dishes_config or list(self._configs.values())
        results: List[ToggleResult] = []

        for config in configs:
            # 确保配置已注册
            if config.dish_id not in self._configs:
                self._configs[config.dish_id] = config

            month = current_date.month
            should_be_on = self._is_in_season(month, config.start_month, config.end_month)
            currently_on = self._dish_status.get(config.dish_id, False)

            if should_be_on and not currently_on:
                # 需要上架
                self._dish_status[config.dish_id] = True
                results.append(ToggleResult(
                    dish_id=config.dish_id,
                    dish_name=config.dish_name,
                    action="上架",
                    previous_status="下架",
                    new_status="上架",
                    reason=f"进入当季（{config.start_month}-{config.end_month}月）",
                ))
            elif not should_be_on and currently_on:
                # 需要下架
                self._dish_status[config.dish_id] = False
                results.append(ToggleResult(
                    dish_id=config.dish_id,
                    dish_name=config.dish_name,
                    action="下架",
                    previous_status="上架",
                    new_status="下架",
                    reason=f"季节结束（{config.start_month}-{config.end_month}月）",
                ))
            else:
                status_str = "上架" if currently_on else "下架"
                results.append(ToggleResult(
                    dish_id=config.dish_id,
                    dish_name=config.dish_name,
                    action="无变化",
                    previous_status=status_str,
                    new_status=status_str,
                    reason="状态正确，无需变更",
                ))

        changed = [r for r in results if r.action != "无变化"]
        self._logger.info(
            "批量上下架完成",
            total=len(results),
            changed=len(changed),
        )
        return results

    def get_seasonal_calendar(self, year: int) -> List[CalendarMonth]:
        """
        全年季节菜品日历

        Args:
            year: 年份
        """
        calendar: List[CalendarMonth] = []

        for month in range(1, 13):
            available = []
            upcoming_on = []
            upcoming_off = []

            for config in self._configs.values():
                in_season = self._is_in_season(month, config.start_month, config.end_month)

                if in_season:
                    available.append(config.dish_name)

                # 本月上架（start_month == month）
                if config.start_month == month:
                    upcoming_on.append(config.dish_name)

                # 本月下架（end_month == month，下个月就不在季了）
                next_month = month + 1 if month < 12 else 1
                if not self._is_in_season(next_month, config.start_month, config.end_month) and in_season:
                    upcoming_off.append(config.dish_name)

            calendar.append(CalendarMonth(
                month=month,
                month_name=MONTH_NAMES[month],
                available_dishes=available,
                upcoming_on=upcoming_on,
                upcoming_off=upcoming_off,
            ))

        return calendar

    def notify_upcoming_change(
        self,
        changes: List[SeasonalChange],
        store_name: str = "",
    ) -> List[ChangeNotification]:
        """
        生成上下架预告通知

        Args:
            changes: 变更列表
            store_name: 门店名称
        """
        notifications: List[ChangeNotification] = []

        # 按紧急度分组
        urgent = [c for c in changes if c.days_until <= 3]
        soon = [c for c in changes if 3 < c.days_until <= 7]
        upcoming = [c for c in changes if c.days_until > 7]

        if urgent:
            items = [
                {"dish": c.dish_name, "action": c.action, "date": c.change_date}
                for c in urgent
            ]
            on_items = [c.dish_name for c in urgent if c.action == "上架"]
            off_items = [c.dish_name for c in urgent if c.action == "下架"]
            parts = []
            if on_items:
                parts.append(f"上架：{'、'.join(on_items)}")
            if off_items:
                parts.append(f"下架：{'、'.join(off_items)}")

            notifications.append(ChangeNotification(
                title=f"【紧急】{store_name}菜品上下架提醒（3天内）",
                content=f"以下菜品将在3天内变更：{'; '.join(parts)}。请提前做好备货/清货准备。",
                changes=items,
                urgency="高",
                notify_roles=["店长", "厨师长", "采购"],
            ))

        if soon:
            items = [
                {"dish": c.dish_name, "action": c.action, "date": c.change_date}
                for c in soon
            ]
            notifications.append(ChangeNotification(
                title=f"【提醒】{store_name}本周菜品上下架预告",
                content=f"本周有 {len(soon)} 道菜品变更，请关注。",
                changes=items,
                urgency="中",
                notify_roles=["店长", "厨师长"],
            ))

        if upcoming:
            items = [
                {"dish": c.dish_name, "action": c.action, "date": c.change_date}
                for c in upcoming
            ]
            notifications.append(ChangeNotification(
                title=f"{store_name}季节菜品预告",
                content=f"未来有 {len(upcoming)} 道菜品即将变更，请提前规划。",
                changes=items,
                urgency="低",
                notify_roles=["店长"],
            ))

        self._logger.info(
            "变更通知生成",
            urgent=len(urgent),
            soon=len(soon),
            upcoming=len(upcoming),
        )
        return notifications

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _is_in_season(self, month: int, start_month: int, end_month: int) -> bool:
        """判断月份是否在季节范围内（支持跨年，如11-2月）"""
        if start_month <= end_month:
            return start_month <= month <= end_month
        else:
            # 跨年：如 11月-2月 → month >= 11 or month <= 2
            return month >= start_month or month <= end_month

    def _month_end_date(self, year: int, month: int) -> date:
        """获取某月最后一天"""
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)

    def _next_month_first(self, year: int, month: int) -> date:
        """获取指定月份的下个月1号"""
        if month == 12:
            return date(year + 1, 1, 1)
        return date(year, month + 1, 1)
