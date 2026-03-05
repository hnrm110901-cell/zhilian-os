"""
门店健康指数 API

GET /api/v1/stores/health?date=YYYY-MM-DD
    — 返回所有活跃门店的健康评分排名

MVP #2（每日利润快报）+ v2.1 StoreHealthScore 扩展：
  系统主动找老板，老板一眼看出5家店哪家有问题
"""

from datetime import date, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()

_LEVEL_LABEL: dict = {
    "excellent": "优秀",
    "good":      "良好",
    "warning":   "需关注",
    "critical":  "危险",
}
_LEVEL_COLOR: dict = {
    "excellent": "green",
    "good":      "blue",
    "warning":   "orange",
    "critical":  "red",
}
_DIM_LABEL: dict = {
    "revenue_completion": "营收完成率",
    "table_turnover":     "翻台率",
    "cost_rate":          "成本率",
    "complaint_rate":     "客诉率",
    "staff_efficiency":   "人效",
}


@router.get("/stores/health")
async def get_stores_health(
    target_date: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取所有活跃门店的健康评分排名。

    Query params:
        target_date (optional): 目标日期，默认昨日

    Returns::

        {
            "target_date": "2026-03-04",
            "stores": [
                {
                    "rank": 1,
                    "store_id": "S001",
                    "store_name": "芙蓉区店",
                    "score": 87.5,
                    "level": "excellent",
                    "level_label": "优秀",
                    "level_color": "green",
                    "dimensions": {"revenue_completion": {"score": 92.0}, ...},
                    "weakest_dimension": "cost_rate",
                    "weakest_label": "成本率",
                    "revenue_yuan": 12400.0,
                }
            ],
            "summary": {
                "total": 5,
                "excellent": 1,
                "good": 2,
                "warning": 1,
                "critical": 1,
            }
        }
    """
    from ..models.store import Store
    from ..services.store_health_service import StoreHealthService

    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    try:
        # 获取所有活跃门店
        result = await db.execute(select(Store).where(Store.is_active == True))
        stores = result.scalars().all()

        if not stores:
            return {
                "target_date": target_date.isoformat(),
                "stores": [],
                "summary": {"total": 0, "excellent": 0, "good": 0, "warning": 0, "critical": 0},
            }

        store_ids = [s.id for s in stores]

        # 批量评分（内部串行，单店失败静默跳过）
        scored = await StoreHealthService.get_multi_store_scores(
            store_ids=store_ids,
            target_date=target_date,
            db=db,
        )

        # 增加展示层字段
        for item in scored:
            lvl = item.get("level", "warning")
            item["level_label"] = _LEVEL_LABEL.get(lvl, lvl)
            item["level_color"] = _LEVEL_COLOR.get(lvl, "default")
            wd = item.get("weakest_dimension")
            item["weakest_label"] = _DIM_LABEL.get(wd, wd) if wd else None

        # 汇总
        summary = {
            "total":     len(scored),
            "excellent": sum(1 for x in scored if x.get("level") == "excellent"),
            "good":      sum(1 for x in scored if x.get("level") == "good"),
            "warning":   sum(1 for x in scored if x.get("level") == "warning"),
            "critical":  sum(1 for x in scored if x.get("level") == "critical"),
        }

        return {
            "target_date": target_date.isoformat(),
            "stores":      scored,
            "summary":     summary,
        }

    except Exception as exc:
        logger.error("stores_health_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
