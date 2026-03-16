"""
Weekly Report Service
周报聚合服务 — 汇总 7 天 DailyReport 数据，生成周环比分析

填补 daily (22:30) 和 monthly (每月1日) 之间的报告间隙。
调度：每周五 10:00 UTC（北京时间 18:00，收市后出周报）
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.models.daily_report import DailyReport
from src.models.store import Store

logger = structlog.get_logger()


class WeeklyReportService:
    """周报聚合服务"""

    async def generate_weekly_report(
        self,
        store_id: str,
        week_end: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        生成指定门店的周报。

        Args:
            store_id: 门店ID
            week_end: 周报截止日期（含），默认为昨天所在周的周日

        Returns:
            周报字典，包含本周汇总 + 上周对比 + 每日趋势
        """
        if week_end is None:
            yesterday = date.today() - timedelta(days=1)
            # 对齐到所在周的周日（weekday(): Mon=0 … Sun=6）
            week_end = yesterday + timedelta(days=(6 - yesterday.weekday()))
        week_start = week_end - timedelta(days=6)

        async with get_db_session() as session:
            # 本周 7 天日报
            this_week = await self._get_daily_reports(session, store_id, week_start, week_end)
            # 上周 7 天日报（用于周环比）
            prev_end = week_start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=6)
            prev_week = await self._get_daily_reports(session, store_id, prev_start, prev_end)

        this_agg = self._aggregate(this_week)
        prev_agg = self._aggregate(prev_week)
        wow = self._week_over_week(this_agg, prev_agg)

        # 每日趋势（按日期排序）
        daily_trend = [
            {
                "date": str(d.report_date),
                "revenue_yuan": round(d.total_revenue / 100, 2) if d.total_revenue else 0,
                "order_count": d.order_count or 0,
                "customer_count": d.customer_count or 0,
            }
            for d in sorted(this_week, key=lambda x: x.report_date)
        ]

        report = {
            "store_id": store_id,
            "week_start": str(week_start),
            "week_end": str(week_end),
            "days_with_data": len(this_week),
            # 本周汇总
            "total_revenue_yuan": this_agg["total_revenue_yuan"],
            "total_orders": this_agg["total_orders"],
            "total_customers": this_agg["total_customers"],
            "avg_daily_revenue_yuan": this_agg["avg_daily_revenue_yuan"],
            "avg_order_value_yuan": this_agg["avg_order_value_yuan"],
            "avg_task_completion_rate": this_agg["avg_task_completion_rate"],
            "total_inventory_alerts": this_agg["total_inventory_alerts"],
            "total_service_issues": this_agg["total_service_issues"],
            # 周环比
            "wow_revenue_pct": wow["revenue_pct"],
            "wow_orders_pct": wow["orders_pct"],
            "wow_customers_pct": wow["customers_pct"],
            # 每日趋势
            "daily_trend": daily_trend,
            # 摘要（供企微推送）
            "summary": self._build_summary(this_agg, wow, week_start, week_end),
        }

        logger.info(
            "weekly_report.generated",
            store_id=store_id,
            week=f"{week_start}~{week_end}",
            days=len(this_week),
            revenue_yuan=this_agg["total_revenue_yuan"],
        )
        return report

    async def generate_all_stores(
        self, week_end: Optional[date] = None
    ) -> Dict[str, Any]:
        """为所有活跃门店生成周报"""
        async with get_db_session() as session:
            result = await session.execute(
                select(Store.id).where(Store.is_active.is_(True))
            )
            store_ids = [str(r[0]) for r in result.fetchall()]

        reports = []
        errors = []
        for sid in store_ids:
            try:
                r = await self.generate_weekly_report(sid, week_end)
                reports.append(r)
            except Exception as e:
                errors.append({"store_id": sid, "error": str(e)[:100]})
                logger.warning("weekly_report.store_failed", store_id=sid, error=str(e))

        return {
            "total_stores": len(store_ids),
            "reports_generated": len(reports),
            "errors": len(errors),
            "reports": reports,
            "error_details": errors[:10],
        }

    # ── 内部方法 ──

    async def _get_daily_reports(
        self,
        session: AsyncSession,
        store_id: str,
        start: date,
        end: date,
    ) -> List[DailyReport]:
        """获取指定日期范围内的日报"""
        stmt = (
            select(DailyReport)
            .where(
                DailyReport.store_id == store_id,
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
            )
            .order_by(DailyReport.report_date)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _aggregate(self, reports: List[DailyReport]) -> Dict[str, Any]:
        """将多天日报汇总为一个聚合字典"""
        if not reports:
            return {
                "total_revenue_yuan": 0,
                "total_orders": 0,
                "total_customers": 0,
                "avg_daily_revenue_yuan": 0,
                "avg_order_value_yuan": 0,
                "avg_task_completion_rate": 0,
                "total_inventory_alerts": 0,
                "total_service_issues": 0,
            }

        total_revenue = sum(r.total_revenue or 0 for r in reports)
        total_orders = sum(r.order_count or 0 for r in reports)
        total_customers = sum(r.customer_count or 0 for r in reports)
        n = len(reports)

        return {
            "total_revenue_yuan": round(total_revenue / 100, 2),
            "total_orders": total_orders,
            "total_customers": total_customers,
            "avg_daily_revenue_yuan": round(total_revenue / 100 / n, 2),
            "avg_order_value_yuan": round(total_revenue / total_orders / 100, 2) if total_orders else 0,
            "avg_task_completion_rate": round(
                sum(r.task_completion_rate or 0 for r in reports) / n, 1
            ),
            "total_inventory_alerts": sum(r.inventory_alert_count or 0 for r in reports),
            "total_service_issues": sum(r.service_issue_count or 0 for r in reports),
        }

    def _week_over_week(
        self, this_week: Dict[str, Any], prev_week: Dict[str, Any]
    ) -> Dict[str, Any]:
        """计算周环比百分比"""

        def _pct(cur: float, prev: float) -> Optional[float]:
            if prev == 0:
                return None
            return round((cur - prev) / prev * 100, 1)

        return {
            "revenue_pct": _pct(this_week["total_revenue_yuan"], prev_week["total_revenue_yuan"]),
            "orders_pct": _pct(this_week["total_orders"], prev_week["total_orders"]),
            "customers_pct": _pct(this_week["total_customers"], prev_week["total_customers"]),
        }

    def _build_summary(
        self,
        agg: Dict[str, Any],
        wow: Dict[str, Any],
        week_start: date,
        week_end: date,
    ) -> str:
        """生成周报摘要文本（供企微推送）"""
        lines = [
            f"📊 周报 {week_start.strftime('%m/%d')}~{week_end.strftime('%m/%d')}",
            f"营收 ¥{agg['total_revenue_yuan']:,.2f}",
            f"订单 {agg['total_orders']} 单 | 客流 {agg['total_customers']} 人",
            f"日均营收 ¥{agg['avg_daily_revenue_yuan']:,.2f} | 客单价 ¥{agg['avg_order_value_yuan']:.2f}",
        ]
        # 周环比
        if wow["revenue_pct"] is not None:
            arrow = "↑" if wow["revenue_pct"] >= 0 else "↓"
            lines.append(f"环比上周: 营收{arrow}{abs(wow['revenue_pct'])}%")
        if agg["total_inventory_alerts"] > 0:
            lines.append(f"⚠️ 库存预警 {agg['total_inventory_alerts']} 次")
        return "\n".join(lines)
