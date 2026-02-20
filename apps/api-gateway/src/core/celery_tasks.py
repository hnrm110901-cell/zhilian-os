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

        # 2. 根据事件类型调用相应的处理任务
        if event_type.startswith("order."):
            await index_order_to_vector_db.delay(data)
        elif event_type.startswith("dish."):
            await index_dish_to_vector_db.delay(data)

        # 3. 标记为已处理
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
    max_retries=2,
    default_retry_delay=300,  # 5分钟
)
async def train_federated_model(
    self,
    store_id: str,
    model_type: str = "demand_forecast",
) -> Dict[str, Any]:
    """
    训练联邦学习模型（低优先级任务）

    Args:
        store_id: 门店ID
        model_type: 模型类型

    Returns:
        训练结果
    """
    try:
        from ..services.federated_learning_service import federated_learning_service

        logger.info(
            "开始联邦学习模型训练",
            store_id=store_id,
            model_type=model_type,
        )

        # 参与联邦学习
        result = await federated_learning_service.participate_in_training(
            store_id=store_id,
            model_type=model_type,
        )

        logger.info(
            "联邦学习模型训练完成",
            store_id=store_id,
            model_type=model_type,
        )

        return {
            "success": True,
            "store_id": store_id,
            "model_type": model_type,
            "result": result,
        }

    except Exception as e:
        logger.error(
            "联邦学习模型训练失败",
            store_id=store_id,
            error=str(e),
            exc_info=e,
        )
        raise self.retry(exc=e)


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
