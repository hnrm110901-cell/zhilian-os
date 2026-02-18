"""
定时任务调度器
用于执行定时备份等任务
"""
import asyncio
from datetime import datetime, time
from typing import Optional
import structlog

from src.services.backup_service import get_backup_service

logger = structlog.get_logger()


class TaskScheduler:
    """任务调度器"""

    def __init__(self):
        self.running = False
        self.backup_time = time(hour=2, minute=0)  # 默认凌晨2点备份
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("scheduler_already_running")
            return

        self.running = True
        self.task = asyncio.create_task(self._run())
        logger.info("scheduler_started")

    async def stop(self):
        """停止调度器"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("scheduler_stopped")

    async def _run(self):
        """运行调度器主循环"""
        while self.running:
            try:
                # 检查是否到了备份时间
                now = datetime.now()
                current_time = now.time()

                # 如果当前时间接近备份时间（在5分钟内）
                backup_datetime = datetime.combine(now.date(), self.backup_time)
                time_diff = (backup_datetime - now).total_seconds()

                if 0 <= time_diff <= 300:  # 5分钟内
                    logger.info("scheduled_backup_starting")
                    await self._execute_backup()

                    # 等待到第二天
                    await asyncio.sleep(86400)  # 24小时
                else:
                    # 等待1小时后再检查
                    await asyncio.sleep(3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
                await asyncio.sleep(60)  # 出错后等待1分钟

    async def _execute_backup(self):
        """执行备份任务"""
        try:
            backup_service = get_backup_service()
            result = await backup_service.create_backup(backup_type="scheduled")
            logger.info("scheduled_backup_completed", result=result)
        except Exception as e:
            logger.error("scheduled_backup_failed", error=str(e))


# 全局调度器实例
scheduler = TaskScheduler()


def get_scheduler() -> TaskScheduler:
    """获取调度器实例"""
    return scheduler
