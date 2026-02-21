"""
定时任务调度器
用于执行业务驱动的定时任务

根据架构评审：调度器应该驱动业务价值
- 每15分钟营收异常检测
- 每天6AM生成昨日简报
- 午高峰前1小时库存预警
"""
import asyncio
from datetime import datetime, time
from typing import Optional
import structlog

logger = structlog.get_logger()


class TaskScheduler:
    """任务调度器 - 驱动业务价值"""

    def __init__(self):
        self.running = False
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
                now = datetime.now()
                current_time = now.time()

                # TODO Week 2: 实现业务驱动的调度任务
                # 1. 每15分钟营收异常检测 → 企微告警
                # 2. 每天6AM生成昨日简报 → 推送
                # 3. 午高峰前1小时库存预警

                logger.debug("scheduler_tick", time=current_time)

                # 等待1分钟后再检查
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
                await asyncio.sleep(60)  # 出错后等待1分钟


# 全局调度器实例
scheduler = TaskScheduler()


def get_scheduler() -> TaskScheduler:
    """获取调度器实例"""
    return scheduler
