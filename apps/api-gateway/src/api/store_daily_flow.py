"""
门店全天业务流程节点管理 — API 路由

四层角色端点：
  /api/v1/daily-flow/mobile/*    — 门店执行层（员工/店长手机端）
  /api/v1/daily-flow/manager/*   — 店长调度层
  /api/v1/daily-flow/hq/*        — 总部巡检层
  /api/v1/daily-flow/config/*    — 配置后台层
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/daily-flow", tags=["门店全天流程"])


# ══════════════════════════════════════════════════════════════
#  请求/响应模型
# ══════════════════════════════════════════════════════════════

class InitFlowRequest(BaseModel):
    store_id: str
    brand_id: str
    biz_date: date
    business_mode: str = "lunch_dinner"


class TaskSubmitRequest(BaseModel):
    task_instance_id: str
    submitted_by: str
    proof_type: str = "none"
    proof_value: Optional[dict] = None
    remark: Optional[str] = None


class NodeCompleteRequest(BaseModel):
    node_instance_id: str
    completed_by: str
    comment: Optional[str] = None


class IncidentCreateRequest(BaseModel):
    store_id: str
    brand_id: str
    biz_date: date
    incident_type: str
    severity: str = "medium"
    title: str
    description: Optional[str] = None
    reporter_id: str
    reporter_role: str = "store_staff"
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    attachments: Optional[list] = None


class IncidentUpdateRequest(BaseModel):
    action: str  # accept / resolve / escalate / close
    assignee_id: Optional[str] = None
    resolution_note: Optional[str] = None


class FlowProgressResponse(BaseModel):
    store_id: str
    biz_date: str
    flow_status: str
    progress_pct: float
    total_nodes: int
    completed_nodes: int
    current_node_name: Optional[str]
    overdue_count: int
    overdue_nodes: list
    nodes: list


class NodeDetailResponse(BaseModel):
    node_instance_id: str
    node_code: str
    node_name: str
    node_order: int
    status: str
    scheduled_start: str
    scheduled_end: str
    actual_start: Optional[str]
    actual_end: Optional[str]
    total_tasks: int
    completed_tasks: int
    tasks: list
    can_complete: bool
    blocking_reasons: list


class StoreRiskSummary(BaseModel):
    store_id: str
    biz_date: str
    flow_status: str
    progress_pct: float
    current_node_name: Optional[str]
    overdue_count: int
    risk_level: str
    incident_summary: dict
    settlement_status: str


# ══════════════════════════════════════════════════════════════
#  内存存储（MVP阶段，后续迁移到DB）
# ══════════════════════════════════════════════════════════════

from ..services.store_daily_flow_service import (
    build_node_instances, calc_flow_progress, check_node_completion,
    should_auto_enter_node, should_mark_overdue, escalation_needed,
    build_store_daily_summary, STANDARD_TASKS, STANDARD_NODES,
)

# MVP: 内存存储，单进程足够种子客户验证
_flows: dict = {}        # {(store_id, biz_date_str): flow_dict}
_nodes: dict = {}        # {node_id: node_dict}
_tasks: dict = {}        # {task_id: task_dict}
_incidents: dict = {}    # {incident_id: incident_dict}
_logs: list = []


def _get_or_init_flow(store_id: str, brand_id: str, biz_date: date, business_mode: str) -> dict:
    """获取或初始化当天流程"""
    key = (store_id, str(biz_date))
    if key in _flows:
        return _flows[key]

    from uuid import uuid4
    flow_id = str(uuid4())
    flow = {
        "id": flow_id,
        "store_id": store_id,
        "brand_id": brand_id,
        "biz_date": str(biz_date),
        "status": "pending",
        "business_mode": business_mode,
    }
    _flows[key] = flow

    # 生成节点实例
    node_instances = build_node_instances(store_id, brand_id, biz_date, flow_id, STANDARD_NODES, business_mode)
    for ni in node_instances:
        ni["scheduled_start"] = ni["scheduled_start"].isoformat()
        ni["scheduled_end"] = ni["scheduled_end"].isoformat()
        _nodes[ni["id"]] = ni

        # 生成任务实例
        task_templates = STANDARD_TASKS.get(ni["node_code"], [])
        task_count = 0
        for tt in task_templates:
            tid = str(uuid4())
            task = {
                "id": tid,
                "node_instance_id": ni["id"],
                "store_id": store_id,
                "biz_date": str(biz_date),
                "task_code": tt["code"],
                "task_name": tt["name"],
                "task_order": tt["order"],
                "is_required": tt.get("required", True),
                "assignee_role": tt.get("role", "store_staff"),
                "status": "todo",
                "proof_type": tt.get("proof", "none"),
                "proof_value": None,
                "submitted_at": None,
                "submitted_by": None,
                "remark": None,
            }
            _tasks[tid] = task
            task_count += 1

        ni["total_tasks"] = task_count
        ni["completed_tasks"] = 0

    flow["total_nodes"] = len(node_instances)
    flow["completed_nodes"] = 0
    return flow


def _get_node_tasks(node_id: str) -> list:
    return sorted(
        [t for t in _tasks.values() if t["node_instance_id"] == node_id],
        key=lambda x: x["task_order"],
    )


def _get_flow_nodes(store_id: str, biz_date: str) -> list:
    return sorted(
        [n for n in _nodes.values() if n["store_id"] == store_id and str(n["biz_date"]) == biz_date],
        key=lambda x: x["node_order"],
    )


def _log_action(store_id, biz_date, node_id, task_id, action_type, action_by, note=None):
    _logs.append({
        "store_id": store_id,
        "biz_date": str(biz_date),
        "node_instance_id": node_id,
        "task_instance_id": task_id,
        "action_type": action_type,
        "action_by": action_by,
        "action_time": datetime.utcnow().isoformat(),
        "action_note": note,
    })


# ══════════════════════════════════════════════════════════════
#  移动执行端 /mobile/*
# ══════════════════════════════════════════════════════════════

@router.post("/mobile/init-flow", summary="初始化当天流程")
async def init_flow(req: InitFlowRequest):
    flow = _get_or_init_flow(req.store_id, req.brand_id, req.biz_date, req.business_mode)
    nodes = _get_flow_nodes(req.store_id, str(req.biz_date))

    # 自动进入到时间的节点
    now = datetime.utcnow()
    for n in nodes:
        n_with_dt = {**n, "scheduled_start": datetime.fromisoformat(n["scheduled_start"])}
        if should_auto_enter_node(n_with_dt, now) and n["status"] == "pending":
            n["status"] = "in_progress"
            n["actual_start"] = now.isoformat()
            _log_action(req.store_id, req.biz_date, n["id"], None, "node_auto_enter", "system")

    progress = calc_flow_progress(nodes)
    return {"flow": flow, "progress": progress, "nodes": nodes}


@router.get("/mobile/workspace/{store_id}", summary="工作台首页")
async def mobile_workspace(store_id: str, biz_date: date = Query(default=None)):
    biz_date = biz_date or date.today()
    key = (store_id, str(biz_date))
    if key not in _flows:
        raise HTTPException(404, "当天流程未初始化，请先调用 init-flow")

    nodes = _get_flow_nodes(store_id, str(biz_date))
    progress = calc_flow_progress(nodes)

    # 我的待办（所有未完成任务）
    my_tasks = [t for t in _tasks.values()
                if t["store_id"] == store_id and t["biz_date"] == str(biz_date) and t["status"] in ("todo", "doing")]

    # 异常提醒
    my_incidents = [i for i in _incidents.values()
                    if i["store_id"] == store_id and i["biz_date"] == str(biz_date) and i["status"] not in ("closed",)]

    return {
        "progress": progress,
        "current_node": progress.get("current_node"),
        "pending_tasks_count": len(my_tasks),
        "open_incidents_count": len(my_incidents),
        "top_tasks": sorted(my_tasks, key=lambda x: x["task_order"])[:5],
    }


@router.get("/mobile/node/{node_instance_id}", summary="节点详情+任务列表")
async def mobile_node_detail(node_instance_id: str):
    node = _nodes.get(node_instance_id)
    if not node:
        raise HTTPException(404, "节点不存在")

    tasks = _get_node_tasks(node_instance_id)
    completion = check_node_completion(node, tasks)

    return {
        "node": node,
        "tasks": tasks,
        "can_complete": completion["can_complete"],
        "blocking_reasons": completion["blocking_reasons"],
    }


@router.post("/mobile/task/submit", summary="提交任务")
async def mobile_submit_task(req: TaskSubmitRequest):
    task = _tasks.get(req.task_instance_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["status"] not in ("todo", "doing"):
        raise HTTPException(400, f"任务状态为 {task['status']}，不可提交")

    task["status"] = "done"
    task["submitted_at"] = datetime.utcnow().isoformat()
    task["submitted_by"] = req.submitted_by
    task["proof_value"] = req.proof_value
    task["remark"] = req.remark

    # 更新节点已完成任务数
    node = _nodes.get(task["node_instance_id"])
    if node:
        node["completed_tasks"] = sum(
            1 for t in _get_node_tasks(node["id"]) if t["status"] == "done"
        )

    _log_action(task["store_id"], task["biz_date"], task["node_instance_id"],
                req.task_instance_id, "task_submit", req.submitted_by, req.remark)

    return {"status": "ok", "task": task}


@router.post("/mobile/node/complete", summary="完成节点")
async def mobile_complete_node(req: NodeCompleteRequest):
    node = _nodes.get(req.node_instance_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    if node["status"] != "in_progress":
        raise HTTPException(400, f"节点状态为 {node['status']}，不可完成")

    tasks = _get_node_tasks(req.node_instance_id)
    completion = check_node_completion(node, tasks)
    if not completion["can_complete"]:
        raise HTTPException(400, f"节点未满足完成条件: {'; '.join(completion['blocking_reasons'])}")

    node["status"] = "completed"
    node["actual_end"] = datetime.utcnow().isoformat()

    # 更新流程已完成节点数
    flow_key = (node["store_id"], str(node["biz_date"]))
    if flow_key in _flows:
        flow_nodes = _get_flow_nodes(node["store_id"], str(node["biz_date"]))
        _flows[flow_key]["completed_nodes"] = sum(1 for n in flow_nodes if n["status"] == "completed")

    # 自动进入下一个节点
    flow_nodes = _get_flow_nodes(node["store_id"], str(node["biz_date"]))
    for n in flow_nodes:
        if n["status"] == "pending" and n["node_order"] == node["node_order"] + 1:
            n["status"] = "in_progress"
            n["actual_start"] = datetime.utcnow().isoformat()
            _log_action(node["store_id"], node["biz_date"], n["id"], None, "node_auto_advance", "system")
            break

    _log_action(node["store_id"], node["biz_date"], req.node_instance_id, None,
                "node_complete", req.completed_by, req.comment)

    return {"status": "ok", "node": node}


@router.post("/mobile/incident/create", summary="上报异常")
async def mobile_create_incident(req: IncidentCreateRequest):
    from uuid import uuid4
    inc_id = str(uuid4())
    incident = {
        "id": inc_id,
        "store_id": req.store_id,
        "brand_id": req.brand_id,
        "biz_date": str(req.biz_date),
        "source_type": req.source_type,
        "source_id": req.source_id,
        "incident_type": req.incident_type,
        "severity": req.severity,
        "title": req.title,
        "description": req.description,
        "status": "new",
        "reporter_id": req.reporter_id,
        "reporter_role": req.reporter_role,
        "assignee_id": None,
        "escalation_level": 0,
        "resolution_note": None,
        "attachments": req.attachments,
        "created_at": datetime.utcnow().isoformat(),
    }
    _incidents[inc_id] = incident

    # 食品安全类直接升级
    esc = escalation_needed(incident, datetime.utcnow())
    if esc == "hq":
        incident["escalation_level"] = 3
        incident["status"] = "escalated"

    _log_action(req.store_id, req.biz_date, None, None, "incident_create", req.reporter_id, req.title)
    return {"status": "ok", "incident": incident}


# ══════════════════════════════════════════════════════════════
#  店长调度端 /manager/*
# ══════════════════════════════════════════════════════════════

@router.get("/manager/dashboard/{store_id}", summary="店长调度看板")
async def manager_dashboard(store_id: str, biz_date: date = Query(default=None)):
    biz_date = biz_date or date.today()
    nodes = _get_flow_nodes(store_id, str(biz_date))
    if not nodes:
        raise HTTPException(404, "当天流程未初始化")

    progress = calc_flow_progress(nodes)

    # 异常统计
    store_incidents = [i for i in _incidents.values()
                       if i["store_id"] == store_id and i["biz_date"] == str(biz_date)]
    incident_counts = {}
    for i in store_incidents:
        sev = i.get("severity", "medium")
        incident_counts[sev] = incident_counts.get(sev, 0) + 1

    # 超时检测
    now = datetime.utcnow()
    for n in nodes:
        n_dt = {**n, "scheduled_end": datetime.fromisoformat(n["scheduled_end"])}
        if should_mark_overdue(n_dt, now):
            n["status"] = "overdue"

    progress = calc_flow_progress(nodes)

    # 待处理任务
    pending_tasks = [t for t in _tasks.values()
                     if t["store_id"] == store_id and t["biz_date"] == str(biz_date) and t["status"] in ("todo", "doing")]

    return {
        "progress": progress,
        "nodes": nodes,
        "pending_tasks_count": len(pending_tasks),
        "incident_counts": incident_counts,
        "open_incidents": [i for i in store_incidents if i["status"] not in ("closed",)],
    }


@router.get("/manager/incidents/{store_id}", summary="异常工单列表")
async def manager_incidents(store_id: str, biz_date: date = Query(default=None), status: str = Query(default=None)):
    biz_date = biz_date or date.today()
    incidents = [i for i in _incidents.values()
                 if i["store_id"] == store_id and i["biz_date"] == str(biz_date)]
    if status:
        incidents = [i for i in incidents if i["status"] == status]
    return {"incidents": incidents, "total": len(incidents)}


@router.post("/manager/incident/{incident_id}/update", summary="处理异常工单")
async def manager_update_incident(incident_id: str, req: IncidentUpdateRequest):
    inc = _incidents.get(incident_id)
    if not inc:
        raise HTTPException(404, "异常工单不存在")

    if req.action == "accept":
        inc["status"] = "accepted"
        if req.assignee_id:
            inc["assignee_id"] = req.assignee_id
    elif req.action == "resolve":
        inc["status"] = "pending_review"
        inc["resolution_note"] = req.resolution_note
    elif req.action == "close":
        inc["status"] = "closed"
        inc["resolved_at"] = datetime.utcnow().isoformat()
        inc["resolution_note"] = req.resolution_note
    elif req.action == "escalate":
        inc["status"] = "escalated"
        inc["escalation_level"] = inc.get("escalation_level", 0) + 1
    else:
        raise HTTPException(400, f"未知操作: {req.action}")

    return {"status": "ok", "incident": inc}


@router.post("/manager/node/{node_instance_id}/skip", summary="跳过节点")
async def manager_skip_node(node_instance_id: str, reason: str = Query(...)):
    node = _nodes.get(node_instance_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    if node["status"] not in ("pending", "in_progress"):
        raise HTTPException(400, "节点已完成或已跳过")

    node["status"] = "skipped"
    _log_action(node["store_id"], node["biz_date"], node_instance_id, None, "node_skip", "manager", reason)
    return {"status": "ok", "node": node}


# ══════════════════════════════════════════════════════════════
#  总部巡检端 /hq/*
# ══════════════════════════════════════════════════════════════

@router.get("/hq/inspection", summary="总部巡检看板")
async def hq_inspection(brand_id: str = Query(default=None), biz_date: date = Query(default=None)):
    biz_date = biz_date or date.today()
    biz_str = str(biz_date)

    # 汇总所有门店
    store_summaries = []
    seen_stores = set()
    for key, flow in _flows.items():
        sid, d = key
        if d != biz_str:
            continue
        if brand_id and flow.get("brand_id") != brand_id:
            continue
        if sid in seen_stores:
            continue
        seen_stores.add(sid)

        nodes = _get_flow_nodes(sid, biz_str)
        progress = calc_flow_progress(nodes)

        store_incidents = [i for i in _incidents.values() if i["store_id"] == sid and i["biz_date"] == biz_str]
        inc_counts = {}
        for i in store_incidents:
            sev = i.get("severity", "medium")
            inc_counts[sev] = inc_counts.get(sev, 0) + 1

        settlement_key = (sid, biz_str)
        settlement_status = _flows.get(settlement_key, {}).get("settlement_status", "pending")

        summary = build_store_daily_summary(sid, biz_date, progress, inc_counts, settlement_status)
        store_summaries.append(summary)

    # 按风险降序排列
    store_summaries.sort(key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["risk_level"], 0), reverse=True)

    return {
        "biz_date": biz_str,
        "total_stores": len(store_summaries),
        "risk_high": sum(1 for s in store_summaries if s["risk_level"] == "high"),
        "risk_medium": sum(1 for s in store_summaries if s["risk_level"] == "medium"),
        "risk_low": sum(1 for s in store_summaries if s["risk_level"] == "low"),
        "avg_progress_pct": round(
            sum(s["progress_pct"] for s in store_summaries) / len(store_summaries), 1
        ) if store_summaries else 0,
        "stores": store_summaries,
    }


@router.get("/hq/store/{store_id}/detail", summary="单店详情（总部视角）")
async def hq_store_detail(store_id: str, biz_date: date = Query(default=None)):
    biz_date = biz_date or date.today()
    nodes = _get_flow_nodes(store_id, str(biz_date))
    if not nodes:
        raise HTTPException(404, "该门店当天无流程数据")

    progress = calc_flow_progress(nodes)
    incidents = [i for i in _incidents.values()
                 if i["store_id"] == store_id and i["biz_date"] == str(biz_date)]

    return {
        "store_id": store_id,
        "biz_date": str(biz_date),
        "progress": progress,
        "nodes": nodes,
        "incidents": incidents,
        "logs": [l for l in _logs if l["store_id"] == store_id and l["biz_date"] == str(biz_date)],
    }


# ══════════════════════════════════════════════════════════════
#  配置端 /config/* （MVP简化版）
# ══════════════════════════════════════════════════════════════

@router.get("/config/standard-nodes", summary="查看标准节点定义")
async def config_standard_nodes():
    return {"nodes": STANDARD_NODES, "total": len(STANDARD_NODES)}


@router.get("/config/standard-tasks/{node_code}", summary="查看节点标准任务")
async def config_standard_tasks(node_code: str):
    tasks = STANDARD_TASKS.get(node_code, [])
    if not tasks:
        raise HTTPException(404, f"节点 {node_code} 无标准任务定义")
    return {"node_code": node_code, "tasks": tasks, "total": len(tasks)}


@router.get("/config/standard-tasks", summary="查看全部标准任务")
async def config_all_standard_tasks():
    result = {}
    total = 0
    for node_code, tasks in STANDARD_TASKS.items():
        result[node_code] = tasks
        total += len(tasks)
    return {"tasks_by_node": result, "total_tasks": total, "total_nodes": len(result)}
