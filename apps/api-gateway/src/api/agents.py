"""
Agent API路由
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any
import structlog

from ..services.agent_service import AgentService
from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()

# 初始化Agent服务
agent_service = AgentService()


class AgentRequest(BaseModel):
    """Agent请求"""

    agent_type: str
    input_data: Dict[str, Any]


class AgentResponse(BaseModel):
    """Agent响应"""

    agent_type: str
    output_data: Dict[str, Any]
    execution_time: float


@router.post("/schedule", response_model=AgentResponse)
async def schedule_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """智能排班Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("schedule", request.input_data)
        return AgentResponse(
            agent_type="schedule",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("排班Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order", response_model=AgentResponse)
async def order_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """订单协同Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("order", request.input_data)
        return AgentResponse(
            agent_type="order",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("订单Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory", response_model=AgentResponse)
async def inventory_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """库存预警Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("inventory", request.input_data)
        return AgentResponse(
            agent_type="inventory",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("库存Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/service", response_model=AgentResponse)
async def service_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """服务质量Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("service", request.input_data)
        return AgentResponse(
            agent_type="service",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("服务Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training", response_model=AgentResponse)
async def training_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """培训辅导Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("training", request.input_data)
        return AgentResponse(
            agent_type="training",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("培训Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decision", response_model=AgentResponse)
async def decision_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """决策支持Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("decision", request.input_data)
        return AgentResponse(
            agent_type="decision",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("决策Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reservation", response_model=AgentResponse)
async def reservation_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_active_user),
):
    """预定宴会Agent (需要登录)"""
    try:
        result = await agent_service.execute_agent("reservation", request.input_data)
        return AgentResponse(
            agent_type="reservation",
            output_data=result,
            execution_time=result.get("execution_time", 0.0),
        )
    except Exception as e:
        logger.error("预定Agent执行失败", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))
