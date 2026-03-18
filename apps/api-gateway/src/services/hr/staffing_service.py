"""StaffingService — WF-2 排班健康度诊断.

双数据源融合:
  orders 近7天小时聚合  权重 40%
  orders 近30天同星期均值  权重 60% (历史基准)

orders 近期数据为空时权重升为 100% 历史均值。
两者皆空时返回 confidence=0.0 空结果，不抛错。
"""
import json
import math
import statistics
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
import structlog

logger = structlog.get_logger()

_ORDERS_WEIGHT = 0.4
_METRICS_WEIGHT = 0.6
_HOURLY_WAGE_DEFAULT = 25.0   # 元/小时 (spec §3.4)
_REDIS_TTL_SECONDS = 24 * 3600
_REDIS_KEY_TEMPLATE = "hr:staffing_diagnosis:{store_id}:{date}"
_AVG_ORDERS_PER_STAFF = 8.0   # 每人每小时可服务订单数（默认）


def _compute_fused_demand(
    recent: Dict[int, float], historical: Dict[int, float]
) -> Dict[int, float]:
    """融合两个数据源; recent 为空时 100% 使用 historical."""
    if not recent and not historical:
        return {}
    if not recent:
        return dict(historical)
    if not historical:
        return dict(recent)
    all_hours = set(recent) | set(historical)
    return {
        h: _ORDERS_WEIGHT * recent.get(h, 0.0) + _METRICS_WEIGHT * historical.get(h, 0.0)
        for h in all_hours
    }


def _compute_peak_hours(fused: Dict[int, float]) -> List[int]:
    """需求量 > 均值 + 1σ 的时段为峰值."""
    if len(fused) < 2:
        return []
    values = list(fused.values())
    mean = statistics.mean(values)
    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        std = 0.0
    threshold = mean + std
    return sorted(h for h, v in fused.items() if v > threshold)


def _compute_recommended_headcount(fused: Dict[int, float]) -> Dict[int, int]:
    """每小时建议人数 = ceil(需求/人效比) + 1（缓冲）."""
    return {
        h: max(1, math.ceil(v / _AVG_ORDERS_PER_STAFF) + 1)
        for h, v in fused.items()
    }


def _compute_savings(actual: Dict[int, int], recommended: Dict[int, int]) -> float:
    """减少过剩排班可节省的人力成本（元）."""
    total = 0.0
    for h, cnt in actual.items():
        surplus = max(0, cnt - recommended.get(h, 0))
        total += surplus * _HOURLY_WAGE_DEFAULT
    return round(total, 2)


class StaffingService:
    """WF-2 排班健康度诊断服务."""

    def __init__(self, session, redis_client=None) -> None:
        self._session = session
        self._redis = redis_client

    async def diagnose_staffing(
        self, store_id: str, analysis_date: date
    ) -> Dict[str, Any]:
        """主入口 — 返回完整排班健康度诊断 (spec §3.3)."""
        # 优先返回 Redis 缓存
        cached = self._get_cached(store_id, analysis_date)
        if cached is not None:
            return cached

        recent_orders = await self._fetch_recent_orders(store_id, analysis_date)
        historical_avg = await self._fetch_historical_avg(store_id, analysis_date)
        actual_shifts = await self._fetch_actual_shifts(store_id, analysis_date)

        fused = _compute_fused_demand(recent_orders, historical_avg)

        if not fused:
            result = self._empty_result(store_id, analysis_date)
            self._cache(store_id, analysis_date, result)
            return result

        peak_hours = _compute_peak_hours(fused)
        recommended = _compute_recommended_headcount(fused)

        understaffed = sorted(
            h for h in fused if actual_shifts.get(h, 0) < recommended.get(h, 0)
        )
        overstaffed = sorted(
            h for h in fused if actual_shifts.get(h, 0) > recommended.get(h, 0) + 1
        )
        savings = _compute_savings(actual_shifts, recommended)

        # 置信度: 两个数据源都有 → 0.75; 只有历史均值 → 0.55; 只有近期 → 0.60
        if recent_orders and historical_avg:
            confidence = 0.75
        elif historical_avg:
            confidence = 0.55
        else:
            confidence = 0.60

        result = {
            "store_id": store_id,
            "analysis_date": str(analysis_date),
            "peak_hours": peak_hours,
            "understaffed_hours": understaffed,
            "overstaffed_hours": overstaffed,
            "recommended_headcount": {str(h): v for h, v in recommended.items()},
            "estimated_savings_yuan": savings,
            "confidence": confidence,
            "data_freshness": {
                "orders_days": 7 if recent_orders else 0,
                "daily_metrics_days": 30 if historical_avg else 0,
            },
        }
        self._cache(store_id, analysis_date, result)
        logger.info("staffing.diagnosed", store_id=store_id, date=str(analysis_date),
                    peak_hours=peak_hours, savings_yuan=savings)
        return result

    # ─── Private ──────────────────────────────────────────────────────────────

    def _get_cached(self, store_id: str, analysis_date: date) -> Optional[Dict]:
        if not self._redis:
            return None
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id, date=str(analysis_date))
        raw = self._redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _cache(self, store_id: str, analysis_date: date, result: dict) -> None:
        if not self._redis:
            return
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id, date=str(analysis_date))
        try:
            self._redis.setex(key, _REDIS_TTL_SECONDS, json.dumps(result).encode())
        except Exception as exc:
            logger.warning("staffing.cache_failed", error=str(exc))

    @staticmethod
    def _empty_result(store_id: str, analysis_date: date) -> Dict:
        return {
            "store_id": store_id, "analysis_date": str(analysis_date),
            "peak_hours": [], "understaffed_hours": [], "overstaffed_hours": [],
            "recommended_headcount": {}, "estimated_savings_yuan": 0.0,
            "confidence": 0.0, "data_freshness": {"orders_days": 0, "daily_metrics_days": 0},
        }

    async def _fetch_recent_orders(
        self, store_id: str, analysis_date: date
    ) -> Dict[int, float]:
        """近7天每小时订单量均值 (40% weight)."""
        since = analysis_date - timedelta(days=7)
        result = await self._session.execute(
            sa.text("""
                SELECT EXTRACT(HOUR FROM created_at)::int AS hour,
                       COUNT(*)::float / 7 AS order_count
                FROM orders
                WHERE store_id = :store_id AND created_at >= :since
                GROUP BY hour ORDER BY hour
            """),
            {"store_id": store_id, "since": str(since)},
        )
        return {r.hour: float(r.order_count) for r in result.fetchall()}

    async def _fetch_historical_avg(
        self, store_id: str, analysis_date: date
    ) -> Dict[int, float]:
        """近30天同星期均值 (60% weight — 历史基准)."""
        since = analysis_date - timedelta(days=30)
        weekday = analysis_date.weekday()
        result = await self._session.execute(
            sa.text("""
                SELECT EXTRACT(HOUR FROM created_at)::int AS hour,
                       AVG(daily_count)::float AS avg_count
                FROM (
                    SELECT DATE_TRUNC('hour', created_at) AS created_at,
                           COUNT(*) AS daily_count
                    FROM orders
                    WHERE store_id = :store_id AND created_at >= :since
                      AND EXTRACT(DOW FROM created_at) = :weekday
                    GROUP BY DATE_TRUNC('hour', created_at)
                ) sub
                GROUP BY hour ORDER BY hour
            """),
            {"store_id": store_id, "since": str(since), "weekday": weekday},
        )
        return {r.hour: float(r.avg_count) for r in result.fetchall()}

    async def _fetch_actual_shifts(
        self, store_id: str, analysis_date: date
    ) -> Dict[int, int]:
        """当日各小时实际排班人数."""
        result = await self._session.execute(
            sa.text("""
                SELECT EXTRACT(HOUR FROM s.start_time)::int AS hour,
                       COUNT(*)::int AS headcount
                FROM shifts s
                JOIN schedules sc ON sc.id = s.schedule_id
                WHERE sc.store_id = :store_id AND DATE(s.start_time) = :d
                GROUP BY hour ORDER BY hour
            """),
            {"store_id": store_id, "d": str(analysis_date)},
        )
        return {r.hour: int(r.headcount) for r in result.fetchall()}
