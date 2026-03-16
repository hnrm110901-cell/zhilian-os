"""人力行业基准服务（Phase 8 Month 3）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

HUNAN_BENCHMARKS = {
    "small": {
        "labor_cost_rate_target": 24.0,
        "labor_efficiency_target": 1100.0,
    },
    "medium": {
        "labor_cost_rate_target": 22.0,
        "labor_efficiency_target": 1300.0,
    },
    "large": {
        "labor_cost_rate_target": 20.0,
        "labor_efficiency_target": 1500.0,
    },
}


def classify_store_size(area: Optional[float], seats: Optional[int]) -> str:
    """门店分档：small / medium / large。"""
    a = float(area or 0)
    s = int(seats or 0)

    if a >= 500 or s >= 220:
        return "large"
    if a >= 250 or s >= 120:
        return "medium"
    return "small"


def get_hunan_benchmark(size_tier: str) -> Dict[str, float]:
    """获取湖南中式餐饮人力基准。"""
    return HUNAN_BENCHMARKS.get(size_tier, HUNAN_BENCHMARKS["medium"])


def evaluate_against_benchmark(
    labor_cost_rate: float,
    labor_efficiency: float,
    benchmark: Dict[str, float],
) -> Dict[str, Any]:
    """计算与行业基准的偏差。"""
    target_rate = float(benchmark["labor_cost_rate_target"])
    target_eff = float(benchmark["labor_efficiency_target"])

    rate_gap = round(float(labor_cost_rate) - target_rate, 2)
    eff_gap = round(float(labor_efficiency) - target_eff, 2)

    if rate_gap <= 0 and eff_gap >= 0:
        level = "excellent"
    elif rate_gap <= 2 and eff_gap >= -100:
        level = "good"
    elif rate_gap <= 4 and eff_gap >= -250:
        level = "warning"
    else:
        level = "critical"

    return {
        "rate_gap_pct": rate_gap,
        "efficiency_gap": eff_gap,
        "health_level": level,
    }


class LaborBenchmarkService:
    """行业基准数据库服务。"""

    @staticmethod
    async def get_store_monthly_benchmark(
        store_id: str,
        month: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """获取门店月度基准对比。"""
        year, mon = map(int, month.split("-"))
        start_date = date(year, mon, 1)
        end_date = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)

        store_result = await db.execute(
            text("""
                SELECT id, name, area, seats
                FROM stores
                WHERE id = :store_id
                LIMIT 1
                """),
            {"store_id": store_id},
        )
        store_row = store_result.fetchone()
        if not store_row:
            raise ValueError("store_not_found")

        size_tier = classify_store_size(store_row.area, store_row.seats)
        benchmark = get_hunan_benchmark(size_tier)

        snap_result = await db.execute(
            text("""
                SELECT
                    AVG(actual_labor_cost_rate) AS avg_rate,
                    AVG(
                        CASE
                            WHEN COALESCE(headcount_actual, 0) > 0 THEN actual_revenue_yuan / headcount_actual
                            ELSE 0
                        END
                    ) AS avg_efficiency
                FROM labor_cost_snapshots
                WHERE store_id = :store_id
                  AND snapshot_date >= :start_date
                  AND snapshot_date < :end_date
                """),
            {
                "store_id": store_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        snap_row = snap_result.fetchone()
        avg_rate = float((snap_row.avg_rate or 0) if snap_row else 0)
        avg_eff = float((snap_row.avg_efficiency or 0) if snap_row else 0)

        evaluation = evaluate_against_benchmark(
            labor_cost_rate=avg_rate,
            labor_efficiency=avg_eff,
            benchmark=benchmark,
        )

        return {
            "store_id": store_id,
            "store_name": store_row.name,
            "month": month,
            "size_tier": size_tier,
            "actual": {
                "labor_cost_rate": round(avg_rate, 2),
                "labor_efficiency": round(avg_eff, 2),
            },
            "benchmark": benchmark,
            "evaluation": evaluation,
        }

    @staticmethod
    async def get_peer_group_baseline(
        month: str,
        size_tier: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """获取同规模门店的脱敏聚合基准。"""
        year, mon = map(int, month.split("-"))
        start_date = date(year, mon, 1)
        end_date = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)

        if size_tier == "large":
            size_filter = "(s.area >= 500 OR s.seats >= 220)"
        elif size_tier == "small":
            size_filter = "(s.area < 250 AND s.seats < 120)"
        else:
            size_filter = "((s.area >= 250 OR s.seats >= 120) AND (s.area < 500 AND s.seats < 220))"

        query = text(f"""
            SELECT
                COUNT(DISTINCT l.store_id) AS store_count,
                AVG(l.actual_labor_cost_rate) AS avg_rate,
                AVG(
                    CASE
                        WHEN COALESCE(l.headcount_actual, 0) > 0 THEN l.actual_revenue_yuan / l.headcount_actual
                        ELSE 0
                    END
                ) AS avg_efficiency
            FROM labor_cost_snapshots l
            JOIN stores s ON s.id = l.store_id
            WHERE l.snapshot_date >= :start_date
              AND l.snapshot_date < :end_date
              AND {size_filter}
            """)
        result = await db.execute(query, {"start_date": start_date, "end_date": end_date})
        row = result.fetchone()

        return {
            "month": month,
            "size_tier": size_tier,
            "store_count": int((row.store_count or 0) if row else 0),
            "avg_labor_cost_rate": round(float((row.avg_rate or 0) if row else 0), 2),
            "avg_labor_efficiency": round(float((row.avg_efficiency or 0) if row else 0), 2),
        }
