"""
门店对标与评分 API

端点：
  GET  /api/v1/benchmarks/{store_id}/ranking        — 同品牌门店排名
  GET  /api/v1/benchmarks/{store_id}/peers           — 标杆门店发现
  GET  /api/v1/benchmarks/{store_id}/gap             — 差距分析
  GET  /api/v1/benchmarks/{store_id}/scorecard       — 门店评分卡
  GET  /api/v1/benchmarks/brand/{brand_id}/insights  — 品牌跨店洞察
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, validate_store_brand
from ..models.user import User
from ..services.benchmark_engine_service import BenchmarkEngineService

logger = structlog.get_logger()
router = APIRouter()


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/benchmarks/{store_id}/ranking",
    summary="同品牌门店排名",
    tags=["benchmarks"],
)
async def get_peer_ranking(
    store_id: str,
    period_type: str = Query(default="monthly", description="周期类型: monthly|weekly|daily"),
    metric: str = Query(default="revenue_fen", description="排名指标: revenue_fen|order_count|avg_ticket_fen"),
    limit: int = Query(default=20, ge=1, le=100, description="返回门店数量上限"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取同品牌门店在指定指标上的排名"""
    await validate_store_brand(store_id, current_user)

    try:
        service = BenchmarkEngineService(db)
        result = await service.get_peer_ranking(
            store_id=store_id,
            period_type=period_type,
            metric=metric,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "peer_ranking_fetched",
        store_id=store_id,
        period_type=period_type,
        metric=metric,
        result_count=len(result.get("rankings", [])),
    )

    return {
        "store_id": store_id,
        "period_type": period_type,
        "metric": metric,
        "rankings": result.get("rankings", []),
        "my_rank": result.get("my_rank"),
        "total_stores": result.get("total_stores", 0),
    }


@router.get(
    "/benchmarks/{store_id}/peers",
    summary="标杆门店发现",
    tags=["benchmarks"],
)
async def find_benchmark_stores(
    store_id: str,
    top_n: int = Query(default=3, ge=1, le=10, description="返回标杆门店数"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """发现与当前门店条件相近的标杆门店，供对标学习"""
    await validate_store_brand(store_id, current_user)

    try:
        service = BenchmarkEngineService(db)
        result = await service.find_benchmark_stores(
            store_id=store_id,
            top_n=top_n,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "benchmark_peers_found",
        store_id=store_id,
        top_n=top_n,
        peer_count=len(result.get("peers", [])),
    )

    return {
        "store_id": store_id,
        "top_n": top_n,
        "peers": result.get("peers", []),
    }


@router.get(
    "/benchmarks/{store_id}/gap",
    summary="差距分析",
    tags=["benchmarks"],
)
async def gap_analysis(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """与标杆门店的多维度差距分析，含改进建议"""
    await validate_store_brand(store_id, current_user)

    try:
        service = BenchmarkEngineService(db)
        result = await service.gap_analysis(store_id=store_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "gap_analysis_completed",
        store_id=store_id,
        gap_count=len(result.get("gaps", [])),
    )

    return {
        "store_id": store_id,
        "gaps": result.get("gaps", []),
        "recommendations": result.get("recommendations", []),
        "overall_gap_score": result.get("overall_gap_score"),
    }


@router.get(
    "/benchmarks/{store_id}/scorecard",
    summary="门店评分卡",
    tags=["benchmarks"],
)
async def get_store_scorecard(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取门店综合评分卡（财务/客户/流程/学习四维度）"""
    await validate_store_brand(store_id, current_user)

    try:
        service = BenchmarkEngineService(db)
        result = await service.get_store_scorecard(store_id=store_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "scorecard_fetched",
        store_id=store_id,
        overall_score=result.get("overall_score"),
    )

    return {
        "store_id": store_id,
        "overall_score": result.get("overall_score"),
        "dimensions": result.get("dimensions", {}),
        "trend": result.get("trend", []),
        "updated_at": result.get("updated_at"),
    }


@router.get(
    "/benchmarks/brand/{brand_id}/insights",
    summary="品牌跨店洞察",
    tags=["benchmarks"],
)
async def cross_store_insights(
    brand_id: str,
    period_type: str = Query(default="monthly", description="周期类型: monthly|weekly|daily"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """品牌维度的跨门店洞察：最佳实践、共性问题、改进空间"""
    # 品牌级别权限验证：用户必须属于该品牌
    if current_user.brand_id and current_user.brand_id != brand_id:
        raise HTTPException(status_code=403, detail="无权访问该品牌数据")

    try:
        service = BenchmarkEngineService(db)
        result = await service.cross_store_insights(
            brand_id=brand_id,
            period_type=period_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "cross_store_insights_fetched",
        brand_id=brand_id,
        period_type=period_type,
        store_count=result.get("store_count", 0),
    )

    return {
        "brand_id": brand_id,
        "period_type": period_type,
        "store_count": result.get("store_count", 0),
        "insights": result.get("insights", []),
        "best_practices": result.get("best_practices", []),
        "common_issues": result.get("common_issues", []),
    }
