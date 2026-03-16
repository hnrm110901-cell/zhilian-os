"""
任务调度器测试
Tests for Task Scheduler
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.scheduler import TaskScheduler, scheduler, get_scheduler


class TestTaskScheduler:
    """TaskScheduler测试类"""

    def test_init(self):
        """测试初始化"""
        sched = TaskScheduler()
        assert sched.running is False
        assert sched.task is None
        assert sched._last_run == {
            "revenue_anomaly": None,
            "daily_report": None,
            "inventory_alert": None,
            "reconciliation": None,
        }

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

    def test_get_scheduler(self):
        """测试获取调度器实例"""
        result = get_scheduler()
        assert isinstance(result, TaskScheduler)
        assert result is scheduler

    def test_global_scheduler_instance(self):
        """测试全局调度器实例"""
        assert scheduler is not None
        assert isinstance(scheduler, TaskScheduler)
