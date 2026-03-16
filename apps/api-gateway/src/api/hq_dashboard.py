"""
总部跨店看板 API
HQ Cross-Store Dashboard
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from ..services.food_cost_service import FoodCostService

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
    from ..models.decision_log import DecisionLog, DecisionStatus
    from ..models.store import Store

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
            except Exception as e:
                logger.debug("hq_dashboard.store_cache_fetch_failed", store_id=getattr(store, "id", None), error=str(e))
                # 降级：使用默认值

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


@router.get("/hq/food-cost-variance")
async def get_food_cost_variance(
    store_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    门店食材成本差异分析：实际成本率 vs 理论成本率
    - 实际成本：库存 usage 事务汇总
    - 理论成本：激活 BOM 配方加权平均 food_cost%
    - Top 10 食材按实际消耗成本排序
    """
    if start_date is None:
        start_date = date.today() - timedelta(days=7)
    if end_date is None:
        end_date = date.today()

    try:
        result = await FoodCostService.get_store_food_cost_variance(
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )
        return result
    except Exception as e:
        logger.error("food_cost_variance_failed", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hq/food-cost-ranking")
async def get_food_cost_ranking(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    总部跨店食材成本排名（按差异率倒序）
    - 含门店级别汇总（ok/warning/critical）
    - 全局摘要（门店总数、平均食材成本率、超预算门店数）
    """
    if start_date is None:
        start_date = date.today() - timedelta(days=7)
    if end_date is None:
        end_date = date.today()

    try:
        result = await FoodCostService.get_hq_food_cost_ranking(
            start_date=start_date,
            end_date=end_date,
            db=db,
        )
        return result
    except Exception as e:
        logger.error("food_cost_ranking_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
