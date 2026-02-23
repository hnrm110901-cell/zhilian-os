"""
Task Service
任务管理服务
"""
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import uuid

from src.core.database import get_db_session
from src.models.task import Task, TaskStatus, TaskPriority
from src.models.user import User
from src.services.neural_system import neural_system

logger = structlog.get_logger()


class TaskService:
    """任务管理服务"""

    async def create_task(
        self,
        title: str,
        content: str,
        creator_id: uuid.UUID,
        store_id: str,
        assignee_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        due_at: Optional[datetime] = None
    ) -> Task:
        """
        创建任务

        Args:
            title: 任务标题
            content: 任务内容
            creator_id: 创建人ID
            store_id: 门店ID
            assignee_id: 指派人ID
            category: 任务类别
            priority: 优先级
            due_at: 截止时间

        Returns:
            创建的任务对象
        """
        try:
            async with get_db_session() as session:
                task = Task(
                    title=title,
                    content=content,
                    creator_id=creator_id,
                    store_id=store_id,
                    assignee_id=assignee_id,
                    category=category,
                    priority=priority,
                    due_at=due_at,
                    status=TaskStatus.PENDING
                )

                session.add(task)
                await session.commit()
                await session.refresh(task)

                logger.info(
                    "任务创建成功",
                    task_id=str(task.id),
                    title=title,
                    creator_id=str(creator_id),
                    assignee_id=str(assignee_id) if assignee_id else None
                )

                # 触发任务创建事件，发送企微通知
                if assignee_id:
                    await neural_system.emit_event(
                        event_type="task.created",
                        data={
                            "task_id": str(task.id),
                            "title": title,
                            "content": content,
                            "assignee_id": str(assignee_id),
                            "creator_id": str(creator_id),
                            "store_id": store_id,
                            "priority": priority.value,
                            "due_at": due_at.isoformat() if due_at else None
                        },
                        store_id=store_id
                    )

                return task

        except Exception as e:
            logger.error("创建任务失败", error=str(e), exc_info=e)
            raise

    async def assign_task(
        self,
        task_id: uuid.UUID,
        assignee_id: uuid.UUID,
        current_user_id: uuid.UUID
    ) -> Task:
        """
        指派任务

        Args:
            task_id: 任务ID
            assignee_id: 指派给谁
            current_user_id: 当前操作用户ID

        Returns:
            更新后的任务对象
        """
        try:
            async with get_db_session() as session:
                # 查询任务
                result = await session.execute(
                    select(Task).where(
                        Task.id == task_id,
                        Task.is_deleted == "false"
                    )
                )
                task = result.scalar_one_or_none()

                if not task:
                    raise ValueError(f"任务不存在: {task_id}")

                # 更新指派人
                task.assignee_id = assignee_id
                task.updated_at = datetime.utcnow()

                await session.commit()
                await session.refresh(task)

                logger.info(
                    "任务指派成功",
                    task_id=str(task_id),
                    assignee_id=str(assignee_id),
                    operator_id=str(current_user_id)
                )

                return task

        except Exception as e:
            logger.error("指派任务失败", task_id=str(task_id), error=str(e), exc_info=e)
            raise

    async def complete_task(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        result: Optional[str] = None,
        attachments: Optional[str] = None
    ) -> Task:
        """
        完成任务

        Args:
            task_id: 任务ID
            user_id: 完成任务的用户ID
            result: 任务结果
            attachments: 附件

        Returns:
            更新后的任务对象
        """
        try:
            async with get_db_session() as session:
                # 查询任务
                result_query = await session.execute(
                    select(Task).where(
                        Task.id == task_id,
                        Task.is_deleted == "false"
                    )
                )
                task = result_query.scalar_one_or_none()

                if not task:
                    raise ValueError(f"任务不存在: {task_id}")

                # 验证是否是指派人
                if task.assignee_id and task.assignee_id != user_id:
                    logger.warning(
                        "非指派人尝试完成任务",
                        task_id=str(task_id),
                        assignee_id=str(task.assignee_id),
                        user_id=str(user_id)
                    )

                # 更新任务状态
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                task.result = result
                if attachments:
                    task.attachments = attachments
                task.updated_at = datetime.utcnow()

                await session.commit()
                await session.refresh(task)

                logger.info(
                    "任务完成",
                    task_id=str(task_id),
                    user_id=str(user_id)
                )

                return task

        except Exception as e:
            logger.error("完成任务失败", task_id=str(task_id), error=str(e), exc_info=e)
            raise

    async def query_tasks(
        self,
        store_id: Optional[str] = None,
        assignee_id: Optional[uuid.UUID] = None,
        creator_id: Optional[uuid.UUID] = None,
        status: Optional[TaskStatus] = None,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        查询任务列表

        Args:
            store_id: 门店ID
            assignee_id: 指派人ID
            creator_id: 创建人ID
            status: 任务状态
            category: 任务类别
            page: 页码
            page_size: 每页数量

        Returns:
            任务列表和分页信息
        """
        try:
            async with get_db_session() as session:
                # 构建查询条件
                conditions = [Task.is_deleted == "false"]

                if store_id:
                    conditions.append(Task.store_id == store_id)
                if assignee_id:
                    conditions.append(Task.assignee_id == assignee_id)
                if creator_id:
                    conditions.append(Task.creator_id == creator_id)
                if status:
                    conditions.append(Task.status == status)
                if category:
                    conditions.append(Task.category == category)

                # 查询总数
                count_query = select(Task).where(and_(*conditions))
                count_result = await session.execute(count_query)
                total = len(count_result.scalars().all())

                # 分页查询
                offset = (page - 1) * page_size
                query = (
                    select(Task)
                    .where(and_(*conditions))
                    .order_by(Task.created_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )

                result = await session.execute(query)
                tasks = result.scalars().all()

                return {
                    "tasks": tasks,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size
                }

        except Exception as e:
            logger.error("查询任务列表失败", error=str(e), exc_info=e)
            raise

    async def get_task_by_id(self, task_id: uuid.UUID) -> Optional[Task]:
        """
        根据ID获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象
        """
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Task).where(
                        Task.id == task_id,
                        Task.is_deleted == "false"
                    )
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error("获取任务失败", task_id=str(task_id), error=str(e), exc_info=e)
            raise

    async def update_task_status(
        self,
        task_id: uuid.UUID,
        status: TaskStatus,
        user_id: uuid.UUID
    ) -> Task:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            user_id: 操作用户ID

        Returns:
            更新后的任务对象
        """
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Task).where(
                        Task.id == task_id,
                        Task.is_deleted == "false"
                    )
                )
                task = result.scalar_one_or_none()

                if not task:
                    raise ValueError(f"任务不存在: {task_id}")

                task.status = status
                task.updated_at = datetime.utcnow()

                if status == TaskStatus.IN_PROGRESS and not task.started_at:
                    task.started_at = datetime.utcnow()
                elif status == TaskStatus.COMPLETED and not task.completed_at:
                    task.completed_at = datetime.utcnow()

                await session.commit()
                await session.refresh(task)

                logger.info(
                    "任务状态更新",
                    task_id=str(task_id),
                    status=status.value,
                    user_id=str(user_id)
                )

                return task

        except Exception as e:
            logger.error("更新任务状态失败", task_id=str(task_id), error=str(e), exc_info=e)
            raise

    async def delete_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        删除任务（软删除）

        Args:
            task_id: 任务ID
            user_id: 操作用户ID

        Returns:
            是否成功
        """
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Task).where(
                        Task.id == task_id,
                        Task.is_deleted == "false"
                    )
                )
                task = result.scalar_one_or_none()

                if not task:
                    raise ValueError(f"任务不存在: {task_id}")

                task.is_deleted = "true"
                task.deleted_at = datetime.utcnow()
                task.updated_at = datetime.utcnow()

                await session.commit()

                logger.info(
                    "任务删除",
                    task_id=str(task_id),
                    user_id=str(user_id)
                )

                return True

        except Exception as e:
            logger.error("删除任务失败", task_id=str(task_id), error=str(e), exc_info=e)
            raise


# 创建全局服务实例
task_service = TaskService()
