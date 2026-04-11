"""经营数据定时聚合任务 — 日/周/月自动收盘

定时规则：
  - 每日 22:30 → daily_close_all_stores()
  - 每周一 06:00 → weekly_review_all_stores()
  - 每月1日 05:00 → monthly_close_all_stores()
"""

import asyncio
import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict

import structlog
from celery import group

from .celery_app import celery_app
from .celery_tasks import CallbackTask

logger = structlog.get_logger()


# ──────────────────────────────────────────────────────────────────────────────
# 任务 1: 单门店日度收盘
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "120")),
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=int(os.getenv("CELERY_RETRY_BACKOFF_MAX", "600")),
    retry_jitter=True,
)
def daily_close_store(
    self,
    store_id: str,
    brand_id: str,
    target_date_str: str,
) -> Dict[str, Any]:
    """单门店日度收盘：先聚合快照，再生成 P&L。

    Args:
        store_id: 门店ID
        brand_id: 品牌ID
        target_date_str: 目标日期 (YYYY-MM-DD)
    """

    async def _run():
        from sqlalchemy import text

        from ..core.database import AsyncSessionLocal
        from ..services.pnl_calculator_service import pnl_calculator_service

        target_date = date.fromisoformat(target_date_str)

        async with AsyncSessionLocal() as session:
            # 步骤1: 检查当日 daily 快照是否已存在
            snap_exists = (
                await session.execute(
                    text(
                        """
                        SELECT 1 FROM operation_snapshots
                         WHERE store_id     = :sid
                           AND brand_id     = :bid
                           AND snapshot_date = :d
                           AND period_type  = 'daily'
                         LIMIT 1
                        """
                    ),
                    {"sid": store_id, "bid": brand_id, "d": target_date},
                )
            ).scalar()

            if not snap_exists:
                logger.warning(
                    "daily_close_no_snapshot",
                    store_id=store_id,
                    target_date=target_date_str,
                )
                return {
                    "status": "skipped",
                    "reason": "no_daily_snapshot",
                    "store_id": store_id,
                }

            # 步骤2: 生成日度 P&L
            d = target_date
            result = await pnl_calculator_service.generate_daily_pnl(
                session=session,
                store_id=store_id,
                brand_id=brand_id,
                target_date=d,
            )

            # Step 3: 回填昨日预测的实际值（反馈闭环）
            try:
                from src.services.prediction_feedback_service import PredictionFeedbackService
                pred_svc = PredictionFeedbackService()
                feedback = await pred_svc.backfill_actuals(session, store_id, brand_id, d)
                logger.info("prediction_feedback_backfilled", store_id=store_id, count=feedback.get("backfilled_count", 0))
            except Exception as e:
                logger.warning("prediction_feedback_failed", store_id=store_id, error=str(e))

            # Step 4: 生成明日预测
            try:
                from src.services.prediction_feedback_service import PredictionFeedbackService
                pred_svc = PredictionFeedbackService()
                from datetime import timedelta as _td
                tomorrow = d + _td(days=1)
                predictions = await pred_svc.generate_predictions(session, store_id, brand_id, tomorrow)
                logger.info("predictions_generated", store_id=store_id, date=str(tomorrow))
            except Exception as e:
                logger.warning("prediction_generation_failed", store_id=store_id, error=str(e))

        logger.info(
            "daily_close_store_done",
            store_id=store_id,
            target_date=target_date_str,
            pnl_status=result.get("status"),
        )
        return {
            "status": "ok",
            "store_id": store_id,
            "target_date": target_date_str,
            "pnl": result,
        }

    return asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# 任务 2: 所有门店日度收盘（入口）
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "120")),
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def daily_close_all_stores(self) -> Dict[str, Any]:
    """查询所有 active 门店，用 Celery group 并行 dispatch daily_close_store。

    默认收盘昨天的数据（T+1 模式）。
    """

    async def _run():
        from sqlalchemy import text

        from ..core.database import AsyncSessionLocal

        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, brand_id
                          FROM stores
                         WHERE is_active = TRUE
                           AND brand_id IS NOT NULL
                        """
                    )
                )
            ).fetchall()

        if not rows:
            logger.info("daily_close_no_active_stores")
            return {"status": "ok", "dispatched": 0}

        # 组建并行任务组
        tasks = group(
            daily_close_store.s(
                store_id=str(row[0]),
                brand_id=str(row[1]),
                target_date_str=yesterday,
            )
            for row in rows
        )
        result = tasks.apply_async()

        logger.info(
            "daily_close_dispatched",
            store_count=len(rows),
            target_date=yesterday,
            group_id=str(result.id),
        )
        return {
            "status": "ok",
            "dispatched": len(rows),
            "target_date": yesterday,
            "group_id": str(result.id),
        }

    return asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# 任务 3: 所有门店周度回顾
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "120")),
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def weekly_review_all_stores(self) -> Dict[str, Any]:
    """每周一触发，以上周日作为 week_end，聚合周度快照。"""

    async def _run():
        from sqlalchemy import text

        from ..core.database import AsyncSessionLocal

        # 上周日 = 本周一 - 1天；周一 = 上周日 - 6天
        today = datetime.now().date()
        week_end = today - timedelta(days=1)  # 上周日
        week_start = week_end - timedelta(days=6)  # 上周一

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, brand_id
                          FROM stores
                         WHERE is_active = TRUE
                           AND brand_id IS NOT NULL
                        """
                    )
                )
            ).fetchall()

            if not rows:
                logger.info("weekly_review_no_active_stores")
                return {"status": "ok", "processed": 0}

            processed = 0
            for row in rows:
                sid = str(row[0])
                bid = str(row[1])

                # 聚合日快照 → 周快照 (UPSERT operation_snapshots weekly)
                await session.execute(
                    text(
                        """
                        INSERT INTO operation_snapshots (
                            brand_id, store_id, snapshot_date, period_type,
                            revenue_fen, cost_material_fen, cost_labor_fen,
                            cost_rent_fen, cost_utility_fen, cost_platform_fee_fen,
                            cost_other_fen, gross_profit_fen, net_profit_fen,
                            customer_count, new_customer_count, returning_customer_count,
                            order_count, dine_in_order_count, takeout_order_count,
                            delivery_order_count,
                            waste_value_fen, employee_count,
                            source_record_count
                        )
                        SELECT
                            :bid, :sid, :week_end, 'weekly',
                            COALESCE(SUM(revenue_fen), 0),
                            COALESCE(SUM(cost_material_fen), 0),
                            COALESCE(SUM(cost_labor_fen), 0),
                            COALESCE(SUM(cost_rent_fen), 0),
                            COALESCE(SUM(cost_utility_fen), 0),
                            COALESCE(SUM(cost_platform_fee_fen), 0),
                            COALESCE(SUM(cost_other_fen), 0),
                            COALESCE(SUM(gross_profit_fen), 0),
                            COALESCE(SUM(net_profit_fen), 0),
                            COALESCE(SUM(customer_count), 0),
                            COALESCE(SUM(new_customer_count), 0),
                            COALESCE(SUM(returning_customer_count), 0),
                            COALESCE(SUM(order_count), 0),
                            COALESCE(SUM(dine_in_order_count), 0),
                            COALESCE(SUM(takeout_order_count), 0),
                            COALESCE(SUM(delivery_order_count), 0),
                            COALESCE(SUM(waste_value_fen), 0),
                            MAX(employee_count),
                            COUNT(*)
                        FROM operation_snapshots
                        WHERE store_id     = :sid
                          AND brand_id     = :bid
                          AND period_type  = 'daily'
                          AND snapshot_date BETWEEN :ws AND :we
                        ON CONFLICT (brand_id, store_id, snapshot_date, period_type)
                        DO UPDATE SET
                            revenue_fen             = EXCLUDED.revenue_fen,
                            cost_material_fen       = EXCLUDED.cost_material_fen,
                            cost_labor_fen          = EXCLUDED.cost_labor_fen,
                            cost_rent_fen           = EXCLUDED.cost_rent_fen,
                            cost_utility_fen        = EXCLUDED.cost_utility_fen,
                            cost_platform_fee_fen   = EXCLUDED.cost_platform_fee_fen,
                            cost_other_fen          = EXCLUDED.cost_other_fen,
                            gross_profit_fen        = EXCLUDED.gross_profit_fen,
                            net_profit_fen          = EXCLUDED.net_profit_fen,
                            customer_count          = EXCLUDED.customer_count,
                            new_customer_count      = EXCLUDED.new_customer_count,
                            returning_customer_count = EXCLUDED.returning_customer_count,
                            order_count             = EXCLUDED.order_count,
                            dine_in_order_count     = EXCLUDED.dine_in_order_count,
                            takeout_order_count     = EXCLUDED.takeout_order_count,
                            delivery_order_count    = EXCLUDED.delivery_order_count,
                            waste_value_fen         = EXCLUDED.waste_value_fen,
                            employee_count          = EXCLUDED.employee_count,
                            source_record_count     = EXCLUDED.source_record_count,
                            aggregated_at           = NOW()
                        """
                    ),
                    {
                        "bid": bid,
                        "sid": sid,
                        "week_end": week_end,
                        "ws": week_start,
                        "we": week_end,
                    },
                )
                processed += 1

            await session.commit()

        logger.info(
            "weekly_review_done",
            week_start=str(week_start),
            week_end=str(week_end),
            processed=processed,
        )
        return {
            "status": "ok",
            "processed": processed,
            "week_start": str(week_start),
            "week_end": str(week_end),
        }

    return asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# 任务 4: 所有门店月度收盘
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "120")),
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def monthly_close_all_stores(self) -> Dict[str, Any]:
    """每月1日触发，对上个月的数据做月度聚合 + 生成月度 P&L + 盈亏平衡线。"""

    async def _run():
        from sqlalchemy import text

        from ..core.database import AsyncSessionLocal
        from ..services.pnl_calculator_service import pnl_calculator_service

        today = datetime.now().date()
        # 上个月的第一天
        last_month_first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        # 上个月最后一天
        last_month_last = today.replace(day=1) - timedelta(days=1)

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, brand_id
                          FROM stores
                         WHERE is_active = TRUE
                           AND brand_id IS NOT NULL
                        """
                    )
                )
            ).fetchall()

            if not rows:
                logger.info("monthly_close_no_active_stores")
                return {"status": "ok", "processed": 0}

            processed = 0
            pnl_results = []
            checked_brand_ids = set()

            for row in rows:
                sid = str(row[0])
                bid = str(row[1])

                # 步骤1: 聚合日快照 → 月快照 (UPSERT operation_snapshots monthly)
                await session.execute(
                    text(
                        """
                        INSERT INTO operation_snapshots (
                            brand_id, store_id, snapshot_date, period_type,
                            revenue_fen, cost_material_fen, cost_labor_fen,
                            cost_rent_fen, cost_utility_fen, cost_platform_fee_fen,
                            cost_other_fen, gross_profit_fen, net_profit_fen,
                            customer_count, new_customer_count, returning_customer_count,
                            order_count, dine_in_order_count, takeout_order_count,
                            delivery_order_count,
                            waste_value_fen, employee_count,
                            source_record_count
                        )
                        SELECT
                            :bid, :sid, :month_date, 'monthly',
                            COALESCE(SUM(revenue_fen), 0),
                            COALESCE(SUM(cost_material_fen), 0),
                            COALESCE(SUM(cost_labor_fen), 0),
                            COALESCE(SUM(cost_rent_fen), 0),
                            COALESCE(SUM(cost_utility_fen), 0),
                            COALESCE(SUM(cost_platform_fee_fen), 0),
                            COALESCE(SUM(cost_other_fen), 0),
                            COALESCE(SUM(gross_profit_fen), 0),
                            COALESCE(SUM(net_profit_fen), 0),
                            COALESCE(SUM(customer_count), 0),
                            COALESCE(SUM(new_customer_count), 0),
                            COALESCE(SUM(returning_customer_count), 0),
                            COALESCE(SUM(order_count), 0),
                            COALESCE(SUM(dine_in_order_count), 0),
                            COALESCE(SUM(takeout_order_count), 0),
                            COALESCE(SUM(delivery_order_count), 0),
                            COALESCE(SUM(waste_value_fen), 0),
                            MAX(employee_count),
                            COUNT(*)
                        FROM operation_snapshots
                        WHERE store_id     = :sid
                          AND brand_id     = :bid
                          AND period_type  = 'daily'
                          AND snapshot_date BETWEEN :ms AND :me
                        ON CONFLICT (brand_id, store_id, snapshot_date, period_type)
                        DO UPDATE SET
                            revenue_fen             = EXCLUDED.revenue_fen,
                            cost_material_fen       = EXCLUDED.cost_material_fen,
                            cost_labor_fen          = EXCLUDED.cost_labor_fen,
                            cost_rent_fen           = EXCLUDED.cost_rent_fen,
                            cost_utility_fen        = EXCLUDED.cost_utility_fen,
                            cost_platform_fee_fen   = EXCLUDED.cost_platform_fee_fen,
                            cost_other_fen          = EXCLUDED.cost_other_fen,
                            gross_profit_fen        = EXCLUDED.gross_profit_fen,
                            net_profit_fen          = EXCLUDED.net_profit_fen,
                            customer_count          = EXCLUDED.customer_count,
                            new_customer_count      = EXCLUDED.new_customer_count,
                            returning_customer_count = EXCLUDED.returning_customer_count,
                            order_count             = EXCLUDED.order_count,
                            dine_in_order_count     = EXCLUDED.dine_in_order_count,
                            takeout_order_count     = EXCLUDED.takeout_order_count,
                            delivery_order_count    = EXCLUDED.delivery_order_count,
                            waste_value_fen         = EXCLUDED.waste_value_fen,
                            employee_count          = EXCLUDED.employee_count,
                            source_record_count     = EXCLUDED.source_record_count,
                            aggregated_at           = NOW()
                        """
                    ),
                    {
                        "bid": bid,
                        "sid": sid,
                        "month_date": last_month_first,
                        "ms": last_month_first,
                        "me": last_month_last,
                    },
                )

                await session.commit()

                # 步骤2: 生成月度 P&L + 盈亏平衡线
                pnl_result = await pnl_calculator_service.generate_monthly_pnl(
                    session=session,
                    store_id=sid,
                    brand_id=bid,
                    month_date=last_month_first,
                )
                pnl_results.append(
                    {"store_id": sid, "pnl_status": pnl_result.get("status")}
                )
                processed += 1

                # 收集 brand_id 用于后续目标偏差检查
                checked_brand_ids.add(bid)

            # Step 3: 检查目标偏差（按品牌去重）
            for _bid in checked_brand_ids:
                try:
                    from src.services.agent_event_processor import AgentEventProcessor
                    proc = AgentEventProcessor()
                    deviations = await proc.check_objective_deviations(session, _bid)
                    logger.info("objective_deviations_checked", brand_id=_bid, behind=deviations.get("behind", 0))
                except Exception as e:
                    logger.warning("objective_deviation_check_failed", brand_id=_bid, error=str(e))

        logger.info(
            "monthly_close_done",
            month=str(last_month_first),
            processed=processed,
        )
        return {
            "status": "ok",
            "processed": processed,
            "month": str(last_month_first),
            "details": pnl_results,
        }

    return asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# beat_schedule 配置说明
# ──────────────────────────────────────────────────────────────────────────────
#
# 需要在 celery_app.py 的 beat_schedule 字典中添加以下 3 项：
#
# from celery.schedules import crontab  # 已有
#
# "daily-close-all-stores": {
#     "task": "src.core.celery_tasks_aggregation.daily_close_all_stores",
#     "schedule": crontab(hour=22, minute=30),
#     "args": (),
#     "options": {"queue": "default", "priority": 5},
# },
# "weekly-review-all-stores": {
#     "task": "src.core.celery_tasks_aggregation.weekly_review_all_stores",
#     "schedule": crontab(hour=6, minute=0, day_of_week=1),  # 每周一
#     "args": (),
#     "options": {"queue": "default", "priority": 5},
# },
# "monthly-close-all-stores": {
#     "task": "src.core.celery_tasks_aggregation.monthly_close_all_stores",
#     "schedule": crontab(hour=5, minute=0, day_of_month=1),  # 每月1日
#     "args": (),
#     "options": {"queue": "default", "priority": 5},
# },
#
# 同时在 task_routes 中添加：
#
# "src.core.celery_tasks_aggregation.daily_close_store": {
#     "queue": "default",
#     "routing_key": "default",
# },
# "src.core.celery_tasks_aggregation.daily_close_all_stores": {
#     "queue": "default",
#     "routing_key": "default",
# },
# "src.core.celery_tasks_aggregation.weekly_review_all_stores": {
#     "queue": "default",
#     "routing_key": "default",
# },
# "src.core.celery_tasks_aggregation.monthly_close_all_stores": {
#     "queue": "default",
#     "routing_key": "default",
# },
