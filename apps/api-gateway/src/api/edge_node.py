"""
Edge Node API Endpoints
边缘节点API端点

Phase 3: 稳定性加固期 (Stability Reinforcement Period)
Provides REST API for edge computing and offline mode management
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from src.services.edge_node_service import EdgeNodeService, OperationMode
from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/api/v1/edge", tags=["edge_node"])


# Request/Response Models
class ModeEnum(str, Enum):
    """Operation mode enum"""
    ONLINE = "online"
    OFFLINE = "offline"
    HYBRID = "hybrid"


class SetModeRequest(BaseModel):
    """Set operation mode request"""
    mode: ModeEnum
    store_id: str


class NetworkStatusRequest(BaseModel):
    """Update network status request"""
    store_id: str
    is_connected: bool
    latency_ms: Optional[int] = None


class OfflineOperationRequest(BaseModel):
    """Execute offline operation request"""
    store_id: str
    operation_type: str
    data: Dict[str, Any]


class SyncRequest(BaseModel):
    """Sync offline data request"""
    store_id: str


# API Endpoints
@router.post("/mode/set")
async def set_operation_mode(
    request: SetModeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Set edge node operation mode
    设置边缘节点运行模式

    Modes:
    - online: All operations go through cloud
    - offline: All operations use local rules engine
    - hybrid: Automatic switching based on network status
    """
    try:
        edge_service = EdgeNodeService()
        edge_service.set_mode(request.store_id, OperationMode(request.mode.value))

        return {
            "success": True,
            "message": f"Operation mode set to {request.mode.value}",
            "store_id": request.store_id,
            "mode": request.mode.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/network/status")
async def update_network_status(
    request: NetworkStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Update network status for edge node
    更新边缘节点网络状态

    Used in hybrid mode to trigger automatic mode switching
    """
    try:
        edge_service = EdgeNodeService()
        edge_service.update_network_status(
            request.store_id,
            request.is_connected,
            request.latency_ms
        )

        return {
            "success": True,
            "message": "Network status updated",
            "store_id": request.store_id,
            "is_connected": request.is_connected,
            "latency_ms": request.latency_ms
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mode/{store_id}")
async def get_operation_mode(
    store_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current operation mode for edge node
    获取边缘节点当前运行模式
    """
    try:
        edge_service = EdgeNodeService()
        mode = edge_service.get_current_mode(store_id)

        return {
            "success": True,
            "store_id": store_id,
            "mode": mode.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/offline/execute")
async def execute_offline_operation(
    request: OfflineOperationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Execute operation using offline rules engine
    使用离线规则引擎执行操作

    Supported operations:
    - inventory_alert: Check inventory levels
    - revenue_anomaly: Detect revenue anomalies
    - order_timeout: Handle order timeouts
    - schedule: Generate schedules
    """
    try:
        edge_service = EdgeNodeService()
        result = edge_service.execute_offline(
            request.store_id,
            request.operation_type,
            request.data
        )

        return {
            "success": True,
            "store_id": request.store_id,
            "operation_type": request.operation_type,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_offline_data(
    request: SyncRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sync offline operations to cloud
    同步离线操作到云端

    Called when network is restored to upload cached operations
    """
    try:
        edge_service = EdgeNodeService()
        synced_count = edge_service.sync_to_cloud(request.store_id)

        return {
            "success": True,
            "store_id": request.store_id,
            "synced_operations": synced_count,
            "message": f"Successfully synced {synced_count} operations"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/{store_id}")
async def get_cache_status(
    store_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get cache status for edge node
    获取边缘节点缓存状态
    """
    try:
        edge_service = EdgeNodeService()
        cache_data = edge_service.local_cache.get(store_id, {})
        sync_queue = edge_service.sync_queue.get(store_id, [])

        return {
            "success": True,
            "store_id": store_id,
            "cache_size": len(cache_data),
            "pending_sync": len(sync_queue),
            "cache_keys": list(cache_data.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
