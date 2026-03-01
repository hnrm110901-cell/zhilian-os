"""
本体层 API（Palantir L2）：图谱初始化、BOM 本体化、同步入口、感知层导入
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from src.core.dependencies import get_current_active_user
from src.core.database import get_db_session
from src.models import User
from src.ontology import get_ontology_repository
from src.services.ontology_sync_service import sync_bom_version_to_pg

router = APIRouter(prefix="/ontology", tags=["Ontology (L2)"])


class InitSchemaRequest(BaseModel):
    tenant_id: str = Field(..., description="租户ID")


class BOMUpsertRequest(BaseModel):
    tenant_id: str
    store_id: str
    dish_id: str
    version: int = 1
    effective_date: str  # YYYY-MM-DD
    expiry_date: Optional[str] = None
    yield_portions: float = 1.0
    requires: List[dict] = Field(default_factory=list)  # [{"ing_id": "", "qty": 0, "unit": "", "waste_factor": 1.0}]


class SyncFromPGRequest(BaseModel):
    tenant_id: str
    store_id: Optional[str] = None  # 不传则同步全部门店


class WasteReasoningRequest(BaseModel):
    tenant_id: str
    store_id: str
    date_start: str  # YYYY-MM-DD
    date_end: Optional[str] = None


class ActionCreateRequest(BaseModel):
    tenant_id: str
    store_id: str
    action_type: str
    assignee_staff_id: str
    assignee_wechat_id: Optional[str] = None
    priority: str = "P1"
    title: Optional[str] = None
    body: Optional[str] = None
    traced_reasoning_id: Optional[str] = None


class ActionStatusUpdate(BaseModel):
    status: str  # sent, acked, in_progress, done, closed


class OntologyNLQueryRequest(BaseModel):
    question: str
    tenant_id: str = ""
    store_id: Optional[str] = None


def _get_repo():
    repo = get_ontology_repository()
    if not repo:
        raise HTTPException(503, "Neo4j ontology layer is not enabled or unavailable")
    return repo


@router.post("/init-schema")
async def init_schema(
    body: InitSchemaRequest,
    _: User = Depends(get_current_active_user),
):
    """创建本体图谱约束与索引（幂等）。"""
    repo = _get_repo()
    repo.init_schema(body.tenant_id)
    return {"ok": True, "message": "ontology schema initialized"}


@router.post("/bom/upsert")
async def bom_upsert(
    body: BOMUpsertRequest,
    _: User = Depends(get_current_active_user),
):
    """写入或更新 BOM 节点及 REQUIRES 关系（BOM 本体化）。"""
    repo = _get_repo()
    bom_id = repo.upsert_bom(
        tenant_id=body.tenant_id,
        store_id=body.store_id,
        dish_id=body.dish_id,
        version=body.version,
        effective_date=body.effective_date,
        expiry_date=body.expiry_date,
        yield_portions=body.yield_portions,
    )
    for r in body.requires:
        repo.upsert_bom_requires(
            bom_id=bom_id,
            ing_id=str(r.get("ing_id", "")),
            qty=float(r.get("qty", 0)),
            unit=str(r.get("unit", "")),
            waste_factor=float(r.get("waste_factor", 1.0)),
        )
    # BOM 双向同步：回写 PG Dish.bom_version / effective_date
    async with get_db_session() as session:
        await sync_bom_version_to_pg(
            session, body.dish_id, body.version, body.effective_date
        )
    return {"ok": True, "bom_id": bom_id}


@router.get("/bom/dish/{dish_id}")
async def get_dish_bom(
    dish_id: str,
    as_of: Optional[str] = None,
    _: User = Depends(get_current_active_user),
):
    """查询某菜品的 BOM 及所需食材。不传 as_of 为最新版本；传 as_of=YYYY-MM-DD 为时间旅行查询当时生效版本。"""
    repo = _get_repo()
    if as_of:
        try:
            __import__("datetime").date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="as_of 需为 YYYY-MM-DD")
        items = repo.get_dish_bom_ingredients_as_of(dish_id, as_of)
        return {"dish_id": dish_id, "as_of": as_of, "items": items}
    items = repo.get_dish_bom_ingredients(dish_id)
    return {"dish_id": dish_id, "items": items}


# ---------- 感知层半自动导入（L1）----------

@router.get("/perception/template/inventory_snapshot", response_class=PlainTextResponse)
async def get_perception_template_inventory_snapshot(
    _: User = Depends(get_current_active_user),
):
    """下载库存快照标准化 CSV 模板（列：store_id, ing_id, qty, unit, ts, source）。"""
    from src.services.perception_import_service import get_inventory_snapshot_template_csv
    return PlainTextResponse(
        get_inventory_snapshot_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ontology_inventory_snapshot_template.csv"},
    )


@router.post("/perception/import")
async def perception_import(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    default_store_id: str = Form(...),
    _: User = Depends(get_current_active_user),
):
    """
    感知层半自动导入：上传 Excel/CSV，按标准化列映射写入本体（当前支持库存快照）。
    列名支持：store_id/门店ID, ing_id/食材ID/物料ID, qty/数量, unit/单位, ts/时间, source/来源。
    """
    from src.services.perception_import_service import import_inventory_snapshots
    raw = await file.read()
    try:
        ok, fail, errors = import_inventory_snapshots(
            raw, file.filename or "upload", tenant_id, default_store_id
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))
    return {"ok": True, "success": ok, "failed": fail, "errors": errors[:50]}


# ---------- P2：IoT 网关 / 边缘节点 → 标准化写入本体 ----------

class EdgeInventorySnapshotItem(BaseModel):
    ing_id: str
    qty: float
    ts: str
    source: str = "edge"
    unit: str = ""


class EdgeEquipmentItem(BaseModel):
    equip_id: str
    equip_type: str = ""
    status: str = ""
    location: str = ""


class EdgePushRequest(BaseModel):
    """边缘节点（如树莓派 5）标准化上报：写入图谱 InventorySnapshot / Equipment。"""
    store_id: str
    tenant_id: Optional[str] = None
    inventory_snapshots: List[EdgeInventorySnapshotItem] = Field(default_factory=list)
    equipment: List[EdgeEquipmentItem] = Field(default_factory=list)


@router.post("/perception/edge-push")
async def perception_edge_push(
    body: EdgePushRequest,
    _: User = Depends(get_current_active_user),
):
    """
    L1 感知层：IoT/边缘节点标准化数据写入图谱。
    树莓派等设备按统一格式上报库存快照、设备状态，写入 InventorySnapshot、Equipment 节点。
    """
    repo = _get_repo()
    tenant = body.tenant_id or body.store_id
    snap_ok, equip_ok = 0, 0
    for s in body.inventory_snapshots:
        try:
            repo.merge_inventory_snapshot(
                tenant_id=tenant,
                store_id=body.store_id,
                ing_id=s.ing_id,
                qty=s.qty,
                ts=s.ts,
                source=s.source,
                unit=s.unit,
            )
            snap_ok += 1
        except Exception:
            pass
    for e in body.equipment:
        try:
            repo.merge_equipment(
                equip_id=e.equip_id,
                store_id=body.store_id,
                equip_type=e.equip_type,
                status=e.status,
                location=e.location,
                tenant_id=tenant,
            )
            equip_ok += 1
        except Exception:
            pass
    return {
        "ok": True,
        "inventory_snapshots_written": snap_ok,
        "equipment_written": equip_ok,
    }


# ---------- L4 Action 状态机 ----------

@router.post("/actions")
async def action_create(
    body: ActionCreateRequest,
    _: User = Depends(get_current_active_user),
):
    """创建 L4 Action 任务（可关联推理报告）。"""
    from src.core.database import get_db_session
    from src.services.ontology_action_service import create_action
    async with get_db_session() as session:
        action = await create_action(
            session,
            tenant_id=body.tenant_id,
            store_id=body.store_id,
            action_type=body.action_type,
            assignee_staff_id=body.assignee_staff_id,
            assignee_wechat_id=body.assignee_wechat_id,
            priority=body.priority,
            title=body.title,
            body=body.body,
            traced_reasoning_id=body.traced_reasoning_id,
        )
        await session.commit()
        aid = str(action.id)
    return {"ok": True, "action_id": aid, "status": action.status, "deadline_at": action.deadline_at.isoformat() if action.deadline_at else None}


@router.get("/actions")
async def action_list(
    tenant_id: str,
    store_id: Optional[str] = None,
    status: Optional[str] = None,
    assignee_staff_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: User = Depends(get_current_active_user),
):
    """L4 Action 列表。"""
    from src.core.database import get_db_session
    from src.services.ontology_action_service import list_actions
    async with get_db_session() as session:
        actions = await list_actions(session, tenant_id, store_id, status, assignee_staff_id, limit, offset)
    return {
        "items": [
            {
                "id": str(a.id),
                "tenant_id": a.tenant_id,
                "store_id": a.store_id,
                "action_type": a.action_type,
                "assignee_staff_id": a.assignee_staff_id,
                "status": a.status,
                "priority": a.priority,
                "deadline_at": a.deadline_at.isoformat() if a.deadline_at else None,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                "acked_at": a.acked_at.isoformat() if a.acked_at else None,
                "title": a.title,
            }
            for a in actions
        ],
    }


@router.patch("/actions/{action_id}/status")
async def action_update_status(
    action_id: str,
    body: ActionStatusUpdate,
    _: User = Depends(get_current_active_user),
):
    """更新 Action 状态（如回执 acked、完成 done）。"""
    from src.core.database import get_db_session
    from src.services.ontology_action_service import update_status
    async with get_db_session() as session:
        action = await update_status(session, action_id, body.status)
        await session.commit()
    if not action:
        raise HTTPException(404, "Action not found")
    return {"ok": True, "action_id": action_id, "status": action.status}


@router.post("/actions/{action_id}/send")
async def action_send_to_wechat(
    action_id: str,
    _: User = Depends(get_current_active_user),
):
    """将 L4 Action 推送到企微并标记为 SENT（需配置企微应用）。"""
    from src.core.database import get_db_session
    from src.services.ontology_action_service import push_action_to_wechat
    async with get_db_session() as session:
        action = await push_action_to_wechat(session, action_id)
        await session.commit()
    if not action:
        raise HTTPException(404, "Action not found or already sent / 企微未配置")
    return {"ok": True, "action_id": action_id, "status": action.status}


@router.post("/query")
async def ontology_nl_query(
    body: OntologyNLQueryRequest,
    _: User = Depends(get_current_active_user),
):
    """自然语言查询图谱：意图识别 → 图谱/推理 → 结构化答案 + 溯源。"""
    from src.services.ontology_nl_query_service import query_ontology_natural_language
    result = await query_ontology_natural_language(
        question=body.question,
        tenant_id=body.tenant_id,
        store_id_hint=body.store_id,
    )
    return result


@router.post("/reasoning/waste")
async def reasoning_waste(
    body: WasteReasoningRequest,
    _: User = Depends(get_current_active_user),
):
    """损耗五步推理：库存差异→BOM偏差→时间窗口员工→供应商批次→根因评分 TOP3。"""
    from src.core.database import get_db_session
    from src.services.waste_reasoning_service import run_waste_reasoning
    async with get_db_session() as session:
        report = await run_waste_reasoning(
            session,
            tenant_id=body.tenant_id,
            store_id=body.store_id,
            date_start=body.date_start,
            date_end=body.date_end,
        )
    return report


@router.post("/sync-from-pg")
async def sync_from_pg(
    body: SyncFromPGRequest,
    _: User = Depends(get_current_active_user),
):
    """从 PostgreSQL 主数据同步 Store、Dish、Ingredient、Staff、Order 到图谱（L2）。"""
    from src.core.database import get_db_session
    from src.services.ontology_sync_service import sync_ontology_from_pg
    async with get_db_session() as session:
        result = await sync_ontology_from_pg(
            session, tenant_id=body.tenant_id, store_id=body.store_id
        )
    return {"ok": True, "synced": result}


@router.get("/replenish")
async def get_replenish(
    store_id: str,
    target_date: str,
    waste_buffer: Optional[float] = Query(None, description="损耗缓冲系数，默认 1.05"),
    servings_per_order: Optional[float] = Query(None, description="每单约份数，默认 2.5"),
    _: User = Depends(get_current_active_user),
):
    """
    时序预测备货建议（P1）：基于近 90 天订单预测 + 图谱 BOM + 损耗缓冲，输出目标日食材级备货建议。
    target_date 格式 YYYY-MM-DD。
    """
    from datetime import date
    from src.core.database import get_db_session
    from src.services.ontology_replenish_service import get_replenish_suggestion

    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="target_date 需为 YYYY-MM-DD")
    async with get_db_session() as session:
        result = await get_replenish_suggestion(
            session,
            store_id=store_id,
            target_date=d,
            waste_buffer=waste_buffer,
            servings_per_order=servings_per_order,
        )
    return result


# ---------- P2：Equipment 节点 ----------

class EquipmentUpsertRequest(BaseModel):
    equip_id: str
    store_id: str
    equip_type: str = ""
    status: str = ""
    location: str = ""
    tenant_id: Optional[str] = None


@router.post("/equipment")
async def upsert_equipment(
    body: EquipmentUpsertRequest,
    _: User = Depends(get_current_active_user),
):
    """写入或更新设备节点（L2 Equipment），并建立 BELONGS_TO Store。边缘节点/硬件可调用。"""
    repo = _get_repo()
    node = repo.merge_equipment(
        equip_id=body.equip_id,
        store_id=body.store_id,
        equip_type=body.equip_type,
        status=body.status,
        location=body.location,
        tenant_id=body.tenant_id,
    )
    return {"ok": True, "equip_id": body.equip_id, "node": node}


# ---------- P2：本体模板复制 ----------

class CloneTemplateRequest(BaseModel):
    source_store_id: str
    target_store_id: str
    tenant_id: Optional[str] = None


@router.post("/clone-template")
async def clone_template(
    body: CloneTemplateRequest,
    _: User = Depends(get_current_active_user),
):
    """将源门店的本体模板（Dish + BOM + REQUIRES）复制到目标门店，用于连锁扩展。"""
    repo = _get_repo()
    tenant = body.tenant_id or body.target_store_id
    counts = repo.clone_template_to_store(
        source_store_id=body.source_store_id,
        target_store_id=body.target_store_id,
        tenant_id=tenant,
    )
    return {"ok": True, "cloned": counts}


# ---------- P2：知识库雏形（损耗规则/BOM基准/异常模式）----------

class KnowledgeAddRequest(BaseModel):
    tenant_id: str
    type: str = Field(..., description="waste_rule | bom_baseline | anomaly_pattern")
    name: str
    content: Dict[str, Any] = Field(default_factory=dict)
    store_id: Optional[str] = None


@router.post("/knowledge")
async def knowledge_add(
    body: KnowledgeAddRequest,
    _: User = Depends(get_current_active_user),
):
    """新增知识库条目（损耗规则库、BOM 基准库、异常模式库）。"""
    from src.services.ontology_knowledge_service import add_knowledge, KNOWLEDGE_TYPES
    if body.type not in KNOWLEDGE_TYPES:
        raise HTTPException(status_code=400, detail=f"type 须为 {list(KNOWLEDGE_TYPES)} 之一")
    record = add_knowledge(
        tenant_id=body.tenant_id,
        knowledge_type=body.type,
        name=body.name,
        content=body.content,
        store_id=body.store_id,
    )
    return {"ok": True, "id": record["id"], "record": record}


@router.get("/knowledge")
async def knowledge_list(
    tenant_id: str,
    type: Optional[str] = None,
    store_id: Optional[str] = None,
    limit: int = 100,
    _: User = Depends(get_current_active_user),
):
    """列表查询知识库。"""
    from src.services.ontology_knowledge_service import list_knowledge
    items = list_knowledge(tenant_id=tenant_id, knowledge_type=type, store_id=store_id, limit=limit)
    return {"items": items}


@router.get("/knowledge/{knowledge_id}")
async def knowledge_get(
    knowledge_id: str,
    _: User = Depends(get_current_active_user),
):
    """按 id 查询知识库条目。"""
    from src.services.ontology_knowledge_service import get_knowledge
    record = get_knowledge(knowledge_id)
    if not record:
        raise HTTPException(status_code=404, detail="未找到")
    return record


class KnowledgeUpdateRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    store_id: Optional[str] = None


@router.patch("/knowledge/{knowledge_id}")
async def knowledge_update(
    knowledge_id: str,
    body: KnowledgeUpdateRequest,
    _: User = Depends(get_current_active_user),
):
    """更新知识库条目（仅更新传入的字段）。"""
    from src.services.ontology_knowledge_service import update_knowledge
    record = update_knowledge(
        knowledge_id,
        name=body.name,
        content=body.content,
        store_id=body.store_id,
    )
    if not record:
        raise HTTPException(status_code=404, detail="未找到")
    return {"ok": True, "record": record}


@router.delete("/knowledge/{knowledge_id}")
async def knowledge_delete(
    knowledge_id: str,
    _: User = Depends(get_current_active_user),
):
    """删除知识库条目。"""
    from src.services.ontology_knowledge_service import delete_knowledge
    if not delete_knowledge(knowledge_id):
        raise HTTPException(status_code=404, detail="未找到")
    return {"ok": True, "id": knowledge_id}


class KnowledgeDistributeRequest(BaseModel):
    tenant_id: str
    target_store_ids: List[str] = Field(default_factory=list, description="目标门店 ID 列表；空表示下发到连锁级（一条 store_id 为空的记录）")


@router.post("/knowledge/{knowledge_id}/distribute")
async def knowledge_distribute(
    knowledge_id: str,
    body: KnowledgeDistributeRequest,
    _: User = Depends(get_current_active_user),
):
    """连锁下发：将知识库条目复制到指定门店或连锁级。"""
    from src.services.ontology_knowledge_service import distribute_knowledge
    result = distribute_knowledge(
        knowledge_id=knowledge_id,
        tenant_id=body.tenant_id,
        target_store_ids=body.target_store_ids,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "下发失败"))
    return result


# ---------- Phase 3：导出与跨店 ----------

# ---------- 徐记 POC 扩展 ----------

class LiveSeafoodUpsertRequest(BaseModel):
    live_seafood_id: str
    store_id: str
    species: str = ""
    weight_kg: float = 0
    price_cents: int = 0
    pool_time: str = ""
    mortality_rate: float = 0
    tenant_id: Optional[str] = None


class SeafoodPoolUpsertRequest(BaseModel):
    pool_id: str
    store_id: str
    capacity: str = ""
    temperature: float = 0
    salinity: float = 0
    equipment_status: str = ""
    tenant_id: Optional[str] = None


@router.post("/xuji/live-seafood")
async def xuji_upsert_live_seafood(
    body: LiveSeafoodUpsertRequest,
    _: User = Depends(get_current_active_user),
):
    """徐记 POC：写入活海鲜节点（死亡损耗 vs 正常损耗异常识别）。"""
    repo = _get_repo()
    repo.merge_live_seafood(
        live_seafood_id=body.live_seafood_id,
        store_id=body.store_id,
        species=body.species,
        weight_kg=body.weight_kg,
        price_cents=body.price_cents,
        pool_time=body.pool_time,
        mortality_rate=body.mortality_rate,
        tenant_id=body.tenant_id,
    )
    return {"ok": True, "live_seafood_id": body.live_seafood_id}


@router.post("/xuji/seafood-pool")
async def xuji_upsert_seafood_pool(
    body: SeafoodPoolUpsertRequest,
    _: User = Depends(get_current_active_user),
):
    """徐记 POC：写入海鲜池节点（设备异常→死亡率推理链）。"""
    repo = _get_repo()
    repo.merge_seafood_pool(
        pool_id=body.pool_id,
        store_id=body.store_id,
        capacity=body.capacity,
        temperature=body.temperature,
        salinity=body.salinity,
        equipment_status=body.equipment_status,
        tenant_id=body.tenant_id,
    )
    return {"ok": True, "pool_id": body.pool_id}


class PortionWeightUpsertRequest(BaseModel):
    portion_id: str
    store_id: str
    dish_id: str = ""
    actual_g: float = 0
    standard_g: float = 0
    staff_id: str = ""
    ts: str = ""
    tenant_id: Optional[str] = None


class PurchaseInvoiceUpsertRequest(BaseModel):
    invoice_id: str
    store_id: str
    supplier_id: str = ""
    batch: str = ""
    price_cents: int = 0
    receiver_staff_id: str = ""
    ts: str = ""
    tenant_id: Optional[str] = None


@router.post("/xuji/portion-weight")
async def xuji_upsert_portion_weight(
    body: PortionWeightUpsertRequest,
    _: User = Depends(get_current_active_user),
):
    """徐记 POC：份量记录（出成率偏差→厨师责任定位）。"""
    repo = _get_repo()
    repo.merge_portion_weight(
        portion_id=body.portion_id,
        store_id=body.store_id,
        dish_id=body.dish_id,
        actual_g=body.actual_g,
        standard_g=body.standard_g,
        staff_id=body.staff_id,
        ts=body.ts,
        tenant_id=body.tenant_id,
    )
    return {"ok": True, "portion_id": body.portion_id}


@router.post("/xuji/purchase-invoice")
async def xuji_upsert_purchase_invoice(
    body: PurchaseInvoiceUpsertRequest,
    _: User = Depends(get_current_active_user),
):
    """徐记 POC：采购凭证（价格虚高→采购异常检测）。"""
    repo = _get_repo()
    repo.merge_purchase_invoice(
        invoice_id=body.invoice_id,
        store_id=body.store_id,
        supplier_id=body.supplier_id,
        batch=body.batch,
        price_cents=body.price_cents,
        receiver_staff_id=body.receiver_staff_id,
        ts=body.ts,
        tenant_id=body.tenant_id,
    )
    return {"ok": True, "invoice_id": body.invoice_id}


@router.get("/context")
async def ontology_context_for_agent(
    store_id: str,
    tenant_id: str = "",
    types: Optional[str] = None,
    _: User = Depends(get_current_active_user),
):
    """为 Agent 拉取图谱上下文（bom, inventory_snapshot, waste_summary）。types 逗号分隔，不传则全部。"""
    from src.services.ontology_context_service import get_ontology_context_for_agent
    want = [x.strip() for x in (types or "").split(",") if x.strip()] or None
    result = await get_ontology_context_for_agent(store_id=store_id, tenant_id=tenant_id, types=want)
    return result


@router.get("/export")
async def ontology_export(
    tenant_id: str = "",
    store_id: Optional[str] = None,
    _: User = Depends(get_current_active_user),
):
    """导出图谱快照（JSON）：门店、菜品、食材、BOM、库存快照。支持按 store_id 过滤。"""
    from src.services.ontology_export_service import export_graph_snapshot
    return export_graph_snapshot(tenant_id=tenant_id, store_id=store_id)


@router.get("/graph-full")
async def ontology_graph_full(
    tenant_id: str = "",
    store_id: Optional[str] = None,
    _: User = Depends(get_current_active_user),
):
    """
    全图模式导出：在快照基础上额外返回 Staff/WasteEvent/TrainingModule 节点
    和 SIMILAR_TO/BELONGS_TO/TRIGGERED_BY/NEEDS_TRAINING/COMPLETED_TRAINING 关系。
    用于 OntologyGraphPage 全图可视化。
    """
    from src.services.ontology_export_service import export_full_graph
    return export_full_graph(tenant_id=tenant_id, store_id=store_id)


@router.get("/waste-events")
async def list_waste_events(
    store_id: Optional[str] = None,
    limit: int = 50,
    _: User = Depends(get_current_active_user),
):
    """
    查询 Neo4j WasteEvent 节点列表，支持按门店过滤。
    返回字段：event_id, store_id, event_type, root_cause, amount。
    """
    repo = get_ontology_repository()
    if not repo:
        return {"waste_events": [], "total": 0, "note": "Neo4j 未启用"}

    where = " WHERE n.store_id = $store_id" if store_id else ""
    params: Dict[str, Any] = {"store_id": store_id} if store_id else {}
    query = (
        "MATCH (n:WasteEvent)"
        + where
        + " RETURN n.event_id AS event_id, n.store_id AS store_id,"
          " n.event_type AS event_type, n.root_cause AS root_cause, n.amount AS amount"
        + " LIMIT $limit"
    )
    params["limit"] = limit
    rows = repo.run_read_only_query(query, params)
    return {"waste_events": rows, "total": len(rows)}


@router.get("/graph-stats")
async def ontology_graph_stats(
    _: User = Depends(get_current_active_user),
):
    """
    图谱节点统计：各类型节点数量快照，用于运维看板。
    """
    repo = get_ontology_repository()
    if not repo:
        return {"error": "Neo4j 未启用", "stats": {}}

    labels = ["Store", "Dish", "BOM", "Ingredient", "InventorySnapshot",
              "Staff", "WasteEvent", "TrainingModule"]
    stats: Dict[str, int] = {}
    for label in labels:
        try:
            rows = repo.run_read_only_query(
                f"MATCH (n:{label}) RETURN count(n) AS cnt"
            )
            stats[label] = rows[0]["cnt"] if rows else 0
        except Exception:
            stats[label] = -1

    # 关系数量
    rel_types = ["HAS_DISH", "HAS_BOM", "REQUIRES", "BELONGS_TO",
                 "SIMILAR_TO", "TRIGGERED_BY", "NEEDS_TRAINING", "COMPLETED_TRAINING"]
    rel_counts: Dict[str, int] = {}
    for rel in rel_types:
        try:
            rows = repo.run_read_only_query(
                f"MATCH ()-[r:{rel}]->() RETURN count(r) AS cnt"
            )
            rel_counts[rel] = rows[0]["cnt"] if rows else 0
        except Exception:
            rel_counts[rel] = -1

    return {
        "nodes": stats,
        "relations": rel_counts,
        "total_nodes": sum(v for v in stats.values() if v >= 0),
        "total_relations": sum(v for v in rel_counts.values() if v >= 0),
    }


# ---------- 数据主权：加密导出与断开权 ----------

class ExportEncryptedRequest(BaseModel):
    tenant_id: str = ""
    store_ids: Optional[List[str]] = None
    customer_key: Optional[str] = None


class DisconnectRequest(BaseModel):
    tenant_id: str
    store_ids: List[str]
    export_first: bool = True
    customer_key: Optional[str] = None


@router.post("/data-sovereignty/export-encrypted")
async def data_sovereignty_export_encrypted(
    body: ExportEncryptedRequest,
    current_user: User = Depends(get_current_active_user),
):
    """导出图谱快照并用客户密钥 AES-256 加密；客户自持密钥则屯象无法解密。需配置 DATA_SOVEREIGNTY_ENABLED。"""
    from src.services.data_sovereignty_service import export_encrypted
    from src.services.audit_log_service import audit_log_service
    from src.models.audit_log import AuditAction, ResourceType

    result = export_encrypted(
        tenant_id=body.tenant_id,
        store_ids=body.store_ids,
        customer_key=body.customer_key,
    )
    from src.core.config import settings
    if settings.DATA_SOVEREIGNTY_ENABLED:
        await audit_log_service.log_action(
            action=AuditAction.DATA_SOVEREIGNTY_EXPORT,
            resource_type=ResourceType.DATA_SOVEREIGNTY,
            user_id=str(current_user.id),
            username=getattr(current_user, "username", None) or getattr(current_user, "email", None),
            resource_id=body.tenant_id,
            description=f"加密导出 tenant={body.tenant_id} store_ids={body.store_ids or []} encrypted={result.get('encrypted', False)}",
            new_value={"tenant_id": body.tenant_id, "store_ids": body.store_ids, "encrypted": result.get("encrypted")},
            status="success" if "error" not in result else "failed",
            error_message=result.get("error"),
        )
    return result


@router.post("/data-sovereignty/disconnect")
async def data_sovereignty_disconnect(
    body: DisconnectRequest,
    current_user: User = Depends(get_current_active_user),
):
    """断开权：先导出（可选加密），再删除图谱中该租户/门店数据。需 DATA_SOVEREIGNTY_ENABLED。调用方负责留存导出文件。"""
    from src.services.data_sovereignty_service import disconnect_tenant
    from src.services.audit_log_service import audit_log_service
    from src.models.audit_log import AuditAction, ResourceType

    result = disconnect_tenant(
        tenant_id=body.tenant_id,
        store_ids=body.store_ids,
        export_first=body.export_first,
        customer_key=body.customer_key,
    )
    from src.core.config import settings
    if settings.DATA_SOVEREIGNTY_ENABLED:
        await audit_log_service.log_action(
            action=AuditAction.DATA_SOVEREIGNTY_DISCONNECT,
            resource_type=ResourceType.DATA_SOVEREIGNTY,
            user_id=str(current_user.id),
            username=getattr(current_user, "username", None) or getattr(current_user, "email", None),
            resource_id=body.tenant_id,
            description=f"断开权 tenant={body.tenant_id} store_ids={body.store_ids} deleted={result.get('deleted_counts', {})}",
            new_value={"tenant_id": body.tenant_id, "store_ids": body.store_ids, "deleted_counts": result.get("deleted_counts")},
            status="success" if result.get("disconnected") else "failed",
            error_message=result.get("error"),
        )
    return result


@router.get("/data-sovereignty/config")
async def data_sovereignty_config(
    _: User = Depends(get_current_active_user),
):
    """数据主权配置状态：是否启用、是否已配置客户密钥（不暴露密钥本身）。"""
    from src.core.config import settings
    enabled = getattr(settings, "DATA_SOVEREIGNTY_ENABLED", False)
    key_configured = bool(getattr(settings, "CUSTOMER_ENCRYPTION_KEY", "") or "")
    return {"enabled": enabled, "key_configured": key_configured}


@router.get("/data-sovereignty/audit-logs")
async def data_sovereignty_audit_logs(
    skip: int = 0,
    limit: int = 50,
    _: User = Depends(get_current_active_user),
):
    """数据主权相关审计日志（导出、断开权等）分页查询。"""
    from src.services.audit_log_service import audit_log_service
    from src.models.audit_log import ResourceType

    logs, total = await audit_log_service.get_logs(
        resource_type=ResourceType.DATA_SOVEREIGNTY,
        skip=skip,
        limit=min(limit, 100),
    )
    return {"logs": [log.to_dict() for log in logs], "total": total}


@router.get("/cross-store/waste")
async def cross_store_waste(
    tenant_id: str,
    date_start: str,
    date_end: str,
    store_ids: Optional[str] = None,
    _: User = Depends(get_current_active_user),
):
    """跨店损耗对比：多门店执行损耗推理并返回对比结果。store_ids 逗号分隔，不传则从图谱/PG 取全部门店。"""
    from src.core.database import get_db_session
    from src.services.ontology_cross_store_service import cross_store_waste_comparison
    ids = [x.strip() for x in store_ids.split(",") if x.strip()] if store_ids else None
    async with get_db_session() as session:
        result = await cross_store_waste_comparison(
            session, tenant_id=tenant_id, date_start=date_start, date_end=date_end, store_ids=ids
        )
    return result


@router.get("/health")
async def ontology_health():
    """Neo4j 本体层健康检查（无需认证）。"""
    repo = get_ontology_repository()
    if not repo:
        return {"status": "disabled", "neo4j": "not configured"}
    ok = repo.health()
    return {"status": "healthy" if ok else "unhealthy", "neo4j": "ok" if ok else "connection failed"}


# ---------- Phase 3: 门店相似度 ----------

class StoreSimilarityRequest(BaseModel):
    store_id_a: str
    store_id_b: str
    similarity_score: float = 0.8
    reason: str = "region"


@router.post("/stores/similarity")
async def upsert_store_similarity(
    req: StoreSimilarityRequest,
    current_user=Depends(get_current_active_user),
):
    """
    建立两门店之间的 SIMILAR_TO 关系（双向，幂等）。
    similarity_score: 0.0–1.0，建议阈值 0.5+。
    reason: 相似原因，如 "region"、"city"、"area_seats"、"revenue_tier"。
    """
    repo = get_ontology_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Neo4j not configured")
    repo.merge_store_similarity(
        store_id_a=req.store_id_a,
        store_id_b=req.store_id_b,
        similarity_score=req.similarity_score,
        reason=req.reason,
    )
    return {"ok": True, "store_id_a": req.store_id_a, "store_id_b": req.store_id_b, "score": req.similarity_score}


@router.get("/stores/{store_id}/similar")
async def get_similar_stores(
    store_id: str,
    min_score: float = 0.5,
    limit: int = 10,
    current_user=Depends(get_current_active_user),
):
    """查询与指定门店相似的门店列表（按相似度得分排序）。"""
    repo = get_ontology_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Neo4j not configured")
    similar = repo.get_similar_stores(store_id=store_id, min_score=min_score, limit=limit)
    return {"store_id": store_id, "similar_stores": similar, "total": len(similar)}


# ---------- 员工培训图谱状态 ----------

@router.get("/staff/{staff_id}/training-status")
async def staff_training_status(
    staff_id: str,
    current_user=Depends(get_current_active_user),
):
    """
    查询员工在 Neo4j 图谱中的培训状态：
    - completed: 已完成的 TrainingModule 列表（含分数、完成时间）
    - needs: 待完成的 TrainingModule 列表（含紧迫度、截止日期、关联损耗事件）
    """
    repo = get_ontology_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Neo4j not configured")
    status = repo.get_staff_training_status(staff_id=staff_id)
    return status


# ---------- 手动触发图谱同步 ----------

@router.post("/admin/sync-graph")
async def admin_sync_graph(
    tenant_id: str = "",
    current_user=Depends(get_current_active_user),
):
    """手动触发 PG → Neo4j 全量同步（生产环境由 Celery Beat 每日自动执行）。"""
    from src.core.celery_tasks import sync_ontology_graph
    task = sync_ontology_graph.delay(tenant_id=tenant_id)
    return {"ok": True, "task_id": task.id, "message": "图谱同步任务已提交"}
