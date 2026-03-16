"""菜品成本压缩机会 API — Phase 6 Month 11"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.dish_cost_compression_service import (
    compute_cost_compression,
    get_compression_summary,
    get_cost_compression,
    get_dish_fcr_history,
    get_top_opportunities,
)

router = APIRouter(prefix="/api/v1/cost-compression", tags=["cost-compression"])

_VALID_ACTIONS = {"renegotiate", "reformulate", "adjust_portion", "monitor"}
_VALID_PRIORITIES = {"high", "medium", "low"}


@router.post("/compute/{store_id}")
async def api_compute(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    target_fcr_reduction: float = Query(2.0, ge=0.5, le=10.0, description="目标降低几个百分点（默认2pp）"),
    db: AsyncSession = Depends(get_db),
):
    """触发成本压缩机会计算并写入数据库（幂等）。"""
    result = await compute_cost_compression(db, store_id, period, target_fcr_reduction=target_fcr_reduction)
    return {"ok": True, "data": result}


@router.get("/{store_id}")
async def api_get_compression(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    action: Optional[str] = Query(None, description="renegotiate/reformulate/adjust_portion/monitor"),
    priority: Optional[str] = Query(None, description="high/medium/low"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询压缩机会明细，可按行动类型或优先级筛选（互斥，action 优先）。"""
    if action and action not in _VALID_ACTIONS:
        return {"ok": False, "error": f"action 必须是 {_VALID_ACTIONS} 之一"}
    if priority and priority not in _VALID_PRIORITIES:
        return {"ok": False, "error": f"priority 必须是 {_VALID_PRIORITIES} 之一"}
    rows = await get_cost_compression(db, store_id, period, action=action, priority=priority, limit=limit)
    return {"ok": True, "data": rows}


@router.get("/summary/{store_id}")
async def api_get_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按行动类型和 FCR 趋势聚合统计。"""
    result = await get_compression_summary(db, store_id, period)
    return {"ok": True, "data": result}


@router.get("/top/{store_id}")
async def api_get_top(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """压缩机会（可节省¥）最大的 Top-N 菜品。"""
    rows = await get_top_opportunities(db, store_id, period, limit=limit)
    return {"ok": True, "data": rows}


@router.get("/dish/{store_id}/{dish_id}")
async def api_get_dish_history(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期的 FCR 历史及压缩机会变化。"""
    rows = await get_dish_fcr_history(db, store_id, dish_id, periods=periods)
    return {"ok": True, "data": rows}


@router.get("/meta/actions")
async def api_meta_actions():
    """返回行动类型枚举说明。"""
    return {
        "ok": True,
        "data": [
            {"value": "renegotiate", "label": "重新谈判", "description": "FCR超标>5pp且持续恶化，与供应商重新谈判食材采购价"},
            {"value": "reformulate", "label": "调整配方", "description": "FCR超标3-5pp，优化配方、替换原料或调整用量比例"},
            {"value": "adjust_portion", "label": "调整份量", "description": "FCR超标1-3pp，微调标准份量或精细化称重管控"},
            {"value": "monitor", "label": "持续监控", "description": "FCR已达目标或缺口<1pp，维持现状定期复查"},
        ],
    }
