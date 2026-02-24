"""
定时任务调度器
用于执行业务驱动的定时任务

调度计划：
- 每15分钟  → detect_revenue_anomaly（营收异常检测）
- 每天22:30 → generate_and_send_daily_report（营业日报）
- 每天10:00 → check_inventory_alert（库存预警）
- 每天03:00 → perform_daily_reconciliation（POS对账）
"""
import asyncio
from datetime import datetime, date
from typing import Optional, Dict
import os
import structlog

logger = structlog.get_logger()


class TaskScheduler:
    """任务调度器 - 驱动业务价值"""

    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self._last_run: Dict[str, Optional[datetime]] = {
            "revenue_anomaly": None,
            "daily_report": None,
            "inventory_alert": None,
            "reconciliation": None,
        }

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
                today = now.date()

                # 每15分钟：营收异常检测
                last = self._last_run["revenue_anomaly"]
                if last is None or (now - last).total_seconds() >= int(os.getenv("SCHEDULER_REVENUE_ANOMALY_INTERVAL", "900")):
                    from src.core.celery_tasks import detect_revenue_anomaly
                    detect_revenue_anomaly.delay()
                    self._last_run["revenue_anomaly"] = now
                    logger.info("scheduler_triggered", task="detect_revenue_anomaly")

                # 每天22:30：营业日报
                last = self._last_run["daily_report"]
                _report_hour = int(os.getenv("DAILY_REPORT_SCHEDULE_HOUR", "22"))
                _report_minute = int(os.getenv("DAILY_REPORT_SCHEDULE_MINUTE", "30"))
                if (now.hour == _report_hour and now.minute == _report_minute and
                        (last is None or last.date() < today)):
                    from src.core.celery_tasks import generate_and_send_daily_report
                    from src.core.database import get_db_session
                    from src.models.store import Store
                    from sqlalchemy import select
                    async with get_db_session() as session:
                        result = await session.execute(
                            select(Store.id).where(Store.is_active == True)
                        )
                        store_ids = [str(row[0]) for row in result.all()]
                    for sid in store_ids:
                        generate_and_send_daily_report.delay(sid)
                    self._last_run["daily_report"] = now
                    logger.info("scheduler_triggered", task="generate_and_send_daily_report", stores=len(store_ids))

                # 每天10:00：库存预警
                last = self._last_run["inventory_alert"]
                _inv_hour = int(os.getenv("INVENTORY_ALERT_SCHEDULE_HOUR", "10"))
                _inv_minute = int(os.getenv("INVENTORY_ALERT_SCHEDULE_MINUTE", "0"))
                if (now.hour == _inv_hour and now.minute == _inv_minute and
                        (last is None or last.date() < today)):
                    from src.core.celery_tasks import check_inventory_alert
                    check_inventory_alert.delay()
                    self._last_run["inventory_alert"] = now
                    logger.info("scheduler_triggered", task="check_inventory_alert")

                # 每天03:00：POS对账
                last = self._last_run["reconciliation"]
                _recon_hour = int(os.getenv("RECONCILIATION_SCHEDULE_HOUR", "3"))
                _recon_minute = int(os.getenv("RECONCILIATION_SCHEDULE_MINUTE", "0"))
                if (now.hour == _recon_hour and now.minute == _recon_minute and
                        (last is None or last.date() < today)):
                    from src.core.celery_tasks import perform_daily_reconciliation
                    from src.core.database import get_db_session
                    from src.models.store import Store
                    from sqlalchemy import select
                    async with get_db_session() as session:
                        result = await session.execute(
                            select(Store.id).where(Store.is_active == True)
                        )
                        store_ids = [str(row[0]) for row in result.all()]
                    for sid in store_ids:
                        perform_daily_reconciliation.delay(sid)
                    self._last_run["reconciliation"] = now
                    logger.info("scheduler_triggered", task="perform_daily_reconciliation", stores=len(store_ids))

                logger.debug("scheduler_tick", time=now.time())
                await asyncio.sleep(int(os.getenv("SCHEDULER_TICK_SECONDS", "60")))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
                await asyncio.sleep(int(os.getenv("SCHEDULER_TICK_SECONDS", "60")))


# 全局调度器实例
scheduler = TaskScheduler()


def get_scheduler() -> TaskScheduler:
    """获取调度器实例"""
    return scheduler
