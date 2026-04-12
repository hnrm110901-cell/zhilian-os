"""
时间线组装器 — 跨系统事件按时间轴对齐
对标 Palantir Foundry 的 Timeline 视图

核心能力：
  1. 多源事件采集：从不同系统的订单/库存/采购/排班中提取时间事件
  2. 时间轴对齐：统一时区，按时间排序
  3. 关联推断：自动关联同一时间窗口内的相关事件
  4. 模式发现：从时间线中提取规律（峰值/异常/季节性）

使用方式：
  assembler = TimelineAssembler()
  assembler.add_events("pos", order_events)
  assembler.add_events("member", member_events)
  timeline = assembler.assemble(store_id, date_range)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class TimelineEvent:
    """时间线事件"""
    id: str
    timestamp: datetime
    event_type: str          # order / inventory_change / purchase / schedule / customer_visit
    source_system: str       # 来源系统
    entity_type: str         # order / dish / customer / ingredient / employee
    entity_id: str           # 实体ID（canonical_id）
    store_id: str
    summary: str             # 事件摘要
    amount_fen: Optional[int] = None  # 涉及金额（分）
    metadata: Dict = field(default_factory=dict)
    related_events: List[str] = field(default_factory=list)  # 关联事件ID


@dataclass
class DailySnapshot:
    """日快照：一天内所有事件的聚合"""
    date: date
    store_id: str
    total_events: int
    total_orders: int
    total_revenue_fen: int
    total_customers: int
    peak_hour: Optional[int]       # 峰值小时 0-23
    peak_hour_orders: int
    events_by_type: Dict[str, int]    # event_type → count
    events_by_hour: Dict[int, int]    # hour → count
    anomalies: List[Dict] = field(default_factory=list)


@dataclass
class TimelineAnalysis:
    """时间线分析结果"""
    store_id: str
    date_range_start: date
    date_range_end: date
    total_days: int
    total_events: int
    daily_snapshots: List[DailySnapshot]
    peak_patterns: Dict            # 峰值模式
    weekly_patterns: Dict          # 周模式（周一~周日）
    anomaly_dates: List[Dict]      # 异常日期
    revenue_trend_fen: List[Dict]  # 营收趋势


# ── 时间线组装器 ──────────────────────────────────────────────────────────────

class TimelineAssembler:
    """
    跨系统时间线组装器

    将来自不同SaaS系统的事件数据按时间轴统一对齐，
    发现跨系统的事件关联和经营模式
    """

    # 事件关联时间窗口（秒）：同一时间窗口内的事件可能相关
    CORRELATION_WINDOW_SECONDS = 300  # 5分钟

    def __init__(self):
        self._events: List[TimelineEvent] = []

    def add_events(self, events: List[TimelineEvent]) -> int:
        """
        添加事件到时间线

        Returns:
            添加的事件数
        """
        self._events.extend(events)
        return len(events)

    def add_order_events(
        self,
        source_system: str,
        orders: List[Dict],
        store_id: str,
    ) -> int:
        """
        从订单数据生成时间线事件

        Args:
            source_system: 来源系统
            orders: 订单列表（需含 id, created_at, total/amount, items等）
            store_id: 门店ID
        """
        count = 0
        for order in orders:
            created_at = order.get("created_at")
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
            if not isinstance(created_at, datetime):
                continue

            # 金额处理：自动检测单位（>1000视为分，否则视为元）
            amount = order.get("total") or order.get("amount") or order.get("final_amount") or 0
            amount_fen = int(amount) if amount > 1000 else int(float(amount) * 100)

            event = TimelineEvent(
                id=order.get("id", order.get("order_id", "")),
                timestamp=created_at,
                event_type="order",
                source_system=source_system,
                entity_type="order",
                entity_id=order.get("id", ""),
                store_id=store_id,
                summary=f"订单 ¥{amount_fen / 100:.2f}",
                amount_fen=amount_fen,
                metadata={
                    "items_count": len(order.get("items", [])),
                    "customer_id": order.get("customer_id"),
                    "order_type": order.get("order_type", "dine_in"),
                },
            )
            self._events.append(event)
            count += 1

        return count

    def add_customer_events(
        self,
        source_system: str,
        visits: List[Dict],
        store_id: str,
    ) -> int:
        """从客户访问记录生成时间线事件"""
        count = 0
        for visit in visits:
            visit_time = visit.get("last_visit_date") or visit.get("visit_time")
            if isinstance(visit_time, str):
                try:
                    visit_time = datetime.fromisoformat(visit_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
            if not isinstance(visit_time, datetime):
                continue

            event = TimelineEvent(
                id=visit.get("id", visit.get("consumer_id", "")),
                timestamp=visit_time,
                event_type="customer_visit",
                source_system=source_system,
                entity_type="customer",
                entity_id=visit.get("consumer_id", visit.get("id", "")),
                store_id=store_id,
                summary=f"客户到店: {visit.get('name', '匿名')}",
                amount_fen=int(float(visit.get("total_amount", 0)) * 100) if visit.get("total_amount") else None,
                metadata={
                    "customer_level": visit.get("customer_level"),
                    "total_visits": visit.get("total_visits"),
                },
            )
            self._events.append(event)
            count += 1

        return count

    def assemble(
        self,
        store_id: str,
        date_range_start: Optional[date] = None,
        date_range_end: Optional[date] = None,
    ) -> TimelineAnalysis:
        """
        组装时间线并生成分析

        Args:
            store_id: 门店ID
            date_range_start: 起始日期
            date_range_end: 截止日期

        Returns:
            TimelineAnalysis 含每日快照 + 模式分析 + 异常检测
        """
        # 过滤和排序事件
        filtered = [
            e for e in self._events
            if e.store_id == store_id
        ]
        if date_range_start:
            start_dt = datetime.combine(date_range_start, datetime.min.time())
            filtered = [e for e in filtered if e.timestamp >= start_dt]
        if date_range_end:
            end_dt = datetime.combine(date_range_end, datetime.max.time())
            filtered = [e for e in filtered if e.timestamp <= end_dt]

        filtered.sort(key=lambda e: e.timestamp)

        # 按日分组
        daily_events: Dict[date, List[TimelineEvent]] = defaultdict(list)
        for event in filtered:
            day = event.timestamp.date()
            daily_events[day].append(event)

        # 生成每日快照
        daily_snapshots = []
        for day in sorted(daily_events.keys()):
            day_evts = daily_events[day]
            snapshot = self._build_daily_snapshot(day, store_id, day_evts)
            daily_snapshots.append(snapshot)

        # 分析模式
        peak_patterns = self._analyze_peak_patterns(daily_snapshots)
        weekly_patterns = self._analyze_weekly_patterns(daily_snapshots)
        anomaly_dates = self._detect_anomalies(daily_snapshots)
        revenue_trend = self._build_revenue_trend(daily_snapshots)

        actual_start = daily_snapshots[0].date if daily_snapshots else (date_range_start or date.today())
        actual_end = daily_snapshots[-1].date if daily_snapshots else (date_range_end or date.today())

        return TimelineAnalysis(
            store_id=store_id,
            date_range_start=actual_start,
            date_range_end=actual_end,
            total_days=len(daily_snapshots),
            total_events=len(filtered),
            daily_snapshots=daily_snapshots,
            peak_patterns=peak_patterns,
            weekly_patterns=weekly_patterns,
            anomaly_dates=anomaly_dates,
            revenue_trend_fen=revenue_trend,
        )

    def _build_daily_snapshot(
        self, day: date, store_id: str, events: List[TimelineEvent]
    ) -> DailySnapshot:
        """构建单日快照"""
        events_by_type: Dict[str, int] = defaultdict(int)
        events_by_hour: Dict[int, int] = defaultdict(int)
        total_revenue_fen = 0
        customer_ids = set()

        for e in events:
            events_by_type[e.event_type] += 1
            events_by_hour[e.timestamp.hour] += 1
            if e.amount_fen:
                total_revenue_fen += e.amount_fen
            if e.event_type == "customer_visit":
                customer_ids.add(e.entity_id)

        order_count = events_by_type.get("order", 0)

        # 找峰值小时
        peak_hour = None
        peak_hour_orders = 0
        if events_by_hour:
            peak_hour = max(events_by_hour, key=events_by_hour.get)
            peak_hour_orders = events_by_hour[peak_hour]

        return DailySnapshot(
            date=day,
            store_id=store_id,
            total_events=len(events),
            total_orders=order_count,
            total_revenue_fen=total_revenue_fen,
            total_customers=len(customer_ids),
            peak_hour=peak_hour,
            peak_hour_orders=peak_hour_orders,
            events_by_type=dict(events_by_type),
            events_by_hour=dict(events_by_hour),
        )

    def _analyze_peak_patterns(self, snapshots: List[DailySnapshot]) -> Dict:
        """分析峰值模式：哪些小时是高峰"""
        if not snapshots:
            return {"peak_hours": [], "avg_daily_orders": 0}

        hourly_totals: Dict[int, int] = defaultdict(int)
        hourly_days: Dict[int, int] = defaultdict(int)

        for snap in snapshots:
            for hour, count in snap.events_by_hour.items():
                hourly_totals[hour] += count
                hourly_days[hour] += 1

        hourly_avg = {}
        for hour in hourly_totals:
            days = hourly_days.get(hour, 1)
            hourly_avg[hour] = round(hourly_totals[hour] / max(days, 1), 1)

        # 全天平均
        total_orders = sum(s.total_orders for s in snapshots)
        avg_daily = round(total_orders / max(len(snapshots), 1), 1)

        # 峰值小时 = 超过日均/营业小时数 × 1.3 的小时
        active_hours = len([h for h in hourly_avg if hourly_avg[h] > 0])
        threshold = (avg_daily / max(active_hours, 1)) * 1.3 if active_hours > 0 else 0
        peak_hours = [
            {"hour": h, "avg_events": hourly_avg[h]}
            for h in sorted(hourly_avg)
            if hourly_avg[h] >= threshold
        ]

        return {
            "peak_hours": peak_hours,
            "avg_daily_orders": avg_daily,
            "hourly_distribution": {str(h): v for h, v in sorted(hourly_avg.items())},
        }

    def _analyze_weekly_patterns(self, snapshots: List[DailySnapshot]) -> Dict:
        """分析周模式：周一到周日的分布"""
        weekday_orders: Dict[int, List[int]] = defaultdict(list)
        weekday_revenue: Dict[int, List[int]] = defaultdict(list)
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for snap in snapshots:
            wd = snap.date.weekday()
            weekday_orders[wd].append(snap.total_orders)
            weekday_revenue[wd].append(snap.total_revenue_fen)

        patterns = {}
        for wd in range(7):
            orders_list = weekday_orders.get(wd, [])
            revenue_list = weekday_revenue.get(wd, [])
            avg_orders = round(sum(orders_list) / max(len(orders_list), 1), 1)
            avg_revenue = round(sum(revenue_list) / max(len(revenue_list), 1))
            patterns[weekday_names[wd]] = {
                "avg_orders": avg_orders,
                "avg_revenue_fen": avg_revenue,
                "avg_revenue_yuan": round(avg_revenue / 100, 2),
                "sample_days": len(orders_list),
            }

        return patterns

    def _detect_anomalies(self, snapshots: List[DailySnapshot]) -> List[Dict]:
        """
        异常日期检测：营收偏离均值超过2个标准差
        """
        if len(snapshots) < 7:
            return []

        revenues = [s.total_revenue_fen for s in snapshots]
        avg_rev = sum(revenues) / len(revenues)
        if avg_rev == 0:
            return []

        variance = sum((r - avg_rev) ** 2 for r in revenues) / len(revenues)
        std_dev = variance ** 0.5
        if std_dev == 0:
            return []

        anomalies = []
        for snap in snapshots:
            z_score = (snap.total_revenue_fen - avg_rev) / std_dev
            if abs(z_score) >= 2.0:
                anomalies.append({
                    "date": snap.date.isoformat(),
                    "revenue_fen": snap.total_revenue_fen,
                    "revenue_yuan": round(snap.total_revenue_fen / 100, 2),
                    "z_score": round(z_score, 2),
                    "direction": "high" if z_score > 0 else "low",
                    "deviation_pct": round((snap.total_revenue_fen - avg_rev) / avg_rev * 100, 1),
                })

        return anomalies

    def _build_revenue_trend(self, snapshots: List[DailySnapshot]) -> List[Dict]:
        """构建营收趋势（用于图表展示）"""
        return [
            {
                "date": snap.date.isoformat(),
                "revenue_fen": snap.total_revenue_fen,
                "revenue_yuan": round(snap.total_revenue_fen / 100, 2),
                "orders": snap.total_orders,
                "customers": snap.total_customers,
            }
            for snap in snapshots
        ]
