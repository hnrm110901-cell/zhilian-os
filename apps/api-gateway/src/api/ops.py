"""
运维 Agent 专属 API
OpsAgent dedicated endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from ..core.dependencies import require_permission, get_db
from ..core.permissions import Permission
from ..models.user import User
from ..core.prompt_injection_guard import prompt_injection_guard, InputSource, SanitizationLevel, PromptInjectionException
from sqlalchemy.ext.asyncio import AsyncSession

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


# V2.0 新增 Request Models ──────────────────────────────────────────────

class DeviceReadingRequest(BaseModel):
    store_id: str
    device_name: str
    metric_type: str                  # temperature/power/online_status/tpm/clean_days
    value_float: Optional[float] = None
    value_bool: Optional[bool] = None
    unit: Optional[str] = None
    asset_id: Optional[str] = None


class NetworkHealthRequest(BaseModel):
    store_id: str
    probe_type: str                   # icmp/http/dns/bandwidth/wifi/vpn
    target: str
    is_available: bool = True
    latency_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    bandwidth_mbps: Optional[float] = None
    status_code: Optional[int] = None
    vlan: Optional[str] = None        # vlan10/vlan20/wan …


class SysHealthRequest(BaseModel):
    store_id: str
    system_name: str
    priority: str                     # P0/P1/P2/P3
    check_method: str                 # api_heartbeat/db_probe/port_check/process_check
    is_available: bool
    response_ms: Optional[float] = None
    http_status: Optional[int] = None
    error_message: Optional[str] = None


class FoodSafetyRequest(BaseModel):
    store_id: str
    record_type: str                  # cold_chain/fridge_power/ice_machine_clean/oil_quality/safety_device
    device_name: Optional[str] = None
    value_float: Optional[float] = None
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


# ─────────────────────────── Helpers ───────────────────────────

def _get_ops_agent():
    from ..agents.ops_agent import OpsAgent
    return OpsAgent()


# ─────────────────────────── 原有端点 ───────────────────────────

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
    try:
        sanitized_question = prompt_injection_guard.sanitize_input(
            body.question,
            source=InputSource.USER_INPUT,
            level=SanitizationLevel.MODERATE,
        )
    except PromptInjectionException as e:
        raise HTTPException(status_code=400, detail=f"输入包含非法内容: {e}")

    agent = _get_ops_agent()
    result = await agent.execute("nl_query", {
        "store_id": body.store_id,
        "question": sanitized_question,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


# ─────────────────────────── V2.0 新增端点 ───────────────────────────

@router.get("/dashboard/{store_id}")
async def store_dashboard(
    store_id: str,
    window_minutes: int = Query(30, ge=5, le=1440),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """
    门店运维健康总览（L1设备 + L2网络 + L3系统实时聚合）。
    返回三层健康分、活跃告警数、以及 Claude 生成的摘要建议。
    """
    agent = _get_ops_agent()
    result = await agent.execute("store_dashboard", {
        "store_id": store_id,
        "session": db,
        "window_minutes": window_minutes,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/monitor/device-reading")
async def record_device_reading(
    body: DeviceReadingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_WRITE)),
):
    """写入 IoT 设备读数（边缘网关上报入口）。自动判断告警并写入 ops_events。"""
    from ..services.ops_monitor_service import OpsMonitorService
    svc = OpsMonitorService()
    result = await svc.record_device_reading(
        db,
        store_id=body.store_id,
        device_name=body.device_name,
        metric_type=body.metric_type,
        value_float=body.value_float,
        value_bool=body.value_bool,
        unit=body.unit,
        asset_id=body.asset_id,
    )
    await db.commit()
    return result


@router.post("/monitor/network-health")
async def record_network_health(
    body: NetworkHealthRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_WRITE)),
):
    """写入网络探针结果（边缘网关上报入口）。"""
    from ..services.ops_monitor_service import OpsMonitorService
    svc = OpsMonitorService()
    result = await svc.record_network_health(
        db,
        store_id=body.store_id,
        probe_type=body.probe_type,
        target=body.target,
        is_available=body.is_available,
        latency_ms=body.latency_ms,
        packet_loss_pct=body.packet_loss_pct,
        bandwidth_mbps=body.bandwidth_mbps,
        status_code=body.status_code,
        vlan=body.vlan,
    )
    await db.commit()
    return result


@router.post("/monitor/sys-health")
async def record_sys_health(
    body: SysHealthRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_WRITE)),
):
    """写入系统心跳结果。P0 系统第1次失败即告警，P1 连续2次，P2/P3 连续3次。"""
    from ..services.ops_monitor_service import OpsMonitorService
    svc = OpsMonitorService()
    result = await svc.record_sys_health(
        db,
        store_id=body.store_id,
        system_name=body.system_name,
        priority=body.priority,
        check_method=body.check_method,
        is_available=body.is_available,
        response_ms=body.response_ms,
        http_status=body.http_status,
        error_message=body.error_message,
    )
    await db.commit()
    return result


@router.post("/monitor/food-safety")
async def record_food_safety(
    body: FoodSafetyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_WRITE)),
):
    """写入食安记录。超出 threshold_min/max 自动标记违规并创建 OpsEvent。"""
    from ..services.ops_monitor_service import OpsMonitorService
    svc = OpsMonitorService()
    result = await svc.record_food_safety(
        db,
        store_id=body.store_id,
        record_type=body.record_type,
        device_name=body.device_name,
        value_float=body.value_float,
        threshold_min=body.threshold_min,
        threshold_max=body.threshold_max,
        unit=body.unit,
        notes=body.notes,
    )
    await db.commit()
    return result


@router.get("/food-safety/{store_id}")
async def food_safety_status(
    store_id: str,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """
    食安合规状态查询（含 Claude 风险评估）。
    对应方案 3.2 食安设备监控SOP + 2026年6月食安新规合规要求。
    """
    agent = _get_ops_agent()
    result = await agent.execute("food_safety_status", {
        "store_id": store_id,
        "session": db,
        "days": days,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/alerts/converge/{store_id}")
async def converge_alerts(
    store_id: str,
    window_minutes: int = Query(5, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_OPS_READ)),
):
    """
    告警收敛：把时间窗口内多条告警归并为根因事件。
    对应方案 5.2 故障关联分析（外网断/交换机故障/软件崩溃/队列积压）。
    """
    agent = _get_ops_agent()
    result = await agent.execute("alert_convergence", {
        "store_id": store_id,
        "session": db,
        "window_minutes": window_minutes,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data



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
    try:
        sanitized_question = prompt_injection_guard.sanitize_input(
            body.question,
            source=InputSource.USER_INPUT,
            level=SanitizationLevel.MODERATE,
        )
    except PromptInjectionException as e:
        raise HTTPException(status_code=400, detail=f"输入包含非法内容: {e}")

    agent = _get_ops_agent()
    result = await agent.execute("nl_query", {
        "store_id": body.store_id,
        "question": sanitized_question,
    })
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data
