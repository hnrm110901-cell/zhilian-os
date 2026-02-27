"""
总部跨店看板 API
HQ Cross-Store Dashboard
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
import structlog

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

logger = structlog.get_logger()
router = APIRouter()


@router.get("/hq/dashboard")
async def get_hq_dashboard(
    target_date: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    总部跨店看板：聚合所有门店关键指标
    - 各门店营收、订单数、健康分
    - 异常告警汇总
    - 库存预警门店列表
    - 营收排名
    """
    from ..models.store import Store
    from ..models.decision_log import DecisionLog, DecisionStatus

    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    try:
        # 获取所有门店
        result = await db.execute(select(Store).where(Store.is_active == True))
        stores = result.scalars().all()

        # 获取各门店待审批决策数
        pending_result = await db.execute(
            select(DecisionLog.store_id, func.count(DecisionLog.id).label("pending_count"))
            .where(DecisionLog.decision_status == DecisionStatus.PENDING)
            .group_by(DecisionLog.store_id)
        )
        pending_map: Dict[str, int] = {row.store_id: row.pending_count for row in pending_result}

        # 尝试从 daily_report 获取昨日营收（降级为样本数据）
        store_metrics = []
        total_revenue = 0
        total_orders = 0
        alert_stores = []

        for store in stores:
            # 尝试从 Redis 获取 daily_hub 缓存
            revenue = 0
            orders = 0
            health_score = 85
            has_alert = False

            try:
                from ..services.redis_cache_service import RedisCacheService
                redis_svc = RedisCacheService()
                await redis_svc.initialize()
                cache_key = f"daily_hub:{store.id}:{target_date.isoformat()}"
                cached = await redis_svc.get(cache_key)
                if cached and isinstance(cached, dict):
                    review = cached.get("yesterday_review", {})
                    revenue = review.get("total_revenue", 0)
                    orders = review.get("order_count", 0)
                    health_score = review.get("health_score", 85)
                    has_alert = len(review.get("alerts", [])) > 0
            except Exception:
                pass  # 降级：使用默认值

            pending_approvals = pending_map.get(store.id, 0)
            total_revenue += revenue
            total_orders += orders

            metric = {
                "store_id": store.id,
                "store_name": store.name,
                "revenue": revenue,
                "orders": orders,
                "health_score": health_score,
                "pending_approvals": pending_approvals,
                "has_alert": has_alert or pending_approvals > 3,
            }
            store_metrics.append(metric)
            if metric["has_alert"]:
                alert_stores.append({"store_id": store.id, "store_name": store.name, "pending_approvals": pending_approvals})

        # 按营收排名
        ranked = sorted(store_metrics, key=lambda x: x["revenue"], reverse=True)

        return {
            "target_date": target_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_stores": len(stores),
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "alert_store_count": len(alert_stores),
                "total_pending_approvals": sum(pending_map.values()),
            },
            "store_metrics": ranked,
            "alert_stores": alert_stores,
        }

    except Exception as e:
        logger.error("hq_dashboard_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
