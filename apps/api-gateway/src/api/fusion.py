"""
L2 融合层 REST API

端点：
  POST   /api/v1/fusion/ingredients/resolve        单条外部食材 → 规范 ID
  POST   /api/v1/fusion/ingredients/batch          批量解析（最多 200 条）
  GET    /api/v1/fusion/ingredients                列出规范映射（分页 + 分类过滤）
  GET    /api/v1/fusion/ingredients/{canonical_id} 查询某规范映射详情
  POST   /api/v1/fusion/ingredients/merge          人工合并两个规范 ID
  GET    /api/v1/fusion/ingredients/conflicts      列出冲突/低置信度映射
  PATCH  /api/v1/fusion/ingredients/{canonical_id}/cost  更新某源成本快照
  GET    /api/v1/fusion/audit                      查询融合审计日志

Neo4j 同步：
  resolve_or_create / merge 操作完成后，自动触发
  OntologyDataSync.upsert_ingredient_mapping + link_external_source
"""

from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.ingredient_fusion_service import (
    IngredientFusionService,
    FusionInput,
    FusionResult,
    reconcile_unit_cost,
    SourceCost,
)

router = APIRouter(prefix="/api/v1/fusion", tags=["fusion"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class ResolveIn(BaseModel):
    source_system: str  = Field(..., description="数据源标识: pinzhi / meituan / tiancai / aoqiwei / yiding / supplier_invoice / manual")
    external_id:   str  = Field(..., description="外部系统的原始食材 ID")
    name:          str  = Field(..., description="食材名称（原始）")
    category: Optional[str] = Field(None, description="食材分类: meat/seafood/vegetable/...")
    unit:     Optional[str] = Field(None, description="单位: kg/piece/ml/...")
    cost_fen: Optional[int] = Field(None, ge=0, description="单位成本（分）")


class BatchResolveIn(BaseModel):
    items: List[ResolveIn] = Field(..., max_items=200)


class ResolveOut(BaseModel):
    canonical_id:   str
    canonical_name: str
    confidence:     float
    method:         str
    is_new:         bool
    conflict_flag:  bool
    evidence:       Dict = {}


class MappingOut(BaseModel):
    canonical_id:      str
    canonical_name:    str
    aliases:           List[str]
    category:          Optional[str]
    unit:              Optional[str]
    external_ids:      Dict
    source_costs:      Dict
    canonical_cost_fen: Optional[int]
    fusion_confidence: float
    fusion_method:     Optional[str]
    conflict_flag:     bool
    merge_of:          List[str]
    is_active:         bool
    created_at:        Optional[datetime]
    updated_at:        Optional[datetime]


class MergeIn(BaseModel):
    keep_id:  str = Field(..., description="保留的规范 ID")
    merge_id: str = Field(..., description="被合并（软删除）的规范 ID")
    reason:   str = Field(..., description="合并原因（人工备注）")


class CostUpdateIn(BaseModel):
    source_system: str
    cost_fen:      int = Field(..., ge=0)
    confidence:    Optional[float] = Field(None, ge=0, le=1)


class AuditOut(BaseModel):
    id:                   str
    entity_type:          str
    canonical_id:         Optional[str]
    action:               str
    source_system:        Optional[str]
    raw_external_id:      Optional[str]
    raw_name:             Optional[str]
    matched_canonical_id: Optional[str]
    confidence:           Optional[float]
    fusion_method:        Optional[str]
    evidence:             Optional[Dict]
    created_at:           Optional[datetime]
    created_by:           Optional[str]


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _sync_to_neo4j(mapping, method: str, source_system: str = None,
                   external_id: str = None, confidence: float = 1.0):
    """异步触发 Neo4j 融合节点同步（不阻断响应）"""
    try:
        from src.ontology.data_sync import OntologyDataSync
        sync = OntologyDataSync()
        sync.upsert_ingredient_mapping(
            canonical_id=mapping.canonical_id,
            canonical_name=mapping.canonical_name,
            category=mapping.category or "",
            unit=mapping.unit or "",
            external_ids=mapping.external_ids or {},
            fusion_confidence=mapping.fusion_confidence,
            fusion_method=mapping.fusion_method or method,
            conflict_flag=mapping.conflict_flag,
            canonical_cost_fen=mapping.canonical_cost_fen or 0,
        )
        if source_system and external_id:
            sync.link_external_source(
                canonical_id=mapping.canonical_id,
                source_system=source_system,
                external_id=external_id,
                confidence=confidence,
                method=method,
            )
        sync.close()
    except Exception:
        pass  # Neo4j 不可用不阻断主流程


def _serialize_mapping(m) -> dict:
    return {
        "canonical_id":      m.canonical_id,
        "canonical_name":    m.canonical_name,
        "aliases":           m.aliases or [],
        "category":          m.category,
        "unit":              m.unit,
        "external_ids":      m.external_ids or {},
        "source_costs":      m.source_costs or {},
        "canonical_cost_fen": m.canonical_cost_fen,
        "fusion_confidence": m.fusion_confidence,
        "fusion_method":     m.fusion_method,
        "conflict_flag":     m.conflict_flag,
        "merge_of":          m.merge_of or [],
        "is_active":         m.is_active,
        "created_at":        m.created_at,
        "updated_at":        m.updated_at,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/ingredients/resolve",
    response_model=ResolveOut,
    status_code=status.HTTP_200_OK,
    summary="单条解析：外部食材 → 规范 canonical_id",
)
async def resolve_ingredient(
    payload:      ResolveIn,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    将任意外部系统食材（名称 + 源 ID）解析为系统内规范 canonical_id。

    置信度策略：
    - exact_id    → 1.00  直接命中 external_ids
    - exact_name  → 0.98  规范名完全匹配
    - fuzzy_name  → Jaccard × 0.92
    - new         → 数据源可靠度权重
    """
    svc = IngredientFusionService(db)
    result = await svc.resolve_or_create(
        source_system=payload.source_system,
        external_id=payload.external_id,
        name=payload.name,
        category=payload.category,
        unit=payload.unit,
        cost_fen=payload.cost_fen,
        submitted_by=str(current_user.id),
    )
    await db.commit()

    # 触发 Neo4j 同步
    if result.is_new:
        mapping = await svc.get_mapping(result.canonical_id)
        if mapping:
            _sync_to_neo4j(
                mapping, result.method,
                payload.source_system, payload.external_id, result.confidence,
            )

    return ResolveOut(
        canonical_id=result.canonical_id,
        canonical_name=result.canonical_name,
        confidence=result.confidence,
        method=result.method,
        is_new=result.is_new,
        conflict_flag=result.conflict_flag,
        evidence=result.evidence,
    )


@router.post(
    "/ingredients/batch",
    response_model=List[ResolveOut],
    summary="批量解析（最多 200 条）",
)
async def batch_resolve_ingredients(
    payload:      BatchResolveIn,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    适合 L1 适配器接入后的批量流水线调用。
    结果顺序与输入一致。
    """
    svc = IngredientFusionService(db)
    inputs = [
        FusionInput(
            source_system=i.source_system,
            external_id=i.external_id,
            name=i.name,
            category=i.category,
            unit=i.unit,
            cost_fen=i.cost_fen,
            submitted_by=str(current_user.id),
        )
        for i in payload.items
    ]
    results = await svc.batch_resolve(inputs)   # 内部已 commit
    return [
        ResolveOut(
            canonical_id=r.canonical_id,
            canonical_name=r.canonical_name,
            confidence=r.confidence,
            method=r.method,
            is_new=r.is_new,
            conflict_flag=r.conflict_flag,
            evidence=r.evidence,
        )
        for r in results
    ]


@router.get(
    "/ingredients",
    response_model=dict,
    summary="列出规范映射（分页）",
)
async def list_ingredient_mappings(
    category:  Optional[str] = Query(None),
    page:      int           = Query(1,  ge=1),
    page_size: int           = Query(50, ge=1, le=200),
    db:        AsyncSession  = Depends(get_db),
    current_user: User       = Depends(get_current_user),
):
    svc = IngredientFusionService(db)
    rows, total = await svc.list_mappings(category=category, page=page, page_size=page_size)
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "items":     [_serialize_mapping(m) for m in rows],
    }


@router.get(
    "/ingredients/conflicts",
    response_model=List[MappingOut],
    summary="列出冲突或低置信度映射（需人工审核）",
)
async def get_ingredient_conflicts(
    confidence_threshold: float        = Query(0.70, ge=0, le=1),
    db:                   AsyncSession = Depends(get_db),
    current_user:         User         = Depends(get_current_user),
):
    svc = IngredientFusionService(db)
    rows = await svc.get_conflicts(confidence_threshold)
    return [_serialize_mapping(m) for m in rows]


@router.get(
    "/ingredients/{canonical_id}",
    response_model=MappingOut,
    summary="查询规范映射详情",
)
async def get_ingredient_mapping(
    canonical_id: str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    svc = IngredientFusionService(db)
    mapping = await svc.get_mapping(canonical_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="规范映射不存在")
    return _serialize_mapping(mapping)


@router.post(
    "/ingredients/merge",
    response_model=MappingOut,
    summary="人工合并两个规范 ID（HitL 审批后调用）",
)
async def merge_ingredient_mappings(
    payload:      MergeIn,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    将 merge_id 合并入 keep_id：
    - 合并 external_ids、aliases、source_costs
    - 重新加权计算规范成本
    - 软删除 merge_id（is_active=False）
    - 写入审计日志
    - 触发 Neo4j 节点更新
    """
    svc = IngredientFusionService(db)
    result = await svc.merge_canonical_ids(
        keep_id=payload.keep_id,
        merge_id=payload.merge_id,
        reason=payload.reason,
        merged_by=str(current_user.id),
    )
    if not result:
        raise HTTPException(status_code=404, detail="keep_id 或 merge_id 不存在")
    await db.commit()
    _sync_to_neo4j(result, "manual_merge")
    return _serialize_mapping(result)


@router.patch(
    "/ingredients/{canonical_id}/cost",
    response_model=MappingOut,
    summary="更新某数据源的成本快照",
)
async def update_ingredient_cost(
    canonical_id: str,
    payload:      CostUpdateIn,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    svc = IngredientFusionService(db)
    mapping = await svc.update_source_cost(
        canonical_id=canonical_id,
        source_system=payload.source_system,
        cost_fen=payload.cost_fen,
        confidence=payload.confidence,
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="规范映射不存在")
    await db.commit()
    return _serialize_mapping(mapping)


@router.get(
    "/audit",
    response_model=List[AuditOut],
    summary="查询融合审计日志",
)
async def get_fusion_audit(
    canonical_id:  Optional[str] = Query(None),
    source_system: Optional[str] = Query(None),
    limit:         int           = Query(100, ge=1, le=500),
    db:            AsyncSession  = Depends(get_db),
    current_user:  User          = Depends(get_current_user),
):
    svc = IngredientFusionService(db)
    logs = await svc.get_audit_log(
        canonical_id=canonical_id,
        source_system=source_system,
        limit=limit,
    )
    return [
        {
            "id":                   str(log.id),
            "entity_type":          log.entity_type,
            "canonical_id":         log.canonical_id,
            "action":               log.action,
            "source_system":        log.source_system,
            "raw_external_id":      log.raw_external_id,
            "raw_name":             log.raw_name,
            "matched_canonical_id": log.matched_canonical_id,
            "confidence":           log.confidence,
            "fusion_method":        log.fusion_method,
            "evidence":             log.evidence,
            "created_at":           log.created_at,
            "created_by":           log.created_by,
        }
        for log in logs
    ]
