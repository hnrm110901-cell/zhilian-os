"""
P2 绩效计算服务

职责：从 orders / order_items / waste_events 聚合各岗位核心指标，
      upsert 到 employee_metric_records 表。

可计算指标：
  store_manager : revenue(monthly_revenue), profit(gross_margin_pct),
                  labor_efficiency, waste_rate
  waiter        : avg_per_table, order_count
  kitchen       : avg_serve_time, waste_rate
  delivery      : order_count

Achievement rate 计算：value / target（target 来自 DEFAULT_ROLE_CONFIG target_value 字段；
无 target 时 achievement_rate=None）。
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.employee import Employee
from src.models.employee_metric import EmployeeMetricRecord
from src.models.order import Order, OrderItem
from src.models.waste_event import WasteEvent
from src.models.store import Store

logger = structlog.get_logger()

# 默认指标目标值（可后续迁移到数据库配置表）
DEFAULT_TARGETS: Dict[str, float] = {
    "revenue":          300_000_00,  # 分：300,000 元
    "profit":           0.55,        # 毛利率 55%
    "labor_efficiency": 5_000_00,    # 分：5,000 元/人
    "waste_rate":       0.05,        # 损耗率 5%
    "avg_per_table":    15_000,      # 分：150 元/桌
    "order_count":      300,         # 单/月
    "avg_serve_time":   15.0,        # 分钟（越低越好，特殊处理）
}

# 出餐时效越低越好：达成率 = target / value（反向）
LOWER_IS_BETTER = {"avg_serve_time", "waste_rate"}


def _achievement(value: Optional[float], target: Optional[float],
                 metric_id: str) -> Optional[float]:
    """计算达成率，最高不超过 2.0，避免除零。"""
    if value is None or target is None or target == 0:
        return None
    if metric_id in LOWER_IS_BETTER:
        rate = target / value  # 越小越好，反转
    else:
        rate = value / target
    return min(round(rate, 4), 2.0)


class PerformanceComputeService:

    @staticmethod
    async def compute_and_write(
        session: AsyncSession,
        store_id: str,
        year: int,
        month: int,
    ) -> int:
        """
        计算并 upsert 指定门店、指定月份的所有可算指标。

        Returns:
            写入（新增 + 更新）的记录条数。
        """
        period_start = date(year, month, 1)
        period_end   = date(year, month, calendar.monthrange(year, month)[1])

        rows: List[dict] = []
        rows += await PerformanceComputeService._compute_store_metrics(
            session, store_id, period_start, period_end
        )
        rows += await PerformanceComputeService._compute_waiter_metrics(
            session, store_id, period_start, period_end
        )
        rows += await PerformanceComputeService._compute_kitchen_metrics(
            session, store_id, period_start, period_end
        )

        if not rows:
            return 0

        # Upsert: ON CONFLICT (employee_id, metric_id, period_start) DO UPDATE
        stmt = pg_insert(EmployeeMetricRecord).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_emp_metric_period",
            set_={
                "value":            stmt.excluded.value,
                "target":           stmt.excluded.target,
                "achievement_rate": stmt.excluded.achievement_rate,
                "data_source":      stmt.excluded.data_source,
                "updated_at":       datetime.utcnow(),
            },
        )
        await session.execute(stmt)
        await session.flush()
        logger.info("performance_compute_written", store_id=store_id,
                    year=year, month=month, rows=len(rows))
        return len(rows)

    # ── 店长指标 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def _compute_store_metrics(
        session: AsyncSession,
        store_id: str,
        period_start: date,
        period_end: date,
    ) -> List[dict]:
        """
        计算店长（store_manager）岗位指标：
          revenue          = SUM(orders.final_amount)
          profit           = AVG(order_items.gross_margin)
          labor_efficiency = revenue / COUNT(active employees)
          waste_rate       = AVG(ABS(waste_events.variance_pct))
        """
        # 找到该门店的店长（position='store_manager'）
        mgr_res = await session.execute(
            select(Employee).where(
                and_(
                    Employee.store_id == store_id,
                    Employee.position == "store_manager",
                    Employee.is_active.is_(True),
                )
            )
        )
        managers = mgr_res.scalars().all()
        if not managers:
            return []

        # 月度营收
        rev_res = await session.execute(
            select(func.sum(Order.final_amount)).where(
                and_(
                    Order.store_id == store_id,
                    Order.status == "completed",
                    func.date(Order.order_time) >= period_start,
                    func.date(Order.order_time) <= period_end,
                )
            )
        )
        monthly_revenue = rev_res.scalar() or 0  # 分

        # 毛利率（AVG gross_margin across order_items in completed orders）
        margin_res = await session.execute(
            select(func.avg(OrderItem.gross_margin)).where(
                and_(
                    OrderItem.order_id.in_(
                        select(Order.id).where(
                            and_(
                                Order.store_id == store_id,
                                Order.status == "completed",
                                func.date(Order.order_time) >= period_start,
                                func.date(Order.order_time) <= period_end,
                            )
                        )
                    ),
                    OrderItem.gross_margin.isnot(None),
                )
            )
        )
        gross_margin_pct = margin_res.scalar()  # Decimal or None

        # 在职员工数
        emp_count_res = await session.execute(
            select(func.count(Employee.id)).where(
                and_(Employee.store_id == store_id, Employee.is_active.is_(True))
            )
        )
        emp_count = emp_count_res.scalar() or 1

        labor_efficiency = (
            float(monthly_revenue) / float(emp_count) if emp_count > 0 else None
        )

        # 损耗率
        waste_res = await session.execute(
            select(func.avg(func.abs(WasteEvent.variance_pct))).where(
                and_(
                    WasteEvent.store_id == store_id,
                    WasteEvent.variance_pct.isnot(None),
                    func.date(WasteEvent.occurred_at) >= period_start,
                    func.date(WasteEvent.occurred_at) <= period_end,
                )
            )
        )
        waste_rate = waste_res.scalar()  # float or None

        metric_values = {
            "revenue":          float(monthly_revenue) if monthly_revenue else None,
            "profit":           float(gross_margin_pct) if gross_margin_pct is not None else None,
            "labor_efficiency": labor_efficiency,
            "waste_rate":       float(waste_rate) if waste_rate is not None else None,
        }

        rows = []
        for manager in managers:
            for metric_id, value in metric_values.items():
                target = DEFAULT_TARGETS.get(metric_id)
                rows.append({
                    "employee_id":      manager.id,
                    "store_id":         store_id,
                    "metric_id":        metric_id,
                    "period_start":     period_start,
                    "period_end":       period_end,
                    "value":            Decimal(str(value)) if value is not None else None,
                    "target":           Decimal(str(target)) if target is not None else None,
                    "achievement_rate": (
                        Decimal(str(_achievement(value, target, metric_id)))
                        if value is not None and target is not None else None
                    ),
                    "data_source": "orders,order_items,waste_events",
                })
        return rows

    # ── 服务员指标 ────────────────────────────────────────────────────────────

    @staticmethod
    async def _compute_waiter_metrics(
        session: AsyncSession,
        store_id: str,
        period_start: date,
        period_end: date,
    ) -> List[dict]:
        """
        按 orders.waiter_id 分组计算：
          avg_per_table = AVG(final_amount)
          order_count   = COUNT(*)
        """
        res = await session.execute(
            select(
                Order.waiter_id,
                func.avg(Order.final_amount).label("avg_per_table"),
                func.count(Order.id).label("order_count"),
            ).where(
                and_(
                    Order.store_id == store_id,
                    Order.status == "completed",
                    Order.waiter_id.isnot(None),
                    func.date(Order.order_time) >= period_start,
                    func.date(Order.order_time) <= period_end,
                )
            ).group_by(Order.waiter_id)
        )
        waiter_stats = res.all()

        rows = []
        for waiter_id, avg_amount, cnt in waiter_stats:
            for metric_id, value in [
                ("avg_per_table", float(avg_amount) if avg_amount is not None else None),
                ("order_count",   float(cnt) if cnt is not None else None),
            ]:
                target = DEFAULT_TARGETS.get(metric_id)
                rows.append({
                    "employee_id":      waiter_id,
                    "store_id":         store_id,
                    "metric_id":        metric_id,
                    "period_start":     period_start,
                    "period_end":       period_end,
                    "value":            Decimal(str(value)) if value is not None else None,
                    "target":           Decimal(str(target)) if target is not None else None,
                    "achievement_rate": (
                        Decimal(str(_achievement(value, target, metric_id)))
                        if value is not None and target is not None else None
                    ),
                    "data_source": "orders",
                })
        return rows

    # ── 后厨指标 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def _compute_kitchen_metrics(
        session: AsyncSession,
        store_id: str,
        period_start: date,
        period_end: date,
    ) -> List[dict]:
        """
        计算后厨（kitchen）岗位指标（门店级别，归属所有 kitchen 员工）：
          avg_serve_time = AVG(EXTRACT(EPOCH FROM completed_at - confirmed_at) / 60)（分钟）
          waste_rate     = AVG(ABS(variance_pct))
        """
        kitchen_res = await session.execute(
            select(Employee).where(
                and_(
                    Employee.store_id == store_id,
                    Employee.position == "kitchen",
                    Employee.is_active.is_(True),
                )
            )
        )
        kitchen_staff = kitchen_res.scalars().all()
        if not kitchen_staff:
            return []

        # 出餐时效（仅限已完成且有 confirmed_at 的订单）
        serve_res = await session.execute(
            select(
                func.avg(
                    func.extract("epoch", Order.completed_at - Order.confirmed_at) / 60.0
                )
            ).where(
                and_(
                    Order.store_id == store_id,
                    Order.status == "completed",
                    Order.confirmed_at.isnot(None),
                    Order.completed_at.isnot(None),
                    func.date(Order.order_time) >= period_start,
                    func.date(Order.order_time) <= period_end,
                )
            )
        )
        avg_serve_time = serve_res.scalar()

        # 损耗率
        waste_res = await session.execute(
            select(func.avg(func.abs(WasteEvent.variance_pct))).where(
                and_(
                    WasteEvent.store_id == store_id,
                    WasteEvent.variance_pct.isnot(None),
                    func.date(WasteEvent.occurred_at) >= period_start,
                    func.date(WasteEvent.occurred_at) <= period_end,
                )
            )
        )
        waste_rate = waste_res.scalar()

        metric_values = {
            "avg_serve_time": float(avg_serve_time) if avg_serve_time is not None else None,
            "waste_rate":     float(waste_rate)     if waste_rate is not None else None,
        }

        rows = []
        for staff in kitchen_staff:
            for metric_id, value in metric_values.items():
                target = DEFAULT_TARGETS.get(metric_id)
                rows.append({
                    "employee_id":      staff.id,
                    "store_id":         store_id,
                    "metric_id":        metric_id,
                    "period_start":     period_start,
                    "period_end":       period_end,
                    "value":            Decimal(str(value)) if value is not None else None,
                    "target":           Decimal(str(target)) if target is not None else None,
                    "achievement_rate": (
                        Decimal(str(_achievement(value, target, metric_id)))
                        if value is not None and target is not None else None
                    ),
                    "data_source": "orders,waste_events",
                })
        return rows
