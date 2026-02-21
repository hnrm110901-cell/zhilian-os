"""
任务调度器测试
Tests for Task Scheduler
"""
import pytest
import asyncio
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.scheduler import TaskScheduler, scheduler, get_scheduler


class TestTaskScheduler:
    """TaskScheduler测试类"""

    def test_init(self):
        """测试初始化"""
        sched = TaskScheduler()
        assert sched.running is False
        assert sched.backup_time == time(hour=2, minute=0)
        assert sched.task is None

    @pytest.mark.asyncio
    async def test_start(self):
        """测试启动调度器"""
        sched = TaskScheduler()

        # Start the scheduler
        await sched.start()

        assert sched.running is True
        assert sched.task is not None

        # Clean up
        await sched.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """测试启动已运行的调度器"""
        sched = TaskScheduler()

        await sched.start()
        assert sched.running is True

        # Try to start again
        await sched.start()
        assert sched.running is True

        # Clean up
        await sched.stop()

    @pytest.mark.asyncio
    async def test_stop(self):
        """测试停止调度器"""
        sched = TaskScheduler()

        await sched.start()
        assert sched.running is True

        await sched.stop()
        assert sched.running is False

    @pytest.mark.asyncio
    async def test_stop_not_running(self):
        """测试停止未运行的调度器"""
        sched = TaskScheduler()

        # Should not raise error
        await sched.stop()
        assert sched.running is False

    @pytest.mark.asyncio
    @patch('src.services.scheduler.get_backup_service')
    async def test_execute_backup_success(self, mock_get_backup):
        """测试执行备份成功"""
        sched = TaskScheduler()

        mock_backup_service = MagicMock()
        mock_backup_service.create_backup = AsyncMock(return_value={"success": True})
        mock_get_backup.return_value = mock_backup_service

        await sched._execute_backup()

        mock_backup_service.create_backup.assert_called_once_with(backup_type="scheduled")

    @pytest.mark.asyncio
    @patch('src.services.scheduler.get_backup_service')
    async def test_execute_backup_failure(self, mock_get_backup):
        """测试执行备份失败"""
        sched = TaskScheduler()

        mock_backup_service = MagicMock()
        mock_backup_service.create_backup = AsyncMock(side_effect=Exception("Backup failed"))
        mock_get_backup.return_value = mock_backup_service

        # Should not raise exception
        await sched._execute_backup()

    def test_get_scheduler(self):
        """测试获取调度器实例"""
        result = get_scheduler()
        assert isinstance(result, TaskScheduler)
        assert result is scheduler

    def test_global_scheduler_instance(self):
        """测试全局调度器实例"""
        assert scheduler is not None
        assert isinstance(scheduler, TaskScheduler)
