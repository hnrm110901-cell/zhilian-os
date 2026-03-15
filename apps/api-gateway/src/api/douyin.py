"""
抖音生活服务 API 端点
团购订单同步、券核销、结算查询等
"""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.models.order import Order
from src.services.douyin_service import DouyinService

router = APIRouter(prefix="/douyin", tags=["douyin"])

douyin_service = DouyinService()


# ── 请求体 ──────────────────────────────────────────────────────────


class SyncOrdersRequest(BaseModel):
    brand_id: str
    store_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class VerifyCouponRequest(BaseModel):
    brand_id: str
    code: str
    shop_id: str


# ── 订单接口 ────────────────────────────────────────────────────────


@router.post("/orders/sync")
async def sync_orders(
    body: SyncOrdersRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """从抖音同步团购订单"""
    start = body.start_time or (datetime.now() - timedelta(days=1)).isoformat()
    end = body.end_time or datetime.now().isoformat()

    try:
        result = await douyin_service.sync_orders(
            db=db,
            brand_id=body.brand_id,
            store_id=body.store_id,
            start_time=start,
            end_time=end,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("/orders")
async def list_orders(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    status: Optional[str] = Query(None, description="订单状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询已同步的抖音团购订单"""
    query = select(Order).where(
        Order.brand_id == brand_id,
        Order.source == "douyin",
    )
    if store_id:
        query = query.where(Order.store_id == store_id)
    if status:
        query = query.where(Order.status == status)

    query = query.order_by(Order.order_time.desc())

    # 总数
    from sqlalchemy import func

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "orders": [
            {
                "id": str(o.id),
                "external_order_id": o.external_order_id,
                "store_id": o.store_id,
                "status": o.status,
                "total_amount": o.total_amount,
                "discount_amount": o.discount_amount,
                "final_amount": o.final_amount,
                "order_time": o.order_time.isoformat() if o.order_time else None,
                "items_count": o.items_count,
            }
            for o in orders
        ],
    }


# ── 团购券接口 ──────────────────────────────────────────────────────


@router.get("/coupons")
async def list_coupons(
    brand_id: str = Query(..., description="品牌ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询团购券列表"""
    try:
        result = await douyin_service.get_coupons(
            brand_id=brand_id, page=page, page_size=page_size,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/coupons/verify")
async def verify_coupon(
    body: VerifyCouponRequest,
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """核销团购券"""
    try:
        result = await douyin_service.verify_coupon(
            brand_id=body.brand_id,
            code=body.code,
            shop_id=body.shop_id,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"核销失败: {str(e)}")


# ── 结算接口 ────────────────────────────────────────────────────────


@router.get("/settlements")
async def list_settlements(
    brand_id: str = Query(..., description="品牌ID"),
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)"),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询结算单列表"""
    try:
        result = await douyin_service.get_settlements(
            brand_id=brand_id,
            start_date=start_date,
            end_date=end_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ── 统计接口 ────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    brand_id: str = Query(..., description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """抖音业务总览统计"""
    try:
        stats = await douyin_service.get_stats(db=db, brand_id=brand_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"统计查询失败: {str(e)}")


# ── Webhook ─────────────────────────────────────────────────────────


@router.post("/webhook")
async def douyin_webhook(request: Request):
    """
    抖音回调通知（无需认证）

    处理团购券核销回调、订单状态变更等
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体解析失败")

    event_type = payload.get("event", "")
    import structlog

    log = structlog.get_logger()
    log.info("收到抖音 webhook", event_type=event_type)

    # 按事件类型分发处理
    if event_type == "coupon_verify":
        log.info("团购券核销回调", data=payload.get("data"))
    elif event_type == "order_status_change":
        log.info("订单状态变更回调", data=payload.get("data"))
    elif event_type == "settlement_notify":
        log.info("结算通知回调", data=payload.get("data"))
    else:
        log.warning("未知抖音 webhook 事件", event_type=event_type)

    return {"err_no": 0, "err_tips": "success"}
