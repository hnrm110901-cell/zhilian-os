"""
ActionTaskService — 异常整改任务服务
负责任务生成、状态流转、闭环管理。
"""
import uuid
from datetime import date, datetime
from typing import List, Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.models.action_task import ActionTask
from src.models.warning_record import WarningRecord

logger = structlog.get_logger()

# 任务类型与预警类型映射
TASK_TYPE_MAP = {
    "food_cost_high": "food_cost_review",
    "discount_high": "discount_review",
    "labor_high": "labor_review",
    "sales_drop": "sales_analysis",
    "food_cost_rate": "food_cost_review",
    "discount_rate": "discount_review",
    "labor_cost_rate": "labor_review",
}

# 任务责任角色映射
TASK_ROLE_MAP = {
    "food_cost_review": "chef",
    "discount_review": "store_manager",
    "labor_review": "store_manager",
    "sales_analysis": "store_manager",
}


class ActionTaskService:
    """整改任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_from_warning(self, warning: WarningRecord) -> ActionTask:
        """从预警记录自动生成整改任务"""
        task_type = TASK_TYPE_MAP.get(warning.warning_type, "general_review")
        assignee_role = TASK_ROLE_MAP.get(task_type, "store_manager")

        task = ActionTask(
            id=uuid.uuid4(),
            task_no=f"TASK_{warning.biz_date.replace('-', '')}_{str(uuid.uuid4())[:6].upper()}",
            store_id=warning.store_id,
            biz_date=warning.biz_date,
            source_type="warning",
            source_id=warning.id,
            task_type=task_type,
            task_title=f"{warning.rule_name}",
            task_description=f"{warning.biz_date} {warning.rule_name}，实际值 {warning.actual_value}，需核查原因并制定整改计划。",
            severity_level=warning.warning_level,
            assignee_role=assignee_role,
            status="generated",
            is_repeated_issue=False,
            repeat_count=0,
        )
        self.db.add(task)

        # 更新预警记录状态 → 已转任务
        warning.status = "linked_task"
        warning.related_task_id = task.id

        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def list(
        self,
        store_id: Optional[str] = None,
        biz_date: Optional[str] = None,
        status: Optional[str] = None,
        assignee_id: Optional[str] = None,
    ) -> List[ActionTask]:
        stmt = select(ActionTask)
        conditions = []
        if store_id:
            conditions.append(ActionTask.store_id == store_id)
        if biz_date:
            conditions.append(ActionTask.biz_date == biz_date)
        if status:
            conditions.append(ActionTask.status == status)
        if assignee_id:
            conditions.append(ActionTask.assignee_id == assignee_id)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(ActionTask.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, task_id: str) -> Optional[ActionTask]:
        result = await self.db.execute(
            select(ActionTask).where(ActionTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def submit(
        self, task_id: str, submit_comment: str, attachments: Optional[list] = None
    ) -> ActionTask:
        """责任人提交任务说明"""
        task = await self.get_by_id(task_id)
        if not task:
            raise ValueError(f"任务 [{task_id}] 不存在")
        allowed = {"generated", "pending_handle", "returned"}
        if task.status not in allowed:
            raise ValueError(f"当前状态 [{task.status}] 不允许提交")
        task.submit_comment = submit_comment
        task.submit_attachments = attachments
        task.status = "pending_review"
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def review(
        self, task_id: str, action: str, review_comment: str
    ) -> ActionTask:
        """审核人复核任务"""
        task = await self.get_by_id(task_id)
        if not task:
            raise ValueError(f"任务 [{task_id}] 不存在")
        if task.status != "pending_review":
            raise ValueError(f"当前状态 [{task.status}] 不允许审核")
        task.review_comment = review_comment
        if action == "approve":
            task.status = "rectifying"
        elif action == "return":
            task.status = "returned"
        else:
            raise ValueError(f"无效动作：{action}")
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def close(self, task_id: str, close_comment: str) -> ActionTask:
        """关闭任务（整改完成）"""
        task = await self.get_by_id(task_id)
        if not task:
            raise ValueError(f"任务 [{task_id}] 不存在")
        task.review_comment = close_comment
        task.status = "closed"
        task.closed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    def to_api_dict(self, t: ActionTask) -> dict:
        return {
            "id": str(t.id),
            "taskNo": t.task_no,
            "storeId": t.store_id,
            "bizDate": t.biz_date,
            "taskType": t.task_type,
            "taskTitle": t.task_title,
            "taskDescription": t.task_description,
            "severityLevel": t.severity_level,
            "assigneeId": t.assignee_id,
            "assigneeRole": t.assignee_role,
            "reviewerId": t.reviewer_id,
            "dueAt": t.due_at.isoformat() if t.due_at else None,
            "status": t.status,
            "submitComment": t.submit_comment,
            "reviewComment": t.review_comment,
            "isRepeatedIssue": t.is_repeated_issue,
            "repeatCount": t.repeat_count,
        }
