"""
PeopleAgent Service — 人力经营智能（Sprint 6）

9-Agent 终态中的 PeopleAgent，核心能力：
1. 人效分析（人均产出 = 营收/排班人数）
2. 排班健康度（实际排班 vs 客流预测的匹配度）
3. 员工绩效排名（订单量/服务评价）
4. 人力成本趋势（人工成本率月环比）
5. 离职风险预警（基于排班频次变化）

定位：老板的人力成本管控，店长的排班决策助手
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.order import Order
from src.models.schedule import Schedule, Shift

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_labor_efficiency(
    revenue_yuan: float,
    labor_hours: float,
) -> float:
    """
    人效 = 营收 / 总工时（元/小时）

    行业基准：正餐 80-150 元/人时
    """
    if labor_hours <= 0:
        return 0.0
    return round(revenue_yuan / labor_hours, 2)


def classify_staffing_health(
    actual_staff: int,
    recommended_staff: int,
) -> str:
    """
    排班匹配度

    overstaffed: 实际 > 推荐 × 1.2
    optimal: ±20%
    understaffed: 实际 < 推荐 × 0.8
    """
    if recommended_staff <= 0:
        return "unknown"
    ratio = actual_staff / recommended_staff
    if ratio > 1.2:
        return "overstaffed"
    if ratio < 0.8:
        return "understaffed"
    return "optimal"


def compute_turnover_risk(
    hire_days: int,
    recent_shift_count: int,
    avg_shift_count: float,
) -> str:
    """
    离职风险评估

    high: 新员工(<90天) 或 排班骤降(近期<均值50%)
    medium: 排班略降(<均值80%)
    low: 正常
    """
    if hire_days < 90:
        return "high"
    if avg_shift_count > 0 and recent_shift_count < avg_shift_count * 0.5:
        return "high"
    if avg_shift_count > 0 and recent_shift_count < avg_shift_count * 0.8:
        return "medium"
    return "low"


def compute_labor_cost_rate(
    labor_cost_yuan: float,
    revenue_yuan: float,
) -> float:
    """
    人工成本率 = 人力成本 / 营收

    行业基准：正餐 20%-28%
    """
    if revenue_yuan <= 0:
        return 0.0
    return round(labor_cost_yuan / revenue_yuan, 4)


class PeopleAgentService:
    """PeopleAgent — 人力经营智能"""

    async def get_people_dashboard(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> dict:
        """
        人力综合仪表盘

        返回：总员工数 + 人效 + 排班覆盖 + 人工成本率
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 在职员工数
        active_count = (
            await db.scalar(
                select(func.count(Person.id)).where(
                    Person.store_id == store_id,
                    Person.is_active.is_(True),
                )
            )
            or 0
        )

        # 按岗位分布
        position_stmt = (
            select(EmploymentAssignment.position, func.count(Person.id))
            .join(EmploymentAssignment, and_(
                EmploymentAssignment.person_id == Person.id,
                EmploymentAssignment.status == "active",
            ))
            .where(
                Person.store_id == store_id,
                Person.is_active.is_(True),
            )
            .group_by(EmploymentAssignment.position)
        )
        pos_result = await db.execute(position_stmt)
        position_dist = {(row[0] or "未分类"): row[1] for row in pos_result.all()}

        # 营收（用于计算人效）
        revenue = await db.scalar(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
            )
        )
        revenue_yuan = float(revenue or 0)

        # 排班总工时（近N天）
        today = date.today()
        start_date = today - timedelta(days=days)
        shift_stats = await db.execute(
            select(
                func.count(Shift.id),
            )
            .join(Schedule, Schedule.id == Shift.schedule_id)
            .where(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= start_date,
                Schedule.schedule_date <= today,
            )
        )
        srow = shift_stats.one()
        total_shifts = srow[0] or 0
        # 估算工时：每班次约8小时
        est_labor_hours = total_shifts * 8

        # 人效
        efficiency = compute_labor_efficiency(revenue_yuan, est_labor_hours)

        # 人工成本估算（按平均时薪20元）
        est_labor_cost = est_labor_hours * 20
        labor_cost_rate = compute_labor_cost_rate(est_labor_cost, revenue_yuan)

        return {
            "period_days": days,
            "active_employees": active_count,
            "position_distribution": position_dist,
            "revenue_yuan": round(revenue_yuan, 2),
            "total_shifts": total_shifts,
            "est_labor_hours": est_labor_hours,
            "labor_efficiency_yuan_per_hour": efficiency,
            "est_labor_cost_yuan": round(est_labor_cost, 2),
            "labor_cost_rate": labor_cost_rate,
        }

    async def get_employee_performance(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> List[dict]:
        """
        员工绩效排名

        按服务订单数排序（waiter_id 关联）
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                Order.waiter_id,
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
                Order.waiter_id.isnot(None),
            )
            .group_by(Order.waiter_id)
            .order_by(func.count(Order.id).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)

        performers = []
        for row in result.all():
            orders = row[1] or 0
            rev = float(row[2] or 0)
            performers.append(
                {
                    "employee_id": row[0],
                    "order_count": orders,
                    "revenue_yuan": round(rev, 2),
                    "avg_ticket_yuan": round(rev / orders, 2) if orders > 0 else 0.0,
                }
            )
        return performers

    async def get_staffing_gaps(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> List[dict]:
        """
        排班缺口分析

        按日期查看排班人数 vs 订单密度
        """
        today = date.today()
        start_date = today - timedelta(days=days)

        # 每日排班人数
        shift_by_date = await db.execute(
            select(
                Schedule.schedule_date,
                func.count(func.distinct(Shift.employee_id)),
            )
            .join(Shift, Shift.schedule_id == Schedule.id)
            .where(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= start_date,
                Schedule.schedule_date <= today,
            )
            .group_by(Schedule.schedule_date)
        )

        # 每日订单数
        order_by_date = await db.execute(
            select(
                func.date(Order.order_time),
                func.count(Order.id),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= datetime.combine(start_date, datetime.min.time()),
                Order.status != "cancelled",
            )
            .group_by(func.date(Order.order_time))
        )

        shifts_map = {str(r[0]): r[1] for r in shift_by_date.all()}
        orders_map = {str(r[0]): r[1] for r in order_by_date.all()}

        gaps = []
        for d in range(days):
            dt = start_date + timedelta(days=d)
            ds = str(dt)
            staff = shifts_map.get(ds, 0)
            orders = orders_map.get(ds, 0)
            # 简单推荐：每15单需要1个服务员
            recommended = max(1, orders // 15)
            health = classify_staffing_health(staff, recommended)
            gaps.append(
                {
                    "date": ds,
                    "actual_staff": staff,
                    "order_count": orders,
                    "recommended_staff": recommended,
                    "staffing_health": health,
                }
            )
        return gaps


# 全局单例
people_agent_service = PeopleAgentService()
