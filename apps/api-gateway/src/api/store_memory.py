"""
ARCH-003: 门店记忆层 API

GET  /api/v1/stores/{store_id}/memory          — 获取门店记忆快照
POST /api/v1/stores/{store_id}/memory/refresh  — 手动触发记忆更新
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status
import structlog

from src.services.store_memory_service import StoreMemoryService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/stores", tags=["store-memory"])


@router.get("/{store_id}/memory")
async def get_store_memory(store_id: str):
    """
    获取门店记忆快照

    返回门店的运营模式记忆：高峰时段、员工基线、菜品健康度、异常模式。
    数据来自 Redis 缓存（TTL 72小时），无缓存时返回 404。
    """
    service = StoreMemoryService()
    memory = await service.get_memory(store_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": f"门店 '{store_id}' 的记忆数据尚未生成",
                "hint": f"POST /api/v1/stores/{store_id}/memory/refresh 可触发生成",
            },
        )

    return {
        "store_id": memory.store_id,
        "brand_id": memory.brand_id,
        "updated_at": memory.updated_at.isoformat(),
        "confidence": memory.confidence,
        "data_coverage_days": memory.data_coverage_days,
        "peak_patterns": [p.model_dump() for p in memory.peak_patterns],
        "staff_profiles": [s.model_dump() for s in memory.staff_profiles],
        "dish_health": [d.model_dump() for d in memory.dish_health],
        "anomaly_patterns": [a.model_dump() for a in memory.anomaly_patterns],
    }


@router.post("/{store_id}/memory/refresh")
async def refresh_store_memory(
    store_id: str,
    lookback_days: int = 30,
    brand_id: Optional[str] = None,
):
    """
    手动触发门店记忆更新

    触发 StoreMemoryService 计算并写入 Redis，
    也可通过 Celery Beat 每日凌晨2点自动触发。
    """
    try:
        service = StoreMemoryService()
        memory = await service.refresh_store_memory(
            store_id=store_id,
            brand_id=brand_id,
            lookback_days=lookback_days,
        )
        return {
            "store_id": memory.store_id,
            "status": "refreshed",
            "confidence": memory.confidence,
            "data_coverage_days": memory.data_coverage_days,
            "updated_at": memory.updated_at.isoformat(),
            "peak_patterns_count": len(memory.peak_patterns),
            "staff_profiles_count": len(memory.staff_profiles),
            "dish_health_count": len(memory.dish_health),
        }
    except Exception as e:
        logger.error("store_memory.refresh_api_failed", store_id=store_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "记忆刷新失败，请稍后重试"},
        )
