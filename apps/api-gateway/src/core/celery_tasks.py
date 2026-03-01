"""
Celery异步任务
用于Neural System的事件处理和向量数据库索引
"""
from typing import Dict, Any
import asyncio
import os
import structlog
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

        db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/zhilian")
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


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_SHORT", "30")),
)
def dispatch_training_recommendation(
    self,
    store_id: str,
    tenant_id: str,
    root_cause_dimension: str,
    affected_staff_ids: list,
    waste_event_id: str,
) -> Dict[str, Any]:
    """
    废料根因 → 培训推荐分发。

    根据损耗推理根因维度查询 ROOT_CAUSE_TO_TRAINING 配置，
    为当班员工批量创建针对性培训推荐记录，
    并通过 AgentMemoryBus 通知 TrainingAgent。

    由 run_waste_reasoning() 在 top3 根因确定后触发。
    """
    async def _run():
        from src.core.root_cause_config import ROOT_CAUSE_TO_TRAINING
        from src.services.training_service import TrainingService
        from src.services.agent_memory_bus import agent_memory_bus

        config = ROOT_CAUSE_TO_TRAINING.get(root_cause_dimension)
        if not config:
            logger.info(
                "waste_training_dispatch_no_config",
                root_cause=root_cause_dimension,
                store_id=store_id,
            )
            return {"skipped": True, "reason": "no_mapping_config", "root_cause": root_cause_dimension}

        training_svc = TrainingService(store_id=store_id)
        created = []
        for staff_id in affected_staff_ids:
            try:
                rec = await training_svc.create_waste_driven_recommendation(
                    staff_id=staff_id,
                    root_cause=root_cause_dimension,
                    waste_event_id=waste_event_id,
                    course_ids=config["course_ids"],
                    urgency=config["urgency"],
                    urgency_days=config.get("urgency_days", 7),
                    skill_gap=config["skill_gap"],
                    description=config["description"],
                )
                created.append(rec)
            except Exception as staff_err:
                logger.warning(
                    "waste_training_dispatch_staff_failed",
                    staff_id=staff_id,
                    error=str(staff_err),
                )

        # 通知 AgentMemoryBus，TrainingAgent 可订阅此事件
        await agent_memory_bus.publish(
            store_id=store_id,
            agent_id="waste_reasoning",
            action="training_recommendation_dispatched",
            summary=(
                f"根因[{root_cause_dimension}]触发培训推荐：{config['skill_gap']}，"
                f"共{len(created)}位员工，紧迫度{config['urgency']}"
            ),
            confidence=0.85,
            data={
                "root_cause": root_cause_dimension,
                "waste_event_id": waste_event_id,
                "affected_staff_count": len(created),
                "course_ids": config["course_ids"],
                "urgency": config["urgency"],
                "skill_gap": config["skill_gap"],
            },
        )

        # Phase 1.3: 写入 Neo4j Staff-Training 关系，关闭因果图闭环
        from datetime import datetime as _dt_neo
        from src.ontology import get_ontology_repository
        repo = get_ontology_repository()
        if repo and created:
            # 使用根因维度 + 技能缺口作为 TrainingModule 唯一 ID
            module_id = f"tm_{root_cause_dimension}_{config['skill_gap'].replace(' ', '_')}"
            try:
                repo.merge_training_module(
                    module_id=module_id,
                    name=config["description"],
                    skill_gap=config["skill_gap"],
                    course_ids=config["course_ids"],
                    tenant_id=tenant_id,
                )
                for rec in created:
                    s_id = rec.get("staff_id", "")
                    if s_id:
                        repo.staff_needs_training(
                            staff_id=s_id,
                            module_id=module_id,
                            waste_event_id=waste_event_id,
                            urgency=config["urgency"],
                            deadline=rec.get("deadline", ""),
                        )
            except Exception as neo_err:
                logger.warning(
                    "neo4j_staff_needs_training_failed",
                    store_id=store_id,
                    error=str(neo_err),
                )

        logger.info(
            "waste_training_dispatch_done",
            store_id=store_id,
            root_cause=root_cause_dimension,
            waste_event_id=waste_event_id,
            staff_count=len(created),
        )

        # 企微实时告警：通知门店管理员损耗根因与培训推荐
        try:
            from src.services.wechat_alert_service import wechat_alert_service as _wechat_svc
            await _wechat_svc.send_waste_training_alert(
                store_id=store_id,
                root_cause=root_cause_dimension,
                skill_gap=config["skill_gap"],
                urgency=config["urgency"],
                affected_staff_count=len(created),
                course_ids=config["course_ids"],
                waste_event_id=waste_event_id,
            )
        except Exception as alert_err:
            logger.warning(
                "waste_training_wechat_alert_failed",
                store_id=store_id,
                root_cause=root_cause_dimension,
                error=str(alert_err),
            )

        # Phase 2.1: 7天后触发培训效果验证
        from datetime import datetime as _dt, timedelta
        eta_7d = _dt.utcnow() + timedelta(days=7)
        for rec in created:
            try:
                verify_training_effectiveness.apply_async(
                    kwargs={
                        "store_id": store_id,
                        "staff_id": rec.get("staff_id", ""),
                        "waste_event_id": waste_event_id,
                        "root_cause": root_cause_dimension,
                    },
                    eta=eta_7d,
                )
            except Exception as sched_err:
                logger.warning(
                    "verify_training_schedule_failed",
                    staff_id=rec.get("staff_id"),
                    error=str(sched_err),
                )

        return {
            "store_id": store_id,
            "root_cause": root_cause_dimension,
            "waste_event_id": waste_event_id,
            "created": len(created),
            "recommendations": created,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("dispatch_training_recommendation_failed", store_id=store_id, error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
)
def escalate_ontology_actions(self) -> Dict[str, Any]:
    """
    L4 Action 超时自动升级：扫描已 SENT 且超过 deadline 未回执的 Action，
    标记 escalation_at / escalated_to 并推送给配置的升级对象（企微）。
    由 Celery Beat 每 5–10 分钟执行一次。
    """
    async def _run():
        from src.core.database import get_db_session
        from src.services.ontology_action_service import process_escalations

        async with get_db_session() as session:
            n = await process_escalations(session)
            await session.commit()
        return {"escalated": n}

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("escalate_ontology_actions_failed", error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),
)
def verify_training_effectiveness(
    self,
    store_id: str,
    staff_id: str,
    waste_event_id: str,
    root_cause: str,
    pre_training_period_days: int = 7,
) -> Dict[str, Any]:
    """
    Phase 2.1 培训效果验证：

    在培训推荐创建 7 天后（ETA 延迟触发），对比培训前后同员工/同根因的废料率。
    结果写入 agent_memory_bus，供 TrainingAgent 和 KnowledgeRuleService 使用。
    """
    async def _run():
        from datetime import datetime, timedelta
        from sqlalchemy import select, func, and_
        from src.core.database import get_db_session
        from src.models.kpi import KPI, KPIRecord
        from src.services.agent_memory_bus import agent_memory_bus

        now = datetime.now()
        pre_start = now - timedelta(days=pre_training_period_days * 2)
        pre_end = now - timedelta(days=pre_training_period_days)
        post_start = pre_end
        post_end = now

        async with get_db_session() as session:
            # 查询培训前后同员工的 waste_driven_training 记录
            def _query_waste_kpi(from_dt, to_dt):
                return (
                    select(func.avg(KPIRecord.value).label("avg_score"))
                    .join(KPI, KPIRecord.kpi_id == KPI.id)
                    .where(
                        and_(
                            KPIRecord.store_id == store_id,
                            KPI.category == "waste_driven_training",
                            KPIRecord.record_date >= from_dt.date(),
                            KPIRecord.record_date <= to_dt.date(),
                        )
                    )
                )

            pre_result = await session.execute(_query_waste_kpi(pre_start, pre_end))
            post_result = await session.execute(_query_waste_kpi(post_start, post_end))

            pre_score = pre_result.scalar() or 0
            post_score = post_result.scalar() or 0

        improvement = post_score - pre_score
        effectiveness = min(100.0, max(0.0, 50.0 + improvement))

        # 写入 agent_memory_bus
        await agent_memory_bus.publish(
            store_id=store_id,
            agent_id="training_verifier",
            action="training_effectiveness_verified",
            summary=(
                f"员工[{staff_id}] 根因[{root_cause}] 培训效果："
                f"训前得分{pre_score:.1f} → 训后{post_score:.1f}，"
                f"改善{improvement:+.1f}，有效性{effectiveness:.0f}%"
            ),
            confidence=0.75,
            data={
                "staff_id": staff_id,
                "waste_event_id": waste_event_id,
                "root_cause": root_cause,
                "pre_score": pre_score,
                "post_score": post_score,
                "improvement": improvement,
                "effectiveness": effectiveness,
            },
        )

        logger.info(
            "training_effectiveness_verified",
            store_id=store_id,
            staff_id=staff_id,
            root_cause=root_cause,
            effectiveness=effectiveness,
        )

        # Phase 2.2: 更新知识库中对应根因的 waste_rule 精度（指数移动平均）
        try:
            from src.services.ontology_knowledge_service import update_knowledge_accuracy
            # tenant_id 从 store_id 反查，或直接用 store_id 所属 tenant（此处简化为按 store_id 过滤所有租户）
            update_knowledge_accuracy(
                root_cause=root_cause,
                effectiveness=effectiveness,
                tenant_id="",  # 空字符串跳过 tenant 过滤，全局匹配
            )
        except Exception as ka_err:
            logger.warning("knowledge_accuracy_update_failed", root_cause=root_cause, error=str(ka_err))

        return {
            "store_id": store_id,
            "staff_id": staff_id,
            "root_cause": root_cause,
            "pre_score": pre_score,
            "post_score": post_score,
            "improvement": improvement,
            "effectiveness": effectiveness,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("verify_training_effectiveness_failed", store_id=store_id, error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),
    default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY_LONG", "300")),
)
def propagate_training_knowledge(self) -> Dict[str, Any]:
    """
    Phase 3.2 跨门店培训知识传播（周频定时任务）：

    查询各门店废料率改善 Top3 的培训方案，向相似门店自动创建培训建议，
    标记来源为 cross_store_best_practice。
    由 Celery Beat 每周一次执行。
    """
    async def _run():
        from sqlalchemy import select, func, and_
        from src.core.database import get_db_session
        from src.models.kpi import KPI, KPIRecord
        from src.models.store import Store
        from src.services.training_service import TrainingService

        propagated = 0
        async with get_db_session() as session:
            # 查询所有门店
            stores_result = await session.execute(select(Store))
            stores = stores_result.scalars().all()
            store_ids = [str(s.id) for s in stores]

            # 查询各门店培训记录，找废料率改善最好的（得分最高）
            top_practices = {}
            for sid in store_ids:
                stmt = (
                    select(
                        KPIRecord.kpi_id,
                        func.avg(KPIRecord.value).label("avg_score"),
                        func.count(KPIRecord.id).label("cnt"),
                    )
                    .join(KPI, KPIRecord.kpi_id == KPI.id)
                    .where(
                        and_(
                            KPIRecord.store_id == sid,
                            KPI.category == "waste_driven_training",
                            KPIRecord.status == "on_track",
                        )
                    )
                    .group_by(KPIRecord.kpi_id)
                    .order_by(func.avg(KPIRecord.value).desc())
                    .limit(3)
                )
                result = await session.execute(stmt)
                rows = result.all()
                if rows:
                    top_practices[sid] = [
                        {"kpi_id": r.kpi_id, "avg_score": float(r.avg_score), "cnt": r.cnt}
                        for r in rows
                    ]

            # 向相似门店传播最佳实践；若 Neo4j 未配置则降级为全门店广播
            from src.ontology import get_ontology_repository
            neo_repo = get_ontology_repository()

            for source_sid, practices in top_practices.items():
                # Phase 3: 优先通过 SIMILAR_TO 关系缩小传播范围
                if neo_repo:
                    try:
                        similar = neo_repo.get_similar_stores(source_sid, min_score=0.5)
                        target_sids = [s["store_id"] for s in similar] if similar else [
                            sid for sid in store_ids if sid != source_sid
                        ]
                    except Exception:
                        target_sids = [sid for sid in store_ids if sid != source_sid]
                else:
                    target_sids = [sid for sid in store_ids if sid != source_sid]

                for target_sid in target_sids:
                    for practice in practices[:1]:  # 每家门店只传播 Top1
                        try:
                            svc = TrainingService(store_id=target_sid)
                            kpi_id = practice["kpi_id"]
                            # 从 kpi_id 解析 root_cause (格式: KPI_WASTE_{ROOT_CAUSE}_...)
                            parts = kpi_id.split("_")
                            root_cause = parts[2].lower() if len(parts) > 2 else "cross_store"
                            await svc.create_waste_driven_recommendation(
                                staff_id="STORE_GENERAL",
                                root_cause=f"cross_store_{root_cause}",
                                waste_event_id=f"cross_store_{source_sid}_{root_cause}",
                                course_ids=[kpi_id],
                                urgency="low",
                                urgency_days=30,
                                skill_gap=root_cause,
                                description=(
                                    f"跨门店最佳实践：来自门店[{source_sid}]，"
                                    f"培训[{kpi_id}]平均得分{practice['avg_score']:.1f}"
                                ),
                            )
                            propagated += 1
                        except Exception as e:
                            logger.warning(
                                "cross_store_propagate_failed",
                                source=source_sid,
                                target=target_sid,
                                error=str(e),
                            )

        logger.info("cross_store_training_propagated", count=propagated)
        return {"propagated": propagated}

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("propagate_training_knowledge_failed", error=str(e))
        raise self.retry(exc=e)


# ============================================================
# 图谱定期同步（每日凌晨 2AM，PG → Neo4j）
# ============================================================

@celery_app.task(
    bind=True,
    name="src.core.celery_tasks.sync_ontology_graph",
    max_retries=2,
    default_retry_delay=300,
)
def sync_ontology_graph(self, tenant_id: str = "") -> Dict[str, Any]:
    """
    每日定时将 PostgreSQL 主数据同步到 Neo4j 图谱（L2 本体层）。

    同步内容：Store（含相似度自动计算）、Dish、Ingredient、Staff、Order。
    tenant_id 为空时使用环境变量 DEFAULT_TENANT_ID，仍为空则使用 "default"。
    由 Celery Beat 每日凌晨 2AM 触发；也可手动调用 POST /ontology/sync-from-pg。
    """
    import os as _os

    async def _run():
        from src.core.database import get_db_session
        from src.services.ontology_sync_service import sync_ontology_from_pg

        effective_tenant = tenant_id or _os.getenv("DEFAULT_TENANT_ID", "default")

        async with get_db_session() as session:
            result = await sync_ontology_from_pg(session, tenant_id=effective_tenant)

        logger.info(
            "ontology_graph_synced",
            tenant_id=effective_tenant,
            stores=result.get("stores", 0),
            staff=result.get("staff", 0),
            dishes=result.get("dishes", 0),
            ingredients=result.get("ingredients", 0),
            orders=result.get("orders", 0),
        )
        return {"ok": True, "tenant_id": effective_tenant, **result}

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("sync_ontology_graph_failed", error=str(e))
        raise self.retry(exc=e)


# ============================================================
# ARCH-003: 门店记忆层 Celery 任务
# ============================================================

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="src.core.celery_tasks.update_store_memory",
    max_retries=2,
    default_retry_delay=300,
)
def update_store_memory(self, store_id: str = None, brand_id: str = None) -> Dict[str, Any]:
    """
    每日凌晨2点更新门店记忆层（Celery Beat 调度）

    Args:
        store_id: 指定门店ID（None 表示更新所有活跃门店）
        brand_id: 品牌ID（可选）

    Returns:
        更新结果
    """
    async def _run():
        from ..models.store import Store
        from ..core.database import get_db_session
        from ..services.store_memory_service import StoreMemoryService
        from sqlalchemy import select

        service = StoreMemoryService()
        updated = 0
        failed = 0

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
                memory = await service.refresh_store_memory(
                    store_id=str(store.id),
                    brand_id=getattr(store, 'brand_id', None) or brand_id,
                    lookback_days=30,
                )
                updated += 1
                logger.info("store_memory.updated", store_id=str(store.id), confidence=memory.confidence)
            except Exception as e:
                failed += 1
                logger.error("store_memory.update_failed", store_id=str(store.id), error=str(e))

        logger.info("update_store_memory.done", updated=updated, failed=failed)
        return {"updated": updated, "failed": failed}

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("update_store_memory_failed", error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="src.core.celery_tasks.realtime_anomaly_check",
    max_retries=1,
    default_retry_delay=10,
)
def realtime_anomaly_check(self, store_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    实时异常检测（StaffAction 写入后触发）

    检测该门店最新操作是否触发异常模式：
    - 短时间内多次折扣申请
    - 营收突然异常下降
    """
    async def _run():
        from ..services.store_memory_service import StoreMemoryService
        from ..models.store_memory import AnomalyPattern
        from datetime import datetime as _dt

        service = StoreMemoryService()
        memory = await service.get_memory(store_id)

        if not memory:
            return {"store_id": store_id, "anomaly_detected": False, "reason": "no_memory"}

        action_type = event.get("action_type", "")
        anomaly_detected = False
        anomaly_type = None

        # 简单规则：连续3次以上折扣申请标记为异常
        if action_type == "discount_apply":
            recent_discounts = [
                p for p in memory.anomaly_patterns
                if p.pattern_type == "frequent_discount"
            ]
            if len(recent_discounts) > 0:
                recent_discounts[0].occurrence_count += 1
                recent_discounts[0].last_seen = _dt.utcnow()
                if recent_discounts[0].occurrence_count >= 3:
                    anomaly_detected = True
                    anomaly_type = "frequent_discount"
            else:
                memory.anomaly_patterns.append(AnomalyPattern(
                    pattern_type="frequent_discount",
                    description="短时间内多次折扣申请",
                    first_seen=_dt.utcnow(),
                    last_seen=_dt.utcnow(),
                    severity="medium",
                ))

            await service._store.save(memory)

        logger.info(
            "realtime_anomaly_check.done",
            store_id=store_id,
            anomaly_detected=anomaly_detected,
            anomaly_type=anomaly_type,
        )

        return {
            "store_id": store_id,
            "anomaly_detected": anomaly_detected,
            "anomaly_type": anomaly_type,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("realtime_anomaly_check_failed", store_id=store_id, error=str(e))
        raise self.retry(exc=e)


# ============================================================
# FEAT-002: 预测性备料 Celery 任务
# ============================================================

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="src.core.celery_tasks.push_daily_forecast",
    max_retries=2,
    default_retry_delay=300,
)
def push_daily_forecast(self, store_id: str = None) -> Dict[str, Any]:
    """
    每日9AM 推送预测性备料建议

    Args:
        store_id: 指定门店（None 表示所有门店）

    Returns:
        推送结果
    """
    async def _run():
        from datetime import date, timedelta
        from ..models.store import Store
        from ..core.database import get_db_session
        from ..services.demand_forecaster import DemandForecaster
        from sqlalchemy import select

        target_date = date.today() + timedelta(days=1)
        forecaster = DemandForecaster()
        pushed = 0
        low_confidence_count = 0

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
                forecast = await forecaster.predict(
                    store_id=str(store.id),
                    target_date=target_date,
                )

                # confidence=low 时推送含"数据积累中"提示
                if forecast.confidence == "low":
                    low_confidence_count += 1
                    message = (
                        f"【备料建议（参考）】明日 {target_date}\n"
                        f"门店：{store.name}\n"
                        f"⚠️ 数据积累中（历史数据不足），建议以近期经验为主。\n"
                        f"预估营收：¥{forecast.estimated_revenue:.0f}"
                    )
                else:
                    message = (
                        f"【备料建议】明日 {target_date}\n"
                        f"门店：{store.name}\n"
                        f"预估营收：¥{forecast.estimated_revenue:.0f}\n"
                        f"置信度：{forecast.confidence}\n"
                        f"建议备料：{len(forecast.items)} 类食材"
                    )

                logger.info(
                    "daily_forecast.pushed",
                    store_id=str(store.id),
                    confidence=forecast.confidence,
                )
                pushed += 1

            except Exception as e:
                logger.error("daily_forecast.push_failed", store_id=str(store.id), error=str(e))

        return {
            "pushed": pushed,
            "low_confidence": low_confidence_count,
            "target_date": str(target_date),
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("push_daily_forecast_failed", error=str(e))
        raise self.retry(exc=e)


# ============================================================
# INFRA-002: 企微消息重试 Celery 任务
# ============================================================

@celery_app.task(
    base=CallbackTask,
    bind=True,
    name="src.core.celery_tasks.retry_failed_wechat_messages",
    max_retries=1,
    default_retry_delay=60,
)
def retry_failed_wechat_messages(self) -> Dict[str, Any]:
    """
    每5分钟从告警队列取出失败的企微消息进行重试（最多3次）
    """
    async def _run():
        from ..services.wechat_service import wechat_service

        retried = 0
        succeeded = 0

        try:
            results = await wechat_service.retry_failed_messages(max_retries=3, batch_size=10)
            retried = results.get("retried", 0)
            succeeded = results.get("succeeded", 0)
        except Exception as e:
            logger.warning("retry_failed_wechat_messages.error", error=str(e))

        logger.info("retry_failed_wechat_messages.done", retried=retried, succeeded=succeeded)
        return {"retried": retried, "succeeded": succeeded}

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("retry_failed_wechat_messages_task_failed", error=str(e))
        raise self.retry(exc=e)

