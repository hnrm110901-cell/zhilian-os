"""
客户360画像API
Customer 360 Profile API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import structlog

from ..services.customer360_service import customer360_service
from ..core.dependencies import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/v1/customer360", tags=["Customer360"])
logger = structlog.get_logger()


@router.get("/profile")
async def get_customer_profile(
    customer_identifier: str = Query(..., description="客户标识（手机号、会员ID等）"),
    identifier_type: str = Query("phone", description="标识类型: phone, member_id, email"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    current_user: User = Depends(get_current_user),
):
    """
    获取客户360画像

    返回客户的完整画像，包括：
    - 会员基础信息
    - 订单历史
    - 预订记录
    - POS交易记录
    - 客户时间线
    - 客户价值指标
    - 客户标签
    """
    try:
        # 如果用户不是超级管理员，使用用户所属门店
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        profile = await customer360_service.get_customer_profile(
            customer_identifier=customer_identifier,
            identifier_type=identifier_type,
            store_id=store_id,
        )

        return {
            "success": True,
            "data": profile,
        }

    except Exception as e:
        logger.error(
            "获取客户360画像失败",
            identifier=customer_identifier,
            error=str(e),
            exc_info=e,
        )
        raise HTTPException(status_code=500, detail=f"获取客户画像失败: {str(e)}")


@router.get("/timeline")
async def get_customer_timeline(
    customer_identifier: str = Query(..., description="客户标识"),
    identifier_type: str = Query("phone", description="标识类型"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    limit: int = Query(50, ge=1, le=200, description="返回事件数量"),
    current_user: User = Depends(get_current_user),
):
    """
    获取客户时间线

    返回客户的所有活动事件，按时间倒序排列
    """
    try:
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        profile = await customer360_service.get_customer_profile(
            customer_identifier=customer_identifier,
            identifier_type=identifier_type,
            store_id=store_id,
        )

        timeline = profile.get("timeline", [])[:limit]

        return {
            "success": True,
            "data": {
                "customer_identifier": customer_identifier,
                "timeline": timeline,
                "total_events": len(profile.get("timeline", [])),
            },
        }

    except Exception as e:
        logger.error("获取客户时间线失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取客户时间线失败: {str(e)}")


@router.get("/value")
async def get_customer_value(
    customer_identifier: str = Query(..., description="客户标识"),
    identifier_type: str = Query("phone", description="标识类型"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    current_user: User = Depends(get_current_user),
):
    """
    获取客户价值指标

    返回客户的RFM评分、消费统计等价值指标
    """
    try:
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        profile = await customer360_service.get_customer_profile(
            customer_identifier=customer_identifier,
            identifier_type=identifier_type,
            store_id=store_id,
        )

        return {
            "success": True,
            "data": {
                "customer_identifier": customer_identifier,
                "customer_value": profile.get("customer_value", {}),
                "customer_tags": profile.get("customer_tags", []),
                "statistics": profile.get("statistics", {}),
            },
        }

    except Exception as e:
        logger.error("获取客户价值指标失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取客户价值指标失败: {str(e)}")


@router.get("/search")
async def search_customers(
    query: str = Query(..., min_length=2, description="搜索关键词（姓名、手机号）"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    current_user: User = Depends(get_current_user),
):
    """
    搜索客户

    根据姓名或手机号搜索客户
    """
    try:
        if not current_user.is_super_admin and current_user.store_id:
            store_id = current_user.store_id

        from src.core.database import get_db_session
        from src.models.order import Order, OrderStatus
        from sqlalchemy import select, func, or_

        async with get_db_session() as session:
            conditions = [
                or_(
                    Order.customer_phone.ilike(f"%{query}%"),
                    Order.customer_name.ilike(f"%{query}%"),
                )
            ]
            if store_id:
                conditions.append(Order.store_id == store_id)

            from sqlalchemy import and_
            rows = (await session.execute(
                select(
                    Order.customer_phone,
                    Order.customer_name,
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.final_amount).label("total_spend"),
                    func.max(Order.order_time).label("last_visit"),
                )
                .where(and_(*conditions))
                .group_by(Order.customer_phone, Order.customer_name)
                .order_by(func.max(Order.order_time).desc())
                .limit(limit)
            )).all()

        results = [
            {
                "phone": r.customer_phone,
                "name": r.customer_name,
                "order_count": r.order_count,
                "total_spend": round((r.total_spend or 0) / 100, 2),
                "last_visit": r.last_visit.isoformat() if r.last_visit else None,
            }
            for r in rows
        ]

        return {
            "success": True,
            "data": {
                "query": query,
                "results": results,
                "total": len(results),
            },
            "message": "success",
        }

    except Exception as e:
        logger.error("搜索客户失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"搜索客户失败: {str(e)}")
