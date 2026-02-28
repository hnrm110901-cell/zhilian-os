"""
AuspiciousDateService — 吉日感知服务

职责：
  - 识别婚庆/宴会"好日子"（固定吉日 + 七夕 + 黄金周 + 周末基础系数）
  - 返回需求倍增因子（供 DailyHubService 注入外部因子模块、ForecastService 调权重）
  - 提供 30 天吉日日历（供前端展示 / 宴会销控参考）

好日子体系（参考 PPT 分析）：
  - 谐音吉日：5/20「我爱你」×2.2、5/21 ×2.0、9/9「长长久久」×1.6、
              1/14 ×1.4、2/14「情人节」×1.3、8/8 ×1.5、
              10/10「十全十美」×1.5、11/11「一生一世」×1.3、12/12 ×1.4
  - 七夕（农历7月初7，每年8月10~25日浮动区间估算）×1.9
  - 国庆黄金周（10/1~10/7）×1.8
  - 劳动节黄金周（5/1~5/7）×1.7
  - 周末基础因子 ×1.2（与其他因子叠加时取 max，不累乘）
  - 门店可自定义额外吉日（store_config["custom_auspicious"]）

设计：
  - 纯内存计算，无 DB/Redis 依赖，可在 Celery、Agent、FastAPI 中直接调用
  - 七夕使用近似区间（每年农历7月7日对应公历 8月10~25 日浮动，
    此处用一个简单规则估算：8月10日~8月20日区间内的第一个周六）
  - 未来可接入农历库（lunarcalendar / LunarPython）精确计算七夕
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# ── 固定谐音吉日 (month, day) → (label, demand_factor) ──────────────────────
_FIXED_AUSPICIOUS: Dict[Tuple[int, int], Tuple[str, float]] = {
    (1, 14):  ("一生一世 1.14",  1.4),
    (2, 14):  ("西方情人节",     1.3),
    (5, 20):  ("我爱你 5.20",    2.2),
    (5, 21):  ("我爱你 5.21",    2.0),
    (7, 7):   ("七夕情人节",     1.9),   # 公历固定7/7占位；精确七夕由 _estimate_qixi 覆盖
    (8, 8):   ("双喜吉日 8.8",   1.5),
    (9, 9):   ("长长久久 9.9",   1.6),
    (10, 10): ("十全十美 10.10", 1.5),
    (11, 11): ("一生一世 11.11", 1.3),
    (12, 12): ("要爱要爱 12.12", 1.4),
}

# ── 黄金周区间 ────────────────────────────────────────────────────────────────
_GOLDEN_WEEK_RANGES: List[Tuple[int, int, int, int, str, float]] = [
    # (start_month, start_day, end_month, end_day, label, factor)
    (5,  1, 5,  7,  "劳动节黄金周", 1.7),
    (10, 1, 10, 7,  "国庆节黄金周", 1.8),
]

# 七夕区间估算（农历7月7日通常落在公历8月10~25日之间）
_QIXI_WINDOW_START = (8, 10)  # (month, day)
_QIXI_WINDOW_END   = (8, 25)  # (month, day)
_QIXI_FACTOR       = 1.9
_QIXI_LABEL        = "七夕情人节"

# 周末基础加成（与其他因子 max 叠加，而非相乘，避免过度高估）
_WEEKEND_FACTOR = 1.2


def _in_golden_week(d: date) -> Optional[Tuple[str, float]]:
    """判断日期是否在黄金周区间内，返回 (label, factor) 或 None。"""
    for sm, sd, em, ed, label, factor in _GOLDEN_WEEK_RANGES:
        start = date(d.year, sm, sd)
        end   = date(d.year, em, ed)
        if start <= d <= end:
            return label, factor
    return None


def _estimate_qixi(year: int) -> date:
    """
    简单估算：取当年8月10日起，第一个周六作为七夕的代理日期。

    这是近似值，若项目后续引入 lunarcalendar 库可替换为精确计算。
    """
    d = date(year, 8, 10)
    # weekday(): Mon=0 … Sat=5
    while d.weekday() != 5:  # 找周六
        d += timedelta(days=1)
    # 不超过8月20日上限
    if d > date(year, 8, 20):
        d = date(year, 8, 10)
    return d


def _is_in_qixi_window(d: date) -> bool:
    """判断日期是否落在七夕区间（8/10~8/25）。"""
    return (
        d.month == 8
        and _QIXI_WINDOW_START[1] <= d.day <= _QIXI_WINDOW_END[1]
    )


class AuspiciousDateInfo:
    """单个日期的吉日信息。"""

    __slots__ = ("date", "is_auspicious", "label", "demand_factor", "sources")

    def __init__(
        self,
        target_date:   date,
        is_auspicious: bool,
        label:         str,
        demand_factor: float,
        sources:       List[str],
    ):
        self.date          = target_date
        self.is_auspicious = is_auspicious
        self.label         = label
        self.demand_factor = demand_factor
        self.sources       = sources  # e.g. ["fixed_auspicious", "golden_week", "weekend"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date":          self.date.isoformat(),
            "is_auspicious": self.is_auspicious,
            "label":         self.label,
            "demand_factor": self.demand_factor,
            "sources":       self.sources,
        }


class AuspiciousDateService:
    """
    吉日感知服务（无状态，可直接实例化使用）。

    Usage:
        svc = AuspiciousDateService()
        info = svc.get_info(date(2025, 5, 20))
        # AuspiciousDateInfo(date=2025-05-20, label="我爱你 5.20", demand_factor=2.2)
        factor = svc.get_factor(date(2025, 5, 20))  # → 2.2
        calendar = svc.get_calendar(30)             # → 30 天日历列表
    """

    def __init__(self, store_config: Optional[Dict[str, Any]] = None):
        """
        Args:
            store_config: 可选门店自定义配置，支持：
              {
                "custom_auspicious": [
                    {"month": 6, "day": 18, "label": "618大吉", "factor": 1.3}
                ]
              }
        """
        self._custom: Dict[Tuple[int, int], Tuple[str, float]] = {}
        if store_config and store_config.get("custom_auspicious"):
            for item in store_config["custom_auspicious"]:
                m = item.get("month")
                d = item.get("day")
                if m and d:
                    self._custom[(m, d)] = (
                        item.get("label", f"{m}/{d}自定义吉日"),
                        float(item.get("factor", 1.3)),
                    )

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_info(self, target_date: date) -> AuspiciousDateInfo:
        """
        获取单日吉日信息。

        优先级（取最高 factor，不累乘）：
          自定义 > 固定谐音 > 七夕区间 > 黄金周 > 周末基础
        """
        candidates: List[Tuple[str, float, str]] = []  # (label, factor, source)

        # 1. 自定义吉日
        custom = self._custom.get((target_date.month, target_date.day))
        if custom:
            candidates.append((custom[0], custom[1], "custom"))

        # 2. 固定谐音吉日（跳过占位 7/7，由七夕区间处理）
        fixed = _FIXED_AUSPICIOUS.get((target_date.month, target_date.day))
        if fixed and not (target_date.month == 7 and target_date.day == 7):
            candidates.append((fixed[0], fixed[1], "fixed_auspicious"))

        # 3. 七夕区间（8/10 ~ 8/25）
        if _is_in_qixi_window(target_date):
            qixi_estimate = _estimate_qixi(target_date.year)
            if target_date == qixi_estimate:
                candidates.append((_QIXI_LABEL, _QIXI_FACTOR, "qixi_estimated"))
            else:
                # 整个七夕窗口期都有宴会需求抬升（略低于七夕当天）
                candidates.append((f"{_QIXI_LABEL}窗口期", _QIXI_FACTOR * 0.85, "qixi_window"))

        # 4. 黄金周
        golden = _in_golden_week(target_date)
        if golden:
            candidates.append((golden[0], golden[1], "golden_week"))

        # 5. 周末基础因子（weekday 5=Sat, 6=Sun）
        if target_date.weekday() >= 5:
            candidates.append(("周末", _WEEKEND_FACTOR, "weekend"))

        if not candidates:
            return AuspiciousDateInfo(
                target_date=target_date,
                is_auspicious=False,
                label="普通工作日",
                demand_factor=1.0,
                sources=[],
            )

        # 取最高因子（不累乘，防止组合过度放大）
        best_label, best_factor, _ = max(candidates, key=lambda x: x[1])
        sources = [c[2] for c in candidates]

        return AuspiciousDateInfo(
            target_date=target_date,
            is_auspicious=best_factor > 1.0,
            label=best_label,
            demand_factor=round(best_factor, 2),
            sources=sources,
        )

    def get_factor(self, target_date: date) -> float:
        """快捷方法：仅返回需求倍增因子（1.0 = 普通日）。"""
        return self.get_info(target_date).demand_factor

    def get_calendar(
        self,
        days:       int  = 30,
        start_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        返回从 start_date 起 days 天的吉日日历列表。

        Args:
            days:       日历长度（默认 30 天）
            start_date: 起始日期（默认今天）

        Returns:
            List[{date, is_auspicious, label, demand_factor, sources}]
        """
        if start_date is None:
            start_date = date.today()

        calendar = []
        for i in range(days):
            d    = start_date + timedelta(days=i)
            info = self.get_info(d)
            calendar.append(info.to_dict())

        return calendar

    def get_high_demand_dates(
        self,
        days:       int           = 90,
        threshold:  float         = 1.5,
        start_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        返回未来 N 天中需求因子 ≥ threshold 的高峰日期列表。

        Args:
            days:      前瞻天数（默认 90 天 ≈ 3 个月）
            threshold: 因子阈值（默认 1.5）

        Returns:
            按日期排序的高峰日列表
        """
        calendar = self.get_calendar(days=days, start_date=start_date)
        return [item for item in calendar if item["demand_factor"] >= threshold]


# ── 全局单例（无门店配置；门店专属实例可 AuspiciousDateService(store_config=...)） ──
auspicious_date_service = AuspiciousDateService()
