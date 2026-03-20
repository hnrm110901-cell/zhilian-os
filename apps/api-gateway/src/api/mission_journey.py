"""
Mission Journey API — 使命旅程引擎端点

路由前缀: /api/v1/mission-journey
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.mission_journey_service import MissionJourneyService

router = APIRouter(prefix="/api/v1/mission-journey", tags=["使命旅程"])


# ── 旅程模板管理 ──────────────────────────────────────


@router.get("/templates")
async def list_templates(
    brand_id: Optional[str] = Query(None),
    journey_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """获取旅程模板列表"""
    return await MissionJourneyService.get_templates(
        db, brand_id=brand_id, journey_type=journey_type,
    )


@router.post("/templates")
async def create_template(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """创建旅程模板

    Body:
    {
        "name": "厨师成长之路",
        "journey_type": "career",
        "brand_id": "brand_xuji",
        "stages": [{"name":"新人融入","min_days":7,"tasks":[...]}]
    }
    """
    return await MissionJourneyService.create_template(
        db,
        name=body["name"],
        journey_type=body.get("journey_type", "career"),
        brand_id=body.get("brand_id"),
        store_id=body.get("store_id"),
        description=body.get("description"),
        applicable_positions=body.get("applicable_positions"),
        estimated_months=body.get("estimated_months"),
        stages=body.get("stages", []),
    )


# ── 员工旅程 ──────────────────────────────────────────


@router.post("/journeys/start")
async def start_journey(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """为员工开启旅程

    Body:
    {
        "person_id": "uuid",
        "store_id": "xuji_wuyi",
        "template_id": "uuid",
        "mentor_name": "李师傅"
    }
    """
    return await MissionJourneyService.start_journey(
        db,
        person_id=UUID(body["person_id"]),
        store_id=body["store_id"],
        template_id=UUID(body["template_id"]),
        mentor_person_id=(UUID(body["mentor_person_id"])
                          if body.get("mentor_person_id") else None),
        mentor_name=body.get("mentor_name"),
    )


@router.get("/journeys/my/{person_id}")
async def get_my_journeys(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取员工的所有旅程"""
    return await MissionJourneyService.get_my_journey(db, person_id)


@router.post("/journeys/{journey_id}/advance")
async def advance_stage(
    journey_id: UUID,
    body: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """推进旅程到下一阶段

    Body:
    {
        "evaluator_name": "张师傅",
        "evaluation_score": 85,
        "evaluation_comment": "刀工进步很大"
    }
    """
    return await MissionJourneyService.advance_stage(
        db,
        journey_id,
        evaluator_name=body.get("evaluator_name"),
        evaluation_score=body.get("evaluation_score"),
        evaluation_comment=body.get("evaluation_comment"),
    )


# ── 里程碑 ────────────────────────────────────────────


@router.get("/journeys/{journey_id}/milestones")
async def get_milestones(
    journey_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取旅程里程碑列表"""
    return await MissionJourneyService.get_milestones(db, journey_id)


@router.post("/journeys/{journey_id}/milestones/{milestone_code}/achieve")
async def achieve_milestone(
    journey_id: UUID,
    milestone_code: str,
    body: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """标记里程碑达成

    Body:
    {
        "evidence": "试岗考核85分，刀工/卫生/协作均达标",
        "reward_fen": 20000,
        "badge_name": "试岗之星"
    }
    """
    return await MissionJourneyService.achieve_milestone(
        db,
        journey_id,
        milestone_code,
        evidence=body.get("evidence"),
        reward_fen=body.get("reward_fen", 0),
        badge_name=body.get("badge_name"),
    )


# ── 成长叙事 ──────────────────────────────────────────


@router.get("/narratives/{person_id}")
async def get_narratives(
    person_id: UUID,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取员工成长叙事时间线"""
    return await MissionJourneyService.get_narratives(
        db, person_id, limit=limit,
    )


# ── 文化墙 ────────────────────────────────────────────


@router.get("/culture-wall/{store_id}")
async def get_culture_wall(
    store_id: str,
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取门店文化墙（公开成长叙事）"""
    return await MissionJourneyService.get_culture_wall(
        db, store_id, limit=limit,
    )


# ── 统计 ──────────────────────────────────────────────


@router.get("/stats/{store_id}")
async def get_journey_stats(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取门店旅程统计"""
    return await MissionJourneyService.get_store_journey_stats(db, store_id)
