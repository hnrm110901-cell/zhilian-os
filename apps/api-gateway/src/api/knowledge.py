"""知识OS层 API 路由

端点前缀: /api/v1/knowledge
  GET   /skills                      列出技能节点
  POST  /skills                      创建技能节点
  POST  /captures                    创建知识采集
  PUT   /captures/{capture_id}/review 审核知识
  GET   /passport/{person_id}        获取技能护照
  POST  /achievements                记录认证
  POST  /behavior-patterns           记录行为模式
  POST  /retention-signals           创建风险信号
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class SkillNodeCreateIn(BaseModel):
    skill_id: str = Field(..., max_length=50, description="技能编码")
    name: str = Field(..., max_length=100, description="技能名称")
    category: Optional[str] = Field(None, max_length=50, description="技能分类")
    max_level: int = Field(5, ge=1, le=10, description="最高等级")
    kpi_impact: Dict[str, Any] = Field(default_factory=dict, description="KPI影响")
    estimated_revenue_lift: float = Field(0.0, description="预估年营收提升(元)")
    prerequisites: List[str] = Field(default_factory=list, description="前置技能")
    related_trainings: List[str] = Field(default_factory=list, description="关联培训")
    description: Optional[str] = None


class KnowledgeCaptureCreateIn(BaseModel):
    person_id: str = Field(..., description="知识贡献者 ID")
    trigger_type: str = Field(..., description="触发类型: exit/review/project_end/spontaneous")
    trigger_context: Dict[str, Any] = Field(default_factory=dict)
    context: Optional[str] = Field(None, description="情境描述")
    action: Optional[str] = Field(None, description="行动描述")
    result: Optional[str] = Field(None, description="结果描述")
    capture_method: str = Field("dialogue", description="采集方式: dialogue/form/auto")


class KnowledgeReviewIn(BaseModel):
    quality_score: str = Field(..., description="质量评级: A/B/C/D")
    reviewer: str = Field(..., description="审核人 ID")


class AchievementCreateIn(BaseModel):
    person_id: str = Field(..., description="员工 ID")
    skill_node_id: str = Field(..., description="技能节点 ID")
    level: int = Field(1, ge=1, le=10, description="达成等级")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="认证证据")
    verification_method: Optional[str] = Field(None, description="验证方式")


class BehaviorPatternCreateIn(BaseModel):
    pattern_type: str = Field(..., description="模式类型: high_performer/churn_risk/service_quality")
    name: Optional[str] = Field(None, description="模式名称")
    description: Optional[str] = None
    feature_vector: Dict[str, Any] = Field(default_factory=dict)
    outcome: Optional[str] = None
    confidence: float = Field(0.0, ge=0, le=1)
    sample_size: int = Field(0, ge=0)
    version: int = Field(1, ge=1)


class RetentionSignalCreateIn(BaseModel):
    assignment_id: str = Field(..., description="任职关系 ID")
    risk_score: int = Field(..., ge=0, le=100, description="离职风险分 0-100")
    risk_level: str = Field("medium", description="风险等级: low/medium/high/critical")
    risk_factors: Dict[str, Any] = Field(default_factory=dict)
    model_version: Optional[str] = None


# ── 端点 ──────────────────────────────────────────────────────────────────────


@router.get("/skills", summary="列出技能节点")
async def list_skills(
    category: Optional[str] = Query(None, description="按分类过滤"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    nodes = await KnowledgeService.list_skill_nodes(db, category=category)
    return {"items": nodes, "total": len(nodes)}


@router.post("/skills", status_code=status.HTTP_201_CREATED, summary="创建技能节点")
async def create_skill(
    body: SkillNodeCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    node = await KnowledgeService.create_skill_node(db, body.model_dump())
    return node


@router.post("/captures", status_code=status.HTTP_201_CREATED, summary="创建知识采集")
async def create_capture(
    body: KnowledgeCaptureCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    capture = await KnowledgeService.capture_knowledge(db, body.model_dump())
    return capture


@router.put("/captures/{capture_id}/review", summary="审核知识")
async def review_capture(
    capture_id: str,
    body: KnowledgeReviewIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        result = await KnowledgeService.review_knowledge(
            db, capture_id, body.quality_score, body.reviewer
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return result


@router.get("/passport/{person_id}", summary="获取技能护照")
async def get_passport(
    person_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    passport = await KnowledgeService.get_person_skill_passport(db, person_id)
    return passport


@router.post("/achievements", status_code=status.HTTP_201_CREATED, summary="记录认证")
async def create_achievement(
    body: AchievementCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    achievement = await KnowledgeService.record_achievement(db, body.model_dump())
    return achievement


@router.post(
    "/behavior-patterns",
    status_code=status.HTTP_201_CREATED,
    summary="记录行为模式",
)
async def create_behavior_pattern(
    body: BehaviorPatternCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    pattern = await KnowledgeService.detect_behavior_pattern(db, body.model_dump())
    return pattern


@router.post(
    "/retention-signals",
    status_code=status.HTTP_201_CREATED,
    summary="创建风险信号",
)
async def create_retention_signal(
    body: RetentionSignalCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    signal = await KnowledgeService.create_retention_signal(db, body.model_dump())
    return signal
