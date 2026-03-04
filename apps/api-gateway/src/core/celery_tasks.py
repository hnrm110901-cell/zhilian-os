"""
Celery异步任务
用于Neural System的事件处理和向量数据库索引
"""
from typing import Dict, Any
import asyncio
import os
import re
import structlog

# 表名只允许小写字母/数字/下划线，防止通过 backup_jobs.tables 字段注入任意 SQL
_SAFE_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
from celery import Task

from .celery_app import celery_app

logger = structlog.get_logger()


class CallbackTask(Task):
    """带回调的任务基类"""

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(
            "Celery任务成功",
            task_id=task_id,
            task_name=self.name,
            result=retval,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(
            "Celery任务失败",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
            traceback=str(einfo),
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试回调"""
        logger.warning(
            "Celery任务重试",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
            retry_count=self.request.retries,
        )


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=int(os.getenv("CELERY_RETRY_BACKOFF_MAX", "600")),
    retry_jitter=True,
)
def process_neural_event(
    self,
    event_id: str,
    event_type: str,
    event_source: str,
    store_id: str,
    data: Dict[str, Any],
    priority: int = 0,
) -> Dict[str, Any]:
    """
    处理神经系统事件（异步任务）

    Args:
        event_id: 事件ID
        event_type: 事件类型
        event_source: 事件来源
        store_id: 门店ID
        data: 事件数据
        priority: 优先级

    Returns:
        处理结果
    """
    async def _run():
        from datetime import datetime
        from ..services.vector_db_service import vector_db_service
        from ..core.database import AsyncSessionLocal
        from ..models.neural_event_log import NeuralEventLog, EventProcessingStatus

        # 1. 写入 DB — 标记为 processing
        async with AsyncSessionLocal() as session:
            log = NeuralEventLog(
                event_id=event_id,
                celery_task_id=self.request.id,
                event_type=event_type,
                event_source=event_source,
                store_id=store_id,
                priority=priority,
                data=data,
                processing_status=EventProcessingStatus.PROCESSING,
                queued_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
            )
            session.add(log)
            await session.commit()

        logger.info(
            "开始处理神经系统事件",
            event_id=event_id,
            event_type=event_type,
            store_id=store_id,
        )

        actions_taken = []
        downstream_tasks = []
        vector_indexed = False
        wechat_sent = False

        try:
            # 2. 向量化存储（全局索引 + 领域分割索引）
            event_payload = {
                "event_id": event_id,
                "event_type": event_type,
                "event_source": event_source,
                "timestamp": datetime.utcnow(),
                "store_id": store_id,
                "data": data,
                "priority": priority,
            }
            await vector_db_service.index_event(event_payload)
            from ..services.domain_vector_service import domain_vector_service
            await domain_vector_service.index_neural_event(store_id, event_payload)
            vector_indexed = True
            actions_taken.append("vector_indexed")

            # 3. 触发企微推送
            from ..services.wechat_trigger_service import wechat_trigger_service
            try:
                await wechat_trigger_service.trigger_push(
                    event_type=event_type,
                    event_data=data,
                    store_id=store_id,
                )
                wechat_sent = True
                actions_taken.append("wechat_sent")
            except Exception as e:
                logger.warning("企微推送触发失败", event_type=event_type, error=str(e))

            # 4. 根据事件类型触发下游任务
            if event_type.startswith("order."):
                t = index_order_to_vector_db.delay(data)
                downstream_tasks.append({"task_name": "index_order_to_vector_db", "task_id": t.id})
                actions_taken.append("dispatched:index_order_to_vector_db")
            elif event_type.startswith("dish."):
                t = index_dish_to_vector_db.delay(data)
                downstream_tasks.append({"task_name": "index_dish_to_vector_db", "task_id": t.id})
                actions_taken.append("dispatched:index_dish_to_vector_db")

            processed_at = datetime.utcnow()

            # 5. 写回 DB — 标记为 completed
            async with AsyncSessionLocal() as session:
                db_log = await session.get(NeuralEventLog, event_id)
                if db_log:
                    db_log.processing_status = EventProcessingStatus.COMPLETED
                    db_log.vector_indexed = vector_indexed
                    db_log.wechat_sent = wechat_sent
                    db_log.downstream_tasks = downstream_tasks
                    db_log.actions_taken = actions_taken
                    db_log.processed_at = processed_at
                    await session.commit()

            logger.info("神经系统事件处理完成", event_id=event_id, event_type=event_type)
            return {
                "success": True,
                "event_id": event_id,
                "processed_at": processed_at.isoformat(),
                "actions_taken": actions_taken,
            }

        except Exception as e:
            logger.error("神经系统事件处理失败", event_id=event_id, error=str(e), exc_info=e)
            # 写回 DB — 标记为 failed / retrying
            try:
                is_last_retry = self.request.retries >= self.max_retries
                async with AsyncSessionLocal() as session:
                    db_log = await session.get(NeuralEventLog, event_id)
                    if db_log:
                        db_log.processing_status = (
                            EventProcessingStatus.FAILED if is_last_retry
                            else EventProcessingStatus.RETRYING
                        )
                        db_log.error_message = str(e)
                        db_log.retry_count = self.request.retries + 1
                        await session.commit()
            except Exception as db_err:
                logger.warning("celery_tasks.status_update_failed", error=str(db_err))
            raise self.retry(exc=e)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_SHORT", "30")),
)
def index_to_vector_db(
    self,
    collection_name: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    索引数据到向量数据库（通用任务）

    Args:
        collection_name: 集合名称
        data: 要索引的数据

    Returns:
        索引结果
    """
    async def _run():
        try:
            from ..services.vector_db_service import vector_db_service

            logger.info(
                "开始索引到向量数据库",
                collection=collection_name,
                data_id=data.get("id"),
            )

            # 根据集合类型调用相应的索引方法
            if collection_name == "orders":
                await vector_db_service.index_order(data)
            elif collection_name == "dishes":
                await vector_db_service.index_dish(data)
            elif collection_name == "events":
                await vector_db_service.index_event(data)
            else:
                raise ValueError(f"不支持的集合类型: {collection_name}")

            logger.info(
                "向量数据库索引完成",
                collection=collection_name,
                data_id=data.get("id"),
            )

            return {
                "success": True,
                "collection": collection_name,
                "data_id": data.get("id"),
            }

        except Exception as e:
            logger.error(
                "向量数据库索引失败",
                collection=collection_name,
                error=str(e),
                exc_info=e,
            )
            raise self.retry(exc=e)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
)
def index_order_to_vector_db(
    self,
    order_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    索引订单到向量数据库

    Args:
        order_data: 订单数据

    Returns:
        索引结果
    """
    async def _run():
        from ..services.vector_db_service import vector_db_service
        from ..services.domain_vector_service import domain_vector_service
        store_id = order_data.get("store_id", "")
        logger.info("开始索引到向量数据库", collection="orders", data_id=order_data.get("id"))
        await vector_db_service.index_order(order_data)
        await domain_vector_service.index_revenue_event(store_id, order_data)
        logger.info("向量数据库索引完成", collection="orders/revenue", data_id=order_data.get("id"))
        return {"success": True, "collection": "orders", "data_id": order_data.get("id")}
    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
)
def index_dish_to_vector_db(
    self,
    dish_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    索引菜品到向量数据库

    Args:
        dish_data: 菜品数据

    Returns:
        索引结果
    """
    async def _run():
        from ..services.vector_db_service import vector_db_service
        from ..services.domain_vector_service import domain_vector_service
        store_id = dish_data.get("store_id", "")
        logger.info("开始索引到向量数据库", collection="dishes", data_id=dish_data.get("id"))
        await vector_db_service.index_dish(dish_data)
        await domain_vector_service.index_menu_item(store_id, dish_data)
        logger.info("向量数据库索引完成", collection="dishes/menu", data_id=dish_data.get("id"))
        return {"success": True, "collection": "dishes", "data_id": dish_data.get("id")}
    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
)
def batch_index_orders(
    self,
    orders: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    批量索引订单到向量数据库

    Args:
        orders: 订单列表

    Returns:
        批量索引结果
    """
    try:
        logger.info("开始批量索引订单", count=len(orders))

        # 为每个订单创建异步任务
        tasks = [
            index_order_to_vector_db.delay(order)
            for order in orders
        ]

        # 等待所有任务完成
        results = [task.get(timeout=int(os.getenv("CELERY_TASK_GET_TIMEOUT", "300"))) for task in tasks]

        success_count = sum(1 for r in results if r.get("success"))

        logger.info(
            "批量索引订单完成",
            total=len(orders),
            success=success_count,
            failed=len(orders) - success_count,
        )

        return {
            "success": True,
            "total": len(orders),
            "success_count": success_count,
            "failed_count": len(orders) - success_count,
        }

    except Exception as e:
        logger.error("批量索引订单失败", error=str(e), exc_info=e)
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
)
def batch_index_dishes(
    self,
    dishes: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    批量索引菜品到向量数据库

    Args:
        dishes: 菜品列表

    Returns:
        批量索引结果
    """
    try:
        logger.info("开始批量索引菜品", count=len(dishes))

        # 为每个菜品创建异步任务
        tasks = [
            index_dish_to_vector_db.delay(dish)
            for dish in dishes
        ]

        # 等待所有任务完成
        results = [task.get(timeout=int(os.getenv("CELERY_TASK_GET_TIMEOUT", "300"))) for task in tasks]

        success_count = sum(1 for r in results if r.get("success"))

        logger.info(
            "批量索引菜品完成",
            total=len(dishes),
            success=success_count,
            failed=len(dishes) - success_count,
        )

        return {
            "success": True,
            "total": len(dishes),
            "success_count": success_count,
            "failed_count": len(dishes) - success_count,
        }

    except Exception as e:
        logger.error("批量索引菜品失败", error=str(e), exc_info=e)
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_LONG", "300")),  # 5分钟
)
def generate_and_send_daily_report(
    self,
    store_id: str = None,
    report_date: str = None,
) -> Dict[str, Any]:
    """
    生成并发送营业日报

    Args:
        store_id: 门店ID (None表示为所有门店生成，Beat调度时使用)
        report_date: 报告日期（YYYY-MM-DD格式，默认为昨天）

    Returns:
        生成和发送结果
    """
    async def _run():
        try:
            from datetime import date, datetime, timedelta
            from ..services.daily_report_service import daily_report_service
            from ..services.wechat_work_message_service import wechat_work_message_service
            from ..models.store import Store
            from ..models.user import User, UserRole
            from ..core.database import get_db_session
            from sqlalchemy import select

            # 解析日期
            target_date = (
                datetime.strptime(report_date, "%Y-%m-%d").date()
                if report_date
                else date.today() - timedelta(days=1)
            )

            logger.info(
                "开始生成营业日报",
                store_id=store_id,
                report_date=str(target_date)
            )

            # 获取要生成报告的门店列表
            async with get_db_session() as session:
                if store_id:
                    result = await session.execute(
                        select(Store).where(Store.id == store_id, Store.is_active == True)
                    )
                else:
                    result = await session.execute(
                        select(Store).where(Store.is_active == True)
                    )
                stores = result.scalars().all()

            total_sent = 0
            for store in stores:
                try:
                    # 1. 生成日报
                    report = await daily_report_service.generate_daily_report(
                        store_id=str(store.id),
                        report_date=target_date
                    )

                    # 2. 构建推送消息
                    message = f"""【营业日报】{target_date.strftime('%Y年%m月%d日')}
门店：{store.name}（{store.id}）

{report.summary}

📊 详细数据：
• 订单数：{report.order_count}笔
• 客流量：{report.customer_count}人
• 客单价：¥{report.avg_order_value / 100:.2f}

📈 运营指标：
• 任务完成率：{report.task_completion_rate:.1f}%
• 库存预警：{report.inventory_alert_count}个
"""

                    if report.highlights:
                        message += "\n✨ 今日亮点：\n"
                        for highlight in report.highlights:
                            message += f"• {highlight}\n"

                    if report.alerts:
                        message += "\n⚠️ 需要关注：\n"
                        for alert in report.alerts:
                            message += f"• {alert}\n"

                    # 3. 查询店长和管理员，发送推送
                    async with get_db_session() as session:
                        mgr_result = await session.execute(
                            select(User).where(
                                User.store_id == store.id,
                                User.is_active == True,
                                User.role.in_([UserRole.STORE_MANAGER, UserRole.ADMIN]),
                                User.wechat_user_id.isnot(None)
                            )
                        )
                        managers = mgr_result.scalars().all()

                    sent_count = 0
                    for manager in managers:
                        try:
                            send_result = await wechat_work_message_service.send_text_message(
                                user_id=manager.wechat_user_id,
                                content=message
                            )
                            if send_result.get("success"):
                                sent_count += 1
                        except Exception as send_err:
                            logger.error(
                                "发送日报失败",
                                user_id=str(manager.id),
                                error=str(send_err)
                            )

                    # 4. 标记为已发送
                    if sent_count > 0:
                        await daily_report_service.mark_as_sent(report.id)

                    logger.info(
                        "营业日报生成并发送完成",
                        store_id=str(store.id),
                        report_date=str(target_date),
                        sent_count=sent_count
                    )
                    total_sent += sent_count

                except Exception as store_err:
                    logger.error(
                        "门店日报生成失败",
                        store_id=str(store.id),
                        error=str(store_err)
                    )
                    continue

            logger.info(
                "所有门店营业日报生成完成",
                stores_processed=len(stores),
                total_sent=total_sent,
                report_date=str(target_date)
            )

            return {
                "success": True,
                "stores_processed": len(stores),
                "total_sent": total_sent,
                "report_date": str(target_date),
            }

        except Exception as e:
            logger.error(
                "生成营业日报失败",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            raise self.retry(exc=e)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_LONG", "300")),  # 5分钟
)
def perform_daily_reconciliation(
    self,
    store_id: str,
    reconciliation_date: str = None,
) -> Dict[str, Any]:
    """
    执行每日对账

    Args:
        store_id: 门店ID
        reconciliation_date: 对账日期（YYYY-MM-DD格式，默认为昨天）

    Returns:
        对账结果
    """
    async def _run():
        try:
            from datetime import date, datetime
            from ..services.reconcile_service import reconcile_service

            logger.info(
                "开始执行每日对账",
                store_id=store_id,
                reconciliation_date=reconciliation_date
            )

            # 解析日期
            if reconciliation_date:
                target_date = datetime.strptime(reconciliation_date, "%Y-%m-%d").date()
            else:
                from datetime import timedelta
                target_date = date.today() - timedelta(days=1)

            # 执行对账
            record = await reconcile_service.perform_reconciliation(
                store_id=store_id,
                reconciliation_date=target_date
            )

            logger.info(
                "每日对账完成",
                store_id=store_id,
                reconciliation_date=str(target_date),
                status=record.status.value,
                diff_ratio=record.diff_ratio
            )

            return {
                "success": True,
                "store_id": store_id,
                "reconciliation_date": str(target_date),
                "record_id": str(record.id),
                "status": record.status.value,
                "diff_ratio": record.diff_ratio,
                "alert_sent": record.alert_sent
            }

        except Exception as e:
            logger.error(
                "执行每日对账失败",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            raise self.retry(exc=e)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
)
def detect_revenue_anomaly(
    self,
    store_id: str = None,
) -> Dict[str, Any]:
    """
    检测营收异常 (每15分钟执行)

    Args:
        store_id: 门店ID (None表示检测所有门店)

    Returns:
        检测结果
    """
    async def _run():
        try:
            from datetime import datetime, timedelta, date
            from ..agents.decision_agent import DecisionAgent
            from ..services.wechat_alert_service import wechat_alert_service
            from ..models.store import Store
            from ..models.user import User, UserRole
            from ..models.order import Order, OrderStatus
            from ..core.database import get_db_session
            from sqlalchemy import select, func

            logger.info(
                "开始检测营收异常",
                store_id=store_id
            )

            decision_agent = DecisionAgent()
            alerts_sent = 0

            # 获取要检测的门店列表
            async with get_db_session() as session:
                if store_id:
                    result = await session.execute(
                        select(Store).where(Store.id == store_id, Store.is_active == True)
                    )
                    stores = result.scalars().all()
                else:
                    result = await session.execute(
                        select(Store).where(Store.is_active == True)
                    )
                    stores = result.scalars().all()

                for store in stores:
                    try:
                        now = datetime.now()
                        today_start = datetime.combine(date.today(), datetime.min.time())

                        # 当前营收：今天到目前为止已完成/已上菜的订单
                        rev_result = await session.execute(
                            select(func.coalesce(func.sum(Order.final_amount), 0)).where(
                                Order.store_id == store.id,
                                Order.order_time >= today_start,
                                Order.order_time <= now,
                                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED])
                            )
                        )
                        current_revenue = float(rev_result.scalar() or 0) / 100

                        # 预期营收：过去4周同星期同时段的平均值
                        current_elapsed = timedelta(hours=now.hour, minutes=now.minute)
                        expected_samples = []
                        for weeks_ago in range(1, 5):
                            past_date = date.today() - timedelta(weeks=weeks_ago)
                            past_start = datetime.combine(past_date, datetime.min.time())
                            past_end = past_start + current_elapsed
                            past_rev = await session.execute(
                                select(func.coalesce(func.sum(Order.final_amount), 0)).where(
                                    Order.store_id == store.id,
                                    Order.order_time >= past_start,
                                    Order.order_time <= past_end,
                                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED])
                                )
                            )
                            val = float(past_rev.scalar() or 0) / 100
                            if val > 0:
                                expected_samples.append(val)

                        if not expected_samples:
                            # 无历史数据，跳过本门店
                            logger.debug("无历史营收数据，跳过", store_id=str(store.id))
                            continue

                        expected_revenue = sum(expected_samples) / len(expected_samples)

                        # 计算偏差
                        deviation = ((current_revenue - expected_revenue) / expected_revenue) * 100

                        # 只有偏差超过阈值才告警
                        if abs(deviation) > float(os.getenv("REVENUE_ANOMALY_THRESHOLD_PERCENT", "15")):
                            # 使用DecisionAgent分析
                            analysis = await decision_agent.analyze_revenue_anomaly(
                                store_id=str(store.id),
                                current_revenue=current_revenue,
                                expected_revenue=expected_revenue,
                                time_period="today"
                            )

                            if analysis["success"]:
                                # 查询店长和管理员的企微ID
                                user_result = await session.execute(
                                    select(User).where(
                                        User.store_id == store.id,
                                        User.is_active == True,
                                        User.role.in_([UserRole.STORE_MANAGER, UserRole.ADMIN]),
                                        User.wechat_user_id.isnot(None)
                                    )
                                )
                                managers = user_result.scalars().all()
                                recipient_ids = [m.wechat_user_id for m in managers]

                                if recipient_ids:
                                    # 使用WeChatAlertService发送告警
                                    alert_result = await wechat_alert_service.send_revenue_alert(
                                        store_id=str(store.id),
                                        store_name=store.name,
                                        current_revenue=current_revenue,
                                        expected_revenue=expected_revenue,
                                        deviation=deviation,
                                        analysis=analysis['data']['analysis'],
                                        recipient_ids=recipient_ids
                                    )

                                    if alert_result.get("success"):
                                        alerts_sent += alert_result.get("sent_count", 0)
                                        logger.info(
                                            "营收异常告警已发送",
                                            store_id=str(store.id),
                                            deviation=deviation,
                                            sent_count=alert_result.get("sent_count")
                                        )
                                else:
                                    logger.warning(
                                        "无可用接收人",
                                        store_id=str(store.id)
                                    )

                    except Exception as e:
                        logger.error(
                            "门店营收异常检测失败",
                            store_id=str(store.id),
                            error=str(e)
                        )
                        continue

            logger.info(
                "营收异常检测完成",
                stores_checked=len(stores),
                alerts_sent=alerts_sent
            )

            return {
                "success": True,
                "stores_checked": len(stores),
                "alerts_sent": alerts_sent,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(
                "营收异常检测失败",
                error=str(e),
                exc_info=e
            )
            raise self.retry(exc=e)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_LONG", "300")),
)
def generate_daily_report_with_rag(
    self,
    store_id: str = None,
) -> Dict[str, Any]:
    """
    生成并发送昨日简报 (RAG增强版，每天6AM执行)

    Args:
        store_id: 门店ID (None表示为所有门店生成)

    Returns:
        生成结果
    """
    async def _run():
        try:
            from datetime import datetime, date, timedelta
            from ..agents.decision_agent import DecisionAgent
            from ..services.wechat_work_message_service import wechat_work_message_service
            from ..models.store import Store
            from ..core.database import get_db_session
            from sqlalchemy import select

            logger.info(
                "开始生成昨日简报(RAG增强)",
                store_id=store_id
            )

            decision_agent = DecisionAgent()
            reports_sent = 0
            yesterday = date.today() - timedelta(days=1)

            # 获取要生成报告的门店列表
            async with get_db_session() as session:
                if store_id:
                    result = await session.execute(
                        select(Store).where(Store.id == store_id, Store.is_active == True)
                    )
                    stores = result.scalars().all()
                else:
                    result = await session.execute(
                        select(Store).where(Store.is_active == True)
                    )
                    stores = result.scalars().all()

                for store in stores:
                    try:
                        # 使用DecisionAgent生成经营建议
                        recommendations = await decision_agent.generate_business_recommendations(
                            store_id=str(store.id),
                            focus_area=None  # 全面分析
                        )

                        if recommendations["success"]:
                            # 构建简报消息
                            message = f"""📊 昨日简报 {yesterday.strftime('%Y年%m月%d日')}

    门店: {store.name}

    AI经营分析:
    {recommendations['data']['recommendations']}

    ---
    基于{recommendations['data']['context_used']}条历史数据分析
    生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    """

                            # 查询店长和管理员的企微ID并发送
                            from ..models.user import User, UserRole
                            user_result = await session.execute(
                                select(User).where(
                                    User.store_id == store.id,
                                    User.is_active == True,
                                    User.role.in_([UserRole.STORE_MANAGER, UserRole.ADMIN]),
                                    User.wechat_user_id.isnot(None)
                                )
                            )
                            managers = user_result.scalars().all()
                            sent_count = 0
                            for manager in managers:
                                try:
                                    send_result = await wechat_work_message_service.send_text_message(
                                        user_id=manager.wechat_user_id,
                                        content=message
                                    )
                                    if send_result.get("success"):
                                        sent_count += 1
                                except Exception as send_err:
                                    logger.error(
                                        "发送简报失败",
                                        user_id=str(manager.id),
                                        error=str(send_err)
                                    )

                            logger.info(
                                "昨日简报已生成并发送",
                                store_id=str(store.id),
                                sent_count=sent_count
                            )
                            reports_sent += sent_count

                    except Exception as e:
                        logger.error(
                            "门店简报生成失败",
                            store_id=str(store.id),
                            error=str(e)
                        )
                        continue

            logger.info(
                "昨日简报生成完成",
                stores_processed=len(stores),
                reports_sent=reports_sent
            )

            return {
                "success": True,
                "stores_processed": len(stores),
                "reports_sent": reports_sent,
                "report_date": str(yesterday),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(
                "昨日简报生成失败",
                error=str(e),
                exc_info=e
            )
            raise self.retry(exc=e)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
)
def check_inventory_alert(
    self,
    store_id: str = None,
) -> Dict[str, Any]:
    """
    检查库存预警 (午高峰前1小时，每天10AM执行)

    Args:
        store_id: 门店ID (None表示检查所有门店)

    Returns:
        检查结果
    """
    async def _run():
        try:
            from datetime import datetime
            from ..agents.inventory_agent import InventoryAgent
            from ..services.wechat_alert_service import wechat_alert_service
            from ..models.store import Store
            from ..models.user import User, UserRole
            from ..models.inventory import InventoryItem, InventoryStatus
            from ..core.database import get_db_session
            from sqlalchemy import select

            logger.info(
                "开始检查库存预警",
                store_id=store_id
            )

            inventory_agent = InventoryAgent()
            alerts_sent = 0

            # 获取要检查的门店列表
            async with get_db_session() as session:
                if store_id:
                    result = await session.execute(
                        select(Store).where(Store.id == store_id, Store.is_active == True)
                    )
                    stores = result.scalars().all()
                else:
                    result = await session.execute(
                        select(Store).where(Store.is_active == True)
                    )
                    stores = result.scalars().all()

                for store in stores:
                    try:
                        # 从数据库查询低库存/缺货库存项
                        inv_result = await session.execute(
                            select(InventoryItem).where(
                                InventoryItem.store_id == store.id,
                                InventoryItem.status.in_([
                                    InventoryStatus.LOW,
                                    InventoryStatus.CRITICAL,
                                    InventoryStatus.OUT_OF_STOCK,
                                ])
                            )
                        )
                        low_stock_items = inv_result.scalars().all()

                        if not low_stock_items:
                            logger.debug("无库存预警项", store_id=str(store.id))
                            continue

                        # 构建 InventoryAgent 所需的 current_inventory 字典
                        current_inventory = {
                            item.id: item.current_quantity for item in low_stock_items
                        }

                        # 使用InventoryAgent检查低库存
                        alert_result = await inventory_agent.check_low_stock_alert(
                            store_id=str(store.id),
                            current_inventory=current_inventory,
                            threshold_hours=int(os.getenv("INVENTORY_ALERT_THRESHOLD_HOURS", "4"))  # 午高峰前N小时预警
                        )

                        if alert_result["success"]:
                            # 构建预警项目列表（来自真实数据）
                            alert_items = [
                                {
                                    "dish_name": item.name,
                                    "quantity": item.current_quantity,
                                    "unit": item.unit or "",
                                    "min_quantity": item.min_quantity,
                                    "risk": "high" if item.status in (
                                        InventoryStatus.CRITICAL, InventoryStatus.OUT_OF_STOCK
                                    ) else "medium",
                                }
                                for item in low_stock_items
                            ]

                            # 查询店长和管理员的企微ID
                            user_result = await session.execute(
                                select(User).where(
                                    User.store_id == store.id,
                                    User.is_active == True,
                                    User.role.in_([UserRole.STORE_MANAGER, UserRole.ADMIN]),
                                    User.wechat_user_id.isnot(None)
                                )
                            )
                            managers = user_result.scalars().all()
                            recipient_ids = [m.wechat_user_id for m in managers]

                            if recipient_ids:
                                # 使用WeChatAlertService发送预警
                                send_result = await wechat_alert_service.send_inventory_alert(
                                    store_id=str(store.id),
                                    store_name=store.name,
                                    alert_items=alert_items,
                                    analysis=alert_result['data']['alert'],
                                    recipient_ids=recipient_ids
                                )

                                if send_result.get("success"):
                                    alerts_sent += send_result.get("sent_count", 0)
                                    logger.info(
                                        "库存预警已发送",
                                        store_id=str(store.id),
                                        sent_count=send_result.get("sent_count")
                                    )
                            else:
                                logger.warning(
                                    "无可用接收人",
                                    store_id=str(store.id)
                                )

                    except Exception as e:
                        logger.error(
                            "门店库存检查失败",
                            store_id=str(store.id),
                            error=str(e)
                        )
                        continue

            logger.info(
                "库存预警检查完成",
                stores_checked=len(stores),
                alerts_sent=alerts_sent
            )

            return {
                "success": True,
                "stores_checked": len(stores),
                "alerts_sent": alerts_sent,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(
                "库存预警检查失败",
                error=str(e),
                exc_info=e
            )
            raise self.retry(exc=e)

    return asyncio.run(_run())


# ------------------------------------------------------------------ #
# 大数据异步导出任务                                                    #
# ------------------------------------------------------------------ #

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="async_export_data",
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
)
def async_export_data(self, job_id: str) -> Dict[str, Any]:
    """
    异步大数据导出任务

    从数据库分批读取数据，生成 CSV/Excel 文件，
    并将结果写入临时目录，更新 ExportJob 状态。
    """
    import csv
    import tempfile
    from datetime import datetime, date

    async def _run():
        from src.core.database import AsyncSessionLocal
        from src.models.export_job import ExportJob, ExportStatus
        from sqlalchemy import select, and_

        BATCH_SIZE = int(os.getenv("EXPORT_BATCH_SIZE", "1000"))

        async with AsyncSessionLocal() as session:
            job = await session.get(ExportJob, job_id)
            if not job:
                logger.error("导出任务不存在", job_id=job_id)
                return {"success": False, "error": "job not found"}
            job.status = ExportStatus.RUNNING
            job.celery_task_id = self.request.id
            await session.commit()
            job_type = job.job_type
            fmt = job.format
            params = job.params or {}

        try:
            rows, headers = await _fetch_export_data(job_type, params)

            total = len(rows)
            tmp_dir = os.getenv("EXPORT_TMP_DIR", tempfile.gettempdir())
            os.makedirs(tmp_dir, exist_ok=True)
            filename = f"export_{job_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{fmt}"
            file_path = os.path.join(tmp_dir, filename)

            if fmt == "csv":
                file_size = _write_csv(file_path, headers, rows)
            elif fmt == "xlsx":
                file_size = _write_xlsx(file_path, headers, rows)
            else:
                raise ValueError(f"不支持的格式: {fmt}")

            async with AsyncSessionLocal() as session:
                job = await session.get(ExportJob, job_id)
                if job:
                    job.status = ExportStatus.COMPLETED
                    job.progress = 100
                    job.total_rows = total
                    job.processed_rows = total
                    job.file_path = file_path
                    job.file_size_bytes = file_size
                    job.completed_at = datetime.utcnow().isoformat()
                    await session.commit()

            logger.info("导出任务完成", job_id=job_id, total_rows=total)
            return {"success": True, "job_id": job_id, "total_rows": total}

        except Exception as e:
            logger.error("导出任务失败", job_id=job_id, error=str(e))
            async with AsyncSessionLocal() as session:
                job = await session.get(ExportJob, job_id)
                if job:
                    job.status = ExportStatus.FAILED
                    job.error_message = str(e)
                    await session.commit()
            raise self.retry(exc=e)

    async def _fetch_export_data(job_type: str, params: Dict):
        from src.core.database import AsyncSessionLocal
        from sqlalchemy import select, and_
        from datetime import datetime, date

        if job_type == "transactions":
            from src.models.finance import FinancialTransaction
            headers = ["日期", "类型", "分类", "子分类", "金额(元)", "描述", "支付方式", "门店ID"]
            async with AsyncSessionLocal() as session:
                conditions = []
                if params.get("store_id"):
                    conditions.append(FinancialTransaction.store_id == params["store_id"])
                if params.get("transaction_type"):
                    conditions.append(FinancialTransaction.transaction_type == params["transaction_type"])
                if params.get("start_date"):
                    conditions.append(FinancialTransaction.transaction_date >= date.fromisoformat(params["start_date"]))
                if params.get("end_date"):
                    conditions.append(FinancialTransaction.transaction_date <= date.fromisoformat(params["end_date"]))
                stmt = select(FinancialTransaction)
                if conditions:
                    stmt = stmt.where(and_(*conditions))
                stmt = stmt.order_by(FinancialTransaction.transaction_date.desc())
                result = await session.execute(stmt)
                rows = [
                    [t.transaction_date.isoformat() if t.transaction_date else "",
                     t.transaction_type or "", t.category or "", t.subcategory or "",
                     round((t.amount or 0) / 100, 2), t.description or "",
                     t.payment_method or "", t.store_id or ""]
                    for t in result.scalars().all()
                ]
            return rows, headers

        elif job_type == "audit_logs":
            from src.models.audit_log import AuditLog
            headers = ["时间", "用户ID", "用户名", "角色", "操作", "资源类型", "资源ID", "描述", "IP", "状态", "门店ID"]
            async with AsyncSessionLocal() as session:
                conditions = []
                if params.get("user_id"):
                    conditions.append(AuditLog.user_id == params["user_id"])
                if params.get("action"):
                    conditions.append(AuditLog.action == params["action"])
                if params.get("store_id"):
                    conditions.append(AuditLog.store_id == params["store_id"])
                if params.get("start_date"):
                    conditions.append(AuditLog.created_at >= datetime.fromisoformat(params["start_date"]))
                if params.get("end_date"):
                    conditions.append(AuditLog.created_at <= datetime.fromisoformat(params["end_date"]))
                stmt = select(AuditLog)
                if conditions:
                    stmt = stmt.where(and_(*conditions))
                stmt = stmt.order_by(AuditLog.created_at.desc())
                result = await session.execute(stmt)
                rows = [
                    [log.created_at.isoformat() if log.created_at else "",
                     str(log.user_id) if log.user_id else "", log.username or "",
                     log.user_role or "", log.action or "", log.resource_type or "",
                     str(log.resource_id) if log.resource_id else "", log.description or "",
                     log.ip_address or "", log.status or "",
                     str(log.store_id) if log.store_id else ""]
                    for log in result.scalars().all()
                ]
            return rows, headers

        elif job_type == "orders":
            from src.models.order import Order
            headers = ["订单号", "状态", "总金额(元)", "桌号", "门店ID", "下单时间"]
            async with AsyncSessionLocal() as session:
                conditions = []
                if params.get("store_id"):
                    conditions.append(Order.store_id == params["store_id"])
                if params.get("status"):
                    conditions.append(Order.status == params["status"])
                if params.get("start_date"):
                    conditions.append(Order.created_at >= datetime.fromisoformat(params["start_date"]))
                if params.get("end_date"):
                    conditions.append(Order.created_at <= datetime.fromisoformat(params["end_date"]))
                stmt = select(Order)
                if conditions:
                    stmt = stmt.where(and_(*conditions))
                stmt = stmt.order_by(Order.created_at.desc())
                result = await session.execute(stmt)
                rows = [
                    [o.order_number or str(o.id),
                     o.status.value if hasattr(o.status, "value") else str(o.status or ""),
                     round((o.total_amount or 0) / 100, 2),
                     o.table_number or "", o.store_id or "",
                     o.created_at.isoformat() if o.created_at else ""]
                    for o in result.scalars().all()
                ]
            return rows, headers

        else:
            raise ValueError(f"不支持的导出类型: {job_type}，可选: transactions/audit_logs/orders")

    def _write_csv(file_path: str, headers: list, rows: list) -> int:
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        return os.path.getsize(file_path)

    def _write_xlsx(file_path: str, headers: list, rows: list) -> int:
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise ImportError("请安装 openpyxl: pip install openpyxl")
        wb = openpyxl.Workbook()
        ws = wb.active
        hf = Font(bold=True, color="FFFFFF")
        hfill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
        for ci, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=ci, value=h)
            c.font = hf
            c.fill = hfill
            ws.column_dimensions[get_column_letter(ci)].width = 16
        for ri, row in enumerate(rows, 2):
            for ci, v in enumerate(row, 1):
                ws.cell(row=ri, column=ci, value=v)
        wb.save(file_path)
        return os.path.getsize(file_path)

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# 增量备份任务
# ---------------------------------------------------------------------------

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="run_backup",
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
)
def run_backup(self, job_id: str) -> Dict[str, Any]:
    """
    执行全量/增量备份任务
    - 全量：导出所有指定表的数据为 JSON，打包成 tar.gz
    - 增量：仅导出 since_timestamp 之后有变更的行（依赖 updated_at 字段）
    """
    import hashlib
    import json
    import tarfile
    import tempfile
    from datetime import datetime, timezone

    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text

        db_url = os.environ["DATABASE_URL"]
        backup_dir = os.getenv("BACKUP_TMP_DIR", "/tmp/backups")
        os.makedirs(backup_dir, exist_ok=True)

        engine = create_async_engine(db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # 读取 BackupJob
            from src.models.backup_job import BackupJob, BackupStatus
            result = await session.execute(
                text("SELECT * FROM backup_jobs WHERE id = :id"),
                {"id": job_id},
            )
            row = result.mappings().first()
            if not row:
                raise ValueError(f"BackupJob {job_id} 不存在")

            backup_type = row["backup_type"]
            since_ts = row["since_timestamp"]
            tables_filter = row["tables"] or []

            # 标记 RUNNING
            await session.execute(
                text("UPDATE backup_jobs SET status='running', celery_task_id=:tid, updated_at=NOW() WHERE id=:id"),
                {"tid": self.request.id, "id": job_id},
            )
            await session.commit()

        # 获取所有用户表
        async with async_session() as session:
            res = await session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            )
            all_tables = [r[0] for r in res.fetchall()]

        target_tables = [t for t in all_tables if not tables_filter or t in tables_filter]
        # 排除备份相关表，避免递归
        target_tables = [t for t in target_tables if t not in ("backup_jobs", "export_jobs")]

        total = len(target_tables)
        row_counts: Dict[str, int] = {}
        tmp_dir = tempfile.mkdtemp(dir=backup_dir)

        try:
            for idx, table in enumerate(target_tables):
                async with async_session() as session:
                    # 表名来自 pg_tables（系统目录）+ tables_filter（用户可控），
                    # 必须通过白名单校验后才能拼入 SQL（表名无法参数化）
                    if not _SAFE_TABLE_RE.match(table):
                        logger.warning("backup.skip_unsafe_table", table=table)
                        row_counts[table] = 0
                        continue
                    if backup_type == "incremental" and since_ts:
                        # 增量：只取 updated_at > since_timestamp 的行
                        try:
                            res = await session.execute(
                                text(f"SELECT * FROM {table} WHERE updated_at > :ts"),
                                {"ts": since_ts},
                            )
                        except Exception:
                            # 表没有 updated_at 字段时跳过
                            row_counts[table] = 0
                            continue
                    else:
                        res = await session.execute(text(f"SELECT * FROM {table}"))

                    cols = list(res.keys())
                    rows_data = [dict(zip(cols, r)) for r in res.fetchall()]

                    # 序列化（UUID/datetime 转字符串）
                    def _serialize(v):
                        if hasattr(v, "isoformat"):
                            return v.isoformat()
                        if hasattr(v, "__str__") and not isinstance(v, (int, float, bool, str, type(None))):
                            return str(v)
                        return v

                    rows_data = [{k: _serialize(v) for k, v in r.items()} for r in rows_data]
                    row_counts[table] = len(rows_data)

                    table_file = os.path.join(tmp_dir, f"{table}.json")
                    with open(table_file, "w", encoding="utf-8") as f:
                        json.dump({"table": table, "rows": rows_data}, f, ensure_ascii=False, indent=2)

                # 更新进度
                progress = int((idx + 1) / total * 90)
                async with async_session() as session:
                    await session.execute(
                        text("UPDATE backup_jobs SET progress=:p, updated_at=NOW() WHERE id=:id"),
                        {"p": progress, "id": job_id},
                    )
                    await session.commit()

            # 打包 tar.gz
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            archive_name = f"backup_{backup_type}_{ts_str}_{job_id[:8]}.tar.gz"
            archive_path = os.path.join(backup_dir, archive_name)
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(tmp_dir, arcname="backup")

            # 计算 SHA256
            sha256 = hashlib.sha256()
            with open(archive_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()
            file_size = os.path.getsize(archive_path)
            completed_at = datetime.now(timezone.utc).isoformat()

            async with async_session() as session:
                await session.execute(
                    text(
                        "UPDATE backup_jobs SET status='completed', progress=100, "
                        "file_path=:fp, file_size_bytes=:fs, checksum=:cs, "
                        "row_counts=:rc, completed_at=:ca, updated_at=NOW() WHERE id=:id"
                    ),
                    {
                        "fp": archive_path,
                        "fs": file_size,
                        "cs": checksum,
                        "rc": json.dumps(row_counts),
                        "ca": completed_at,
                        "id": job_id,
                    },
                )
                await session.commit()

            logger.info("备份任务完成", job_id=job_id, archive=archive_path, checksum=checksum)
            return {"job_id": job_id, "file_path": archive_path, "checksum": checksum}

        except Exception as e:
            logger.error("备份任务失败", job_id=job_id, error=str(e))
            async with async_session() as session:
                await session.execute(
                    text("UPDATE backup_jobs SET status='failed', error_message=:err, updated_at=NOW() WHERE id=:id"),
                    {"err": str(e)[:1000], "id": job_id},
                )
                await session.commit()
            raise self.retry(exc=e)

        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return asyncio.run(_run())


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_LONG", "300")),
)
def generate_daily_hub(
    self,
    store_id: str = None,
) -> Dict[str, Any]:
    """
    生成 T+1 经营统筹备战板

    Args:
        store_id: 门店ID (None 表示为所有活跃门店生成)

    Returns:
        生成结果
    """
    async def _run():
        from datetime import date, timedelta
        from ..services.daily_hub_service import daily_hub_service
        from ..models.store import Store
        from ..core.database import get_db_session
        from sqlalchemy import select

        target_date = date.today() + timedelta(days=1)

        async with get_db_session() as session:
            if store_id:
                result = await session.execute(
                    select(Store).where(Store.id == store_id, Store.is_active == True)
                )
            else:
                result = await session.execute(
                    select(Store).where(Store.is_active == True)
                )
            stores = result.scalars().all()

        generated = 0
        for store in stores:
            try:
                await daily_hub_service.generate_battle_board(
                    store_id=str(store.id), target_date=target_date
                )
                generated += 1
                logger.info("备战板生成成功", store_id=str(store.id), target_date=str(target_date))
            except Exception as e:
                logger.error("备战板生成失败", store_id=str(store.id), error=str(e))

        return {"success": True, "generated": generated, "target_date": str(target_date)}

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — 损耗推理 / 规则评估 / 本体日同步
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="tasks.process_waste_event",
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_waste_event(
    self,
    event_id: str,
) -> Dict[str, Any]:
    """
    损耗事件五步推理（异步，由 WasteEventService._enqueue_analysis 投递）

    步骤：
      1. 从 PostgreSQL 加载 WasteEvent
      2. 调用 WasteReasoningEngine.infer_root_cause(event_id)
      3. 将根因 / 置信度 / 证据链回写 PostgreSQL
      4. 同步推理结论到 Neo4j

    Args:
        event_id: WasteEvent.event_id（格式 WE-XXXXXXXX）

    Returns:
        {"success": True, "event_id": ..., "root_cause": ..., "confidence": ...}
    """
    async def _run():
        from ..core.database import get_db_session
        from ..services.waste_event_service import WasteEventService

        async with get_db_session() as session:
            svc = WasteEventService(session)

            # 标记推理中
            from sqlalchemy import update as _update
            from ..models.waste_event import WasteEvent, WasteEventStatus
            await session.execute(
                _update(WasteEvent)
                .where(WasteEvent.event_id == event_id)
                .values(status=WasteEventStatus.ANALYZING)
            )
            await session.commit()

        # 调用推理引擎（同步驱动，独立 session）
        try:
            from ..ontology.reasoning import WasteReasoningEngine
            engine = WasteReasoningEngine()
            result = engine.infer_root_cause(event_id)
        except Exception as e:
            logger.warning("推理引擎调用失败", event_id=event_id, error=str(e))
            return {"success": False, "event_id": event_id, "error": str(e)}

        if not result.get("success"):
            return {"success": False, "event_id": event_id, "error": result.get("error")}

        # 写回分析结论
        async with get_db_session() as session:
            svc = WasteEventService(session)
            await svc.write_back_analysis(
                event_id=event_id,
                root_cause=result.get("root_cause", "unknown"),
                confidence=result.get("confidence", 0.0),
                evidence=result.get("evidence_chain", {}),
                scores=result.get("scores", {}),
            )
            # 同步到 Neo4j
            ev = await svc.get_event(event_id)
            if ev:
                await svc._sync_analysis_to_neo4j(ev)
            await session.commit()

        logger.info(
            "损耗推理任务完成",
            event_id=event_id,
            root_cause=result.get("root_cause"),
            confidence=result.get("confidence"),
        )
        return {
            "success": True,
            "event_id": event_id,
            "root_cause": result.get("root_cause"),
            "confidence": result.get("confidence"),
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


# ═══════════════════════════════════════════════════════════════════════════════
# L3 — 跨店知识聚合夜间物化（凌晨 2:30 触发）
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="tasks.nightly_cross_store_sync",
    max_retries=2,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=False,
)
def nightly_cross_store_sync(
    self,
    store_ids: list = None,
) -> Dict[str, Any]:
    """
    L3 跨店知识聚合夜间物化任务（建议凌晨 2:30 触发）

    执行步骤：
      1. 计算两两门店相似度矩阵，写入 store_similarity_cache
      2. 重建同伴组 store_peer_groups（tier + region 分组）
      3. 物化昨日 cross_store_metrics（6 项指标 × 全门店）
      4. 同步 Neo4j 图（Store 节点 + SIMILAR_TO / BENCHMARK_OF / SHARES_RECIPE 边）

    Args:
        store_ids: 指定门店列表（None = 全部活跃门店）

    Returns:
        {
          "similarity_pairs":  N,
          "peer_groups":       N,
          "metrics_upserted":  N,
          "graph_synced":      bool,
          "errors":            [...]
        }
    """
    async def _run():
        from ..core.database import get_db_session
        from ..services.cross_store_knowledge_service import CrossStoreKnowledgeService

        errors = []

        async with get_db_session() as session:
            svc = CrossStoreKnowledgeService(session)

            # Step 1: 相似度矩阵
            try:
                sim_result = await svc.compute_pairwise_similarity(store_ids=store_ids)
                similarity_pairs = sim_result.get("pairs_computed", 0)
                logger.info("跨店相似度矩阵已计算", pairs=similarity_pairs)
            except Exception as e:
                errors.append({"step": "similarity", "error": str(e)})
                similarity_pairs = 0
                logger.error("相似度矩阵计算失败", error=str(e))

            # Step 2: 同伴组重建
            try:
                pg_result = await svc.build_peer_groups(store_ids=store_ids)
                peer_groups = pg_result.get("groups_built", 0)
                logger.info("同伴组重建完成", groups=peer_groups)
            except Exception as e:
                errors.append({"step": "peer_groups", "error": str(e)})
                peer_groups = 0
                logger.error("同伴组重建失败", error=str(e))

            # Step 3: 日维度指标物化
            try:
                mat_result = await svc.materialize_metrics(store_ids=store_ids)
                metrics_upserted = mat_result.get("upserted", 0)
                logger.info("跨店指标物化完成", upserted=metrics_upserted)
            except Exception as e:
                errors.append({"step": "materialize", "error": str(e)})
                metrics_upserted = 0
                logger.error("指标物化失败", error=str(e))

            await session.commit()

            # Step 4: Neo4j 图同步（独立异常处理，不影响前序结果）
            graph_synced = False
            try:
                graph_result = await svc.sync_store_graph(store_ids=store_ids)
                graph_synced = not graph_result.get("skipped", False)
                logger.info("Neo4j 跨店图同步完成", result=graph_result)
            except Exception as e:
                errors.append({"step": "graph_sync", "error": str(e)})
                logger.error("Neo4j 跨店图同步失败", error=str(e))

        logger.info(
            "L3 跨店知识聚合夜间任务完成",
            similarity_pairs=similarity_pairs,
            peer_groups=peer_groups,
            metrics_upserted=metrics_upserted,
            graph_synced=graph_synced,
            errors=len(errors),
        )
        return {
            "success":          len(errors) == 0,
            "similarity_pairs": similarity_pairs,
            "peer_groups":      peer_groups,
            "metrics_upserted": metrics_upserted,
            "graph_synced":     graph_synced,
            "errors":           errors,
        }

    try:
        return asyncio.run(_run())
    except Exception as nightly_e:
        raise self.retry(exc=nightly_e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="tasks.evaluate_store_rules",
    max_retries=2,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def evaluate_store_rules(
    self,
    store_id: str,
    kpi_context: Dict[str, Any],
    industry_type: str = "general",
) -> Dict[str, Any]:
    """
    对门店 KPI 上下文运行推理规则库，匹配触发规则并自动推送企微告警

    工作流程：
      1. 从规则库加载 ACTIVE 规则
      2. 对 kpi_context 执行规则匹配，获取 Top-10 匹配规则
      3. 对命中规则写入 RuleExecution 日志
      4. 置信度 >= 0.70 时，自动创建企微 P1/P2 Action
      5. 行业基准对比（若 industry_type 非 "general"）

    Args:
        store_id: 门店ID
        kpi_context: 当前 KPI 指标字典，如
            {"waste_rate": 0.18, "labor_cost_ratio": 0.36, ...}
        industry_type: 行业类型（seafood / hotpot / fastfood / general）

    Returns:
        {"matched": [...], "actions_created": N, "store_id": ...}
    """
    async def _run():
        from ..core.database import get_db_session
        from ..services.knowledge_rule_service import KnowledgeRuleService

        matched_rules = []
        actions_created = 0

        async with get_db_session() as session:
            rule_svc = KnowledgeRuleService(session)

            # 规则匹配（全品类）
            matched = await rule_svc.match_rules(kpi_context)

            for hit in matched:
                matched_rules.append(hit)

                # 写入执行日志
                rule_obj = await rule_svc.get_by_code(hit["rule_code"])
                if rule_obj:
                    await rule_svc.log_execution(
                        rule=rule_obj,
                        store_id=store_id,
                        event_id=None,
                        condition_values=kpi_context,
                        conclusion_output=hit.get("conclusion", {}),
                        confidence_score=hit["confidence"],
                    )

                # 置信度 ≥ 0.70 → 推送企微告警
                if hit["confidence"] >= 0.70:
                    try:
                        from ..services.wechat_action_fsm import (
                            ActionCategory,
                            ActionPriority,
                            get_wechat_fsm,
                        )
                        fsm = get_wechat_fsm()
                        priority = (
                            ActionPriority.P1 if hit["confidence"] >= 0.80
                            else ActionPriority.P2
                        )
                        conclusion = hit.get("conclusion", {})
                        action_text = (
                            conclusion.get("action") or
                            conclusion.get("conclusion", "请检查相关指标")
                        )
                        await fsm.create_action(
                            store_id=store_id,
                            category=ActionCategory.KPI_ALERT,
                            priority=priority,
                            title=f"规则告警：{hit['rule_code']}",
                            content=(
                                f"**{hit['name']}**\n"
                                f"置信度：{hit['confidence']:.0%}\n"
                                f"建议：{action_text}"
                            ),
                            receiver_user_id="store_manager",
                            source_event_id=f"RULE-{hit['rule_code']}-{store_id}",
                            evidence={"kpi_context": kpi_context, "rule_code": hit["rule_code"]},
                        )
                        actions_created += 1
                    except Exception as e:
                        logger.warning(
                            "规则触发企微告警失败",
                            store_id=store_id,
                            rule_code=hit["rule_code"],
                            error=str(e),
                        )

            # 行业基准对比（非 general 时）
            benchmark_summary = []
            if industry_type != "general":
                benchmark_results = await rule_svc.compare_to_benchmark(
                    industry_type, kpi_context
                )
                for br in benchmark_results:
                    if br["percentile_band"] == "bottom_25":
                        benchmark_summary.append(br)

            await session.commit()

        logger.info(
            "门店规则评估完成",
            store_id=store_id,
            matched=len(matched_rules),
            actions_created=actions_created,
        )
        return {
            "success": True,
            "store_id": store_id,
            "matched": matched_rules,
            "actions_created": actions_created,
            "bottom_25_benchmarks": benchmark_summary,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="tasks.daily_ontology_sync",
    max_retries=2,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=False,
)
def daily_ontology_sync(
    self,
    store_id: str = None,
) -> Dict[str, Any]:
    """
    每日全量 PostgreSQL → Neo4j 本体同步（建议凌晨 3:00 触发）

    范围：
      - 活跃 BOMTemplate 及明细行 → BOM 节点 + HAS_INGREDIENT 边
      - WasteEvent（最近 30 天）→ WasteEvent 节点 + WASTE_OF 边

    Args:
        store_id: 指定门店（None = 全部活跃门店）

    Returns:
        {"synced_stores": N, "nodes_upserted": N, "errors": [...]}
    """
    async def _run():
        from ..core.database import get_db_session
        from ..models.store import Store
        from ..models.bom import BOMTemplate
        from ..models.waste_event import WasteEvent
        from sqlalchemy import select, and_
        from datetime import datetime, timedelta

        synced_stores = 0
        nodes_upserted = 0
        errors = []

        async with get_db_session() as session:
            # 确定要同步的门店
            if store_id:
                stmt = select(Store).where(Store.id == store_id, Store.is_active.is_(True))
            else:
                stmt = select(Store).where(Store.is_active.is_(True))
            result = await session.execute(stmt)
            stores = result.scalars().all()

            for store in stores:
                sid = str(store.id)
                try:
                    # 1. 同步活跃 BOM
                    bom_stmt = (
                        select(BOMTemplate)
                        .where(
                            and_(BOMTemplate.store_id == sid, BOMTemplate.is_active.is_(True))
                        )
                    )
                    bom_result = await session.execute(bom_stmt)
                    active_boms = bom_result.scalars().all()

                    try:
                        from ..ontology.data_sync import OntologyDataSync
                        with OntologyDataSync() as sync:
                            for bom in active_boms:
                                dish_id_str = f"DISH-{bom.dish_id}"
                                sync.upsert_bom(
                                    dish_id=dish_id_str,
                                    version=bom.version,
                                    effective_date=bom.effective_date,
                                    yield_rate=float(bom.yield_rate),
                                    expiry_date=bom.expiry_date,
                                    notes=bom.notes,
                                )
                                nodes_upserted += 1
                    except Exception as neo4j_err:
                        logger.warning("Neo4j BOM 同步失败", store_id=sid, error=str(neo4j_err))

                    # 2. 同步近 30 天 WasteEvent
                    since = datetime.utcnow() - timedelta(days=30)
                    we_stmt = select(WasteEvent).where(
                        and_(
                            WasteEvent.store_id == sid,
                            WasteEvent.occurred_at >= since,
                        )
                    )
                    we_result = await session.execute(we_stmt)
                    events = we_result.scalars().all()

                    from ..services.waste_event_service import WasteEventService
                    svc = WasteEventService(session)
                    for ev in events:
                        try:
                            await svc._sync_to_neo4j(ev)
                            nodes_upserted += 1
                        except Exception as e:
                            logger.warning(
                                "WasteEvent Neo4j 同步失败",
                                event_id=ev.event_id,
                                error=str(e),
                            )

                    synced_stores += 1
                    logger.info(
                        "门店本体同步完成",
                        store_id=sid,
                        boms=len(active_boms),
                        waste_events=len(events),
                    )

                except Exception as e:
                    errors.append({"store_id": sid, "error": str(e)})
                    logger.error("门店本体同步失败", store_id=sid, error=str(e))

        logger.info(
            "日常本体同步完成",
            synced_stores=synced_stores,
            nodes_upserted=nodes_upserted,
            errors=len(errors),
        )
        return {
            "success": True,
            "synced_stores": synced_stores,
            "nodes_upserted": nodes_upserted,
            "errors": errors,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


# ═══════════════════════════════════════════════════════════════════════════════
# L4 — 全平台推理扫描夜间任务（凌晨 3:30 触发）
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="tasks.nightly_reasoning_scan",
    max_retries=2,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=False,
)
def nightly_reasoning_scan(
    self,
    store_ids: list = None,
) -> Dict[str, Any]:
    """
    L4 全平台推理扫描夜间任务（建议凌晨 3:30 触发，在 L3 nightly_cross_store_sync 之后）

    执行步骤：
      1. 从 PostgreSQL 拉取所有活跃门店最近 24h KPI 快照
      2. 调用 DiagnosisService.run_full_diagnosis() 全维度推理
      3. 结论写入 reasoning_reports（upsert，幂等）
      4. 对 P1/P2 报告同步写入 Neo4j ReasoningReport 节点
      5. 置信度 ≥ 0.70 的 P1/P2 告警自动推送企微

    Args:
        store_ids: 指定门店列表（None = 全部活跃门店）

    Returns:
        {
          "stores_scanned":  N,
          "p1_alerts":       N,
          "p2_alerts":       N,
          "wechat_sent":     N,
          "errors":          [...]
        }
    """
    async def _run():
        from ..core.database import get_db_session
        from ..models.store import Store
        from ..services.diagnosis_service import DiagnosisService
        from ..services.reasoning_engine import ALL_DIMENSIONS
        from ..models.reasoning import ReasoningReport
        from sqlalchemy import select, and_, func

        errors = []
        stores_scanned = 0
        p1_count = 0
        p2_count = 0
        wechat_sent = 0

        async with get_db_session() as session:
            # 拉取活跃门店列表
            if store_ids:
                stmt = select(Store).where(
                    and_(Store.id.in_(store_ids), Store.is_active.is_(True))
                )
            else:
                stmt = select(Store).where(Store.is_active.is_(True))
            stores = (await session.execute(stmt)).scalars().all()

            svc = DiagnosisService(session)

            for store in stores:
                sid = str(store.id)
                try:
                    # 构造门店 KPI 快照（从近 30 天 cross_store_metrics 物化数据）
                    kpi_context = await _build_kpi_context(session, sid)
                    if not kpi_context:
                        logger.debug("门店无 KPI 数据，跳过推理", store_id=sid)
                        continue

                    # 全维度诊断
                    report = await svc.run_full_diagnosis(
                        store_id=sid,
                        kpi_context=kpi_context,
                    )
                    stores_scanned += 1

                    # 统计 P1/P2
                    for dim, c in report.dimensions.items():
                        if c.severity == "P1":
                            p1_count += 1
                        elif c.severity == "P2":
                            p2_count += 1

                    # P1/P2 → 同步 Neo4j + 企微推送
                    for dim, c in report.dimensions.items():
                        if c.severity in ("P1", "P2") and c.confidence >= 0.70:
                            # Neo4j 同步
                            try:
                                from ..ontology.data_sync import OntologyDataSync
                                import uuid as _uuid
                                # 查找刚写入的 reasoning_report id
                                from ..models.reasoning import ReasoningReport as RR
                                from datetime import date
                                rr_stmt = select(RR).where(
                                    and_(
                                        RR.store_id    == sid,
                                        RR.report_date == date.today(),
                                        RR.dimension   == dim,
                                    )
                                ).limit(1)
                                rr = (await session.execute(rr_stmt)).scalar_one_or_none()
                                if rr:
                                    with OntologyDataSync() as sync:
                                        sync.upsert_reasoning_report(
                                            report_id=str(rr.id),
                                            store_id=sid,
                                            report_date=rr.report_date.isoformat(),
                                            dimension=dim,
                                            severity=c.severity,
                                            root_cause=c.root_cause,
                                            confidence=c.confidence,
                                            triggered_rules=c.triggered_rules,
                                        )
                            except Exception as neo4j_err:
                                logger.warning(
                                    "Neo4j ReasoningReport 同步失败",
                                    store_id=sid,
                                    error=str(neo4j_err),
                                )

                            # 企微推送
                            try:
                                from ..services.wechat_action_fsm import (
                                    ActionCategory,
                                    ActionPriority,
                                    get_wechat_fsm,
                                )
                                fsm      = get_wechat_fsm()
                                priority = (
                                    ActionPriority.P1
                                    if c.severity == "P1"
                                    else ActionPriority.P2
                                )
                                action_text = (
                                    c.recommended_actions[0]
                                    if c.recommended_actions
                                    else "请查看推理报告并采取行动"
                                )
                                await fsm.create_action(
                                    store_id=sid,
                                    category=ActionCategory.KPI_ALERT,
                                    priority=priority,
                                    title=f"L4推理告警：{dim} 维度 {c.severity}",
                                    content=(
                                        f"**{dim}** 维度异常\n"
                                        f"根因: {c.root_cause or '待分析'}\n"
                                        f"置信度: {c.confidence:.0%}\n"
                                        f"建议: {action_text}"
                                    ),
                                    receiver_user_id="store_manager",
                                    source_event_id=f"L4-{sid}-{dim}",
                                    evidence={"dimension": dim, "severity": c.severity},
                                )
                                wechat_sent += 1
                            except Exception as wx_err:
                                logger.warning(
                                    "L4 企微告警推送失败",
                                    store_id=sid,
                                    dim=dim,
                                    error=str(wx_err),
                                )

                except Exception as e:
                    errors.append({"store_id": sid, "error": str(e)})
                    logger.error("门店推理扫描失败", store_id=sid, error=str(e))

            await session.commit()

        logger.info(
            "L4 夜间推理扫描完成",
            stores_scanned=stores_scanned,
            p1_alerts=p1_count,
            p2_alerts=p2_count,
            wechat_sent=wechat_sent,
            errors=len(errors),
        )
        return {
            "success":       len(errors) == 0,
            "stores_scanned": stores_scanned,
            "p1_alerts":     p1_count,
            "p2_alerts":     p2_count,
            "wechat_sent":   wechat_sent,
            "errors":        errors,
        }

    async def _build_kpi_context(session, store_id: str) -> Dict[str, Any]:
        """从 cross_store_metrics 物化表拉取近期 KPI 值"""
        from ..models.cross_store import CrossStoreMetric
        from datetime import date, timedelta
        from sqlalchemy import select, and_

        yesterday = date.today() - timedelta(days=1)
        stmt = select(
            CrossStoreMetric.metric_name,
            CrossStoreMetric.value,
        ).where(
            and_(
                CrossStoreMetric.store_id    == store_id,
                CrossStoreMetric.metric_date == yesterday,
            )
        )
        rows = (await session.execute(stmt)).all()
        return {r[0]: r[1] for r in rows}

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


# ── L5 夜间行动派发任务 ───────────────────────────────────────────────────────

@celery_app.task(
    base=CallbackTask, bind=True,
    name="tasks.nightly_action_dispatch",
    max_retries=2, default_retry_delay=300,
    autoretry_for=(Exception,), retry_backoff=True,
    retry_backoff_max=1800, retry_jitter=False,
)
def nightly_action_dispatch(
    self,
    store_ids: list = None,
    days_back: int  = 1,
) -> Dict[str, Any]:
    """
    L5 夜间行动批量派发任务（建议调度时间: 04:30，L4 nightly_reasoning_scan 完成后执行）

    执行步骤：
      1. 查询近 days_back 天内所有未派发行动的 P1/P2 推理报告
      2. 按 severity 优先级（P1 优先）逐一触发 ActionDispatchService.dispatch_from_report()
      3. 汇总派发统计并返回

    Args:
        store_ids: 指定门店列表（None = 全平台）
        days_back: 回溯天数（默认 1 = 仅处理昨日和今日报告）

    Returns:
        {success, stores_covered, plans_created, dispatched, partial, skipped, errors}
    """
    import asyncio
    from typing import Dict, Any

    async def _run():
        from src.core.database import async_session_factory
        from src.services.action_dispatch_service import ActionDispatchService
        from src.models.reasoning import ReasoningReport
        from src.models.action_plan import ActionPlan
        from datetime import date, timedelta
        from sqlalchemy import select, and_

        total_stats = {
            "plans_created": 0, "dispatched": 0,
            "partial": 0, "skipped": 0, "errors": 0,
        }
        stores_covered: set = set()

        async with async_session_factory() as session:
            # 确定目标门店
            if store_ids:
                target_stores = store_ids
            else:
                from src.models.store import Store
                rows  = (await session.execute(
                    select(Store.id).where(Store.is_active == True)  # noqa: E712
                )).all()
                target_stores = [r[0] for r in rows]

            svc = ActionDispatchService(session)
            for sid in target_stores:
                try:
                    stats = await svc.dispatch_pending_alerts(
                        store_id=sid, days_back=days_back
                    )
                    if stats["plans_created"] > 0 or stats["dispatched"] > 0:
                        stores_covered.add(sid)
                    for k in ("plans_created", "dispatched", "partial", "skipped", "errors"):
                        total_stats[k] += stats.get(k, 0)
                except Exception as e:
                    total_stats["errors"] += 1
                    logger.error("L5 门店行动派发失败", store_id=sid, error=str(e))

            await session.commit()

        logger.info(
            "L5 夜间行动派发完成",
            stores_covered=len(stores_covered),
            **total_stats,
        )
        return {
            "success":         total_stats["errors"] == 0,
            "stores_covered":  len(stores_covered),
            **total_stats,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


# ── 多阶段工作流 Celery 任务 ──────────────────────────────────────────────────

@celery_app.task(
    base=CallbackTask, bind=True,
    name="tasks.start_evening_planning_all_stores",
    max_retries=2, default_retry_delay=120,
    autoretry_for=(Exception,), retry_backoff=True,
    retry_backoff_max=600, retry_jitter=True,
)
def start_evening_planning_all_stores(
    self,
    store_ids: list = None,
) -> Dict[str, Any]:
    """
    每日 17:00 触发：为全平台所有活跃门店启动 Day N+1 规划工作流，
    并立即触发 initial_plan 阶段的快速规划（Fast Mode，<30s）。

    调度建议：beat_schedule 中设置 crontab(hour=17, minute=0)

    Args:
        store_ids: 指定门店列表（None = 全平台活跃门店）

    Returns:
        {success, stores_started, fast_plan_ok, fast_plan_failed, errors}
    """
    async def _run():
        from datetime import date, timedelta
        from src.core.database import async_session_factory
        from src.services.workflow_engine import WorkflowEngine
        from src.services.fast_planning_service import FastPlanningService

        plan_date      = date.today() + timedelta(days=1)
        started        = 0
        fast_plan_ok   = 0
        fast_plan_fail = 0
        errors         = 0

        async with async_session_factory() as session:
            # 确定目标门店
            if store_ids:
                target_stores = store_ids
            else:
                from src.models.store import Store
                from sqlalchemy import select
                rows = (await session.execute(
                    select(Store.id).where(Store.is_active == True)  # noqa: E712
                )).all()
                target_stores = [str(r[0]) for r in rows]

            engine   = WorkflowEngine(session)
            fast_svc = FastPlanningService(session)

            for sid in target_stores:
                try:
                    # 1. 启动工作流（幂等）
                    wf = await engine.start_daily_workflow(
                        store_id=sid,
                        plan_date=plan_date,
                    )
                    started += 1

                    # 2. 获取 initial_plan 阶段，触发快速规划
                    try:
                        init_phase = await engine.get_phase(wf.id, "initial_plan")
                        if init_phase:
                            content = await fast_svc.generate_initial_plan(sid, plan_date)
                            await engine.submit_decision(
                                phase_id=init_phase.id,
                                content=content,
                                submitted_by="system",
                                mode="fast",
                                data_completeness=content.get("data_completeness", 0.7),
                                confidence=content.get("confidence", 0.75),
                                change_reason="系统 17:00 快速规划自动生成",
                            )
                            fast_plan_ok += 1
                    except Exception as fp_err:
                        fast_plan_fail += 1
                        logger.warning(
                            "快速规划触发失败（非致命）",
                            store_id=sid,
                            error=str(fp_err),
                        )

                except Exception as e:
                    errors += 1
                    logger.error("启动工作流失败", store_id=sid, error=str(e))

            await session.commit()

        logger.info(
            "晚间规划工作流批量启动完成",
            plan_date=str(plan_date),
            stores_started=started,
            fast_plan_ok=fast_plan_ok,
            fast_plan_failed=fast_plan_fail,
            errors=errors,
        )
        return {
            "success":          errors == 0,
            "plan_date":        str(plan_date),
            "stores_started":   started,
            "fast_plan_ok":     fast_plan_ok,
            "fast_plan_failed": fast_plan_fail,
            "errors":           errors,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask, bind=True,
    name="tasks.check_workflow_deadlines",
    max_retries=1, default_retry_delay=30,
)
def check_workflow_deadlines(self) -> Dict[str, Any]:
    """
    每 5 分钟扫描全平台所有 running/reviewing 工作流阶段：
      - 距 deadline ≤ 10 分钟 → 发送企微预警
      - 已过 deadline          → 自动锁定阶段并推进到下一阶段

    调度建议：beat_schedule 中设置 crontab(minute="*/5")

    Returns:
        {success, auto_locked, locked_phases}
    """
    async def _run():
        from src.core.database import async_session_factory
        from src.services.timing_service import TimingService

        async with async_session_factory() as session:
            timing = TimingService(session)
            locked = await timing.check_and_auto_lock_all()
            await session.commit()

        return {
            "success":       True,
            "auto_locked":   len(locked),
            "locked_phases": locked,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask, bind=True,
    name="tasks.release_expired_room_locks",
    max_retries=2, default_retry_delay=60,
    autoretry_for=(Exception,), retry_backoff=True,
)
def release_expired_room_locks(self) -> Dict[str, Any]:
    """
    每天凌晨 01:00 扫描全平台超时锁台预约并自动释放。

    锁台（room_lock）超过 ROOM_LOCK_TIMEOUT_DAYS（默认 7 天）未签约，
    自动回退到意向（intent）阶段，释放场地资源。

    调度建议：beat_schedule 中设置 crontab(hour=1, minute=0)

    Returns:
        {success, released_count, released_ids}
    """
    async def _run():
        from src.core.database import async_session_factory
        from src.services.banquet_lifecycle_service import BanquetLifecycleService

        async with async_session_factory() as session:
            svc      = BanquetLifecycleService(session)
            released = await svc.release_expired_locks()
            await session.commit()

        return {
            "success":        True,
            "released_count": len(released),
            "released_ids":   released,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="tasks.monthly_save_fct_tax",
    max_retries=2,
    default_retry_delay=300,
)
def monthly_save_fct_tax(self, year: int = 0, month: int = 0) -> Dict[str, Any]:
    """
    月度税务记录自动保存（FCT 业财税一体化）

    每月1日凌晨 01:00 自动运行：
      - 遍历所有门店
      - 调用 FCTService.estimate_monthly_tax() 估算上月税务
      - 将结果持久化到 fct_tax_records 表

    Args:
        year:  被保存的年份（默认 0 表示自动推断上个月所在年）
        month: 被保存的月份（默认 0 表示自动推断上个月）
    """
    from datetime import date, timedelta

    async def _run():
        from src.core.database import async_session_factory
        from src.models.store import Store
        from src.services.fct_service import FCTService
        from sqlalchemy import select

        # 自动推断上个月
        today = date.today()
        if year == 0 or month == 0:
            first_of_this_month = today.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            _year  = last_month_end.year
            _month = last_month_end.month
        else:
            _year, _month = year, month

        saved, failed = 0, 0

        async with async_session_factory() as session:
            stores_result = await session.execute(select(Store.id))
            store_ids = [row[0] for row in stores_result.all()]

        for store_id in store_ids:
            try:
                async with async_session_factory() as session:
                    svc = FCTService(session)
                    await svc.estimate_monthly_tax(
                        store_id=store_id,
                        year=_year,
                        month=_month,
                        save=True,
                    )
                    await session.commit()
                    saved += 1
            except Exception as exc:
                logger.warning(
                    "月度税务保存失败",
                    store_id=store_id,
                    year=_year,
                    month=_month,
                    error=str(exc),
                )
                failed += 1

        logger.info(
            "月度税务批量保存完成",
            year=_year, month=_month,
            saved=saved, failed=failed,
        )
        return {"year": _year, "month": _month, "saved": saved, "failed": failed}

    try:
        return asyncio.run(_run())
    except Exception as e:
        raise self.retry(exc=e)


# ============================================================
# ARCH-003: 门店记忆层更新任务
# ============================================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def update_store_memory(self, store_id: str = None, brand_id: str = None):
    """每日凌晨2AM更新门店记忆层（峰时模式/菜品健康度/员工基线）"""
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.services.store_memory_service import StoreMemoryService

        async with get_db_session() as db:
            service = StoreMemoryService(db_session=db)
            if store_id:
                await service.refresh_store_memory(store_id=store_id, brand_id=brand_id)
            else:
                # 全量刷新：从 DB 获取所有门店
                from sqlalchemy import select
                from src.models.store import Store
                result = await db.execute(select(Store.id, Store.brand_id))
                stores = result.all()
                for row in stores:
                    try:
                        await service.refresh_store_memory(
                            store_id=str(row.id),
                            brand_id=str(row.brand_id) if row.brand_id else None,
                        )
                    except Exception as exc:
                        logger.warning(
                            "update_store_memory.store_failed",
                            store_id=str(row.id),
                            error=str(exc),
                        )

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def realtime_anomaly_check(self, store_id: str, event: dict):
    """StaffAction 写入后触发的实时异常检测"""
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.services.store_memory_service import StoreMemoryService

        async with get_db_session() as db:
            service = StoreMemoryService(db_session=db)
            await service.detect_anomaly(store_id=store_id, event=event)

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ============================================================
# FEAT-002: 预测性备料推送任务
# ============================================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def push_daily_forecast(self, store_id: str = None):
    """每日9AM推送预测性备料建议，confidence=low 时附\"数据积累中\"提示"""
    import asyncio
    from datetime import date, timedelta

    async def _run():
        from src.core.database import get_db_session
        from src.services.demand_forecaster import DemandForecaster
        from src.services.wechat_service import wechat_service

        target_date = date.today() + timedelta(days=1)

        async with get_db_session() as db:
            forecaster = DemandForecaster(db_session=db)

            stores_to_forecast = []
            if store_id:
                stores_to_forecast = [store_id]
            else:
                from sqlalchemy import select
                from src.models.store import Store
                result = await db.execute(select(Store.id))
                stores_to_forecast = [str(row.id) for row in result.all()]

            for sid in stores_to_forecast:
                try:
                    result = await forecaster.predict(store_id=sid, target_date=target_date)
                    message_data = {
                        "store_id": sid,
                        "target_date": str(result.target_date),
                        "estimated_revenue": result.estimated_revenue,
                        "confidence": result.confidence,
                        "basis": result.basis,
                        "note": result.note or "",
                        "item_count": len(result.items),
                    }
                    await wechat_service.send_templated_message(
                        template="daily_forecast",
                        data=message_data,
                        to_user_id=f"store_{sid}",
                    )
                except Exception as exc:
                    logger.warning(
                        "push_daily_forecast.store_failed",
                        store_id=sid,
                        error=str(exc),
                    )

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ============================================================
# INFRA-002: 企微消息重试任务
# ============================================================

@celery_app.task(bind=True, max_retries=1)
def retry_failed_wechat_messages(self):
    """每5分钟从失败队列取出企微消息重试（最多3次）"""
    import asyncio

    async def _run():
        from src.services.wechat_service import wechat_service
        await wechat_service.retry_failed_messages(max_retries=3, batch_size=10)

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.warning("retry_failed_wechat_messages.error", error=str(exc))


# ============================================================
# v2.0 决策效果反馈（48h 后检查）
# ============================================================

@celery_app.task(bind=True, max_retries=2, default_retry_delay=300)
def check_decision_impact(self, decision_id: str):
    """
    审批后 48h 效果回检。

    对比决策前后的关键指标，向审批人发送效果反馈消息，
    并将决策 outcome 设为 PENDING（待人工核实）。
    """
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.models.decision_log import DecisionLog, DecisionStatus, DecisionOutcome
        from src.services.wechat_service import wechat_service
        from src.services.decision_push_service import _APPROVAL_BASE_URL
        from sqlalchemy import select

        async with get_db_session() as db:
            result = await db.execute(
                select(DecisionLog).where(DecisionLog.id == decision_id)
            )
            dl = result.scalar_one_or_none()
            if not dl:
                logger.warning("check_decision_impact.not_found", decision_id=decision_id)
                return

            # 仅处理已批准且尚无结果的决策
            if dl.decision_status not in (DecisionStatus.APPROVED, DecisionStatus.EXECUTED):
                logger.info("check_decision_impact.skip_status",
                            decision_id=decision_id, status=str(dl.decision_status))
                return
            if dl.outcome is None:
                dl.outcome = DecisionOutcome.PENDING
                await db.commit()

            # 向审批人发送 48h 效果反馈提醒
            try:
                title       = f"【48h效果反馈】{dl.decision_type}"
                description = (
                    f"您于48小时前批准的决策\n"
                    f"来源：{dl.agent_type} / {dl.agent_method}\n"
                    f"门店：{dl.store_id}\n"
                    f"请核实执行效果并在系统中记录结果"
                )
                action_url = f"{_APPROVAL_BASE_URL}/{decision_id}/outcome"
                recipient  = dl.manager_id or f"store_{dl.store_id}"
                await wechat_service.send_decision_card(
                    title=title,
                    description=description,
                    action_url=action_url,
                    btntxt="记录结果",
                    to_user_id=recipient,
                )
                logger.info("check_decision_impact.feedback_sent",
                            decision_id=decision_id, recipient=recipient)
            except Exception as exc:
                logger.warning("check_decision_impact.feedback_failed",
                               decision_id=decision_id, error=str(exc))

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ============================================================
# v2.0 决策型企微推送（4时间点）
# ============================================================

def _get_store_recipient(store_id: str) -> str:
    """获取门店负责人的企微 user_id（优先从环境变量读，兜底返回 store_{id}）。"""
    return os.getenv(f"WECHAT_RECIPIENT_{store_id.upper()}", f"store_{store_id}")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def push_morning_decisions(self, store_id: str = None):
    """08:00晨推：为所有（或指定）门店推送今日 Top3 决策卡片。"""
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.models.store import Store
        from sqlalchemy import select
        from src.services.decision_push_service import DecisionPushService

        async with get_db_session() as db:
            if store_id:
                stores = [(store_id, "")]
            else:
                rows = (await db.execute(select(Store.id, Store.name))).all()
                stores = [(str(r.id), r.name or "") for r in rows]

            for sid, sname in stores:
                try:
                    await DecisionPushService.push_morning_decisions(
                        store_id=sid,
                        brand_id="",
                        recipient_user_id=_get_store_recipient(sid),
                        db=db,
                        store_name=sname,
                    )
                except Exception as exc:
                    logger.warning("push_morning_decisions.store_failed",
                                   store_id=sid, error=str(exc))

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def push_noon_anomaly(self, store_id: str = None):
    """12:00午推：上午损耗/成本率异常汇总（仅在存在异常时推送）。"""
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.models.store import Store
        from sqlalchemy import select
        from src.services.decision_push_service import DecisionPushService

        async with get_db_session() as db:
            if store_id:
                stores = [(store_id, "")]
            else:
                rows = (await db.execute(select(Store.id, Store.name))).all()
                stores = [(str(r.id), r.name or "") for r in rows]

            for sid, sname in stores:
                try:
                    await DecisionPushService.push_noon_anomaly(
                        store_id=sid,
                        brand_id="",
                        recipient_user_id=_get_store_recipient(sid),
                        db=db,
                        store_name=sname,
                    )
                except Exception as exc:
                    logger.warning("push_noon_anomaly.store_failed",
                                   store_id=sid, error=str(exc))

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def push_prebattle_decisions(self, store_id: str = None):
    """17:30战前推：库存/排班备战核查（仅在有库存或紧急决策时推送）。"""
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.models.store import Store
        from sqlalchemy import select
        from src.services.decision_push_service import DecisionPushService

        async with get_db_session() as db:
            if store_id:
                stores = [(store_id, "")]
            else:
                rows = (await db.execute(select(Store.id, Store.name))).all()
                stores = [(str(r.id), r.name or "") for r in rows]

            for sid, sname in stores:
                try:
                    await DecisionPushService.push_prebattle_decisions(
                        store_id=sid,
                        brand_id="",
                        recipient_user_id=_get_store_recipient(sid),
                        db=db,
                        store_name=sname,
                    )
                except Exception as exc:
                    logger.warning("push_prebattle_decisions.store_failed",
                                   store_id=sid, error=str(exc))

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def push_evening_recap(self, store_id: str = None):
    """20:30晚推：当日回顾+待批决策提醒。"""
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.models.store import Store
        from sqlalchemy import select
        from src.services.decision_push_service import DecisionPushService

        async with get_db_session() as db:
            if store_id:
                stores = [(store_id, "")]
            else:
                rows = (await db.execute(select(Store.id, Store.name))).all()
                stores = [(str(r.id), r.name or "") for r in rows]

            for sid, sname in stores:
                try:
                    await DecisionPushService.push_evening_recap(
                        store_id=sid,
                        brand_id="",
                        recipient_user_id=_get_store_recipient(sid),
                        db=db,
                        store_name=sname,
                    )
                except Exception as exc:
                    logger.warning("push_evening_recap.store_failed",
                                   store_id=sid, error=str(exc))

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ============================================================
# v2.0 KPI 食材成本率告警（09:30 日检）
# ============================================================

@celery_app.task(bind=True, max_retries=2, default_retry_delay=300)
def check_food_cost_kpi_alert(self):
    """
    每日 09:30 检查所有门店食材成本率是否超过 AlertThresholdsPage 中配置的阈值。
    超标时发送企业微信告警（warning=橙 / critical=红）。
    """
    import asyncio

    async def _run():
        from src.core.database import get_db_session
        from src.services.kpi_alert_service import KPIAlertService

        async with get_db_session() as db:
            result = await KPIAlertService.run_and_notify(db=db)
            logger.info(
                "food_cost_kpi_alert_done",
                total=result["total"],
                alerts=result["alert_count"],
                sent=result["sent_count"],
                failed=result["failed_count"],
            )
            return result

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)
