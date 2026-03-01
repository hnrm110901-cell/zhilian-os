"""
连锁扩展 API — 多店本体复制与跨店对比分析

端点：
  POST  /api/v1/chain/replicate          克隆源门店本体到新门店
  GET   /api/v1/chain/compare            跨店指标对比（损耗率/BOM差异/热销菜品）
  GET   /api/v1/chain/brand/benchmark    品牌级汇总基准报告
  GET   /api/v1/chain/stores/{store_id}/diff/{other_id}  两店 BOM 差异详情
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user, require_role
from src.models.user import User, UserRole
from src.services.store_ontology_replicator import StoreOntologyReplicator

router = APIRouter(prefix="/api/v1/chain", tags=["chain_expansion"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ReplicateIn(BaseModel):
    source_store_id: str = Field(..., description="源门店 ID（已运营，作为模板）")
    target_store_id: str = Field(..., description="目标门店 ID（新店）")
    target_store_name: str = Field(..., description="目标门店名称")
    include_bom: bool = Field(True, description="是否复制 BOM 配方")
    include_inventory: bool = Field(True, description="是否复制食材主档")
    dish_filter: Optional[List[str]] = Field(
        None, description="限定菜品编码列表（为空则复制全部）"
    )


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.post("/replicate", status_code=status.HTTP_201_CREATED)
async def replicate_store_ontology(
    payload: ReplicateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """
    将源门店本体结构克隆到新门店

    复制内容：菜品主档 + BOM 激活版本 + 食材主档（库存归零）
    """
    if payload.source_store_id == payload.target_store_id:
        raise HTTPException(status_code=400, detail="源门店与目标门店不能相同")

    repl = StoreOntologyReplicator(db, created_by=str(current_user.id))
    report = await repl.replicate(
        source_store_id=payload.source_store_id,
        target_store_id=payload.target_store_id,
        target_store_name=payload.target_store_name,
        include_bom=payload.include_bom,
        include_inventory=payload.include_inventory,
        dish_filter=payload.dish_filter,
    )
    return report


@router.get("/compare")
async def cross_store_compare(
    store_ids: str = Query(..., description="逗号分隔的门店 ID，如 XJ-CS-001,XJ-SZ-001"),
    metric: str = Query("waste_rate", description="对比指标：waste_rate / bom_diff / top_dishes"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    跨店指标对比分析

    metric=waste_rate  : 各店损耗总量排行
    metric=bom_diff    : 同一道菜各店 BOM 食材用量对比
    metric=top_dishes  : 各店订单量 Top 菜品
    """
    ids = [s.strip() for s in store_ids.split(",") if s.strip()]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="至少提供 2 个门店 ID")
    if len(ids) > 10:
        raise HTTPException(status_code=400, detail="单次对比不超过 10 家门店")

    repl = StoreOntologyReplicator(db)
    results = await repl.get_cross_store_comparison(ids, metric=metric)
    return {
        "metric": metric,
        "store_ids": ids,
        "results": results,
        "count": len(results),
    }


@router.get("/brand/benchmark")
async def brand_benchmark(
    store_ids: str = Query(..., description="品牌下所有门店 ID，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """品牌级知识图谱汇总基准报告"""
    ids = [s.strip() for s in store_ids.split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="请提供至少 1 个门店 ID")

    repl = StoreOntologyReplicator(db)
    report = await repl.get_brand_benchmark(ids)
    return report


@router.get("/stores/{store_id}/diff/{other_id}")
async def bom_diff_two_stores(
    store_id: str,
    other_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对比两家门店的 BOM 配方差异（Neo4j Cypher 图查询）"""
    repl = StoreOntologyReplicator(db)
    results = await repl.get_cross_store_comparison([store_id, other_id], metric="bom_diff")

    # 按菜品分组 pivot
    pivot: dict = {}
    for row in results:
        dish = row.get("dish_name", "")
        store = row.get("store_id", "")
        ing = row.get("ingredient", "")
        qty = row.get("qty")
        unit = row.get("unit", "")

        if dish not in pivot:
            pivot[dish] = {}
        if ing not in pivot[dish]:
            pivot[dish][ing] = {}
        pivot[dish][ing][store] = f"{qty} {unit}"

    # 标记差异菜品
    diffs = []
    for dish, ingredients in pivot.items():
        for ing, store_qtys in ingredients.items():
            vals = list(store_qtys.values())
            if len(vals) >= 2 and len(set(vals)) > 1:
                diffs.append({
                    "dish_name": dish,
                    "ingredient": ing,
                    store_id: store_qtys.get(store_id, "—"),
                    other_id: store_qtys.get(other_id, "—"),
                })

    return {
        "store_a": store_id,
        "store_b": other_id,
        "diff_count": len(diffs),
        "diffs": diffs,
    }
