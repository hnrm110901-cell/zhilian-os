"""
Platform Agent API — Sprint 6

端点：
  PeopleAgent（人力经营智能）:
    GET  /people/dashboard          — 人力综合仪表盘
    GET  /people/performance        — 员工绩效排名
    GET  /people/staffing-gaps      — 排班缺口分析

  OntologyAgent（本体知识智能）:
    GET  /ontology/dashboard        — 本体知识仪表盘
    GET  /ontology/entities         — 实体详细统计
    GET  /ontology/issues           — 数据质量问题清单

  TenantReplicator（多客户复制引擎）:
    GET  /tenant/onboarding         — 门店入驻进度
    POST /tenant/replicate          — 复制门店本体
    GET  /tenant/onboarding/all     — 多门店入驻一览
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdp/platform", tags=["CDP-Platform"])


# ── PeopleAgent ──────────────────────────────────────────────────


@router.get("/people/dashboard")
async def get_people_dashboard(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """人力综合仪表盘（员工数 + 人效 + 排班覆盖 + 人工成本率）"""
    from src.services.people_agent_service import people_agent_service

    return await people_agent_service.get_people_dashboard(db, store_id, days=days)


@router.get("/people/performance")
async def get_people_performance(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    limit: int = Query(20, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """员工绩效排名（按服务订单数排序）"""
    from src.services.people_agent_service import people_agent_service

    return await people_agent_service.get_employee_performance(db, store_id, days=days, limit=limit)


@router.get("/people/staffing-gaps")
async def get_staffing_gaps(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """排班缺口分析（每日排班 vs 订单密度）"""
    from src.services.people_agent_service import people_agent_service

    return await people_agent_service.get_staffing_gaps(db, store_id, days=days)


# ── OntologyAgent ────────────────────────────────────────────────


@router.get("/ontology/dashboard")
async def get_ontology_dashboard(
    store_id: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """本体知识仪表盘（覆盖率 + 健康评分 + 数据质量等级）"""
    from src.services.ontology_agent_service import ontology_agent_service

    return await ontology_agent_service.get_ontology_dashboard(db, store_id)


@router.get("/ontology/entities")
async def get_ontology_entities(
    store_id: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """实体详细统计（品类分布 + 孤立记录）"""
    from src.services.ontology_agent_service import ontology_agent_service

    return await ontology_agent_service.get_entity_stats(db, store_id)


@router.get("/ontology/issues")
async def get_ontology_issues(
    store_id: str = Query(...),
    limit: int = Query(20, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """数据质量问题清单（缺价格/缺成本/空BOM）"""
    from src.services.ontology_agent_service import ontology_agent_service

    return await ontology_agent_service.get_data_issues(db, store_id, limit=limit)


# ── TenantReplicator ─────────────────────────────────────────────


@router.get("/tenant/onboarding")
async def get_tenant_onboarding(
    store_id: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """门店入驻进度（数据完成度 + 状态 + 预计天数）"""
    from src.services.tenant_replicator_service import tenant_replicator_service

    return await tenant_replicator_service.get_onboarding_status(db, store_id)


class ReplicateRequest(BaseModel):
    source_store_id: str
    target_store_id: str


@router.post("/tenant/replicate")
async def replicate_store(
    req: ReplicateRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """复制门店本体（从源门店克隆菜品/BOM/食材到目标门店）"""
    from src.services.tenant_replicator_service import tenant_replicator_service

    return await tenant_replicator_service.replicate_store(
        db,
        req.source_store_id,
        req.target_store_id,
    )


@router.get("/tenant/onboarding/all")
async def get_all_onboarding(
    store_ids: Optional[str] = Query(None, description="逗号分隔的门店ID"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """多门店入驻进度一览"""
    from src.services.tenant_replicator_service import tenant_replicator_service

    ids = store_ids.split(",") if store_ids else None
    return await tenant_replicator_service.get_multi_store_onboarding(db, store_ids=ids)
