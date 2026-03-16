"""
合规引擎 API — /api/v1/compliance-engine
统一合规评分计算、告警管理、自动操作、仪表盘。
"""

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import require_role
from ..models.user import User, UserRole
from ..services.compliance_engine_service import ComplianceEngineService

router = APIRouter(prefix="/api/v1/compliance-engine", tags=["compliance-engine"])

svc = ComplianceEngineService()


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class ComputeRequest(BaseModel):
    brand_id: str


class ResolveRequest(BaseModel):
    resolved_by: str


# ── 序列化辅助 ────────────────────────────────────────────────────────────────


def _serialize_score(s) -> Dict[str, Any]:
    return {
        "id": str(s.id),
        "brand_id": s.brand_id,
        "store_id": s.store_id,
        "score_date": s.score_date.isoformat() if s.score_date else None,
        "health_cert_score": s.health_cert_score,
        "food_safety_score": s.food_safety_score,
        "license_score": s.license_score,
        "hygiene_score": s.hygiene_score,
        "overall_score": s.overall_score,
        "grade": s.grade,
        "risk_items": s.risk_items or [],
        "auto_actions_taken": s.auto_actions_taken,
        "created_at": str(s.created_at) if s.created_at else None,
    }


def _serialize_alert(a) -> Dict[str, Any]:
    return {
        "id": str(a.id),
        "brand_id": a.brand_id,
        "store_id": a.store_id,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "title": a.title,
        "description": a.description,
        "related_entity_id": a.related_entity_id,
        "is_resolved": a.is_resolved,
        "resolved_by": a.resolved_by,
        "resolved_at": str(a.resolved_at) if a.resolved_at else None,
        "auto_action": a.auto_action,
        "created_at": str(a.created_at) if a.created_at else None,
    }


# ── 评分端点 ──────────────────────────────────────────────────────────────────


@router.post("/compute")
async def compute_scores(
    body: ComputeRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """批量计算品牌下所有门店的合规评分"""
    scores = await svc.compute_all_stores(db, body.brand_id)
    await db.commit()
    return {
        "message": f"已完成 {len(scores)} 家门店的合规评分计算",
        "count": len(scores),
        "scores": [_serialize_score(s) for s in scores],
    }


@router.get("/scores")
async def list_scores(
    brand_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    grade: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询门店合规评分"""
    scores, total = await svc.get_scores(db, brand_id, page, page_size, grade)
    return {
        "items": [_serialize_score(s) for s in scores],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/scores/{score_id}")
async def get_score_detail(
    score_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取评分详情"""
    score = await svc.get_score_detail(db, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="评分记录不存在")
    return _serialize_score(score)


# ── 告警端点 ──────────────────────────────────────────────────────────────────


@router.post("/alerts/generate")
async def generate_alerts(
    body: ComputeRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """扫描数据源生成合规告警"""
    alerts = await svc.generate_alerts(db, body.brand_id)
    await db.commit()
    return {
        "message": f"已生成 {len(alerts)} 条告警",
        "count": len(alerts),
        "alerts": [_serialize_alert(a) for a in alerts],
    }


@router.get("/alerts")
async def list_alerts(
    brand_id: str = Query(...),
    severity: Optional[str] = Query(None),
    is_resolved: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询合规告警"""
    alerts, total = await svc.get_alerts(
        db,
        brand_id,
        severity,
        is_resolved,
        page,
        page_size,
    )
    return {
        "items": [_serialize_alert(a) for a in alerts],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """处置告警"""
    alert = await svc.resolve_alert(db, alert_id, body.resolved_by)
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    await db.commit()
    return _serialize_alert(alert)


# ── 自动操作端点 ──────────────────────────────────────────────────────────────


@router.post("/auto-actions")
async def execute_auto_actions(
    body: ComputeRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """执行自动合规操作"""
    actions = await svc.execute_auto_actions(db, body.brand_id)
    await db.commit()
    return {
        "message": f"已执行 {len(actions)} 项自动操作",
        "count": len(actions),
        "actions": actions,
    }


# ── 仪表盘端点 ────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_dashboard(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """品牌级合规仪表盘"""
    return await svc.get_dashboard(db, brand_id)
