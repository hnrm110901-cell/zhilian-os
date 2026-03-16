"""
人工成本服务（LaborCostService）— Phase 8 Step 3

职责：
  1. 每日人工成本率快照：实际 vs 预算对比，写入 labor_cost_snapshots
  2. ¥节省/超支计算（Rule 6）：量化每日排班决策的¥影响
  3. 成本率趋势：N日区间内的成本率走势 + 环比对比
  4. 跨店排名：在同品牌门店中计算成本率排名，写入 labor_cost_rankings

人工成本估算来源（按优先级）：
  A. 调用方直接传入 actual_labor_cost_yuan（最准确）
  B. 从 shifts 表统计实际出勤时长 × 岗位时薪（需要 position_wage_map）
  C. 从 store_labor_budgets.daily_budget_yuan 作为参考值
  D. 兜底：排班人数 × 每人日均¥200（行业参考）

状态判断阈值（对比预算成本率）：
  偏差 ≤ 0        → saving（节省）
  偏差 0-2 个百分点 → ok
  偏差 2-5 个百分点 → warning
  偏差 > 5 个百分点 → critical

SQL：全部使用 text() + :param 绑定。
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────────────────────────

# 各岗位默认时薪（元/小时），无法从员工档案取到时使用
_DEFAULT_HOURLY_WAGE: Dict[str, float] = {
    "waiter": 18.0,
    "chef": 25.0,
    "cashier": 18.0,
    "manager": 35.0,
    "default": 20.0,
}

# 人均兜底日薪（方案 D）
_FALLBACK_DAILY_WAGE_YUAN = 200.0

# 状态判定阈值（超出预算成本率的百分点）
_THRESHOLD_WARNING = 2.0  # 超预算 2pp → warning
_THRESHOLD_CRITICAL = 5.0  # 超预算 5pp → critical

# 行业人工成本率参考基准（餐饮，无预算时用）
_INDUSTRY_BENCHMARK_RATE = 28.0  # %


# ─── 纯函数（可单元测试） ─────────────────────────────────────────────────────


def compute_labor_cost_rate(
    labor_cost_yuan: float,
    revenue_yuan: float,
) -> float:
    """人工成本率 = 人工成本 / 营收 × 100（%），营收为 0 时返回 0"""
    if revenue_yuan <= 0:
        return 0.0
    return round(labor_cost_yuan / revenue_yuan * 100, 2)


def compute_variance(
    actual_rate: float,
    budget_rate: float,
    revenue_yuan: float,
) -> dict:
    """
    计算实际 vs 预算的偏差（Rule 6：必须包含¥字段）。

    Args:
        actual_rate:   实际成本率（%）
        budget_rate:   预算成本率（%）
        revenue_yuan:  当日营收（元）

    Returns:
        {
            variance_pct:      float  # 百分点差（正=超支，负=节省）
            variance_yuan:     float  # ¥差额（正=超支，负=节省）
            saving_yuan:       float  # 节省金额（仅节省时 > 0）
            overspend_yuan:    float  # 超支金额（仅超支时 > 0）
            status:            str    # saving / ok / warning / critical
        }
    """
    variance_pct = round(actual_rate - budget_rate, 2)
    variance_yuan = round(revenue_yuan * variance_pct / 100, 2)
    saving_yuan = round(-variance_yuan, 2) if variance_yuan < 0 else 0.0
    overspend_yuan = round(variance_yuan, 2) if variance_yuan > 0 else 0.0

    if variance_pct <= 0:
        status = "saving"
    elif variance_pct <= _THRESHOLD_WARNING:
        status = "ok"
    elif variance_pct <= _THRESHOLD_CRITICAL:
        status = "warning"
    else:
        status = "critical"

    return {
        "variance_pct": variance_pct,
        "variance_yuan": variance_yuan,
        "saving_yuan": saving_yuan,
        "overspend_yuan": overspend_yuan,
        "status": status,
    }


def compute_overtime_cost(
    overtime_hours: float,
    base_hourly_wage: float = _DEFAULT_HOURLY_WAGE["default"],
    overtime_multiplier: float = 1.5,
) -> float:
    """加班费 = 加班时长 × 时薪 × 加班倍率（默认1.5倍）"""
    return round(overtime_hours * base_hourly_wage * overtime_multiplier, 2)


# ─── 服务类 ────────────────────────────────────────────────────────────────────


class LaborCostService:
    """人工成本服务（全静态方法）"""

    # ── 快照计算与持久化 ────────────────────────────────────────────────────────

    @staticmethod
    async def compute_and_save_snapshot(
        store_id: str,
        snapshot_date: date,
        db: AsyncSession,
        *,
        actual_labor_cost_yuan: Optional[float] = None,
        position_wage_map: Optional[Dict[str, float]] = None,
    ) -> dict:
        """
        计算当日人工成本率快照并写入 labor_cost_snapshots。

        Args:
            store_id:               门店ID
            snapshot_date:          快照日期
            db:                     异步数据库会话
            actual_labor_cost_yuan: 由调用方直接传入的实际人工成本（最优先）
            position_wage_map:      岗位 → 时薪映射，为 None 时用默认值

        Returns:
            快照 dict，含所有¥字段
        """
        log = logger.bind(store_id=store_id, date=str(snapshot_date))

        # ── 1. 营收 ──────────────────────────────────────────────────────────
        revenue_yuan = await LaborCostService._fetch_daily_revenue(store_id, snapshot_date, db)

        # ── 2. 实际出勤人数 & 加班时长 ────────────────────────────────────────
        shift_stats = await LaborCostService._fetch_shift_stats(store_id, snapshot_date, db)

        # ── 3. 人工成本 ───────────────────────────────────────────────────────
        if actual_labor_cost_yuan is None:
            actual_labor_cost_yuan = await LaborCostService._estimate_labor_cost(
                store_id, snapshot_date, shift_stats, db, position_wage_map
            )

        # ── 4. 预算 ───────────────────────────────────────────────────────────
        budget = await LaborCostService._fetch_budget(store_id, snapshot_date, db)
        budgeted_labor_cost_yuan = budget.get("daily_budget_yuan")
        budgeted_labor_cost_rate = budget.get("target_labor_cost_rate")

        # 如果没有明确日预算，用预算成本率 × 实际营收反推
        if budgeted_labor_cost_yuan is None and budgeted_labor_cost_rate is not None:
            budgeted_labor_cost_yuan = round(revenue_yuan * budgeted_labor_cost_rate / 100, 2)
        effective_budget_rate = budgeted_labor_cost_rate or _INDUSTRY_BENCHMARK_RATE

        # ── 5. 计算成本率与偏差 ───────────────────────────────────────────────
        actual_rate = compute_labor_cost_rate(actual_labor_cost_yuan, revenue_yuan)
        variance = compute_variance(actual_rate, effective_budget_rate, revenue_yuan)

        overtime_cost_yuan = compute_overtime_cost(shift_stats.get("overtime_hours", 0.0))

        snapshot = {
            "store_id": store_id,
            "snapshot_date": snapshot_date.isoformat(),
            "actual_revenue_yuan": round(revenue_yuan, 2),
            "actual_labor_cost_yuan": round(actual_labor_cost_yuan, 2),
            "actual_labor_cost_rate": actual_rate,
            "budgeted_labor_cost_yuan": budgeted_labor_cost_yuan,
            "budgeted_labor_cost_rate": budgeted_labor_cost_rate,
            "variance_yuan": variance["variance_yuan"],
            "variance_pct": variance["variance_pct"],
            "saving_yuan": variance["saving_yuan"],
            "overspend_yuan": variance["overspend_yuan"],
            "status": variance["status"],
            "headcount_actual": shift_stats.get("headcount_actual", 0),
            "headcount_scheduled": shift_stats.get("headcount_scheduled", 0),
            "overtime_hours": shift_stats.get("overtime_hours", 0.0),
            "overtime_cost_yuan": overtime_cost_yuan,
        }

        await LaborCostService._upsert_snapshot(snapshot, db)

        log.info(
            "labor_cost.snapshot_saved",
            actual_rate=actual_rate,
            status=variance["status"],
            saving_yuan=variance["saving_yuan"],
            overspend_yuan=variance["overspend_yuan"],
        )
        return snapshot

    @staticmethod
    async def get_snapshot(
        store_id: str,
        snapshot_date: date,
        db: AsyncSession,
    ) -> Optional[dict]:
        """查询某门店某日的成本快照（不存在时返回 None）"""
        result = await db.execute(
            text("""
                SELECT
                    store_id, snapshot_date,
                    actual_revenue_yuan, actual_labor_cost_yuan, actual_labor_cost_rate,
                    budgeted_labor_cost_yuan, budgeted_labor_cost_rate,
                    variance_yuan, variance_pct,
                    headcount_actual, headcount_scheduled,
                    overtime_hours, overtime_cost_yuan
                FROM labor_cost_snapshots
                WHERE store_id = :sid AND snapshot_date = :dt
                LIMIT 1
            """),
            {"sid": store_id, "dt": snapshot_date},
        )
        row = result.fetchone()
        if not row:
            return None
        return _row_to_snapshot_dict(row)

    # ── 成本率趋势 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_cost_trend(
        store_id: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> dict:
        """
        查询区间内每日成本率趋势。

        Returns:
            {
                store_id, start_date, end_date,
                avg_labor_cost_rate:    float   # 区间均值
                total_saving_yuan:      float   # 区间累计节省¥
                total_overspend_yuan:   float   # 区间累计超支¥
                net_variance_yuan:      float   # 累计净差额（负=节省）
                days:                   list    # 每日明细
                period_status:          str     # saving/ok/warning/critical
            }
        """
        result = await db.execute(
            text("""
                SELECT
                    snapshot_date,
                    actual_revenue_yuan,
                    actual_labor_cost_yuan,
                    actual_labor_cost_rate,
                    budgeted_labor_cost_rate,
                    variance_yuan,
                    variance_pct,
                    headcount_actual,
                    overtime_hours,
                    overtime_cost_yuan
                FROM labor_cost_snapshots
                WHERE store_id     = :sid
                  AND snapshot_date >= :start
                  AND snapshot_date <= :end
                ORDER BY snapshot_date
            """),
            {"sid": store_id, "start": start_date, "end": end_date},
        )
        rows = result.fetchall()

        if not rows:
            return {
                "store_id": store_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "avg_labor_cost_rate": 0.0,
                "total_saving_yuan": 0.0,
                "total_overspend_yuan": 0.0,
                "net_variance_yuan": 0.0,
                "period_status": "no_data",
                "days": [],
            }

        days = [_row_to_snapshot_dict(r) for r in rows]
        rates = [d["actual_labor_cost_rate"] for d in days if d["actual_labor_cost_rate"]]
        variances = [d["variance_yuan"] or 0.0 for d in days]
        saving_sum = sum(max(-v, 0.0) for v in variances)
        overspend_sum = sum(max(v, 0.0) for v in variances)
        net_variance = sum(variances)
        avg_rate = round(sum(rates) / len(rates), 2) if rates else 0.0

        # 用最差的单日状态决定区间状态
        if net_variance <= 0:
            period_status = "saving"
        elif abs(net_variance) / max(sum(d["actual_revenue_yuan"] or 1 for d in days), 1) * 100 <= _THRESHOLD_WARNING:
            period_status = "ok"
        elif abs(net_variance) / max(sum(d["actual_revenue_yuan"] or 1 for d in days), 1) * 100 <= _THRESHOLD_CRITICAL:
            period_status = "warning"
        else:
            period_status = "critical"

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "avg_labor_cost_rate": avg_rate,
            "total_saving_yuan": round(saving_sum, 2),
            "total_overspend_yuan": round(overspend_sum, 2),
            "net_variance_yuan": round(net_variance, 2),
            "period_status": period_status,
            "days": days,
        }

    # ── 跨店排名 ────────────────────────────────────────────────────────────────

    @staticmethod
    async def refresh_store_rankings(
        brand_id: str,
        ranking_date: date,
        period_type: str,
        db: AsyncSession,
    ) -> dict:
        """
        计算品牌内所有门店的人工成本率排名，写入 labor_cost_rankings。

        Args:
            brand_id:     品牌ID（用于圈定参与排名的门店）
            ranking_date: 排名基准日期
            period_type:  daily / weekly / monthly
            db:           异步数据库会话

        Returns:
            {total_stores, rankings: [{store_id, rank, rate, percentile, ...}]}
        """
        start_date, end_date = _period_range(ranking_date, period_type)

        # 拉取品牌内各店的平均成本率
        rows_result = await db.execute(
            text("""
                SELECT
                    lcs.store_id,
                    AVG(lcs.actual_labor_cost_rate) AS avg_rate,
                    AVG(lcs.actual_revenue_yuan)    AS avg_revenue
                FROM labor_cost_snapshots lcs
                JOIN stores s ON lcs.store_id = s.id
                WHERE s.brand_id          = :brand_id
                  AND lcs.snapshot_date  >= :start
                  AND lcs.snapshot_date  <= :end
                  AND lcs.actual_labor_cost_rate IS NOT NULL
                GROUP BY lcs.store_id
                ORDER BY avg_rate ASC
            """),
            {"brand_id": brand_id, "start": start_date, "end": end_date},
        )
        rows = rows_result.fetchall()

        if not rows:
            return {
                "brand_id": brand_id,
                "ranking_date": ranking_date.isoformat(),
                "period_type": period_type,
                "total_stores": 0,
                "rankings": [],
            }

        total = len(rows)
        rates = [float(r.avg_rate) for r in rows]
        avg_rate = round(sum(rates) / total, 2)
        median_rate = round(sorted(rates)[total // 2], 2)
        best_rate = round(min(rates), 2)

        rankings = []
        for rank, row in enumerate(rows, start=1):
            rate = round(float(row.avg_rate), 2)
            percentile = round((total - rank) / (total - 1) * 100, 1) if total > 1 else 100.0
            rankings.append(
                {
                    "store_id": row.store_id,
                    "rank_in_group": rank,
                    "total_stores": total,
                    "labor_cost_rate": rate,
                    "percentile_score": percentile,
                    "group_avg_rate": avg_rate,
                    "group_median_rate": median_rate,
                    "best_rate_in_group": best_rate,
                }
            )

        # 批量 upsert 到 labor_cost_rankings
        await LaborCostService._upsert_rankings(rankings, brand_id, ranking_date, period_type, db)

        logger.info(
            "labor_cost.rankings_refreshed",
            brand_id=brand_id,
            date=str(ranking_date),
            period_type=period_type,
            total_stores=total,
        )
        return {
            "brand_id": brand_id,
            "ranking_date": ranking_date.isoformat(),
            "period_type": period_type,
            "total_stores": total,
            "group_avg_rate": avg_rate,
            "group_median_rate": median_rate,
            "best_rate_in_group": best_rate,
            "rankings": rankings,
        }

    @staticmethod
    async def get_store_ranking(
        store_id: str,
        ranking_date: date,
        period_type: str,
        db: AsyncSession,
    ) -> Optional[dict]:
        """查询某门店的最新排名快照"""
        result = await db.execute(
            text("""
                SELECT
                    store_id, ranking_date, period_type,
                    labor_cost_rate, rank_in_group, total_stores_in_group,
                    percentile_score, group_avg_rate, group_median_rate, best_rate_in_group
                FROM labor_cost_rankings
                WHERE store_id    = :sid
                  AND ranking_date = :dt
                  AND period_type  = :pt
                LIMIT 1
            """),
            {"sid": store_id, "dt": ranking_date, "pt": period_type},
        )
        row = result.fetchone()
        if not row:
            return None

        rate = float(row.labor_cost_rate)
        avg = float(row.group_avg_rate or 0)
        return {
            "store_id": row.store_id,
            "ranking_date": row.ranking_date.isoformat() if hasattr(row.ranking_date, "isoformat") else str(row.ranking_date),
            "period_type": row.period_type,
            "labor_cost_rate": rate,
            "rank_in_group": row.rank_in_group,
            "total_stores": row.total_stores_in_group,
            "percentile_score": float(row.percentile_score or 0),
            "group_avg_rate": avg,
            "group_median_rate": float(row.group_median_rate or 0),
            "best_rate_in_group": float(row.best_rate_in_group or 0),
            # ¥ 化排名洞察（Rule 7：建议 + ¥影响）
            "rank_insight": _build_rank_insight(
                store_id=row.store_id,
                rank=row.rank_in_group,
                total=row.total_stores_in_group,
                rate=rate,
                avg=avg,
            ),
        }

    # ── 内部工具方法 ────────────────────────────────────────────────────────────

    @staticmethod
    async def _fetch_daily_revenue(
        store_id: str,
        snapshot_date: date,
        db: AsyncSession,
    ) -> float:
        """查询当日营收（元，已除以100）"""
        result = await db.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS revenue_fen
                FROM orders
                WHERE store_id  = :sid
                  AND created_at >= :start
                  AND created_at  < :end
            """),
            {
                "sid": store_id,
                "start": snapshot_date,
                "end": snapshot_date + timedelta(days=1),
            },
        )
        revenue_fen = int(result.scalar() or 0)
        return round(revenue_fen / 100, 2)

    @staticmethod
    async def _fetch_shift_stats(
        store_id: str,
        snapshot_date: date,
        db: AsyncSession,
    ) -> dict:
        """
        统计当日排班情况：
          - headcount_scheduled: 排班人数
          - headcount_actual:    实际出勤人数（is_completed=True）
          - total_hours:         合计工时（小时）
          - overtime_hours:      超出8小时/人 的加班时长汇总
          - position_hours:      各岗位工时分布（用于成本估算）
        """
        result = await db.execute(
            text("""
                SELECT
                    sh.position,
                    COUNT(*)                   AS headcount_scheduled,
                    SUM(CASE WHEN sh.is_completed THEN 1 ELSE 0 END) AS headcount_actual,
                    SUM(
                        EXTRACT(EPOCH FROM (sh.end_time - sh.start_time)) / 3600.0
                    )                          AS total_hours,
                    SUM(
                        GREATEST(
                            EXTRACT(EPOCH FROM (sh.end_time - sh.start_time)) / 3600.0 - 8.0,
                            0.0
                        )
                    )                          AS overtime_hours
                FROM shifts sh
                JOIN schedules sc ON sh.schedule_id = sc.id
                WHERE sc.store_id      = :sid
                  AND sc.schedule_date = :dt
                GROUP BY sh.position
            """),
            {"sid": store_id, "dt": snapshot_date},
        )
        rows = result.fetchall()

        total_scheduled = 0
        total_actual = 0
        total_hours = 0.0
        overtime_hours = 0.0
        position_hours: Dict[str, float] = {}

        for row in rows:
            pos = row.position or "default"
            total_scheduled += int(row.headcount_scheduled or 0)
            total_actual += int(row.headcount_actual or 0)
            hrs = float(row.total_hours or 0)
            ot = float(row.overtime_hours or 0)
            total_hours += hrs
            overtime_hours += ot
            position_hours[pos] = round(hrs, 2)

        return {
            "headcount_scheduled": total_scheduled,
            "headcount_actual": total_actual,
            "total_hours": round(total_hours, 2),
            "overtime_hours": round(overtime_hours, 2),
            "position_hours": position_hours,
        }

    @staticmethod
    async def _estimate_labor_cost(
        store_id: str,
        snapshot_date: date,
        shift_stats: dict,
        db: AsyncSession,
        position_wage_map: Optional[Dict[str, float]],
    ) -> float:
        """
        从排班工时估算人工成本（元）。
        优先级：position_wage_map > _DEFAULT_HOURLY_WAGE > daily_budget / headcount
        """
        position_hours = shift_stats.get("position_hours", {})
        wage_map = position_wage_map or _DEFAULT_HOURLY_WAGE

        # 方案 B：岗位工时 × 时薪
        if position_hours:
            cost = 0.0
            for pos, hours in position_hours.items():
                hourly = wage_map.get(pos) or wage_map.get("default", _DEFAULT_HOURLY_WAGE["default"])
                cost += hours * hourly
            # 加上加班补贴（方案 B 已包含在工时内，再补贴 0.5 倍）
            ot_hrs = shift_stats.get("overtime_hours", 0.0)
            avg_wage = wage_map.get("default", _DEFAULT_HOURLY_WAGE["default"])
            cost += ot_hrs * avg_wage * 0.5  # 0.5 倍额外加班费
            return round(cost, 2)

        # 方案 C：日预算参考值
        budget = await LaborCostService._fetch_budget(store_id, snapshot_date, db)
        if budget.get("daily_budget_yuan"):
            return float(budget["daily_budget_yuan"])

        # 方案 D：兜底
        headcount = shift_stats.get("headcount_actual") or shift_stats.get("headcount_scheduled", 0)
        return round(headcount * _FALLBACK_DAILY_WAGE_YUAN, 2)

    @staticmethod
    async def _fetch_budget(
        store_id: str,
        snapshot_date: date,
        db: AsyncSession,
    ) -> dict:
        """查询门店当月有效预算配置（monthly 优先）"""
        period = snapshot_date.strftime("%Y-%m")
        try:
            result = await db.execute(
                text("""
                    SELECT
                        target_labor_cost_rate,
                        max_labor_cost_yuan,
                        daily_budget_yuan,
                        alert_threshold_pct
                    FROM store_labor_budgets
                    WHERE store_id      = :sid
                      AND budget_period = :period
                      AND is_active     = TRUE
                    ORDER BY budget_type  -- monthly 先于 weekly
                    LIMIT 1
                """),
                {"sid": store_id, "period": period},
            )
            row = result.fetchone()
            if row:
                return {
                    "target_labor_cost_rate": float(row.target_labor_cost_rate or 0),
                    "max_labor_cost_yuan": float(row.max_labor_cost_yuan or 0),
                    "daily_budget_yuan": float(row.daily_budget_yuan) if row.daily_budget_yuan else None,
                    "alert_threshold_pct": float(row.alert_threshold_pct or 90),
                }
        except Exception as exc:
            logger.warning("labor_cost.fetch_budget_failed", store_id=store_id, error=str(exc))
        return {}

    @staticmethod
    async def _upsert_snapshot(snapshot: dict, db: AsyncSession) -> None:
        """Upsert 到 labor_cost_snapshots（ON CONFLICT store_id + snapshot_date）"""
        try:
            await db.execute(
                text("""
                    INSERT INTO labor_cost_snapshots (
                        store_id, snapshot_date,
                        actual_revenue_yuan, actual_labor_cost_yuan, actual_labor_cost_rate,
                        budgeted_labor_cost_yuan, budgeted_labor_cost_rate,
                        variance_yuan, variance_pct,
                        headcount_actual, headcount_scheduled,
                        overtime_hours, overtime_cost_yuan,
                        created_at, updated_at
                    ) VALUES (
                        :store_id, :snapshot_date,
                        :revenue_yuan, :labor_cost_yuan, :labor_cost_rate,
                        :budgeted_yuan, :budgeted_rate,
                        :variance_yuan, :variance_pct,
                        :hc_actual, :hc_scheduled,
                        :ot_hours, :ot_cost_yuan,
                        NOW(), NOW()
                    )
                    ON CONFLICT (store_id, snapshot_date)
                    DO UPDATE SET
                        actual_revenue_yuan      = EXCLUDED.actual_revenue_yuan,
                        actual_labor_cost_yuan   = EXCLUDED.actual_labor_cost_yuan,
                        actual_labor_cost_rate   = EXCLUDED.actual_labor_cost_rate,
                        budgeted_labor_cost_yuan = EXCLUDED.budgeted_labor_cost_yuan,
                        budgeted_labor_cost_rate = EXCLUDED.budgeted_labor_cost_rate,
                        variance_yuan            = EXCLUDED.variance_yuan,
                        variance_pct             = EXCLUDED.variance_pct,
                        headcount_actual         = EXCLUDED.headcount_actual,
                        headcount_scheduled      = EXCLUDED.headcount_scheduled,
                        overtime_hours           = EXCLUDED.overtime_hours,
                        overtime_cost_yuan       = EXCLUDED.overtime_cost_yuan,
                        updated_at               = NOW()
                """),
                {
                    "store_id": snapshot["store_id"],
                    "snapshot_date": snapshot["snapshot_date"],
                    "revenue_yuan": snapshot["actual_revenue_yuan"],
                    "labor_cost_yuan": snapshot["actual_labor_cost_yuan"],
                    "labor_cost_rate": snapshot["actual_labor_cost_rate"],
                    "budgeted_yuan": snapshot.get("budgeted_labor_cost_yuan"),
                    "budgeted_rate": snapshot.get("budgeted_labor_cost_rate"),
                    "variance_yuan": snapshot["variance_yuan"],
                    "variance_pct": snapshot["variance_pct"],
                    "hc_actual": snapshot.get("headcount_actual"),
                    "hc_scheduled": snapshot.get("headcount_scheduled"),
                    "ot_hours": snapshot.get("overtime_hours"),
                    "ot_cost_yuan": snapshot.get("overtime_cost_yuan"),
                },
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("labor_cost.upsert_snapshot_failed", error=str(exc))
            raise

    @staticmethod
    async def _upsert_rankings(
        rankings: List[dict],
        brand_id: str,
        ranking_date: date,
        period_type: str,
        db: AsyncSession,
    ) -> None:
        """批量 upsert labor_cost_rankings"""
        try:
            for r in rankings:
                await db.execute(
                    text("""
                        INSERT INTO labor_cost_rankings (
                            store_id, ranking_date, period_type,
                            labor_cost_rate, rank_in_group, total_stores_in_group,
                            percentile_score, group_avg_rate, group_median_rate,
                            best_rate_in_group, brand_id, created_at
                        ) VALUES (
                            :store_id, :ranking_date, :period_type,
                            :rate, :rank, :total,
                            :percentile, :avg_rate, :median_rate,
                            :best_rate, :brand_id, NOW()
                        )
                        ON CONFLICT (store_id, ranking_date, period_type)
                        DO UPDATE SET
                            labor_cost_rate       = EXCLUDED.labor_cost_rate,
                            rank_in_group         = EXCLUDED.rank_in_group,
                            total_stores_in_group = EXCLUDED.total_stores_in_group,
                            percentile_score      = EXCLUDED.percentile_score,
                            group_avg_rate        = EXCLUDED.group_avg_rate,
                            group_median_rate     = EXCLUDED.group_median_rate,
                            best_rate_in_group    = EXCLUDED.best_rate_in_group
                    """),
                    {
                        "store_id": r["store_id"],
                        "ranking_date": ranking_date,
                        "period_type": period_type,
                        "rate": r["labor_cost_rate"],
                        "rank": r["rank_in_group"],
                        "total": r["total_stores"],
                        "percentile": r["percentile_score"],
                        "avg_rate": r["group_avg_rate"],
                        "median_rate": r["group_median_rate"],
                        "best_rate": r["best_rate_in_group"],
                        "brand_id": brand_id,
                    },
                )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("labor_cost.upsert_rankings_failed", error=str(exc))
            raise


# ─── 私有工具函数 ──────────────────────────────────────────────────────────────


def _period_range(ranking_date: date, period_type: str):
    """根据 period_type 返回 (start_date, end_date)"""
    if period_type == "daily":
        return ranking_date, ranking_date
    if period_type == "weekly":
        # 本周一到 ranking_date
        start = ranking_date - timedelta(days=ranking_date.weekday())
        return start, ranking_date
    # monthly
    start = ranking_date.replace(day=1)
    return start, ranking_date


def _row_to_snapshot_dict(row) -> dict:
    """将 SQLAlchemy Row 转换为 dict"""
    return {
        "snapshot_date": str(row.snapshot_date),
        "actual_revenue_yuan": float(row.actual_revenue_yuan or 0),
        "actual_labor_cost_yuan": float(row.actual_labor_cost_yuan or 0),
        "actual_labor_cost_rate": float(row.actual_labor_cost_rate or 0),
        "budgeted_labor_cost_yuan": float(row.budgeted_labor_cost_yuan) if row.budgeted_labor_cost_yuan else None,
        "budgeted_labor_cost_rate": float(row.budgeted_labor_cost_rate) if row.budgeted_labor_cost_rate else None,
        "variance_yuan": float(row.variance_yuan or 0),
        "variance_pct": float(row.variance_pct or 0),
        "headcount_actual": int(row.headcount_actual or 0) if row.headcount_actual else None,
        "headcount_scheduled": int(row.headcount_scheduled or 0) if row.headcount_scheduled else None,
        "overtime_hours": float(row.overtime_hours or 0) if row.overtime_hours else None,
        "overtime_cost_yuan": float(row.overtime_cost_yuan or 0) if row.overtime_cost_yuan else None,
    }


def _build_rank_insight(
    store_id: str,
    rank: int,
    total: int,
    rate: float,
    avg: float,
) -> str:
    """生成排名洞察文案（Rule 7：含¥影响 + 行动建议）"""
    if total <= 1:
        return "暂无跨店排名数据"

    delta_pp = round(rate - avg, 2)

    if rank == 1:
        return f"本店人工成本率 {rate}% 为全品牌最优，领先均值 {abs(delta_pp)} 个百分点，建议总结最佳排班实践供其他门店参考。"

    percentile = round((total - rank) / (total - 1) * 100)
    if delta_pp > 0:
        # 超出均值 → 超支
        return (
            f"本店人工成本率 {rate}%，在 {total} 家门店中排第 {rank}（超均值 {delta_pp}pp）。"
            f"若降至均值水平，每日可节省约 ¥{round(abs(delta_pp) / 100 * 5000, 0):.0f}"
            f"（按日均营收¥5000估算）。"
        )
    else:
        # 低于均值 → 节省
        return (
            f"本店人工成本率 {rate}%，在 {total} 家门店中排第 {rank}（优于均值 {abs(delta_pp)}pp），"
            f"人力管控处于较好水平（超过 {percentile}% 的门店）。"
        )
