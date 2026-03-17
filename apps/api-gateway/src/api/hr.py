"""HR REST API — retention signals, achievements, skill catalog, BFF, diagnose."""
import uuid
from datetime import date
from typing import Optional

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class RetentionSignalOut(BaseModel):
    id: str
    assignment_id: str
    risk_score: float
    risk_factors: dict
    intervention_status: str
    computed_at: Optional[str] = None


class AchievementCreateRequest(BaseModel):
    person_id: str
    skill_node_id: str
    achieved_at: Optional[date] = None
    evidence: Optional[str] = None
    trigger_type: str = "manual"


class SkillNodeOut(BaseModel):
    id: str
    skill_name: str
    category: Optional[str] = None
    description: Optional[str] = None
    estimated_revenue_lift: Optional[float] = None


class DiagnoseRequest(BaseModel):
    intent: str
    store_id: str
    person_id: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/retention-signals")
async def list_retention_signals(
    store_id: str = Query(..., description="门店ID"),
    min_risk: float = Query(0.0, description="最低风险分"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List retention signals for a store, filtered by min risk score."""
    # Resolve store → org_node_id
    org_result = await session.execute(
        sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
        {"store_id": store_id},
    )
    org_node_id = org_result.scalar_one_or_none()
    if not org_node_id:
        raise HTTPException(status_code=404, detail="门店未配置组织节点")

    result = await session.execute(
        sa.text(
            "SELECT rs.id, rs.assignment_id, rs.risk_score, "
            "       rs.risk_factors, rs.intervention_status, rs.computed_at "
            "FROM retention_signals rs "
            "JOIN employment_assignments ea ON ea.id = rs.assignment_id "
            "WHERE ea.org_node_id = :org_node_id "
            "  AND rs.risk_score >= :min_risk "
            "ORDER BY rs.risk_score DESC"
        ),
        {"org_node_id": org_node_id, "min_risk": min_risk},
    )
    rows = result.fetchall()

    return {
        "store_id": store_id,
        "total": len(rows),
        "items": [
            {
                "id": str(row.id),
                "assignment_id": str(row.assignment_id),
                "risk_score": row.risk_score,
                "risk_factors": row.risk_factors,
                "intervention_status": row.intervention_status,
                "computed_at": row.computed_at.isoformat() if row.computed_at else None,
            }
            for row in rows
        ],
    }


@router.post("/achievements", status_code=201)
async def create_achievement(
    req: AchievementCreateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a skill achievement for a person."""
    achievement_id = uuid.uuid4()
    achieved_at = req.achieved_at or date.today()

    try:
        await session.execute(
            sa.text(
                "INSERT INTO person_achievements "
                "(id, person_id, skill_node_id, achieved_at, evidence, trigger_type) "
                "VALUES (:id, :person_id, :skill_node_id, :achieved_at, "
                "        :evidence, :trigger_type)"
            ),
            {
                "id": str(achievement_id),
                "person_id": req.person_id,
                "skill_node_id": req.skill_node_id,
                "achieved_at": achieved_at.isoformat(),
                "evidence": req.evidence,
                "trigger_type": req.trigger_type,
            },
        )
        await session.commit()
    except Exception as exc:
        error_str = str(exc)
        if "uq_person_skill" in error_str:
            raise HTTPException(
                status_code=409,
                detail="该员工已拥有此技能认证",
            ) from exc
        raise

    logger.info(
        "hr.achievement_created",
        achievement_id=str(achievement_id),
        person_id=req.person_id,
    )
    return {
        "id": str(achievement_id),
        "person_id": req.person_id,
        "skill_node_id": req.skill_node_id,
        "achieved_at": achieved_at.isoformat(),
    }


@router.get("/skill-nodes")
async def list_skill_nodes(
    category: Optional[str] = Query(None, description="技能类别"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List skill catalog."""
    if category:
        result = await session.execute(
            sa.text(
                "SELECT id, skill_name, category, description, "
                "       estimated_revenue_lift "
                "FROM skill_nodes "
                "WHERE category = :category "
                "ORDER BY COALESCE(estimated_revenue_lift, 0) DESC"
            ),
            {"category": category},
        )
    else:
        result = await session.execute(
            sa.text(
                "SELECT id, skill_name, category, description, "
                "       estimated_revenue_lift "
                "FROM skill_nodes "
                "ORDER BY COALESCE(estimated_revenue_lift, 0) DESC"
            ),
        )

    rows = result.fetchall()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(row.id),
                "skill_name": row.skill_name,
                "category": row.category,
                "description": row.description,
                "estimated_revenue_lift": float(row.estimated_revenue_lift)
                    if row.estimated_revenue_lift else None,
            }
            for row in rows
        ],
    }


@router.post("/diagnose")
async def diagnose(
    req: DiagnoseRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Run HRAgent v1 diagnosis."""
    from src.agents.hr_agent import HRAgentV1

    agent = HRAgentV1()
    diagnosis = await agent.diagnose(
        req.intent,
        store_id=req.store_id,
        session=session,
        person_id=req.person_id,
    )
    return diagnosis.to_dict()


@router.get("/bff/sm/{store_id}")
async def bff_sm_hr(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """BFF首屏: 店长HR视角聚合数据.

    Returns retention risks + skill gaps + pending tasks, all in one call.
    Partial failure → null per section, never blocks entire response.
    """
    from src.agents.hr_agent import HRAgentV1
    agent = HRAgentV1()

    # Retention risk section
    retention = None
    try:
        diag = await agent.diagnose("retention_risk", store_id=store_id, session=session)
        retention = {
            "high_risk_count": len(diag.high_risk_persons),
            "persons": diag.high_risk_persons[:5],
            "recommendations": diag.recommendations[:3],
        }
    except Exception as exc:
        logger.warning("bff_sm_hr.retention_failed", store_id=store_id, error=str(exc))

    # Skill gap section
    skill_gaps = None
    try:
        diag = await agent.diagnose("skill_gaps", store_id=store_id, session=session)
        skill_gaps = {
            "total_potential_yuan": sum(
                r.get("expected_yuan", 0) for r in diag.recommendations
            ),
            "top_recommendations": diag.recommendations[:5],
        }
    except Exception as exc:
        logger.warning("bff_sm_hr.skill_gaps_failed", store_id=store_id, error=str(exc))

    return {
        "store_id": store_id,
        "retention": retention,
        "skill_gaps": skill_gaps,
    }
