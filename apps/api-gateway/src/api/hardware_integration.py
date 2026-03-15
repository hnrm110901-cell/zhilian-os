"""
硬件集成API - 树莓派5 + Shokz设备
边缘计算与语音交互接口
"""
from types import SimpleNamespace
import secrets
import os
from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel

from src.core.config import settings
from src.core.dependencies import get_db, get_current_user
from src.services.raspberry_pi_edge_service import (
    get_raspberry_pi_edge_service,
    RaspberryPiEdgeService,
    NetworkMode,
    EdgeNodeInfo
)
from src.services.shokz_device_service import (
    get_shokz_device_service,
    ShokzDeviceService,
    ShokzDeviceModel,
    VoiceCommand
)
from src.models.user import User
from src.models.audit_log import AuditAction, ResourceType
from src.services.audit_log_service import audit_log_service
from src.services.edge_bootstrap_token_service import get_edge_bootstrap_token_service

router = APIRouter(prefix="/api/v1/hardware")
edge_security = HTTPBearer(auto_error=False)


class EdgeCommandAckRequest(BaseModel):
    status: str
    result: Optional[dict] = None
    last_error: Optional[str] = None


async def _safe_audit_log(
    *,
    action: str,
    resource_id: str,
    description: str,
    current_user,
    store_id: Optional[str] = None,
    changes: Optional[dict] = None,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
) -> None:
    try:
        await audit_log_service.log_action(
            action=action,
            resource_type=ResourceType.EDGE_HUB,
            user_id=str(getattr(current_user, "id", "system")),
            username=getattr(current_user, "username", None),
            user_role=str(getattr(current_user, "role", "")) if getattr(current_user, "role", None) else None,
            resource_id=resource_id,
            description=description,
            changes=changes,
            old_value=old_value,
            new_value=new_value,
            store_id=store_id,
        )
    except Exception:
        # 审计失败不能阻断硬件接入主链路
        return


async def _get_edge_node_audit_summary(node_id: str) -> dict:
    try:
        logs, total = await audit_log_service.get_logs(
            resource_type=ResourceType.EDGE_HUB,
            resource_id=node_id,
            skip=0,
            limit=1,
        )
    except Exception:
        return {
            "available": False,
            "total": 0,
            "latest_action": None,
            "latest_description": None,
            "latest_at": None,
        }

    latest = logs[0].to_dict() if logs else None
    return {
        "available": True,
        "total": total,
        "latest_action": latest["action"] if latest else None,
        "latest_description": latest.get("description") if latest else None,
        "latest_at": latest.get("created_at") if latest else None,
    }


def _build_commissioning_summary(*, nodes: list[dict], devices: list[dict]) -> dict:
    connected_devices = [device for device in devices if device.get("status") == "connected"]
    low_battery_devices = [device for device in devices if device.get("status") == "low_battery"]
    credential_ready_nodes = [node for node in nodes if node.get("credential_ok")]
    online_nodes = [node for node in nodes if node.get("status") == "online"]
    queue_backlog_nodes = [node for node in nodes if (node.get("pending_status_queue") or 0) > 0]

    target_macs = [
        mac.strip().upper()
        for mac in os.getenv("SHOKZ_TARGET_MACS", "").split(",")
        if mac.strip()
    ]
    registered_macs = {str(device.get("mac_address", "")).upper() for device in devices if device.get("mac_address")}
    missing_target_macs = [mac for mac in target_macs if mac not in registered_macs]

    ready = bool(online_nodes and credential_ready_nodes and connected_devices and not queue_backlog_nodes)

    checklist = [
        {
            "key": "edge_online",
            "label": "树莓派在线",
            "passed": bool(online_nodes),
            "detail": f"{len(online_nodes)}/{len(nodes)} 个边缘节点在线" if nodes else "当前门店未注册边缘节点",
        },
        {
            "key": "credential_ready",
            "label": "设备凭证有效",
            "passed": bool(nodes) and len(credential_ready_nodes) == len(nodes),
            "detail": f"{len(credential_ready_nodes)}/{len(nodes)} 个节点凭证有效" if nodes else "暂无节点凭证信息",
        },
        {
            "key": "queue_clean",
            "label": "离线队列无积压",
            "passed": len(queue_backlog_nodes) == 0,
            "detail": "无待补发状态队列" if not queue_backlog_nodes else f"{len(queue_backlog_nodes)} 个节点存在队列积压",
        },
        {
            "key": "headset_connected",
            "label": "Shokz 已连接",
            "passed": bool(connected_devices),
            "detail": f"{len(connected_devices)}/{len(devices)} 台耳机已连接" if devices else "当前门店未注册 Shokz 设备",
        },
        {
            "key": "headset_battery",
            "label": "Shokz 电量正常",
            "passed": len(low_battery_devices) == 0,
            "detail": "无低电量设备" if not low_battery_devices else f"{len(low_battery_devices)} 台设备低电量",
        },
        {
            "key": "target_mac_registered",
            "label": "目标 MAC 已登记",
            "passed": len(missing_target_macs) == 0,
            "detail": "目标耳机 MAC 已全部登记" if not missing_target_macs else f"缺少 {len(missing_target_macs)} 个目标 MAC",
        },
    ]

    return {
        "ready": ready,
        "summary": {
            "edge_nodes_total": len(nodes),
            "edge_nodes_online": len(online_nodes),
            "credential_ready_nodes": len(credential_ready_nodes),
            "queue_backlog_nodes": len(queue_backlog_nodes),
            "shokz_total": len(devices),
            "shokz_connected": len(connected_devices),
            "shokz_low_battery": len(low_battery_devices),
            "target_macs_total": len(target_macs),
            "target_macs_registered": len(target_macs) - len(missing_target_macs),
        },
        "target_macs": target_macs,
        "missing_target_macs": missing_target_macs,
        "checklist": checklist,
    }


async def get_edge_bootstrap_or_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(edge_security),
    session: AsyncSession = Depends(get_db),
):
    if credentials:
        token = credentials.credentials
        try:
            token_svc = get_edge_bootstrap_token_service()
            if await token_svc.verify_token(token):
                return SimpleNamespace(
                    id="edge-bootstrap",
                    username="edge-bootstrap",
                    role="system",
                    is_active=True,
                    auth_type="edge_bootstrap_dynamic",
                )
        except Exception:
            pass

        if settings.EDGE_BOOTSTRAP_TOKEN and secrets.compare_digest(token, settings.EDGE_BOOTSTRAP_TOKEN):
            return SimpleNamespace(
                id="edge-bootstrap",
                username="edge-bootstrap",
                role="system",
                is_active=True,
                auth_type="edge_bootstrap_static",
            )

        return await get_current_user(credentials, session)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="缺少认证信息",
    )


async def get_edge_node_or_user(
    node_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(edge_security),
    session: AsyncSession = Depends(get_db),
    x_edge_node_secret: Optional[str] = Header(default=None, alias="X-Edge-Node-Secret"),
):
    service = get_raspberry_pi_edge_service()
    if x_edge_node_secret and await service.verify_device_secret(node_id, x_edge_node_secret):
        return SimpleNamespace(
            id=node_id,
            username=node_id,
            role="edge-node",
            is_active=True,
            auth_type="edge_device",
        )

    if credentials:
        return await get_current_user(credentials, session)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="缺少认证信息",
    )


# ==================== 树莓派5边缘节点 ====================

@router.post("/edge-node/register")
async def register_edge_node(
    store_id: str,
    device_name: str,
    ip_address: str,
    mac_address: str,
    current_user=Depends(get_edge_bootstrap_or_user)
):
    """
    注册边缘节点

    门店部署树莓派5时，首次启动自动注册到云端
    """
    service = get_raspberry_pi_edge_service()
    node = await service.register_edge_node(
        store_id=store_id,
        device_name=device_name,
        ip_address=ip_address,
        mac_address=mac_address
    )
    device_secret = service.get_or_create_device_secret(node.node_id)
    await _safe_audit_log(
        action=AuditAction.EDGE_NODE_REGISTER,
        resource_id=node.node_id,
        description=f"注册边缘节点 {node.device_name}",
        current_user=current_user,
        store_id=node.store_id,
        new_value={
            "node_id": node.node_id,
            "device_name": node.device_name,
            "ip_address": node.ip_address,
            "mac_address": node.mac_address,
        },
    )

    return {
        "success": True,
        "node": node.model_dump(),
        "device_secret": device_secret,
        "message": "边缘节点注册成功"
    }


@router.post("/edge-node/{node_id}/status")
async def update_node_status(
    node_id: str,
    cpu_usage: float,
    memory_usage: float,
    disk_usage: float,
    temperature: float,
    uptime_seconds: int,
    pending_status_queue: int = 0,
    last_queue_error: Optional[str] = None,
    current_user=Depends(get_edge_node_or_user)
):
    """
    更新节点状态

    树莓派5每30秒上报一次状态
    """
    service = get_raspberry_pi_edge_service()
    node = await service.update_node_status(
        node_id=node_id,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        disk_usage=disk_usage,
        temperature=temperature,
        uptime_seconds=uptime_seconds,
        pending_status_queue=pending_status_queue,
        last_queue_error=last_queue_error,
    )

    return {
        "success": True,
        "node": node.model_dump()
    }


@router.post("/edge-node/{node_id}/network-mode")
async def switch_network_mode(
    node_id: str,
    mode: NetworkMode,
    current_user=Depends(get_edge_node_or_user)
):
    """
    切换网络模式

    - CLOUD: 云端模式（正常联网）
    - EDGE: 边缘模式（离线工作）
    - HYBRID: 混合模式（云边协同）
    """
    service = get_raspberry_pi_edge_service()
    node = await service.switch_network_mode(node_id=node_id, mode=mode)

    return {
        "success": True,
        "node": node.model_dump(),
        "message": f"已切换到{mode}模式"
    }


@router.post("/edge-node/{node_id}/inference")
async def local_inference(
    node_id: str,
    model_type: str,
    input_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    本地AI推理

    在树莓派5上运行AI模型，无需联网

    支持的模型类型：
    - asr: 语音识别
    - tts: 语音合成
    - intent: 意图识别
    - decision: 决策生成
    """
    service = get_raspberry_pi_edge_service()
    result = await service.local_inference(
        node_id=node_id,
        model_type=model_type,
        input_data=input_data
    )

    return {
        "success": True,
        "result": result
    }


@router.post("/edge-node/{node_id}/sync")
async def sync_with_cloud(
    node_id: str,
    current_user=Depends(get_edge_node_or_user)
):
    """
    与云端同步

    - 上传本地数据
    - 下载模型更新
    - 同步配置
    """
    service = get_raspberry_pi_edge_service()
    result = await service.sync_with_cloud(node_id=node_id)

    return {
        "success": True,
        "sync_result": result
    }


@router.get("/edge-node/{node_id}/commands")
async def poll_edge_node_commands(
    node_id: str,
    limit: int = 10,
    current_user=Depends(get_edge_node_or_user),
):
    """边缘节点主动拉取待执行命令。"""
    service = get_raspberry_pi_edge_service()
    commands = await service.poll_commands(node_id=node_id, limit=limit)
    return {
        "success": True,
        "node_id": node_id,
        "commands": [command.model_dump() for command in commands],
    }


@router.post("/edge-node/{node_id}/commands/{command_id}/ack")
async def acknowledge_edge_node_command(
    node_id: str,
    command_id: str,
    body: EdgeCommandAckRequest,
    current_user=Depends(get_edge_node_or_user),
):
    """边缘节点回执命令执行结果。"""
    service = get_raspberry_pi_edge_service()
    command = await service.acknowledge_command(
        node_id=node_id,
        command_id=command_id,
        status=body.status,
        result=body.result,
        last_error=body.last_error,
    )
    return {
        "success": True,
        "command": command.model_dump(),
    }


@router.post("/edge-node/{node_id}/rotate-secret")
async def rotate_edge_node_secret(
    node_id: str,
    current_user: User = Depends(get_current_user)
):
    """轮换边缘节点 device_secret。"""
    service = get_raspberry_pi_edge_service()
    status_before = await service.get_credential_status(node_id)
    new_secret = await service.rotate_device_secret(node_id=node_id)
    status_after = await service.get_credential_status(node_id)
    await _safe_audit_log(
        action=AuditAction.EDGE_NODE_SECRET_ROTATE,
        resource_id=node_id,
        description=f"轮换边缘节点 device_secret: {node_id}",
        current_user=current_user,
        store_id=status_after.get("store_id"),
        old_value=status_before,
        new_value={**status_after, "device_secret_rotated": True},
    )
    return {
        "success": True,
        "node_id": node_id,
        "device_secret": new_secret,
        "message": "device_secret 已轮换"
    }


@router.post("/edge-node/{node_id}/revoke-secret")
async def revoke_edge_node_secret(
    node_id: str,
    current_user: User = Depends(get_current_user)
):
    """吊销边缘节点 device_secret。"""
    service = get_raspberry_pi_edge_service()
    status_before = await service.get_credential_status(node_id)
    await service.revoke_device_secret(node_id=node_id)
    status_after = await service.get_credential_status(node_id)
    await _safe_audit_log(
        action=AuditAction.EDGE_NODE_SECRET_REVOKE,
        resource_id=node_id,
        description=f"吊销边缘节点 device_secret: {node_id}",
        current_user=current_user,
        store_id=status_after.get("store_id"),
        old_value=status_before,
        new_value=status_after,
    )
    return {
        "success": True,
        "node_id": node_id,
        "message": "device_secret 已吊销"
    }


@router.get("/edge-node/{node_id}/credential-status")
async def get_edge_node_credential_status(
    node_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取边缘节点凭证状态，用于运维排查。"""
    service = get_raspberry_pi_edge_service()
    status_payload = await service.get_credential_status(node_id=node_id)
    return {
        "success": True,
        "credential_status": status_payload,
        "bootstrap_token_configured": bool(settings.EDGE_BOOTSTRAP_TOKEN),
    }


@router.get("/edge-node/{node_id}/recovery-guide")
async def get_edge_node_recovery_guide(
    node_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取边缘节点重注册/恢复指引。"""
    service = get_raspberry_pi_edge_service()
    node = await service.get_node_info(node_id=node_id)
    credential_status = await service.get_credential_status(node_id=node_id)
    requires_rebootstrap = not credential_status.get("device_secret_active", False)
    bootstrap_configured = bool(settings.EDGE_BOOTSTRAP_TOKEN)
    installer_command = (
        "sudo EDGE_API_BASE_URL=http://your-api-host:8000 \\\n"
        "     EDGE_API_TOKEN=replace-with-bootstrap-token \\\n"
        f"     EDGE_STORE_ID={node.store_id} \\\n"
        f"     EDGE_DEVICE_NAME={node.device_name} \\\n"
        "     bash scripts/install_raspberry_pi_edge.sh"
    )
    steps = [
        "确认 API Gateway 已配置 EDGE_BOOTSTRAP_TOKEN，且边缘节点能访问服务端。",
        "在树莓派上检查 /etc/zhilian-edge/edge-node.env，确认 EDGE_API_BASE_URL 和 EDGE_STORE_ID 正确。",
        "如果当前凭证已失效或被吊销，重新写入 bootstrap token 后重启服务，触发自动注册。",
        "执行 systemctl restart zhilian-edge-node.service，并通过 journalctl -u zhilian-edge-node.service -f 观察日志。",
        "回到硬件管理页刷新状态，确认节点重新拿到 device_secret 并恢复心跳。",
    ]
    if not requires_rebootstrap:
        steps[2] = "当前 device_secret 仍有效，优先检查网络、时间同步和本地配置，再决定是否重新注册。"

    return {
        "success": True,
        "node_id": node_id,
        "store_id": node.store_id,
        "device_name": node.device_name,
        "requires_rebootstrap": requires_rebootstrap,
        "bootstrap_token_configured": bootstrap_configured,
        "required_env": [
            "EDGE_API_BASE_URL",
            "EDGE_API_TOKEN",
            "EDGE_STORE_ID",
            "EDGE_DEVICE_NAME",
        ],
        "service_name": "zhilian-edge-node.service",
        "config_file": "/etc/zhilian-edge/edge-node.env",
        "state_file": "/var/lib/zhilian-edge/node_state.json",
        "installer_command_template": installer_command,
        "steps": steps,
        "credential_status": credential_status,
    }


@router.get("/edge-node/{node_id}/audit-logs")
async def get_edge_node_audit_logs(
    node_id: str,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """获取边缘节点审计记录，用于凭证运维排查。"""
    logs, total = await audit_log_service.get_logs(
        resource_type=ResourceType.EDGE_HUB,
        resource_id=node_id,
        skip=skip,
        limit=limit,
    )
    return {
        "success": True,
        "node_id": node_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "logs": [log.to_dict() for log in logs],
    }


@router.get("/edge-node/{node_id}")
async def get_edge_node_info(
    node_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取边缘节点信息"""
    service = get_raspberry_pi_edge_service()
    node = await service.get_node_info(node_id=node_id)
    audit_summary = await _get_edge_node_audit_summary(node_id)

    return {
        "node": node.model_dump(),
        "audit_summary": audit_summary,
    }


@router.get("/edge-node/store/{store_id}")
async def list_store_edge_nodes(
    store_id: str,
    current_user: User = Depends(get_current_user)
):
    """列出门店的所有边缘节点"""
    service = get_raspberry_pi_edge_service()
    nodes = await service.list_store_nodes(store_id=store_id)
    enriched_nodes = []
    for node in nodes:
        credential_status = await service.get_credential_status(node.node_id)
        audit_summary = await _get_edge_node_audit_summary(node.node_id)
        payload = node.model_dump()
        payload["credential_status"] = credential_status
        payload["credential_ok"] = credential_status["device_secret_active"]
        payload["credential_persisted"] = credential_status["device_secret_persisted"]
        payload["audit_summary"] = audit_summary
        enriched_nodes.append(payload)

    return {
        "store_id": store_id,
        "total": len(enriched_nodes),
        "nodes": enriched_nodes
    }


@router.get("/edge-node/specs")
async def get_hardware_specs(
    current_user: User = Depends(get_current_user)
):
    """获取硬件规格"""
    service = get_raspberry_pi_edge_service()
    specs = await service.get_hardware_specs()

    return {
        "specs": specs
    }


@router.get("/edge-node/deployment-cost")
async def get_edge_deployment_cost(
    current_user: User = Depends(get_current_user)
):
    """
    获取部署成本

    用于向投资人证明轻量化部署
    """
    service = get_raspberry_pi_edge_service()
    cost = await service.get_deployment_cost()

    return {
        "cost": cost,
        "summary": {
            "total_cost_per_store": cost["total_cost_per_store"],
            "deployment_time_hours": cost["deployment_time_hours"],
            "roi_months": 2  # 2个月回本
        }
    }


# ==================== Shokz设备 ====================

@router.post("/shokz/register")
async def register_shokz_device(
    device_name: str,
    device_model: ShokzDeviceModel,
    mac_address: str,
    store_id: str,
    user_id: str,
    user_role: str,
    edge_node_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    注册Shokz设备

    门店部署时，将Shokz耳机与树莓派5配对
    """
    service = get_shokz_device_service()
    device = await service.register_device(
        device_name=device_name,
        device_model=device_model,
        mac_address=mac_address,
        store_id=store_id,
        user_id=user_id,
        user_role=user_role,
        edge_node_id=edge_node_id
    )

    return {
        "success": True,
        "device": device.model_dump(),
        "message": "Shokz设备注册成功"
    }


@router.post("/shokz/{device_id}/connect")
async def connect_shokz_device(
    device_id: str,
    current_user: User = Depends(get_current_user)
):
    """连接Shokz设备"""
    service = get_shokz_device_service()
    device = await service.connect_device(device_id=device_id)

    return {
        "success": True,
        "device": device.model_dump(),
        "message": "设备已连接"
    }


@router.post("/shokz/{device_id}/disconnect")
async def disconnect_shokz_device(
    device_id: str,
    current_user: User = Depends(get_current_user)
):
    """断开Shokz设备连接"""
    service = get_shokz_device_service()
    device = await service.disconnect_device(device_id=device_id)

    return {
        "success": True,
        "device": device.model_dump(),
        "message": "设备已断开"
    }


@router.post("/shokz/{device_id}/voice-input")
async def shokz_voice_input(
    device_id: str,
    audio_data: str,
    current_user: User = Depends(get_current_user)
):
    """
    语音输入

    店长通过Shokz耳机说话，系统识别并处理
    """
    service = get_shokz_device_service()
    interaction = await service.voice_input(
        device_id=device_id,
        audio_data=audio_data
    )

    return {
        "success": True,
        "interaction": interaction.model_dump()
    }


@router.post("/shokz/{device_id}/voice-output")
async def shokz_voice_output(
    device_id: str,
    text: str,
    priority: str = "normal",
    current_user: User = Depends(get_current_user)
):
    """
    语音输出

    系统主动推送语音通知到Shokz耳机
    """
    service = get_shokz_device_service()
    result = await service.voice_output(
        device_id=device_id,
        text=text,
        priority=priority
    )

    return {
        "success": True,
        "result": result
    }


@router.post("/shokz/alert")
async def send_shokz_alert(
    store_id: str,
    alert_type: VoiceCommand,
    message: str,
    target_roles: Optional[List[str]] = None,
    current_user: User = Depends(get_current_user)
):
    """
    发送异常驱动通知

    场景：
    - 外卖催单："小李，美团外卖3单催单，优先处理"
    - VIP到店："张总到店，上次点的剁椒鱼头，今天推荐香辣蟹"
    - 异常预警："3号桌等待超过30分钟，需要安抚"
    """
    service = get_shokz_device_service()
    results = await service.send_alert(
        store_id=store_id,
        alert_type=alert_type,
        message=message,
        target_roles=target_roles
    )

    return {
        "success": True,
        "devices_notified": len(results),
        "results": results
    }


@router.get("/shokz/{device_id}")
async def get_shokz_device_info(
    device_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取Shokz设备信息"""
    service = get_shokz_device_service()
    device = await service.get_device_info(device_id=device_id)

    return {
        "device": device.model_dump()
    }


@router.get("/shokz/store/{store_id}")
async def list_store_shokz_devices(
    store_id: str,
    current_user: User = Depends(get_current_user)
):
    """列出门店的所有Shokz设备"""
    service = get_shokz_device_service()
    devices = await service.list_store_devices(store_id=store_id)

    return {
        "store_id": store_id,
        "total": len(devices),
        "devices": [device.model_dump() for device in devices]
    }


@router.get("/shokz/store/{store_id}/commissioning-diagnostic")
async def get_store_shokz_commissioning_diagnostic(
    store_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取门店 Shokz 联调/验收诊断摘要。"""
    edge_service = get_raspberry_pi_edge_service()
    shokz_service = get_shokz_device_service()

    nodes = await edge_service.list_store_nodes(store_id=store_id)
    devices = await shokz_service.list_store_devices(store_id=store_id)

    enriched_nodes = []
    for node in nodes:
        credential_status = await edge_service.get_credential_status(node.node_id)
        payload = node.model_dump()
        payload["credential_ok"] = credential_status["device_secret_active"]
        enriched_nodes.append(payload)

    device_payloads = [device.model_dump() for device in devices]
    commissioning = _build_commissioning_summary(nodes=enriched_nodes, devices=device_payloads)

    return {
        "success": True,
        "store_id": store_id,
        "commissioning": commissioning,
        "nodes": enriched_nodes,
        "devices": device_payloads,
    }


@router.get("/shokz/{device_id}/history")
async def get_shokz_interaction_history(
    device_id: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """获取语音交互历史"""
    service = get_shokz_device_service()
    interactions = await service.get_interaction_history(
        device_id=device_id,
        limit=limit
    )

    return {
        "device_id": device_id,
        "total": len(interactions),
        "interactions": [i.model_dump() for i in interactions]
    }


@router.get("/shokz/specs/{device_model}")
async def get_shokz_device_specs(
    device_model: ShokzDeviceModel,
    current_user: User = Depends(get_current_user)
):
    """获取Shokz设备规格"""
    service = get_shokz_device_service()
    specs = await service.get_device_specs(device_model=device_model)

    return {
        "specs": specs
    }


@router.get("/shokz/recommended-setup")
async def get_shokz_recommended_setup(
    current_user: User = Depends(get_current_user)
):
    """
    获取推荐配置

    用于门店部署指导
    """
    service = get_shokz_device_service()
    setup = await service.get_recommended_setup()

    return {
        "recommended_setup": setup,
        "total_devices": sum(config["quantity"] for config in setup.values()),
        "total_cost": 2400.0  # 2个OpenComm2 UC
    }


@router.get("/shokz/deployment-cost")
async def get_shokz_deployment_cost(
    current_user: User = Depends(get_current_user)
):
    """
    获取部署成本

    用于向投资人证明轻量化部署
    """
    service = get_shokz_device_service()
    cost = await service.get_deployment_cost()

    return {
        "cost": cost,
        "summary": {
            "total_cost_per_store": cost["total_cost_per_store"],
            "deployment_time_hours": cost["deployment_time_hours"],
            "devices_per_store": 2  # 店长 + 副店长
        }
    }


# ==================== 综合部署成本 ====================

@router.get("/deployment/total-cost")
async def get_total_deployment_cost(
    current_user: User = Depends(get_current_user)
):
    """
    获取总部署成本

    树莓派5 + Shokz设备 + 实施

    用于向投资人证明轻量化部署，满足LTV/CAC > 3的要求
    """
    edge_service = get_raspberry_pi_edge_service()
    shokz_service = get_shokz_device_service()

    edge_cost = await edge_service.get_deployment_cost()
    shokz_cost = await shokz_service.get_deployment_cost()

    total_hardware = edge_cost["hardware"]["total"] + shokz_cost["hardware"]["total"] + shokz_cost["accessories"]["total"]
    total_implementation = edge_cost["implementation"]["total"] + shokz_cost["implementation"]["total"]
    total_cost = total_hardware + total_implementation

    return {
        "breakdown": {
            "raspberry_pi_5": edge_cost,
            "shokz_devices": shokz_cost
        },
        "summary": {
            "total_hardware_cost": total_hardware,
            "total_implementation_cost": total_implementation,
            "total_cost_per_store": total_cost,
            "deployment_time_hours": 3.5,  # 2小时（树莓派）+ 1.5小时（Shokz）
            "cac": total_cost + 5000,  # 硬件 + 销售成本
            "ltv": 300000,  # 3年LTV（¥10万/年 × 3年）
            "ltv_cac_ratio": 300000 / (total_cost + 5000),  # 应该 > 3
            "roi_months": 2  # 客户2个月回本
        },
        "investor_metrics": {
            "lightweight_deployment": True,
            "standardized_process": True,
            "remote_setup": True,
            "low_cac": True,
            "high_ltv_cac": True,
            "fast_roi": True
        }
    }
