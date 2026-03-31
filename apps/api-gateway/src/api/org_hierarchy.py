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
from src.services.org_aggregator import OrgAggregator

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
    try:
        node = await svc.create_node(
            id_=req.id, name=req.name, node_type=req.node_type,
            parent_id=req.parent_id, store_type=req.store_type,
            operation_mode=req.operation_mode, description=req.description,
            sort_order=req.sort_order,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"id": node.id, "path": node.path, "depth": node.depth}


@router.post("/nodes/{node_id}/config", status_code=201)
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


@router.get("/nodes/{node_id}/snapshot/{period}")
async def get_org_snapshot(
    node_id: str,
    period: str,                    # 格式: "2026-03" 或 "2026-03-17"
    db: AsyncSession = Depends(get_db),
):
    """
    获取节点聚合快照（含子节点）
    区域经理调用：返回区域内所有门店汇总
    集团CFO调用：返回集团所有品牌汇总
    """
    aggregator = OrgAggregator(db)
    try:
        snapshot = await aggregator.get_snapshot(node_id, period=period)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return snapshot.to_dict()


# ── 批量配置管理接口（运维交付团队） ─────────────────────────────────────────


class BulkConfigRequest(BaseModel):
    configs: list[SetConfigRequest]  # 复用已有的 SetConfigRequest


@router.post("/nodes/{node_id}/config/bulk", status_code=200)
async def bulk_set_config(
    node_id: str, req: BulkConfigRequest, db: AsyncSession = Depends(get_db)
):
    """批量设置多个配置项，原子操作（全成功或全失败）"""
    svc = OrgHierarchyService(db)
    node = await svc.get_node(node_id)
    if not node:
        raise HTTPException(404, f"节点不存在: {node_id}")
    results = []
    for item in req.configs:
        cfg = await svc.set_config(
            node_id=node_id, key=item.key, value=item.value,
            value_type=item.value_type, is_override=item.is_override,
        )
        results.append({"key": cfg.config_key, "effective_value": cfg.typed_value()})
    await db.commit()
    return {"updated": len(results), "configs": results}


@router.post("/nodes/{node_id}/config/copy-from/{source_id}", status_code=200)
async def copy_config_from(
    node_id: str, source_id: str,
    overwrite: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """从 source_id 节点复制所有配置到 node_id（不含继承，只复制直接设置的配置）"""
    svc = OrgHierarchyService(db)
    target = await svc.get_node(node_id)
    source = await svc.get_node(source_id)
    if not target:
        raise HTTPException(404, f"目标节点不存在: {node_id}")
    if not source:
        raise HTTPException(404, f"源节点不存在: {source_id}")

    from src.models.org_config import OrgConfig
    from sqlalchemy import select
    result = await db.execute(
        select(OrgConfig).where(OrgConfig.org_node_id == source_id)
    )
    source_configs = result.scalars().all()

    copied = 0
    for src_cfg in source_configs:
        # 如果 overwrite=False，跳过目标节点已存在的 key
        if not overwrite:
            existing = await db.execute(
                select(OrgConfig).where(
                    OrgConfig.org_node_id == node_id,
                    OrgConfig.config_key == src_cfg.config_key
                )
            )
            if existing.scalar_one_or_none():
                continue
        await svc.set_config(
            node_id=node_id, key=src_cfg.config_key,
            value=src_cfg.config_value, value_type=src_cfg.value_type,
            is_override=True,
        )
        copied += 1
    await db.commit()
    return {"copied": copied, "source": source_id, "target": node_id}


@router.delete("/nodes/{node_id}/config/{key}", status_code=200)
async def delete_config(
    node_id: str, key: str, db: AsyncSession = Depends(get_db)
):
    """删除节点的直接配置项，使其回退到父节点继承值"""
    from src.models.org_config import OrgConfig
    from sqlalchemy import select, delete

    result = await db.execute(
        select(OrgConfig).where(
            OrgConfig.org_node_id == node_id,
            OrgConfig.config_key == key
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, f"配置项不存在: {key}")

    await db.execute(
        delete(OrgConfig).where(
            OrgConfig.org_node_id == node_id,
            OrgConfig.config_key == key
        )
    )
    await db.commit()

    # 返回删除后的继承值
    svc = OrgHierarchyService(db)
    inherited_value = await svc.resolve(node_id, key, default=None)
    return {"deleted_key": key, "now_inherits": inherited_value}


@router.get("/nodes/{node_id}/config/diff")
async def get_config_diff(node_id: str, db: AsyncSession = Depends(get_db)):
    """返回本节点与父节点继承值的差异（仅展示本节点有直接配置的项）"""
    from src.models.org_config import OrgConfig
    from sqlalchemy import select

    svc = OrgHierarchyService(db)
    node = await svc.get_node(node_id)
    if not node:
        raise HTTPException(404, f"节点不存在: {node_id}")

    # 本节点直接设置的配置
    result = await db.execute(
        select(OrgConfig).where(OrgConfig.org_node_id == node_id)
    )
    direct_configs = result.scalars().all()

    diffs = []
    for cfg in direct_configs:
        # 查父节点继承值（resolver 从父节点往上查）
        parent_id = node.parent_id
        parent_value = None
        if parent_id:
            parent_value = await svc.resolve(parent_id, cfg.config_key, default=None)

        diffs.append({
            "key": cfg.config_key,
            "this_node_value": cfg.typed_value(),
            "parent_inherits": parent_value,
            "is_override": cfg.is_override,
            "value_type": cfg.value_type,
            "description": cfg.description,
        })

    return {
        "node_id": node_id,
        "node_name": node.name,
        "direct_config_count": len(diffs),
        "diffs": diffs,
    }


@router.post("/nodes/{node_id}/config/reset", status_code=200)
async def reset_all_configs(
    node_id: str,
    confirm: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """删除节点所有直接配置，使其完全从父节点继承（危险操作，需 confirm=true）"""
    if not confirm:
        raise HTTPException(400, "危险操作：需要传入 confirm=true 参数确认")

    from src.models.org_config import OrgConfig
    from sqlalchemy import delete, select, func

    # 先统计数量
    count_result = await db.execute(
        select(func.count()).where(OrgConfig.org_node_id == node_id)
    )
    count = count_result.scalar()

    await db.execute(
        delete(OrgConfig).where(OrgConfig.org_node_id == node_id)
    )
    await db.commit()
    return {"reset": count, "node_id": node_id, "message": "所有直接配置已清除，现在完全继承父节点"}


@router.get("/config/keys")
async def list_config_keys():
    """列出系统支持的所有配置 key 及其默认值说明"""
    from src.models.org_config import ConfigKey
    keys = {k: v for k, v in vars(ConfigKey).items()
            if not k.startswith("_") and isinstance(v, str)}
    return {"config_keys": keys, "total": len(keys)}
