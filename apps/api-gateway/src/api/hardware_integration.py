"""
硬件集成API - 树莓派5 + Shokz设备
边缘计算与语音交互接口
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel

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

router = APIRouter(prefix="/api/v1/hardware")


# ==================== 树莓派5边缘节点 ====================

@router.post("/edge-node/register")
async def register_edge_node(
    store_id: str,
    device_name: str,
    ip_address: str,
    mac_address: str,
    current_user: User = Depends(get_current_user)
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

    return {
        "success": True,
        "node": node.model_dump(),
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
    current_user: User = Depends(get_current_user)
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
        uptime_seconds=uptime_seconds
    )

    return {
        "success": True,
        "node": node.model_dump()
    }


@router.post("/edge-node/{node_id}/network-mode")
async def switch_network_mode(
    node_id: str,
    mode: NetworkMode,
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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


@router.get("/edge-node/{node_id}")
async def get_edge_node_info(
    node_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取边缘节点信息"""
    service = get_raspberry_pi_edge_service()
    node = await service.get_node_info(node_id=node_id)

    return {
        "node": node.model_dump()
    }


@router.get("/edge-node/store/{store_id}")
async def list_store_edge_nodes(
    store_id: str,
    current_user: User = Depends(get_current_user)
):
    """列出门店的所有边缘节点"""
    service = get_raspberry_pi_edge_service()
    nodes = await service.list_store_nodes(store_id=store_id)

    return {
        "store_id": store_id,
        "total": len(nodes),
        "nodes": [node.model_dump() for node in nodes]
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
