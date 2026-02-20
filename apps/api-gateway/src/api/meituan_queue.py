"""
美团等位集成API
Meituan Queue Integration API
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from typing import Optional, Dict, Any
import structlog

from ..services.meituan_queue_integration import meituan_queue_integration
from ..services.meituan_queue_service import meituan_queue_service
from ..core.dependencies import get_current_user
from ..schemas.user import User

router = APIRouter(prefix="/api/v1/meituan/queue", tags=["Meituan Queue"])
logger = structlog.get_logger()


@router.post("/webhook/user-queue")
async def handle_user_queue_webhook(
    request: Request,
):
    """
    处理美团用户取号推送

    当用户通过美团/大众点评App取号时，美团会推送到此接口

    请求体示例:
    {
        "orderViewId": "meituan_order_123",
        "customerName": "张三",
        "customerPhone": "13800138000",
        "partySize": 4,
        "tableTypeId": 1,
        "storeId": "store_123",
        "appAuthToken": "xxx"
    }
    """
    try:
        # 获取请求数据
        data = await request.json()

        order_view_id = data.get("orderViewId")
        customer_name = data.get("customerName", "美团用户")
        customer_phone = data.get("customerPhone", "")
        party_size = data.get("partySize", 2)
        table_type_id = data.get("tableTypeId", 1)
        store_id = data.get("storeId")
        app_auth_token = data.get("appAuthToken")

        if not all([order_view_id, store_id, app_auth_token]):
            raise HTTPException(status_code=400, detail="缺少必要参数")

        # 处理线上取号
        result = await meituan_queue_integration.handle_meituan_online_queue(
            order_view_id=order_view_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            party_size=party_size,
            table_type_id=table_type_id,
            store_id=store_id,
            app_auth_token=app_auth_token,
        )

        return {
            "success": result["success"],
            "data": result.get("queue_data"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("处理美团用户取号推送失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.post("/sync/table-types")
async def sync_table_types(
    store_id: str = Body(...),
    app_auth_token: str = Body(...),
    table_types: list = Body(...),
    current_user: User = Depends(get_current_user),
):
    """
    同步桌型配置到美团

    请求体示例:
    {
        "storeId": "store_123",
        "appAuthToken": "xxx",
        "tableTypes": [
            {
                "tableTypeId": 1,
                "tableTypeName": "小桌",
                "displayName": "小桌(2-4人)",
                "minCapacity": 2,
                "maxCapacity": 4,
                "numPrefix": "A",
                "operateType": 1
            }
        ]
    }
    """
    try:
        result = await meituan_queue_service.sync_table_types(
            app_auth_token=app_auth_token,
            table_types=table_types,
        )

        return {
            "success": result.get("code") == "OP_SUCCESS",
            "message": result.get("msg"),
            "data": result.get("data"),
        }

    except Exception as e:
        logger.error("同步桌型到美团失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.post("/sync/queue-status")
async def sync_queue_status(
    queue_id: str = Body(...),
    order_view_id: str = Body(...),
    app_auth_token: str = Body(...),
    current_user: User = Depends(get_current_user),
):
    """
    同步排队状态到美团

    请求体示例:
    {
        "queueId": "local_queue_123",
        "orderViewId": "meituan_order_123",
        "appAuthToken": "xxx"
    }
    """
    try:
        from ..models.queue import Queue
        from ..core.database import get_session
        from sqlalchemy import select

        # 获取排队记录
        async with get_session() as session:
            result = await session.execute(
                select(Queue).where(Queue.queue_id == queue_id)
            )
            queue = result.scalar_one_or_none()

            if not queue:
                raise HTTPException(status_code=404, detail="排队记录不存在")

        # 同步状态到美团
        success = await meituan_queue_integration.update_queue_status_to_meituan(
            queue=queue,
            app_auth_token=app_auth_token,
            order_view_id=order_view_id,
        )

        return {
            "success": success,
            "message": "状态已同步" if success else "同步失败",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("同步排队状态到美团失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.post("/sync/waiting-info")
async def sync_waiting_info(
    store_id: str = Body(...),
    app_auth_token: str = Body(...),
    current_user: User = Depends(get_current_user),
):
    """
    同步等位信息到美团

    自动获取当前门店的等位信息并同步到美团
    """
    try:
        from ..services.queue_service import queue_service, QueueStatus

        # 获取当前等待的排队列表
        queues = await queue_service.get_queue_list(
            store_id=store_id,
            status=QueueStatus.WAITING,
            limit=100,
        )

        # 构建订单等位列表
        order_wait_list = []
        for queue in queues:
            # 假设已经有美团订单ID存储在notes字段
            # 实际应该在Queue模型中添加meituan_order_view_id字段
            order_wait_list.append({
                "orderViewId": queue.get("notes", ""),  # 需要改进
                "orderId": queue["queue_id"],
                "index": len(order_wait_list) + 1,
            })

        # 构建桌型等位列表（简化版本，实际需要按桌型统计）
        table_type_wait_list = [
            {
                "tableTypeId": 1,
                "waitCount": len(queues),
            }
        ]

        # 同步到美团
        result = await meituan_queue_service.sync_waiting_info(
            app_auth_token=app_auth_token,
            order_wait_list=order_wait_list,
            table_type_wait_list=table_type_wait_list,
        )

        return {
            "success": result.get("code") == "OP_SUCCESS",
            "message": result.get("msg"),
            "data": {
                "order_count": len(order_wait_list),
                "table_type_count": len(table_type_wait_list),
            },
        }

    except Exception as e:
        logger.error("同步等位信息到美团失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("/config")
async def get_meituan_config(
    current_user: User = Depends(get_current_user),
):
    """
    获取美团等位配置

    返回当前的美团等位集成配置信息
    """
    try:
        return {
            "success": True,
            "data": {
                "business_id": "49",
                "base_url": "https://api-open-cater.meituan.com",
                "enabled": True,
                "features": [
                    "线上线下排队统一",
                    "自动同步排队状态",
                    "美团/大众点评双端展示",
                    "微信公众号通知",
                ],
            },
        }

    except Exception as e:
        logger.error("获取美团配置失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")
