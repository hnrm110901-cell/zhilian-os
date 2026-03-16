"""
RFM 阈值管理 API — P1 补齐（易订PRO 2.2 客户价值设置）

管理门店级别的 RFM 评分阈值：
- 不同品牌/门店的消费频次、金额、周期标准不同
- 支持自定义 S1-S5 各档位的划分阈值
- 用于 dining_journey_service._calc_rfm_level() 动态读取
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

router = APIRouter()

# 默认 RFM 阈值（全局兜底）
DEFAULT_RFM_THRESHOLDS = {
    "recency": {
        "description": "最近一次消费距今天数",
        "S1": {"max_days": 7, "label": "活跃"},
        "S2": {"max_days": 14, "label": "近期"},
        "S3": {"max_days": 30, "label": "一般"},
        "S4": {"max_days": 60, "label": "流失风险"},
        "S5": {"max_days": 999, "label": "沉睡"},
    },
    "frequency": {
        "description": "过去90天消费次数",
        "S1": {"min_visits": 8, "label": "超高频"},
        "S2": {"min_visits": 5, "label": "高频"},
        "S3": {"min_visits": 3, "label": "中频"},
        "S4": {"min_visits": 1, "label": "低频"},
        "S5": {"min_visits": 0, "label": "零消费"},
    },
    "monetary": {
        "description": "过去90天累计消费（元）",
        "S1": {"min_amount": 3000, "label": "高价值"},
        "S2": {"min_amount": 1500, "label": "中高价值"},
        "S3": {"min_amount": 500, "label": "中价值"},
        "S4": {"min_amount": 100, "label": "低价值"},
        "S5": {"min_amount": 0, "label": "微价值"},
    },
}

# 内存缓存（生产环境应用 Redis）
_store_rfm_cache: Dict[str, Dict] = {}


class RFMThresholdRequest(BaseModel):
    store_id: str
    thresholds: Dict[str, Any]  # 完整的 RFM 阈值配置


@router.get("/api/v1/rfm-config/defaults")
async def get_default_thresholds(
    current_user: User = Depends(get_current_active_user),
):
    """获取系统默认 RFM 阈值（供参考/初始化）"""
    return {"thresholds": DEFAULT_RFM_THRESHOLDS}


@router.get("/api/v1/rfm-config/{store_id}")
async def get_store_rfm_config(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店的 RFM 阈值配置（无自定义则返回默认）"""
    # 优先从缓存读取
    if store_id in _store_rfm_cache:
        return {
            "store_id": store_id,
            "source": "custom",
            "thresholds": _store_rfm_cache[store_id],
        }

    # 尝试从数据库读取（存在 stores 表的 metadata 字段中）
    from sqlalchemy import select

    from ..models.store import Store

    result = await session.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if store and hasattr(store, "metadata_json"):
        meta = store.metadata_json or {}
        if isinstance(meta, dict) and "rfm_thresholds" in meta:
            thresholds = meta["rfm_thresholds"]
            _store_rfm_cache[store_id] = thresholds
            return {
                "store_id": store_id,
                "source": "custom",
                "thresholds": thresholds,
            }

    return {
        "store_id": store_id,
        "source": "default",
        "thresholds": DEFAULT_RFM_THRESHOLDS,
    }


@router.put("/api/v1/rfm-config/{store_id}")
async def update_store_rfm_config(
    store_id: str,
    req: RFMThresholdRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新门店的 RFM 阈值配置"""
    # 验证结构
    for dimension in ["recency", "frequency", "monetary"]:
        if dimension not in req.thresholds:
            raise HTTPException(
                status_code=400,
                detail=f"缺少维度 {dimension}，必须包含 recency/frequency/monetary",
            )
        dim_config = req.thresholds[dimension]
        for level in ["S1", "S2", "S3", "S4", "S5"]:
            if level not in dim_config:
                raise HTTPException(
                    status_code=400,
                    detail=f"{dimension} 缺少等级 {level}",
                )

    # 存入缓存
    _store_rfm_cache[store_id] = req.thresholds

    # 持久化到 store metadata（尝试写入）
    try:
        from sqlalchemy import select

        from ..models.store import Store

        result = await session.execute(select(Store).where(Store.id == store_id))
        store = result.scalar_one_or_none()
        if store and hasattr(store, "metadata_json"):
            meta = store.metadata_json or {}
            if not isinstance(meta, dict):
                meta = {}
            meta["rfm_thresholds"] = req.thresholds
            store.metadata_json = meta
            await session.commit()
    except Exception:
        pass  # 缓存已更新，持久化失败不阻塞

    return {
        "store_id": store_id,
        "message": "RFM阈值配置已更新",
        "thresholds": req.thresholds,
    }


@router.delete("/api/v1/rfm-config/{store_id}")
async def reset_store_rfm_config(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """重置门店 RFM 配置为系统默认"""
    _store_rfm_cache.pop(store_id, None)

    return {
        "store_id": store_id,
        "message": "已重置为系统默认RFM阈值",
        "thresholds": DEFAULT_RFM_THRESHOLDS,
    }


# ── 供 Service 层调用的公开函数 ──────────────────────────────────


def get_rfm_thresholds(store_id: str) -> Dict[str, Any]:
    """获取门店RFM阈值（同步接口，供service层调用）"""
    return _store_rfm_cache.get(store_id, DEFAULT_RFM_THRESHOLDS)
