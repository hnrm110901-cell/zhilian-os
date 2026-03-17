"""
WeeklyReviewService — 周复盘服务
负责周度经营汇总、复盘草稿生成、提交审核流。
"""
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from src.models.weekly_review import WeeklyReview, WeeklyReviewItem
from src.models.daily_metric import StoreDailyMetric
from src.models.action_task import ActionTask

logger = structlog.get_logger()


class WeeklyReviewService:
    """周复盘服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_generate(
        self, scope: str, scope_id: str, week_start: date, week_end: date
    ) -> WeeklyReview:
        """获取或自动生成周复盘草稿"""
        result = await self.db.execute(
            select(WeeklyReview).where(
                and_(
                    WeeklyReview.scope_id == scope_id,
                    WeeklyReview.review_scope == scope,
                    WeeklyReview.week_start_date == week_start,
                )
            )
        )
        review = result.scalar_one_or_none()
        if not review:
            review = await self._generate_draft(scope, scope_id, week_start, week_end)
        return review

    async def _generate_draft(
        self, scope: str, scope_id: str, week_start: date, week_end: date
    ) -> WeeklyReview:
        """自动汇总7天数据生成周复盘草稿"""
        # 查询本周所有日经营数据
        metrics_result = await self.db.execute(
            select(StoreDailyMetric).where(
                and_(
                    StoreDailyMetric.store_id == scope_id,
                    StoreDailyMetric.biz_date >= week_start,
                    StoreDailyMetric.biz_date <= week_end,
                )
            )
        )
        metrics = list(metrics_result.scalars().all())

        # 统计各异常天数
        total_sales = sum(m.total_sales_amount or 0 for m in metrics)
        profit_days = sum(1 for m in metrics if (m.net_profit_amount or 0) > 0)
        loss_days = sum(1 for m in metrics if (m.net_profit_amount or 0) < 0)
        cost_abnormal_days = sum(1 for m in metrics if (m.food_cost_rate or 0) > 3500)
        discount_abnormal_days = sum(1 for m in metrics if (m.discount_rate or 0) > 1200)
        labor_abnormal_days = sum(1 for m in metrics if (m.labor_cost_rate or 0) > 2000)
        abnormal_days = sum(1 for m in metrics if m.warning_level in ("yellow", "red"))

        # 汇总利润率（简单加权）
        net_profit_rate = 0
        gross_profit_rate = 0
        if total_sales > 0:
            total_net_profit = sum(m.net_profit_amount or 0 for m in metrics)
            total_gross_profit = sum(m.gross_profit_amount or 0 for m in metrics)
            net_profit_rate = int(total_net_profit * 10000 / total_sales)
            gross_profit_rate = int(total_gross_profit * 10000 / total_sales)

        # 统计任务
        tasks_result = await self.db.execute(
            select(ActionTask).where(
                and_(
                    ActionTask.store_id == scope_id,
                    ActionTask.biz_date >= str(week_start),
                    ActionTask.biz_date <= str(week_end),
                )
            )
        )
        tasks = list(tasks_result.scalars().all())
        closed_tasks = sum(1 for t in tasks if t.status == "closed")
        pending_tasks = sum(1 for t in tasks if t.status not in ("closed", "canceled"))

        # 生成系统摘要
        if loss_days > 0:
            summary = f"本周销售 ¥{total_sales/100:,.0f}，出现 {loss_days} 个亏损日。成本异常 {cost_abnormal_days} 天，折扣异常 {discount_abnormal_days} 天。"
        elif abnormal_days > 0:
            summary = f"本周销售 ¥{total_sales/100:,.0f}，共 {abnormal_days} 天触发预警，请重点复盘成本与折扣管控。"
        else:
            summary = f"本周销售 ¥{total_sales/100:,.0f}，整体经营稳定，各项指标基本达标。"

        review_no = f"WR_{scope_id}_{week_start.strftime('%Y%m%d')}"
        review = WeeklyReview(
            id=uuid.uuid4(),
            review_no=review_no,
            review_scope=scope,
            scope_id=scope_id,
            week_start_date=week_start,
            week_end_date=week_end,
            actual_sales_amount=total_sales,
            gross_profit_rate=gross_profit_rate,
            net_profit_rate=net_profit_rate,
            profit_day_count=profit_days,
            loss_day_count=loss_days,
            abnormal_day_count=abnormal_days,
            cost_abnormal_day_count=cost_abnormal_days,
            discount_abnormal_day_count=discount_abnormal_days,
            labor_abnormal_day_count=labor_abnormal_days,
            submitted_task_count=len(tasks),
            closed_task_count=closed_tasks,
            pending_task_count=pending_tasks,
            system_summary=summary,
            status="draft",
        )
        self.db.add(review)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def submit(
        self,
        review_id: str,
        submitted_by: str,
        manager_summary: str,
        next_week_plan: str,
        next_week_focus_targets: Optional[dict] = None,
    ) -> WeeklyReview:
        """提交周复盘"""
        result = await self.db.execute(
            select(WeeklyReview).where(WeeklyReview.id == review_id)
        )
        review = result.scalar_one_or_none()
        if not review:
            raise ValueError(f"周复盘 [{review_id}] 不存在")
        allowed = {"draft", "pending_submit", "returned"}
        if review.status not in allowed:
            raise ValueError(f"当前状态 [{review.status}] 不允许提交")

        review.manager_summary = manager_summary
        review.next_week_plan = next_week_plan
        review.next_week_focus_targets = next_week_focus_targets
        review.submitted_by = submitted_by
        review.submitted_at = datetime.utcnow()
        review.status = "submitted"
        await self.db.commit()
        await self.db.refresh(review)
        return review

    def to_api_dict(self, r: WeeklyReview) -> dict:
        def fen(v): return round(v / 100, 2) if v else None
        def rate(v): return round(v / 10000, 4) if v is not None else None
        return {
            "id": str(r.id),
            "reviewNo": r.review_no,
            "reviewScope": r.review_scope,
            "scopeId": r.scope_id,
            "weekStartDate": str(r.week_start_date),
            "weekEndDate": str(r.week_end_date),
            "salesTargetAmount": fen(r.sales_target_amount),
            "actualSalesAmount": fen(r.actual_sales_amount),
            "targetAchievementRate": rate(r.target_achievement_rate),
            "grossProfitRate": rate(r.gross_profit_rate),
            "netProfitRate": rate(r.net_profit_rate),
            "profitDayCount": r.profit_day_count,
            "lossDayCount": r.loss_day_count,
            "abnormalDayCount": r.abnormal_day_count,
            "costAbnormalDayCount": r.cost_abnormal_day_count,
            "discountAbnormalDayCount": r.discount_abnormal_day_count,
            "laborAbnormalDayCount": r.labor_abnormal_day_count,
            "submittedTaskCount": r.submitted_task_count,
            "closedTaskCount": r.closed_task_count,
            "pendingTaskCount": r.pending_task_count,
            "repeatedIssueCount": r.repeated_issue_count,
            "systemSummary": r.system_summary,
            "managerSummary": r.manager_summary,
            "nextWeekPlan": r.next_week_plan,
            "nextWeekFocusTargets": r.next_week_focus_targets,
            "status": r.status,
            "submittedBy": r.submitted_by,
            "submittedAt": r.submitted_at.isoformat() if r.submitted_at else None,
        }
