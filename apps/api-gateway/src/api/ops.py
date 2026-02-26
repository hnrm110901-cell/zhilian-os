"""
运维 Agent 专属 API
OpsAgent dedicated endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from ..core.dependencies import require_permission
from ..core.permissions import Permission
from ..models.user import User

router = APIRouter()


# ─────────────────────────── Request Models ───────────────────────────

class DiagnoseRequest(BaseModel):
    store_id: str
    component: Optional[str] = None   # pos / router / printer / kds …
    symptom: str


class RunbookRequest(BaseModel):
    store_id: Optional[str] = None
    fault_type: str


class LinkSwitchRequest(BaseModel):
    store_id: str
    quality_score: float              # 主链路质量分 0-100


class NLQueryRequest(BaseModel):
    store_id: Optional[str] = None
    question: str


# ─────────────────────────── Helpers ───────────────────────────

def _get_ops_agent():
    from ..agents.ops_agent import OpsAgent
    return OpsAgent()


# ─────────────────────────── Endpoints ───────────────────────────

@router.get("/health/{store_id}")
async def health_check(
    store_id: str,
    scope: str = Query("store", regex="^(store|all)$"),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """门店 IT 健康检查（软件/硬件/网络三域）"""
    agent = _get_ops_agent()
    result = await agent.execute("health_check", {"store_id": store_id, "scope": scope})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/diagnose")
async def diagnose_fault(
    body: DiagnoseRequest,
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_WRITE)),
):
    """故障根因分析（目标 80% 故障 5 分钟内定位）"""
    agent = _get_ops_agent()
    result = await agent.execute("diagnose_fault", {
        "store_id": body.store_id,
        "component": body.component,
        "symptom": body.symptom,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/runbook")
async def runbook_suggestion(
    body: RunbookRequest,
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """修复步骤 / Runbook 建议"""
    agent = _get_ops_agent()
    result = await agent.execute("runbook_suggestion", {
        "store_id": body.store_id,
        "fault_type": body.fault_type,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/maintenance/{store_id}")
async def predict_maintenance(
    store_id: str,
    device_type: Optional[str] = Query(None),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """预测性维护建议（打印机/路由器/KDS/门禁等）"""
    agent = _get_ops_agent()
    result = await agent.execute("predict_maintenance", {
        "store_id": store_id,
        "device_type": device_type or "",
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/security/{store_id}")
async def security_advice(
    store_id: str,
    focus: Optional[str] = Query(None, regex="^(password|unauthorized_device|firmware|vpn)?$"),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """安全加固建议（弱密码/非授权设备/固件漏洞/VPN）"""
    agent = _get_ops_agent()
    result = await agent.execute("security_advice", {
        "store_id": store_id,
        "focus": focus,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/link-switch")
async def link_switch_advice(
    body: LinkSwitchRequest,
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_WRITE)),
):
    """主备链路切换建议（质量分 <70 时 30 秒内切换）"""
    agent = _get_ops_agent()
    result = await agent.execute("link_switch_advice", {
        "store_id": body.store_id,
        "quality_score": body.quality_score,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/assets/{store_id}")
async def asset_overview(
    store_id: str,
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """资产概览与台账建议（软件/硬件/网络三域）"""
    agent = _get_ops_agent()
    result = await agent.execute("asset_overview", {"store_id": store_id})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/query")
async def nl_query(
    body: NLQueryRequest,
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """自然语言运维问答（如「3号店今天网络为什么慢」）"""
    agent = _get_ops_agent()
    result = await agent.execute("nl_query", {
        "store_id": body.store_id,
        "question": body.question,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data
