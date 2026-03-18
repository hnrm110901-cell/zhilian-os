"""HR REST API — retention signals, achievements, skill catalog, BFF, diagnose."""
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

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


class KnowledgeCaptureOut(BaseModel):
    id: str
    person_id: str
    person_name: Optional[str] = None
    trigger_type: Optional[str] = None
    context: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    quality_score: Optional[float] = None
    created_at: Optional[str] = None


class KnowledgeCaptureTriggerRequest(BaseModel):
    person_id: str
    trigger_type: str  # exit/monthly_review/incident/onboarding/growth_review


class KnowledgeCaptureSubmitRequest(BaseModel):
    person_id: str
    trigger_type: str
    raw_dialogue: str


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


@router.get("/bff/hq/{org_node_id}")
async def bff_hq_hr(
    org_node_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """BFF首屏: 总部HR视角聚合数据.

    Returns risk distribution + knowledge captures stats + skill health + savings.
    Partial failure → null per section, never blocks entire response.
    30s Redis缓存（?refresh=true强刷）
    """
    # ── 留任风险分布 ──
    risk_distribution = None
    try:
        result = await session.execute(
            sa.text(
                "SELECT "
                "  SUM(CASE WHEN rs.risk_score >= 0.70 THEN 1 ELSE 0 END) AS high_count, "
                "  SUM(CASE WHEN rs.risk_score >= 0.40 AND rs.risk_score < 0.70 THEN 1 ELSE 0 END) AS medium_count, "
                "  SUM(CASE WHEN rs.risk_score < 0.40 THEN 1 ELSE 0 END) AS low_count, "
                "  COUNT(*) AS total "
                "FROM retention_signals rs "
                "JOIN employment_assignments ea ON ea.id = rs.assignment_id "
                "JOIN org_nodes on_node ON on_node.id = ea.org_node_id "
                "WHERE on_node.root_id = :org_node_id "
                "  AND rs.computed_at >= NOW() - :interval * INTERVAL '1 day'"
            ),
            {"org_node_id": org_node_id, "interval": 1},
        )
        row = result.fetchone()
        if row:
            risk_distribution = {
                "high": int(row.high_count or 0),
                "medium": int(row.medium_count or 0),
                "low": int(row.low_count or 0),
                "total": int(row.total or 0),
            }
    except Exception as exc:
        logger.warning("bff_hq_hr.risk_distribution_failed", org_node_id=org_node_id, error=str(exc))

    # ── 知识采集统计（近30天）──
    knowledge_stats = None
    try:
        result = await session.execute(
            sa.text(
                "SELECT trigger_type, COUNT(*) AS cnt "
                "FROM knowledge_captures kc "
                "JOIN persons p ON p.id = kc.person_id "
                "JOIN employment_assignments ea ON ea.person_id = p.id "
                "JOIN org_nodes on_node ON on_node.id = ea.org_node_id "
                "WHERE on_node.root_id = :org_node_id "
                "  AND kc.created_at >= NOW() - :interval * INTERVAL '1 day' "
                "GROUP BY trigger_type "
                "ORDER BY cnt DESC"
            ),
            {"org_node_id": org_node_id, "interval": 30},
        )
        rows = result.fetchall()
        by_type = {row.trigger_type: int(row.cnt) for row in rows}
        knowledge_stats = {
            "total_30d": sum(by_type.values()),
            "by_type": by_type,
        }
    except Exception as exc:
        logger.warning("bff_hq_hr.knowledge_stats_failed", org_node_id=org_node_id, error=str(exc))

    # ── 门店技能缺口排名 ──
    skill_health_ranking = None
    try:
        result = await session.execute(
            sa.text(
                "SELECT s.id AS store_id, s.name AS store_name, "
                "       COUNT(DISTINCT sn.id) AS total_skills, "
                "       COUNT(DISTINCT pa.skill_node_id) AS achieved_skills "
                "FROM stores s "
                "JOIN org_nodes on_node ON on_node.id = s.org_node_id "
                "JOIN employment_assignments ea ON ea.org_node_id = s.org_node_id "
                "  AND ea.status = 'active' "
                "LEFT JOIN person_achievements pa ON pa.person_id = ea.person_id "
                "CROSS JOIN skill_nodes sn "
                "WHERE on_node.root_id = :org_node_id "
                "GROUP BY s.id, s.name "
                "ORDER BY achieved_skills ASC "
                "LIMIT 10"
            ),
            {"org_node_id": org_node_id},
        )
        rows = result.fetchall()
        skill_health_ranking = [
            {
                "store_id": str(row.store_id),
                "store_name": row.store_name,
                "total_skills": int(row.total_skills or 0),
                "achieved_skills": int(row.achieved_skills or 0),
                "coverage_pct": round(
                    int(row.achieved_skills or 0) / int(row.total_skills or 1) * 100, 1
                ),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.warning("bff_hq_hr.skill_health_failed", org_node_id=org_node_id, error=str(exc))

    return {
        "org_node_id": org_node_id,
        "risk_distribution": risk_distribution,
        "knowledge_stats": knowledge_stats,
        "skill_health_ranking": skill_health_ranking,
    }


@router.get("/knowledge-captures")
async def list_knowledge_captures(
    store_id: Optional[str] = Query(None, description="门店ID（可选，不传则按org_node_id聚合）"),
    trigger_type: Optional[str] = Query(None, description="触发类型过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """列出知识采集记录，支持门店和触发类型过滤."""
    # 四种过滤组合，各用独立的参数化查询，避免 f-string 拼接（见 lessons L011）
    _BASE = (
        "SELECT kc.id, kc.person_id, p.name AS person_name, "
        "       kc.trigger_type, kc.context, kc.action, kc.result, "
        "       kc.quality_score, kc.created_at "
        "FROM knowledge_captures kc "
        "LEFT JOIN persons p ON p.id = kc.person_id "
    )
    _ORDER = "ORDER BY kc.created_at DESC LIMIT :limit"
    _STORE_FILTER = (
        "WHERE EXISTS ("
        "  SELECT 1 FROM employment_assignments ea "
        "  JOIN stores s ON s.org_node_id = ea.org_node_id "
        "  WHERE ea.person_id = kc.person_id AND s.id = :store_id"
        ") "
    )
    _TYPE_FILTER = "WHERE kc.trigger_type = :trigger_type "
    _BOTH_FILTER = (
        "WHERE kc.trigger_type = :trigger_type "
        "  AND EXISTS ("
        "    SELECT 1 FROM employment_assignments ea "
        "    JOIN stores s ON s.org_node_id = ea.org_node_id "
        "    WHERE ea.person_id = kc.person_id AND s.id = :store_id"
        "  ) "
    )

    if store_id and trigger_type:
        sql = _BASE + _BOTH_FILTER + _ORDER
        params: dict = {"limit": limit, "store_id": store_id, "trigger_type": trigger_type}
    elif store_id:
        sql = _BASE + _STORE_FILTER + _ORDER
        params = {"limit": limit, "store_id": store_id}
    elif trigger_type:
        sql = _BASE + _TYPE_FILTER + _ORDER
        params = {"limit": limit, "trigger_type": trigger_type}
    else:
        sql = _BASE + _ORDER
        params = {"limit": limit}

    result = await session.execute(sa.text(sql), params)
    rows = result.fetchall()

    # 本月统计
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    result_month = await session.execute(
        sa.text(
            "SELECT COUNT(*) FROM knowledge_captures "
            "WHERE TO_CHAR(created_at, 'YYYY-MM') = :month"
        ),
        {"month": this_month},
    )
    month_count = int(result_month.scalar() or 0)

    items = [
        {
            "id": str(row.id),
            "person_id": str(row.person_id),
            "person_name": row.person_name,
            "trigger_type": row.trigger_type,
            "context": row.context,
            "action": row.action,
            "result": row.result,
            "quality_score": float(row.quality_score) if row.quality_score is not None else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    high_quality = sum(1 for i in items if (i["quality_score"] or 0) >= 0.8)

    return {
        "total": len(items),
        "high_quality_count": high_quality,
        "this_month_count": month_count,
        "items": items,
    }


@router.post("/knowledge-captures/trigger", status_code=202)
async def trigger_knowledge_capture(
    req: KnowledgeCaptureTriggerRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """WF-4: 触发知识采集——生成AI问题并通过企微推送给员工."""
    from src.services.hr.knowledge_capture_service import KnowledgeCaptureService
    svc = KnowledgeCaptureService(session=session)
    result = await svc.trigger_capture(req.person_id, req.trigger_type)
    return {"status": "queued", "person_id": req.person_id, "detail": result}


@router.post("/knowledge-captures/submit", status_code=201)
async def submit_knowledge_capture(
    req: KnowledgeCaptureSubmitRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """WF-4: 提交对话内容——LLM解析 + 质量评分 + 写knowledge_captures."""
    from src.services.hr.knowledge_capture_service import KnowledgeCaptureService
    svc = KnowledgeCaptureService(session=session)
    capture = await svc.submit_capture(req.person_id, req.trigger_type, req.raw_dialogue)
    return capture


# ── Person CRUD ───────────────────────────────────────────────────────

@router.get("/persons")
async def list_persons(
    store_id: str = Query(..., description="门店ID"),
    search: Optional[str] = Query(None, description="姓名搜索"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """列出门店员工，含风险分和技能达标数."""
    if search:
        result = await session.execute(
            sa.text(
                "SELECT p.id, p.name, p.phone, "
                "       ea.id AS assignment_id, ea.employment_type, ea.start_date, "
                "       js.title AS job_title, "
                "       (SELECT rs.risk_score FROM retention_signals rs "
                "        WHERE rs.assignment_id = ea.id "
                "        ORDER BY rs.computed_at DESC LIMIT 1) AS risk_score, "
                "       (SELECT COUNT(*) FROM person_achievements pa "
                "        WHERE pa.person_id = p.id) AS achieved_count "
                "FROM persons p "
                "JOIN employment_assignments ea ON ea.person_id = p.id "
                "JOIN stores s ON s.org_node_id = ea.org_node_id "
                "LEFT JOIN job_standards js ON js.id = ea.job_standard_id "
                "WHERE s.id = :store_id "
                "  AND ea.status = 'active' "
                "  AND p.name ILIKE :search "
                "ORDER BY COALESCE("
                "  (SELECT rs2.risk_score FROM retention_signals rs2 "
                "   WHERE rs2.assignment_id = ea.id "
                "   ORDER BY rs2.computed_at DESC LIMIT 1), 0) DESC "
                "LIMIT :limit"
            ),
            {"store_id": store_id, "search": f"%{search}%", "limit": limit},
        )
    else:
        result = await session.execute(
            sa.text(
                "SELECT p.id, p.name, p.phone, "
                "       ea.id AS assignment_id, ea.employment_type, ea.start_date, "
                "       js.title AS job_title, "
                "       (SELECT rs.risk_score FROM retention_signals rs "
                "        WHERE rs.assignment_id = ea.id "
                "        ORDER BY rs.computed_at DESC LIMIT 1) AS risk_score, "
                "       (SELECT COUNT(*) FROM person_achievements pa "
                "        WHERE pa.person_id = p.id) AS achieved_count "
                "FROM persons p "
                "JOIN employment_assignments ea ON ea.person_id = p.id "
                "JOIN stores s ON s.org_node_id = ea.org_node_id "
                "LEFT JOIN job_standards js ON js.id = ea.job_standard_id "
                "WHERE s.id = :store_id "
                "  AND ea.status = 'active' "
                "ORDER BY COALESCE("
                "  (SELECT rs2.risk_score FROM retention_signals rs2 "
                "   WHERE rs2.assignment_id = ea.id "
                "   ORDER BY rs2.computed_at DESC LIMIT 1), 0) DESC "
                "LIMIT :limit"
            ),
            {"store_id": store_id, "limit": limit},
        )

    rows = result.fetchall()
    return {
        "store_id": store_id,
        "total": len(rows),
        "items": [
            {
                "id": str(row.id),
                "name": row.name,
                "phone": row.phone,
                "assignment_id": str(row.assignment_id),
                "employment_type": row.employment_type,
                "start_date": row.start_date.isoformat() if row.start_date else None,
                "job_title": row.job_title,
                "risk_score": float(row.risk_score) if row.risk_score is not None else None,
                "achieved_count": int(row.achieved_count or 0),
            }
            for row in rows
        ],
    }


@router.get("/persons/{person_id}")
async def get_person(
    person_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工详情：基本信息 + 当前在岗关系 + 技能认证 + 最新风险信号 + 近期知识采集."""
    # 基本信息
    person_result = await session.execute(
        sa.text(
            "SELECT id, name, phone, email, photo_url, preferences, created_at "
            "FROM persons WHERE id = :person_id"
        ),
        {"person_id": person_id},
    )
    person_row = person_result.fetchone()
    if not person_row:
        raise HTTPException(status_code=404, detail="员工不存在")

    # 在岗关系（全部，含历史）
    assign_result = await session.execute(
        sa.text(
            "SELECT ea.id, ea.employment_type, ea.start_date, ea.end_date, ea.status, "
            "       s.name AS store_name, s.id AS store_id, "
            "       js.title AS job_title "
            "FROM employment_assignments ea "
            "LEFT JOIN stores s ON s.org_node_id = ea.org_node_id "
            "LEFT JOIN job_standards js ON js.id = ea.job_standard_id "
            "WHERE ea.person_id = :person_id "
            "ORDER BY ea.start_date DESC"
        ),
        {"person_id": person_id},
    )
    assignments = [
        {
            "id": str(r.id),
            "employment_type": r.employment_type,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "status": r.status,
            "store_name": r.store_name,
            "store_id": str(r.store_id) if r.store_id else None,
            "job_title": r.job_title,
        }
        for r in assign_result.fetchall()
    ]

    # 技能认证
    ach_result = await session.execute(
        sa.text(
            "SELECT pa.id, pa.achieved_at, pa.evidence, "
            "       sn.skill_name, sn.category, sn.estimated_revenue_lift "
            "FROM person_achievements pa "
            "JOIN skill_nodes sn ON sn.id = pa.skill_node_id "
            "WHERE pa.person_id = :person_id "
            "ORDER BY pa.achieved_at DESC"
        ),
        {"person_id": person_id},
    )
    achievements = [
        {
            "id": str(r.id),
            "skill_name": r.skill_name,
            "category": r.category,
            "achieved_at": r.achieved_at.isoformat() if r.achieved_at else None,
            "evidence": r.evidence,
            "estimated_revenue_lift": float(r.estimated_revenue_lift) if r.estimated_revenue_lift else None,
        }
        for r in ach_result.fetchall()
    ]

    # 最新留任风险信号
    risk_result = await session.execute(
        sa.text(
            "SELECT rs.risk_score, rs.risk_factors, rs.intervention_status, rs.computed_at "
            "FROM retention_signals rs "
            "JOIN employment_assignments ea ON ea.id = rs.assignment_id "
            "WHERE ea.person_id = :person_id "
            "ORDER BY rs.computed_at DESC LIMIT 1"
        ),
        {"person_id": person_id},
    )
    risk_row = risk_result.fetchone()
    latest_risk = {
        "risk_score": float(risk_row.risk_score) if risk_row else None,
        "risk_factors": risk_row.risk_factors if risk_row else {},
        "intervention_status": risk_row.intervention_status if risk_row else None,
        "computed_at": risk_row.computed_at.isoformat() if risk_row and risk_row.computed_at else None,
    } if risk_row else None

    # 近期知识采集（最近5条）
    kc_result = await session.execute(
        sa.text(
            "SELECT id, trigger_type, context, quality_score, created_at "
            "FROM knowledge_captures "
            "WHERE person_id = :person_id "
            "ORDER BY created_at DESC LIMIT 5"
        ),
        {"person_id": person_id},
    )
    captures = [
        {
            "id": str(r.id),
            "trigger_type": r.trigger_type,
            "context": (r.context or "")[:100] if r.context else None,
            "quality_score": float(r.quality_score) if r.quality_score is not None else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in kc_result.fetchall()
    ]

    return {
        "id": str(person_row.id),
        "name": person_row.name,
        "phone": person_row.phone,
        "email": person_row.email,
        "photo_url": person_row.photo_url,
        "created_at": person_row.created_at.isoformat() if person_row.created_at else None,
        "assignments": assignments,
        "achievements": achievements,
        "latest_risk": latest_risk,
        "recent_captures": captures,
    }


# ── WF-5 新店人才梯队 ─────────────────────────────────────────────────

class TalentPipelineRequest(BaseModel):
    new_store_org_node_id: str
    open_date: Optional[str] = None    # ISO date string，如 "2026-06-01"
    headcount_plan: Optional[dict] = None  # {"kitchen": 5, "service": 8, ...}


@router.post("/talent-pipeline/analyze")
async def analyze_talent_pipeline(
    req: TalentPipelineRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """WF-5: 新店人才梯队分析.

    输入：新店OrgNode + 预计开业日期 + 岗位需求（可选）
    输出：人才就绪率 + 内部候选人清单 + 技能缺口 + 补招建议（含¥预算）
    """
    from src.services.hr.talent_pipeline_service import TalentPipelineService
    svc = TalentPipelineService(session=session)
    result = await svc.analyze(
        new_store_org_node_id=req.new_store_org_node_id,
        open_date=req.open_date,
        headcount_plan=req.headcount_plan,
    )
    return result
