"""
Federated API (compatibility shim)
用于兼容 main.py 中既有路由挂载，避免缺失模块导致测试与启动失败。
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/federated", tags=["federated"])


@router.get("/health")
async def federated_health() -> dict:
    """联邦模块占位健康检查。"""
    return {"ok": True, "service": "federated", "status": "available"}
