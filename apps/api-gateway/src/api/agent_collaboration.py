"""
Agent Collaboration API Endpoints
Agent协同API端点

Phase 4: 智能优化期 (Intelligence Optimization Period)
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from src.services.agent_collaboration_optimizer import (
    AgentCollaborationOptimizer,
    AgentType,
    AgentDecision,
    ConflictType,
    ResolutionStrategy
)
from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/api/v1/collaboration", tags=["agent_collaboration"])


# Request/Response Models
class AgentTypeEnum(str, Enum):
    """Agent type enum"""
    SCHEDULE = "schedule"
    ORDER = "order"
    INVENTORY = "inventory"
    SERVICE = "service"
    TRAINING = "training"
    DECISION = "decision"
    RESERVATION = "reservation"


class ResolutionStrategyEnum(str, Enum):
    """Resolution strategy enum"""
    PRIORITY_BASED = "priority_based"
    NEGOTIATION = "negotiation"
    OPTIMIZATION = "optimization"
    ESCALATION = "escalation"


class SubmitDecisionRequest(BaseModel):
    """Submit agent decision request"""
    agent_type: AgentTypeEnum
    decision_id: str
    action: str
    resources_required: Dict[str, float]
    expected_benefit: float
    priority: int = Field(ge=1, le=10)
    constraints: List[str] = []


class CoordinateRequest(BaseModel):
    """Coordinate decisions request"""
    store_id: str
    time_window: int = int(os.getenv("AGENT_COLLAB_TIME_WINDOW", "3600"))  # seconds


class ResolveConflictRequest(BaseModel):
    """Resolve conflict request"""
    conflict_id: str
    strategy: Optional[ResolutionStrategyEnum] = None


class AgentPerformanceRequest(BaseModel):
    """Get agent performance request"""
    agent_type: AgentTypeEnum
    start_date: datetime
    end_date: datetime


# API Endpoints
@router.post("/decision/submit")
async def submit_decision(
    request: SubmitDecisionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Submit decision from agent
    提交Agent决策

    Agents submit decisions for coordination.
    System detects conflicts automatically.
    """
    try:
        optimizer = AgentCollaborationOptimizer(db)

        decision = AgentDecision(
            agent_type=AgentType(request.agent_type.value),
            decision_id=request.decision_id,
            action=request.action,
            resources_required=request.resources_required,
            expected_benefit=request.expected_benefit,
            priority=request.priority,
            constraints=request.constraints,
            timestamp=datetime.utcnow()
        )

        result = optimizer.submit_decision(
            agent_type=AgentType(request.agent_type.value),
            decision=decision
        )

        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coordinate")
async def coordinate_decisions(
    request: CoordinateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Coordinate all pending decisions
    协调所有待处理决策

    Performs global optimization:
    1. Collect all pending decisions
    2. Detect conflicts
    3. Resolve conflicts
    4. Optimize resource allocation
    5. Return coordinated plan
    """
    try:
        optimizer = AgentCollaborationOptimizer(db)

        result = optimizer.coordinate_decisions(
            store_id=request.store_id,
            time_window=request.time_window
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conflict/resolve")
async def resolve_conflict(
    request: ResolveConflictRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Resolve specific conflict
    解决特定冲突

    Resolution strategies:
    - PRIORITY_BASED: Use agent priorities
    - NEGOTIATION: Negotiate resource sharing
    - OPTIMIZATION: Global optimization
    - ESCALATION: Escalate to human
    """
    try:
        optimizer = AgentCollaborationOptimizer(db)

        strategy = None
        if request.strategy:
            strategy = ResolutionStrategy(request.strategy.value)

        resolution = optimizer.resolve_conflict(
            conflict_id=request.conflict_id,
            strategy=strategy
        )

        return {
            "success": True,
            "conflict_id": resolution.conflict_id,
            "strategy": resolution.strategy.value,
            "approved_decisions": resolution.approved_decisions,
            "rejected_decisions": resolution.rejected_decisions,
            "modifications": resolution.modifications,
            "reason": resolution.reason,
            "resolved_at": resolution.resolved_at.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{store_id}")
async def get_collaboration_status(
    store_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get agent collaboration status
    获取Agent协同状态

    Returns:
    - Pending decisions by agent
    - Active conflicts
    - Resolved conflicts
    - Coordination efficiency
    """
    try:
        optimizer = AgentCollaborationOptimizer(db)

        status = optimizer.get_collaboration_status(store_id=store_id)

        return {
            "success": True,
            **status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance")
async def get_agent_performance(
    request: AgentPerformanceRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Get agent performance metrics
    获取Agent性能指标

    Tracks:
    - Decision approval rate
    - Conflict rate
    - Resource utilization
    - Benefit realization
    """
    try:
        optimizer = AgentCollaborationOptimizer(db)

        performance = optimizer.get_agent_performance(
            agent_type=AgentType(request.agent_type.value),
            start_date=request.start_date,
            end_date=request.end_date
        )

        return {
            "success": True,
            **performance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
