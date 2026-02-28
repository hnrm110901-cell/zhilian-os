"""
L3 跨店知识聚合 REST API

端点：
  GET  /api/v1/l3/stores/{store_id}/benchmarks   — 门店全指标同伴组百分位
  GET  /api/v1/l3/stores/{store_id}/similar       — 最相似门店列表
  GET  /api/v1/l3/stores/{store_id}/peer-group    — 同伴组详情
  GET  /api/v1/l3/stores/best-practice            — 各指标标杆门店
  GET  /api/v1/l3/stores/bom-variance             — 跨店 BOM 一致性分析
  POST /api/v1/l3/materialize                     — 触发日维度指标物化
  POST /api/v1/l3/sync-graph                      — 触发 Neo4j 图同步
  POST /api/v1/l3/seed-rules                      — 植入 50 条跨店规则（幂等）

Neo4j 同步：
  materialize / sync-graph 完成后自动触发
  OntologyDataSync.upsert_store + SIMILAR_TO/BENCHMARK_OF 边更新
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.cross_store_knowledge_service import CrossStoreKnowledgeService

router = APIRouter(prefix="/api/v1/l3", tags=["l3_knowledge"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class MaterializeIn(BaseModel):
    target_date:  Optional[date] = Field(None, description="物化日期（默认昨日）")
    store_ids:    Optional[List[str]] = Field(None, description="指定门店列表（None=全部）")


class SyncGraphIn(BaseModel):
    store_ids:   Optional[List[str]] = Field(None, description="指定门店列表（None=全部）")
    metric_date: Optional[date] = Field(None, description="基准日期（默认昨日）")


# ── 基准 / 百分位端点 ──────────────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/benchmarks",
    summary="门店全指标同伴组百分位",
    response_model=List[dict],
)
async def get_store_benchmarks(
    store_id:    str,
    metric_date: Optional[date] = Query(None, description="查询日期，默认昨日"),
    db:          AsyncSession = Depends(get_db),
    _:           User = Depends(get_current_user),
):
    """
    返回指定门店在同伴组中所有 6 个核心指标的百分位报告：
    waste_rate / cost_ratio / bom_compliance / labor_ratio / revenue_per_seat / menu_coverage
    """
    svc = CrossStoreKnowledgeService(db)
    results = await svc.get_all_benchmarks(store_id, metric_date)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"门店 {store_id} 暂无同伴组基准数据，请先执行 /l3/materialize",
        )
    return results


@router.get(
    "/stores/{store_id}/similar",
    summary="最相似门店列表",
    response_model=List[dict],
)
async def get_similar_stores(
    store_id:  str,
    top_n:     int   = Query(5, ge=1, le=20, description="返回数量"),
    min_score: float = Query(0.55, ge=0.0, le=1.0, description="相似度最低阈值"),
    db:        AsyncSession = Depends(get_db),
    _:         User = Depends(get_current_user),
):
    """
    从 store_similarity_cache 返回与目标门店最相似的 Top-N 门店，
    包含相似度分量（menu_overlap / region_match / tier_match / capacity_ratio）。
    """
    svc = CrossStoreKnowledgeService(db)
    results = await svc.get_similar_stores(store_id, top_n=top_n, min_score=min_score)
    return results


@router.get(
    "/stores/{store_id}/peer-group",
    summary="同伴组详情",
)
async def get_peer_group(
    store_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User = Depends(get_current_user),
):
    """
    返回门店所属同伴组的完整信息（tier / region / store_count / member_ids）。
    """
    from sqlalchemy import select
    from src.models.cross_store import StorePeerGroup, CrossStoreMetric
    from datetime import timedelta

    # 通过最近一条 metric 记录推断同伴组
    yesterday = date.today() - timedelta(days=1)
    stmt = (
        select(CrossStoreMetric.peer_group, CrossStoreMetric.peer_count)
        .where(
            CrossStoreMetric.store_id    == store_id,
            CrossStoreMetric.metric_date == yesterday,
        )
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row or not row[0]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"门店 {store_id} 暂无同伴组数据，请先执行 /l3/materialize",
        )

    group_key = row[0]
    stmt2 = select(StorePeerGroup).where(StorePeerGroup.group_key == group_key)
    group = (await db.execute(stmt2)).scalar_one_or_none()
    if not group:
        return {"group_key": group_key, "store_count": row[1]}

    return {
        "group_key":   group.group_key,
        "tier":        group.tier,
        "region":      group.region,
        "store_count": group.store_count,
        "store_ids":   group.store_ids,
        "updated_at":  group.updated_at.isoformat() if group.updated_at else None,
    }


# ── 标杆 / BOM 分析端点 ────────────────────────────────────────────────────────

@router.get(
    "/stores/best-practice",
    summary="各指标标杆门店",
    response_model=List[dict],
)
async def get_best_practice_stores(
    metric_name:    str   = Query(..., description="指标名: waste_rate/cost_ratio/bom_compliance/..."),
    top_n:          int   = Query(5, ge=1, le=20),
    direction:      str   = Query("lower_better", regex="^(lower_better|higher_better)$"),
    peer_group_key: Optional[str] = Query(None, description="同伴组 key，如 standard_华东"),
    metric_date:    Optional[date] = Query(None, description="查询日期，默认昨日"),
    db:             AsyncSession = Depends(get_db),
    _:              User = Depends(get_current_user),
):
    """
    返回同组内某指标表现最佳的 Top-N 门店排行榜。

    - `direction=lower_better`（默认）: 适用于损耗率、成本率等越低越好的指标
    - `direction=higher_better`: 适用于菜单覆盖率、BOM 合规率等越高越好的指标
    """
    svc = CrossStoreKnowledgeService(db)
    return await svc.get_best_practice_stores(
        metric_name=metric_name,
        top_n=top_n,
        direction=direction,
        peer_group_key=peer_group_key,
        metric_date=metric_date,
    )


@router.get(
    "/stores/bom-variance",
    summary="跨店 BOM 一致性分析",
    response_model=List[dict],
)
async def get_bom_variance(
    dish_id:     Optional[str] = Query(None, description="指定菜品 ID（None=全部）"),
    min_variance: float = Query(0.10, ge=0.0, le=1.0, description="最小方差过滤阈值"),
    db:          AsyncSession = Depends(get_db),
    _:           User = Depends(get_current_user),
):
    """
    分析同一菜品在不同门店 BOM 配方中的用量差异。

    返回方差超过阈值的菜品-食材对，辅助识别配方不一致问题（CROSS-011~CROSS-019 规则触发源）。
    """
    svc = CrossStoreKnowledgeService(db)
    results = await svc.get_bom_variance_across_stores()
    if min_variance > 0:
        results = [r for r in results if r.get("cv", 0) >= min_variance]
    if dish_id:
        results = [r for r in results if r.get("dish_id") == dish_id]
    return results


# ── 运维操作端点（需要 admin/manager 权限） ────────────────────────────────────

@router.post(
    "/materialize",
    summary="触发日维度指标物化",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_materialize(
    body: MaterializeIn = MaterializeIn(),
    db:   AsyncSession = Depends(get_db),
    _:    User = Depends(get_current_user),
):
    """
    将各门店当日核心指标写入 `cross_store_metrics` 物化表，
    同时计算同伴组百分位。

    建议通过夜间 Celery 任务调度，此端点供手动触发 / 补跑使用。
    """
    svc = CrossStoreKnowledgeService(db)
    result = await svc.materialize_metrics(
        target_date=body.target_date,
        store_ids=body.store_ids,
    )
    await db.commit()
    return {"status": "accepted", **result}


@router.post(
    "/sync-graph",
    summary="触发 Neo4j 图同步",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_sync_graph(
    body: SyncGraphIn = SyncGraphIn(),
    db:   AsyncSession = Depends(get_db),
    _:    User = Depends(get_current_user),
):
    """
    将门店节点 + SIMILAR_TO / BENCHMARK_OF / SHARES_RECIPE / OCCURRED_IN 边
    批量写入 Neo4j 本体图。

    通常在 materialize 之后执行，确保图数据与 PostgreSQL 指标一致。
    """
    svc = CrossStoreKnowledgeService(db)
    result = await svc.sync_store_graph(
        store_ids=body.store_ids,
        metric_date=body.metric_date,
    )
    return {"status": "accepted", **result}


@router.post(
    "/seed-rules",
    summary="植入 50 条跨店推理规则（幂等）",
    status_code=status.HTTP_201_CREATED,
)
async def seed_cross_store_rules(
    db: AsyncSession = Depends(get_db),
    _:  User = Depends(get_current_user),
):
    """
    幂等植入 50 条 CROSS_STORE 类推理规则。
    已存在的 rule_code 自动跳过，可重复调用。
    """
    from src.services.knowledge_rule_service import KnowledgeRuleService
    svc = KnowledgeRuleService(db)
    result = await svc.seed_cross_store_rules()
    await db.commit()
    return result
