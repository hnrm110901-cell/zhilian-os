"""
Agent API路由
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any
import structlog

from ..services.agent_service import AgentService
from ..core.dependencies import get_current_active_user, require_permission
from ..core.permissions import Permission
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
    current_user: User = Depends(require_permission(Permission.AGENT_SCHEDULE_WRITE)),
):
    """
    智能排班Agent

    基于AI的客流预测和自动排班生成。

    **认证要求**: 需要 `agent:schedule:write` 权限

    **支持的操作**:
    - `generate_schedule`: 生成排班计划
    - `optimize_schedule`: 优化现有排班
    - `analyze_staffing`: 分析人员需求

    **示例请求**:
    ```json
    {
        "agent_type": "schedule",
        "input_data": {
            "action": "generate_schedule",
            "params": {
                "store_id": "STORE_001",
                "start_date": "2024-02-20",
                "end_date": "2024-02-26",
                "constraints": {
                    "max_hours_per_week": 40,
                    "min_rest_hours": 12
                }
            }
        }
    }
    ```

    **示例响应**:
    ```json
    {
        "agent_type": "schedule",
        "output_data": {
            "schedule_id": "SCH_20240220_001",
            "shifts": [...],
            "coverage_rate": 0.95,
            "recommendations": [...]
        },
        "execution_time": 0.234
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未认证
    - `403 Forbidden`: 权限不足
    - `500 Internal Server Error`: Agent执行失败
    """
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
    current_user: User = Depends(require_permission(Permission.AGENT_ORDER_WRITE)),
):
    """订单协同Agent (需要订单权限)"""
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
    current_user: User = Depends(require_permission(Permission.AGENT_INVENTORY_WRITE)),
):
    """库存预警Agent (需要库存权限)"""
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
    current_user: User = Depends(require_permission(Permission.AGENT_SERVICE_WRITE)),
):
    """服务质量Agent (需要服务权限)"""
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
    current_user: User = Depends(require_permission(Permission.AGENT_TRAINING_WRITE)),
):
    """培训辅导Agent (需要培训权限)"""
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
    current_user: User = Depends(require_permission(Permission.AGENT_DECISION_READ)),
):
    """
    决策支持Agent

    提供KPI分析、业务洞察生成和改进建议。

    **认证要求**: 需要 `agent:decision:read` 权限

    **支持的操作**:
    - `generate_report`: 生成决策报告
    - `analyze_kpi`: 分析KPI指标
    - `get_insights`: 获取业务洞察
    - `get_recommendations`: 获取改进建议

    **示例请求**:
    ```json
    {
        "agent_type": "decision",
        "input_data": {
            "action": "generate_report",
            "params": {
                "store_id": "STORE_001",
                "start_date": "2024-02-01",
                "end_date": "2024-02-18",
                "include_recommendations": true
            }
        }
    }
    ```

    **示例响应**:
    ```json
    {
        "agent_type": "decision",
        "output_data": {
            "report_id": "RPT_20240218_001",
            "overall_health_score": 85.5,
            "kpi_summary": {
                "total_kpis": 12,
                "on_track": 8,
                "at_risk": 3,
                "off_track": 1
            },
            "insights": [...],
            "recommendations": [...]
        },
        "execution_time": 0.456
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未认证
    - `403 Forbidden`: 权限不足
    - `500 Internal Server Error`: Agent执行失败
    """
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
    current_user: User = Depends(require_permission(Permission.AGENT_RESERVATION_WRITE)),
):
    """预定宴会Agent (需要预订权限)"""
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
