# apps/api-gateway/src/services/marketing_task_service.py
"""营销任务服务 — P3"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.marketing_task import (
    MarketingTask, MarketingTaskTarget, MarketingTaskAssignment,
    MarketingTaskExecution, MarketingTaskStats,
)

logger = structlog.get_logger(__name__)


class MarketingTaskService:
    """营销任务 CRUD + 人群筛选"""

    async def create_task(
        self,
        db: AsyncSession,
        *,
        brand_id: str,
        title: str,
        audience_type: str,
        audience_config: Dict,
        created_by: UUID,
        description: str = "",
        script_template: str = "",
        coupon_config: Optional[Dict] = None,
        deadline: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        task = MarketingTask(
            brand_id=brand_id,
            title=title,
            description=description,
            audience_type=audience_type,
            audience_config=audience_config,
            script_template=script_template,
            coupon_config=coupon_config,
            deadline=deadline,
            created_by=created_by,
        )
        db.add(task)
        await db.flush()
        return {"success": True, "task_id": str(task.id)}

    async def preview_audience(
        self,
        db: AsyncSession,
        *,
        audience_type: str,
        audience_config: Dict,
        store_ids: List[str],
    ) -> Dict[str, Any]:
        """预览人群数量。

        预设人群包使用 ORM 构建参数化查询（安全）。
        AI 查询由 LLM 生成结构化过滤条件，服务端构建参数化查询（不拼接 SQL）。
        """
        if audience_type == "preset":
            preset_id = audience_config.get("preset_id", "")
            filters_fn = self._preset_to_orm(preset_id)
            if filters_fn is None:
                return {"total_count": 0, "error": f"未知预设包: {preset_id}"}

            from ..models.consumer_identity import ConsumerIdentity
            stmt = select(func.count()).select_from(ConsumerIdentity).where(
                ConsumerIdentity.is_merged.is_(False),
                *filters_fn(ConsumerIdentity),
            )
            result = await db.execute(stmt)
            total = result.scalar() or 0
            return {"total_count": total, "by_store": []}

        elif audience_type == "ai_query":
            filters = audience_config.get("filters", [])
            return await self._query_by_structured_filters(db, filters)

        return {"total_count": 0, "by_store": []}

    async def _query_by_structured_filters(
        self, db: AsyncSession, filters: List[Dict],
    ) -> Dict[str, Any]:
        from ..models.consumer_identity import ConsumerIdentity

        ALLOWED_COLUMNS = {
            "total_order_count", "total_order_amount_fen", "rfm_recency_days",
            "rfm_frequency", "rfm_monetary_fen", "birth_date", "last_order_at",
            "first_order_at", "total_reservation_count",
        }
        ALLOWED_OPS = {"=", "!=", ">", ">=", "<", "<="}

        stmt = select(func.count()).select_from(ConsumerIdentity).where(
            ConsumerIdentity.is_merged.is_(False),
        )

        for f in filters:
            col_name = f.get("column", "")
            op = f.get("op", "")
            value = f.get("value")

            if col_name not in ALLOWED_COLUMNS or op not in ALLOWED_OPS:
                continue

            col = getattr(ConsumerIdentity, col_name, None)
            if col is None:
                continue

            if op == "=":
                stmt = stmt.where(col == value)
            elif op == "!=":
                stmt = stmt.where(col != value)
            elif op == ">":
                stmt = stmt.where(col > value)
            elif op == ">=":
                stmt = stmt.where(col >= value)
            elif op == "<":
                stmt = stmt.where(col < value)
            elif op == "<=":
                stmt = stmt.where(col <= value)

        result = await db.execute(stmt)
        total = result.scalar() or 0
        return {"total_count": total, "by_store": []}

    @staticmethod
    def _preset_to_orm(preset_id: str):
        """返回一个函数 fn(CI) -> list[条件]，用于 ORM 构建参数化查询。

        返回 None 表示未知预设包。绝不使用 text() f-string。
        """
        from datetime import timedelta

        def _birthday_week(CI):
            # 近一周生日：使用 raw SQL text() 但不拼接任何变量
            return [
                CI.birth_date.isnot(None),
                text("""(DATE_PART('month', consumer_identities.birth_date) * 100
                    + DATE_PART('day', consumer_identities.birth_date))
                    IN (SELECT DATE_PART('month', d) * 100 + DATE_PART('day', d)
                        FROM generate_series(CURRENT_DATE,
                             CURRENT_DATE + INTERVAL '7 days',
                             '1 day'::interval) d)"""),
            ]

        def _inactive_30d(CI):
            return [CI.last_order_at < func.now() - text("INTERVAL '30 days'"), CI.total_order_count > 3]

        def _low_balance(CI):
            return [CI.total_order_amount_fen > 0]

        def _high_value_vip(CI):
            return [CI.total_order_count >= 10, CI.total_order_amount_fen >= 1000000]

        def _new_customer(CI):
            return [CI.total_order_count == 1, CI.first_order_at > func.now() - text("INTERVAL '30 days'")]

        def _declining(CI):
            return [CI.rfm_frequency.isnot(None)]

        def _dormant(CI):
            return [CI.last_order_at < func.now() - text("INTERVAL '90 days'")]

        presets = {
            "birthday_week": _birthday_week,
            "inactive_30d": _inactive_30d,
            "low_balance": _low_balance,
            "high_value_vip": _high_value_vip,
            "new_customer": _new_customer,
            "declining": _declining,
            "dormant": _dormant,
        }
        return presets.get(preset_id)

    async def publish_task(
        self,
        db: AsyncSession,
        *,
        task_id: UUID,
        store_ids: List[str],
    ) -> Dict[str, Any]:
        task = await db.get(MarketingTask, task_id)
        if not task or task.status != "draft":
            return {"success": False, "error": "任务不存在或状态不正确"}

        task.status = "published"
        task.published_at = datetime.now(timezone.utc)

        for sid in store_ids:
            assignment = MarketingTaskAssignment(
                task_id=task.id,
                store_id=sid,
                status="pending",
            )
            db.add(assignment)

        await db.flush()
        return {"success": True, "assignment_count": len(store_ids)}

    async def assign_staff(
        self,
        db: AsyncSession,
        *,
        assignment_id: UUID,
        assigned_to: UUID,
    ) -> Dict[str, Any]:
        assignment = await db.get(MarketingTaskAssignment, assignment_id)
        if not assignment:
            return {"success": False, "error": "分配记录不存在"}

        assignment.assigned_to = assigned_to
        assignment.status = "assigned"
        assignment.assigned_at = datetime.now(timezone.utc)
        await db.flush()
        return {"success": True}

    async def record_execution(
        self,
        db: AsyncSession,
        *,
        assignment_id: UUID,
        target_id: UUID,
        executor_id: UUID,
        action_type: str,
        action_detail: Optional[Dict] = None,
        feedback: str = "",
        distribution_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        execution = MarketingTaskExecution(
            assignment_id=assignment_id,
            target_id=target_id,
            executor_id=executor_id,
            action_type=action_type,
            action_detail=action_detail or {},
            distribution_id=distribution_id,
            feedback=feedback,
            executed_at=datetime.now(timezone.utc),
        )
        db.add(execution)

        assignment = await db.get(MarketingTaskAssignment, assignment_id)
        if assignment:
            assignment.completed_count = (assignment.completed_count or 0) + 1
            if assignment.completed_count >= assignment.target_count and assignment.target_count > 0:
                assignment.status = "completed"
                assignment.completed_at = datetime.now(timezone.utc)

        await db.flush()
        return {"success": True, "execution_id": str(execution.id)}


marketing_task_service = MarketingTaskService()
