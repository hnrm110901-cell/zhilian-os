"""
Blindbox API (compatibility shim)
历史上 main.py 已挂载 blindbox 路由；该模块用于保持导入兼容，避免应用启动失败。
"""

from fastapi import APIRouter

router = APIRouter(prefix="/blindbox", tags=["blindbox"])


@router.get("/health")
async def blindbox_health() -> dict:
    """基础健康检查，供路由加载与联调验证。"""
    return {"ok": True, "service": "blindbox", "status": "available"}
