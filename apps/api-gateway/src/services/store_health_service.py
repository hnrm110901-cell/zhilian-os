"""
StoreHealthService — 门店健康指数（架构升级 v2.1）

5维度加权综合指数（0-100分）：
  营收完成率  30%  — 当日营收 vs 日均目标（Store.monthly_revenue_target/天数）
  翻台率      20%  — COUNT(DISTINCT table_number) / Store.seats
  成本率      25%  — 复用 FoodCostService 差异状态（ok/warning/critical）
  客诉率      15%  — quality_inspections.status='fail' 比例
  人效        10%  — 人均日营收 vs 基准¥500/人/天

设计原则：
  - 缺失维度时按已有维度比例归一化，不返回 0
  - 纯函数 + 静态 class 方法，便于单元测试
  - 任何单店查询失败时静默降级（get_multi_store_scores 跳过该店）

Rule 6 兼容：revenue_yuan 字段包含¥金额（元单位）
Rule 3 兼容：成本率维度复用 FoodCostService，不重复 SQL
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import func, select, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 维度权重 ────────────────────────────────────────────────────────────────────
_WEIGHTS: Dict[str, float] = {
    "revenue_completion": 0.30,
    "table_turnover":     0.20,
    "cost_rate":          0.25,
    "complaint_rate":     0.15,
    "staff_efficiency":   0.10,
}

# 翻台率目标（次/天）
_TURNOVER_TARGET = 2.0
# 人效基准（元/人/天）
_STAFF_EFFICIENCY_TARGET = 500.0


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数（无 DB 依赖，便于单元测试）
# ════════════════════════════════════════════════════════════════════════════════

def compute_health_score(dimension_scores: Dict[str, Optional[float]]) -> float:
    """
    按已有维度比例归一化计算综合健康分（0-100）。

    对缺失维度（None）排除后，将剩余维度的权重重新归一化，
    确保有 1 个以上有效维度时总权重为 1.0。

    Args:
        dimension_scores: {dim_name: score (0-100) 或 None（维度缺失）}

    Returns:
        float 0-100，保留1位小数；全部缺失时返回 50.0
    """
    available = {k: v for k, v in dimension_scores.items() if v is not None}
    if not available:
        return 50.0

    total_weight = sum(_WEIGHTS.get(k, 0.0) for k in available)
    if total_weight <= 0:
        return 50.0

    weighted_sum = sum(v * _WEIGHTS.get(k, 0.0) for k, v in available.items())
    return round(weighted_sum / total_weight, 1)


def classify_health(score: float) -> str:
    """
    将健康分分类为文字等级。

    Returns:
        'excellent' (≥85) | 'good' (≥70) | 'warning' (≥50) | 'critical' (<50)
    """
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "warning"
    return "critical"


def _score_revenue_completion(
    actual_fen: float,
    monthly_target_yuan: Optional[float],
    target_date: date,
) -> Optional[float]:
    """
    营收完成率得分（0-100）。

    日均目标 = monthly_revenue_target(元) / 当月天数
    score = min(100, actual_fen / daily_target_fen * 100)
    """
    if not monthly_target_yuan or monthly_target_yuan <= 0:
        return None
    days_in_month = calendar.monthrange(target_date.year, target_date.month)[1]
    daily_target_fen = float(monthly_target_yuan) * 100.0 / days_in_month
    if daily_target_fen <= 0:
        return None
    return min(100.0, actual_fen / daily_target_fen * 100.0)


def _score_table_turnover(
    distinct_tables: int,
    seats: Optional[int],
) -> Optional[float]:
    """
    翻台率得分（0-100）。

    turns = distinct_tables / seats
    score = min(100, turns / _TURNOVER_TARGET * 100)
    """
    if not seats or seats <= 0:
        return None
    turns = distinct_tables / seats
    return min(100.0, turns / _TURNOVER_TARGET * 100.0)


def _score_cost_rate(variance_status: Optional[str]) -> Optional[float]:
    """
    成本率得分（基于 FoodCostService 差异状态）。

    ok → 100 | warning → 60 | critical → 20
    """
    if variance_status is None:
        return None
    return {"ok": 100.0, "warning": 60.0, "critical": 20.0}.get(variance_status, 50.0)


def _score_complaint_rate(fail_count: int, total_count: int) -> Optional[float]:
    """
    客诉率得分（0-100）。

    fail_rate = fail_count / total_count
    score = max(0, 100 - fail_rate * 200)
    （0% 投诉→100分，50% 投诉→0分）
    """
    if total_count <= 0:
        return None
    fail_rate = fail_count / total_count
    return max(0.0, 100.0 - fail_rate * 200.0)


def _score_staff_efficiency(
    revenue_yuan: float,
    staff_count: int,
) -> Optional[float]:
    """
    人效得分（0-100）。

    rev_per_staff = revenue_yuan / staff_count
    score = min(100, rev_per_staff / _STAFF_EFFICIENCY_TARGET * 100)
    """
    if staff_count <= 0 or revenue_yuan <= 0:
        return None
    rev_per_staff = revenue_yuan / staff_count
    return min(100.0, rev_per_staff / _STAFF_EFFICIENCY_TARGET * 100.0)


# ════════════════════════════════════════════════════════════════════════════════
# StoreHealthService（含 DB 查询的完整入口）
# ════════════════════════════════════════════════════════════════════════════════

class StoreHealthService:
    """
    门店健康指数主入口。

    用法::

        from src.services.store_health_service import StoreHealthService
        result = await StoreHealthService.get_store_score(
            store_id="S001", target_date=date.today(), db=session
        )
    """

    @staticmethod
    async def get_store_score(
        store_id: str,
        target_date: date,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        计算单店当日健康评分。

        Returns::

            {
                "store_id": str,
                "store_name": str,
                "score": float (0-100),
                "level": str,           # excellent / good / warning / critical
                "dimensions": {dim: {"score": float|None}},
                "weakest_dimension": str | None,
                "revenue_yuan": float,  # Rule 6: ¥金额
                "target_date": str,
            }
        """
        from src.models.store import Store
        from src.models.employee import Employee
        from src.services.food_cost_service import FoodCostService

        # 1. 加载门店信息
        store = await db.get(Store, store_id)
        if not store:
            return _empty_result(store_id, target_date)

        day_start = target_date
        day_end   = target_date + timedelta(days=1)

        # 2. 当日营收 + DISTINCT 桌台数（两项合一查询，减少 round-trip）
        rev_row = await db.execute(
            text("""
                SELECT
                    COALESCE(SUM(total_amount), 0)       AS revenue_fen,
                    COUNT(DISTINCT table_number)          AS distinct_tables
                FROM orders
                WHERE store_id    = :sid
                  AND created_at >= :start
                  AND created_at  < :end
            """),
            {"sid": store_id, "start": day_start, "end": day_end},
        )
        rev = rev_row.one()
        revenue_fen     = float(rev.revenue_fen)
        distinct_tables = int(rev.distinct_tables)
        revenue_yuan    = revenue_fen / 100.0

        # 3. 在职员工数
        staff_row = await db.execute(
            select(func.count(Employee.id)).where(
                and_(
                    Employee.store_id == store_id,
                    Employee.is_active == True,
                )
            )
        )
        staff_count = staff_row.scalar() or 0

        # 4. 成本率状态（复用 FoodCostService，Rule 3）
        variance_status: Optional[str] = None
        try:
            fc = await FoodCostService.get_store_food_cost_variance(
                store_id=store_id,
                start_date=target_date - timedelta(days=6),
                end_date=day_end,
                db=db,
            )
            variance_status = fc.get("variance_status")
        except Exception as exc:
            logger.warning(
                "store_health.cost_rate_failed",
                store_id=store_id,
                error=str(exc),
            )

        # 5. 客诉率（quality_inspections）
        qi_row = await db.execute(
            text("""
                SELECT
                    COUNT(*)                                           AS total,
                    COUNT(*) FILTER (WHERE status = 'fail')           AS fail_count
                FROM quality_inspections
                WHERE store_id    = :sid
                  AND created_at >= :start
                  AND created_at  < :end
            """),
            {"sid": store_id, "start": day_start, "end": day_end},
        )
        qi       = qi_row.one()
        qi_total = int(qi.total)
        qi_fail  = int(qi.fail_count)

        # 6. 各维度得分
        dimension_scores: Dict[str, Optional[float]] = {
            "revenue_completion": _score_revenue_completion(
                revenue_fen,
                getattr(store, "monthly_revenue_target", None),
                target_date,
            ),
            "table_turnover": _score_table_turnover(
                distinct_tables,
                getattr(store, "seats", None),
            ),
            "cost_rate": _score_cost_rate(variance_status),
            "complaint_rate": _score_complaint_rate(qi_fail, qi_total),
            "staff_efficiency": _score_staff_efficiency(revenue_yuan, staff_count),
        }

        score = compute_health_score(dimension_scores)
        level = classify_health(score)

        # weakest = 有有效分的维度中得分最低的
        scored = {k: v for k, v in dimension_scores.items() if v is not None}
        weakest = min(scored, key=lambda k: scored[k]) if scored else None

        logger.info(
            "store_health.computed",
            store_id=store_id,
            score=score,
            level=level,
            target_date=target_date.isoformat(),
        )

        return {
            "store_id":           store_id,
            "store_name":         getattr(store, "name", store_id),
            "score":              score,
            "level":              level,
            "dimensions":         {k: {"score": v} for k, v in dimension_scores.items()},
            "weakest_dimension":  weakest,
            "revenue_yuan":       round(revenue_yuan, 2),
            "target_date":        target_date.isoformat(),
        }

    @staticmethod
    async def get_multi_store_scores(
        store_ids: List[str],
        target_date: date,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """
        多店评分，按分数降序排名（供老板看全局）。

        单店查询失败时静默跳过，不中断整体输出。

        Returns:
            list of store result dicts, each with "rank" field added.
        """
        results: List[Dict[str, Any]] = []
        for store_id in store_ids:
            try:
                r = await StoreHealthService.get_store_score(store_id, target_date, db)
                results.append(r)
            except Exception as exc:
                logger.warning(
                    "store_health.store_score_failed",
                    store_id=store_id,
                    error=str(exc),
                )

        results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        for i, r in enumerate(results):
            r["rank"] = i + 1

        return results


# ── 内部工具 ───────────────────────────────────────────────────────────────────

def _empty_result(store_id: str, target_date: date) -> Dict[str, Any]:
    """门店不存在时的兜底返回值"""
    return {
        "store_id":          store_id,
        "store_name":        store_id,
        "score":             50.0,
        "level":             "warning",
        "dimensions":        {},
        "weakest_dimension": None,
        "revenue_yuan":      0.0,
        "target_date":       target_date.isoformat(),
    }
