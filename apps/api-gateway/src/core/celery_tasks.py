"""
Celery异步任务
用于Neural System的事件处理和向量数据库索引
"""
from typing import Dict, Any
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
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
async def process_neural_event(
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
    try:
        from datetime import datetime
        from ..services.vector_db_service import vector_db_service

        # 构建事件对象
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "event_source": event_source,
            "timestamp": datetime.now(),
            "store_id": store_id,
            "data": data,
            "priority": priority,
            "processed": False,
        }

        logger.info(
            "开始处理神经系统事件",
            event_id=event_id,
            event_type=event_type,
            store_id=store_id,
        )

        # 1. 向量化存储
        await vector_db_service.index_event(event)

        # 2. 触发企微推送（如果配置了触发规则）
        from ..services.wechat_trigger_service import wechat_trigger_service
        try:
            await wechat_trigger_service.trigger_push(
                event_type=event_type,
                event_data=data,
                store_id=store_id,
            )
        except Exception as e:
            # 企微推送失败不影响主流程
            logger.warning(
                "企微推送触发失败",
                event_type=event_type,
                error=str(e),
            )

        # 3. 根据事件类型调用相应的处理任务
        if event_type.startswith("order."):
            await index_order_to_vector_db.delay(data)
        elif event_type.startswith("dish."):
            await index_dish_to_vector_db.delay(data)

        # 4. 标记为已处理
        event["processed"] = True

        logger.info(
            "神经系统事件处理完成",
            event_id=event_id,
            event_type=event_type,
        )

        return {
            "success": True,
            "event_id": event_id,
            "processed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(
            "神经系统事件处理失败",
            event_id=event_id,
            error=str(e),
            exc_info=e,
        )
        # 重试任务
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
async def index_to_vector_db(
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


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
)
async def index_order_to_vector_db(
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
    return await index_to_vector_db(self, "orders", order_data)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
)
async def index_dish_to_vector_db(
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
    return await index_to_vector_db(self, "dishes", dish_data)


@celery_app.task(
    base=CallbackTask,
    bind=True,
)
async def batch_index_orders(
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
        results = [task.get(timeout=300) for task in tasks]

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
async def batch_index_dishes(
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
        results = [task.get(timeout=300) for task in tasks]

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
    max_retries=3,
    default_retry_delay=300,  # 5分钟
)
async def generate_and_send_daily_report(
    self,
    store_id: str,
    report_date: str = None,
) -> Dict[str, Any]:
    """
    生成并发送营业日报

    Args:
        store_id: 门店ID
        report_date: 报告日期（YYYY-MM-DD格式，默认为昨天）

    Returns:
        生成和发送结果
    """
    try:
        from datetime import date, datetime
        from ..services.daily_report_service import daily_report_service
        from ..services.wechat_work_message_service import wechat_work_message_service
        from ..models.user import User, UserRole
        from ..core.database import get_db_session
        from sqlalchemy import select

        logger.info(
            "开始生成营业日报",
            store_id=store_id,
            report_date=report_date
        )

        # 解析日期
        if report_date:
            target_date = datetime.strptime(report_date, "%Y-%m-%d").date()
        else:
            from datetime import timedelta
            target_date = date.today() - timedelta(days=1)

        # 1. 生成日报
        report = await daily_report_service.generate_daily_report(
            store_id=store_id,
            report_date=target_date
        )

        # 2. 构建推送消息
        revenue_yuan = report.total_revenue / 100
        message = f"""【营业日报】{target_date.strftime('%Y年%m月%d日')}

{report.summary}

📊 详细数据：
• 订单数：{report.order_count}笔
• 客流量：{report.customer_count}人
• 客单价：¥{report.avg_order_value / 100:.2f}

📈 运营指标：
• 任务完成率：{report.task_completion_rate:.1f}%
• 库存预警：{report.inventory_alert_count}个
"""

        # 添加亮点
        if report.highlights:
            message += "\n✨ 今日亮点：\n"
            for highlight in report.highlights:
                message += f"• {highlight}\n"

        # 添加预警
        if report.alerts:
            message += "\n⚠️ 需要关注：\n"
            for alert in report.alerts:
                message += f"• {alert}\n"

        # 3. 查询店长和老板，发送推送
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(
                    User.store_id == store_id,
                    User.is_active == True,
                    User.role.in_([UserRole.STORE_MANAGER, UserRole.ADMIN]),
                    User.wechat_user_id.isnot(None)
                )
            )
            managers = result.scalars().all()

            sent_count = 0
            for manager in managers:
                try:
                    result = await wechat_work_message_service.send_text_message(
                        user_id=manager.wechat_user_id,
                        content=message
                    )
                    if result.get("success"):
                        sent_count += 1
                except Exception as e:
                    logger.error(
                        "发送日报失败",
                        user_id=str(manager.id),
                        error=str(e)
                    )

        # 4. 标记为已发送
        if sent_count > 0:
            await daily_report_service.mark_as_sent(report.id)

        logger.info(
            "营业日报生成并发送完成",
            store_id=store_id,
            report_date=str(target_date),
            sent_count=sent_count
        )

        return {
            "success": True,
            "store_id": store_id,
            "report_date": str(target_date),
            "report_id": str(report.id),
            "sent_count": sent_count
        }

    except Exception as e:
        logger.error(
            "生成营业日报失败",
            store_id=store_id,
            error=str(e),
            exc_info=e
        )
        raise self.retry(exc=e)


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5分钟
)
async def perform_daily_reconciliation(
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


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
async def detect_revenue_anomaly(
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
    try:
        from datetime import datetime, timedelta
        from ..agents.decision_agent import DecisionAgent
        from ..services.wechat_work_message_service import wechat_work_message_service
        from ..models.store import Store
        from ..core.database import get_db_session
        from sqlalchemy import select

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
                    # TODO: 从数据库获取当前营收和预期营收
                    # 这里使用模拟数据
                    current_revenue = 8000.0  # 实际应从数据库查询
                    expected_revenue = 10000.0  # 实际应从历史数据计算

                    # 计算偏差
                    deviation = ((current_revenue - expected_revenue) / expected_revenue) * 100

                    # 只有偏差超过15%才告警
                    if abs(deviation) > 15:
                        # 使用DecisionAgent分析
                        analysis = await decision_agent.analyze_revenue_anomaly(
                            store_id=str(store.id),
                            current_revenue=current_revenue,
                            expected_revenue=expected_revenue,
                            time_period="today"
                        )

                        if analysis["success"]:
                            # 构建告警消息
                            alert_emoji = "⚠️" if deviation < 0 else "📈"
                            message = f"""{alert_emoji} 营收异常告警

门店: {store.name}
当前营收: ¥{current_revenue:.2f}
预期营收: ¥{expected_revenue:.2f}
偏差: {deviation:+.1f}%

AI分析:
{analysis['data']['analysis']}

时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""

                            # 发送企微告警
                            # TODO: 查询店长和管理员的企微ID
                            # await wechat_work_message_service.send_text_message(...)

                            logger.info(
                                "营收异常告警已生成",
                                store_id=str(store.id),
                                deviation=deviation
                            )
                            alerts_sent += 1

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


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
async def generate_daily_report_with_rag(
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

                        # 发送企微消息
                        # TODO: 查询店长和管理员的企微ID
                        # await wechat_work_message_service.send_text_message(...)

                        logger.info(
                            "昨日简报已生成",
                            store_id=str(store.id)
                        )
                        reports_sent += 1

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


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
async def check_inventory_alert(
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
    try:
        from datetime import datetime
        from ..agents.inventory_agent import InventoryAgent
        from ..services.wechat_work_message_service import wechat_work_message_service
        from ..models.store import Store
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
                    # TODO: 从数据库获取当前库存
                    # 这里使用模拟数据
                    current_inventory = {
                        "DISH001": 20,  # 宫保鸡丁
                        "DISH002": 50,  # 鱼香肉丝
                        "DISH003": 10,  # 麻婆豆腐
                    }

                    # 使用InventoryAgent检查低库存
                    alert_result = await inventory_agent.check_low_stock_alert(
                        store_id=str(store.id),
                        current_inventory=current_inventory,
                        threshold_hours=4  # 午高峰前4小时预警
                    )

                    if alert_result["success"]:
                        # 构建预警消息
                        message = f"""🔔 库存预警 (午高峰前)

门店: {store.name}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

AI分析:
{alert_result['data']['alert']}

当前库存状态:
{chr(10).join([f'• {dish_id}: {qty}份' for dish_id, qty in current_inventory.items()])}

请及时补货，确保午高峰供应充足。
"""

                        # 发送企微预警
                        # TODO: 查询店长和管理员的企微ID
                        # await wechat_work_message_service.send_text_message(...)

                        logger.info(
                            "库存预警已生成",
                            store_id=str(store.id)
                        )
                        alerts_sent += 1

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
