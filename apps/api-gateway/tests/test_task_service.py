"""
任务管理服务单元测试
"""
import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.task_service import TaskService
from src.models.task import Task, TaskStatus, TaskPriority
from src.models.user import User, UserRole
from src.core.security import get_password_hash


@pytest.fixture
async def task_service(test_db):
    """创建任务服务实例"""
    return TaskService(test_db)


@pytest.fixture
async def test_user(test_db):
    """创建测试用户"""
    user = User(
        id=uuid.uuid4(),
        username="taskuser",
        email="task@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Task User",
        role=UserRole.STAFF,
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest.fixture
async def test_manager(test_db):
    """创建测试管理员"""
    manager = User(
        id=uuid.uuid4(),
        username="manager",
        email="manager@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Manager User",
        role=UserRole.MANAGER,
        is_active=True,
    )
    test_db.add(manager)
    await test_db.commit()
    await test_db.refresh(manager)
    return manager


@pytest.fixture
async def sample_task(test_db, test_user, test_manager):
    """创建示例任务"""
    task = Task(
        id=uuid.uuid4(),
        title="测试任务",
        description="这是一个测试任务",
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        creator_id=test_manager.id,
        assignee_id=test_user.id,
        due_date=datetime.utcnow() + timedelta(days=7),
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)
    return task


class TestTaskService:
    """任务服务测试类"""

    @pytest.mark.asyncio
    async def test_create_task(self, task_service, test_user, test_manager):
        """测试创建任务"""
        with patch('src.services.task_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            task_data = {
                "title": "新任务",
                "description": "任务描述",
                "priority": TaskPriority.HIGH,
                "assignee_id": test_user.id,
                "due_date": datetime.utcnow() + timedelta(days=3),
            }

            task = await task_service.create_task(
                creator_id=test_manager.id,
                **task_data
            )

            assert task.title == "新任务"
            assert task.status == TaskStatus.PENDING
            assert task.priority == TaskPriority.HIGH
            assert task.creator_id == test_manager.id
            assert task.assignee_id == test_user.id

            # 验证事件发送
            mock_neural.emit.assert_called_once()
            call_args = mock_neural.emit.call_args
            assert call_args[0][0] == "task.created"

    @pytest.mark.asyncio
    async def test_get_task(self, task_service, sample_task):
        """测试获取任务"""
        task = await task_service.get_task(sample_task.id)

        assert task is not None
        assert task.id == sample_task.id
        assert task.title == sample_task.title

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, task_service):
        """测试获取不存在的任务"""
        task = await task_service.get_task(uuid.uuid4())
        assert task is None

    @pytest.mark.asyncio
    async def test_update_task_status(self, task_service, sample_task):
        """测试更新任务状态"""
        with patch('src.services.task_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            updated_task = await task_service.update_task_status(
                task_id=sample_task.id,
                status=TaskStatus.IN_PROGRESS
            )

            assert updated_task.status == TaskStatus.IN_PROGRESS
            assert updated_task.updated_at > sample_task.updated_at

    @pytest.mark.asyncio
    async def test_complete_task(self, task_service, sample_task):
        """测试完成任务"""
        with patch('src.services.task_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            completed_task = await task_service.update_task_status(
                task_id=sample_task.id,
                status=TaskStatus.COMPLETED
            )

            assert completed_task.status == TaskStatus.COMPLETED
            assert completed_task.completed_at is not None

            # 验证完成事件发送
            mock_neural.emit.assert_called()
            call_args = mock_neural.emit.call_args
            assert call_args[0][0] == "task.completed"

    @pytest.mark.asyncio
    async def test_list_tasks_by_assignee(self, task_service, sample_task, test_user):
        """测试按分配人列出任务"""
        tasks = await task_service.list_tasks(assignee_id=test_user.id)

        assert len(tasks) > 0
        assert all(task.assignee_id == test_user.id for task in tasks)

    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, task_service, sample_task):
        """测试按状态列出任务"""
        tasks = await task_service.list_tasks(status=TaskStatus.PENDING)

        assert len(tasks) > 0
        assert all(task.status == TaskStatus.PENDING for task in tasks)

    @pytest.mark.asyncio
    async def test_list_tasks_by_priority(self, task_service, sample_task):
        """测试按优先级列出任务"""
        tasks = await task_service.list_tasks(priority=TaskPriority.MEDIUM)

        assert len(tasks) > 0
        assert all(task.priority == TaskPriority.MEDIUM for task in tasks)

    @pytest.mark.asyncio
    async def test_delete_task(self, task_service, sample_task):
        """测试删除任务"""
        result = await task_service.delete_task(sample_task.id)
        assert result is True

        # 验证任务已删除
        deleted_task = await task_service.get_task(sample_task.id)
        assert deleted_task is None

    @pytest.mark.asyncio
    async def test_update_task_details(self, task_service, sample_task):
        """测试更新任务详情"""
        update_data = {
            "title": "更新后的标题",
            "description": "更新后的描述",
            "priority": TaskPriority.HIGH,
        }

        updated_task = await task_service.update_task(
            task_id=sample_task.id,
            **update_data
        )

        assert updated_task.title == "更新后的标题"
        assert updated_task.description == "更新后的描述"
        assert updated_task.priority == TaskPriority.HIGH

