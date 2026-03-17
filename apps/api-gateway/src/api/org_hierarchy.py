"""
OrgHierarchy API
GET  /api/v1/org/nodes/{node_id}          — 获取节点详情
GET  /api/v1/org/nodes/{node_id}/subtree  — 获取子树
GET  /api/v1/org/nodes/{node_id}/config   — 获取节点生效配置（含继承）
POST /api/v1/org/nodes                    — 创建节点
POST /api/v1/org/nodes/{node_id}/config   — 设置节点配置
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.org_hierarchy_service import OrgHierarchyService

router = APIRouter(prefix="/api/v1/org", tags=["org-hierarchy"])


class CreateNodeRequest(BaseModel):
    id: str
    name: str
    node_type: str
    parent_id: Optional[str] = None
    store_type: Optional[str] = None
    operation_mode: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0


class SetConfigRequest(BaseModel):
    key: str
    value: str
    value_type: str = "str"
    is_override: bool = False
    description: Optional[str] = None


@router.get("/nodes/{node_id}")
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgHierarchyService(db)
    node = await svc.get_node(node_id)
    if not node:
        raise HTTPException(404, f"节点不存在: {node_id}")
    return {
        "id": node.id, "name": node.name, "node_type": node.node_type,
        "parent_id": node.parent_id, "path": node.path, "depth": node.depth,
        "store_type": node.store_type, "operation_mode": node.operation_mode,
    }


@router.get("/nodes/{node_id}/subtree")
async def get_subtree(node_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgHierarchyService(db)
    nodes = await svc.get_subtree(node_id)
    return [{"id": n.id, "name": n.name, "node_type": n.node_type,
              "parent_id": n.parent_id, "depth": n.depth} for n in nodes]


@router.get("/nodes/{node_id}/config")
async def get_effective_config(node_id: str, db: AsyncSession = Depends(get_db)):
    """返回该节点继承链解析后的所有生效配置"""
    svc = OrgHierarchyService(db)
    resolver = await svc.get_resolver(node_id)
    return resolver.resolve_all(node_id)


@router.post("/nodes", status_code=201)
async def create_node(req: CreateNodeRequest, db: AsyncSession = Depends(get_db)):
    svc = OrgHierarchyService(db)
    node = await svc.create_node(
        id_=req.id, name=req.name, node_type=req.node_type,
        parent_id=req.parent_id, store_type=req.store_type,
        operation_mode=req.operation_mode, description=req.description,
        sort_order=req.sort_order,
    )
    await db.commit()
    return {"id": node.id, "path": node.path, "depth": node.depth}


@router.post("/nodes/{node_id}/config", status_code=200)
async def set_config(
    node_id: str, req: SetConfigRequest, db: AsyncSession = Depends(get_db)
):
    svc = OrgHierarchyService(db)
    node = await svc.get_node(node_id)
    if not node:
        raise HTTPException(404, f"节点不存在: {node_id}")
    cfg = await svc.set_config(
        node_id=node_id, key=req.key, value=req.value,
        value_type=req.value_type, is_override=req.is_override,
    )
    await db.commit()
    return {"node_id": node_id, "key": cfg.config_key,
            "effective_value": cfg.typed_value()}
