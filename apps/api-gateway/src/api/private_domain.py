"""
私域运营 API
Private Domain Operations API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from ..core.dependencies import get_current_active_user
from ..models.user import User

import sys
from pathlib import Path
# packages/ 目录位于仓库根（相对于此文件向上 5 级）
_repo_root = Path(__file__).resolve().parents[4]
agent_path = _repo_root / "packages" / "agents" / "private_domain" / "src"
_core_path = Path(__file__).resolve().parents[1] / "core"  # src/core（base_agent 所在目录）
for _p in (agent_path, _core_path):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from agent import PrivateDomainAgent

router = APIRouter(prefix="/api/v1/private-domain", tags=["private_domain"])


def _get_agent(store_id: str) -> PrivateDomainAgent:
    return PrivateDomainAgent(store_id=store_id)


# ─────────────────────────── Request Models ───────────────────────────

class TriggerJourneyRequest(BaseModel):
    journey_type: str
    customer_id: str


class ProcessReviewRequest(BaseModel):
    review_id: str
    customer_id: Optional[str] = None
    rating: int = 2
    content: str = ""


class QuadrantRequest(BaseModel):
    competition_density: float = 4.0
    member_count: int = 0
    estimated_population: int = 1000


# ─────────────────────────── Endpoints ───────────────────────────

@router.get("/dashboard/{store_id}")
async def get_dashboard(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取私域运营看板"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_dashboard", {})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/rfm/{store_id}")
async def get_rfm_segments(
    store_id: str,
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_active_user),
):
    """获取RFM用户分层"""
    agent = _get_agent(store_id)
    result = await agent.execute("analyze_rfm", {"days": days})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"segments": result.data, "total": len(result.data)}


@router.get("/signals/{store_id}")
async def get_signals(
    store_id: str,
    signal_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
):
    """获取信号列表"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_signals", {"signal_type": signal_type, "limit": limit})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"signals": result.data, "total": len(result.data)}


@router.get("/churn-risks/{store_id}")
async def get_churn_risks(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取流失风险用户"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_churn_risks", {})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"users": result.data, "total": len(result.data)}


@router.get("/journeys/{store_id}")
async def get_journeys(
    store_id: str,
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
):
    """获取旅程列表"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_journeys", {"status": status})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"journeys": result.data, "total": len(result.data)}


@router.post("/journeys/{store_id}/trigger")
async def trigger_journey(
    store_id: str,
    body: TriggerJourneyRequest,
    current_user: User = Depends(get_current_active_user),
):
    """触发用户旅程"""
    agent = _get_agent(store_id)
    result = await agent.execute("trigger_journey", {
        "journey_type": body.journey_type,
        "customer_id": body.customer_id,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/quadrant/{store_id}")
async def calculate_quadrant(
    store_id: str,
    body: QuadrantRequest,
    current_user: User = Depends(get_current_active_user),
):
    """计算门店四象限"""
    agent = _get_agent(store_id)
    result = await agent.execute("calculate_store_quadrant", {
        "competition_density": body.competition_density,
        "member_count": body.member_count,
        "estimated_population": body.estimated_population,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/reviews/{store_id}/process")
async def process_bad_review(
    store_id: str,
    body: ProcessReviewRequest,
    current_user: User = Depends(get_current_active_user),
):
    """处理差评，触发差评修复旅程"""
    agent = _get_agent(store_id)
    result = await agent.execute("process_bad_review", {
        "review_id": body.review_id,
        "customer_id": body.customer_id,
        "rating": body.rating,
        "content": body.content,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data
