"""
排队管理API
Queue Management API
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional
import structlog

from ..services.queue_service import queue_service, QueueStatus
from ..core.dependencies import get_current_user
from ..schemas.user import User

router = APIRouter(prefix="/api/v1/queue", tags=["Queue"])
logger = structlog.get_logger()


@router.post("/add")
async def add_to_queue(
    customer_name: str = Body(...),
    customer_phone: str = Body(...),
    party_size: int = Body(..., ge=1, le=20),
    special_requests: Optional[str] = Body(None),
    store_id: Optional[str] = Body(None),
    current_user: User = Depends(get_current_user),
):
    """
    添加到排队队列

    Args:
        customer_name: 客户姓名
        customer_phone: 客户电话
        party_size: 就餐人数
        special_requests: 特殊要求
        store_id: 门店ID
    """
    try:
        # 如果用户不是超级管理员，使用用户所属门店
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        if not store_id:
            raise HTTPException(status_code=400, detail="门店ID不能为空")

        result = await queue_service.add_to_queue(
            store_id=store_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            party_size=party_size,
            special_requests=special_requests,
        )

        return result

    except Exception as e:
        logger.error("添加排队失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"添加排队失败: {str(e)}")


@router.post("/call-next")
async def call_next(
    store_id: Optional[str] = Body(None),
    table_number: Optional[str] = Body(None),
    current_user: User = Depends(get_current_user),
):
    """
    叫号（叫下一位）

    Args:
        store_id: 门店ID
        table_number: 分配的桌号
    """
    try:
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        if not store_id:
            raise HTTPException(status_code=400, detail="门店ID不能为空")

        result = await queue_service.call_next(
            store_id=store_id,
            table_number=table_number,
        )

        return result

    except Exception as e:
        logger.error("叫号失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"叫号失败: {str(e)}")


@router.put("/{queue_id}/seated")
async def mark_seated(
    queue_id: str,
    table_number: str = Body(...),
    current_user: User = Depends(get_current_user),
):
    """
    标记为已入座

    Args:
        queue_id: 排队ID
        table_number: 桌号
    """
    try:
        result = await queue_service.mark_seated(
            queue_id=queue_id,
            table_number=table_number,
        )

        return result

    except Exception as e:
        logger.error("标记入座失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"标记入座失败: {str(e)}")


@router.delete("/{queue_id}")
async def cancel_queue(
    queue_id: str,
    reason: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
):
    """
    取消排队

    Args:
        queue_id: 排队ID
        reason: 取消原因
    """
    try:
        result = await queue_service.cancel_queue(
            queue_id=queue_id,
            reason=reason,
        )

        return result

    except Exception as e:
        logger.error("取消排队失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"取消排队失败: {str(e)}")


@router.get("/list")
async def get_queue_list(
    store_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """
    获取排队列表

    Args:
        store_id: 门店ID
        status: 状态筛选（waiting, called, seated, cancelled）
        limit: 返回数量
    """
    try:
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        if not store_id:
            raise HTTPException(status_code=400, detail="门店ID不能为空")

        # 转换状态
        queue_status = None
        if status:
            try:
                queue_status = QueueStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的状态: {status}")

        queues = await queue_service.get_queue_list(
            store_id=store_id,
            status=queue_status,
            limit=limit,
        )

        return {
            "success": True,
            "data": queues,
            "total": len(queues),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取排队列表失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取排队列表失败: {str(e)}")


@router.get("/stats")
async def get_queue_stats(
    store_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """
    获取排队统计

    Args:
        store_id: 门店ID
    """
    try:
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        if not store_id:
            raise HTTPException(status_code=400, detail="门店ID不能为空")

        stats = await queue_service.get_queue_stats(store_id=store_id)

        return {
            "success": True,
            "data": stats,
        }

    except Exception as e:
        logger.error("获取排队统计失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取排队统计失败: {str(e)}")


@router.get("/{queue_id}")
async def get_queue_detail(
    queue_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取排队详情

    Args:
        queue_id: 排队ID
    """
    try:
        from ..models.queue import Queue
        from ..core.database import get_session
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(Queue).where(Queue.queue_id == queue_id)
            )
            queue = result.scalar_one_or_none()

            if not queue:
                raise HTTPException(status_code=404, detail="排队记录不存在")

            return {
                "success": True,
                "data": queue.to_dict(),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取排队详情失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取排队详情失败: {str(e)}")
