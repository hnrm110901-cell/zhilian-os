"""
Edge Hub API

提供：
  GET  /api/v1/edge-hub/dashboard/summary       — 总览指标卡
  GET  /api/v1/edge-hub/dashboard/trends        — 趋势图数据
  GET  /api/v1/edge-hub/dashboard/risk-stores   — 异常门店排行
  GET  /api/v1/edge-hub/dashboard/todos         — 待处理事项
  GET  /api/v1/edge-hub/dashboard/recent-alerts — 今日告警列表

  GET  /api/v1/edge-hub/nodes                  — 全局边缘节点列表（支持状态/关键词筛选）

  GET  /api/v1/edge-hub/stores/{store_id}       — 门店边缘详情
  GET  /api/v1/edge-hub/stores/{store_id}/devices — 门店设备列表
  GET  /api/v1/edge-hub/stores/{store_id}/alerts  — 门店告警列表

  GET    /api/v1/edge-hub/alerts               — 全局告警列表（支持多维筛选）
  PATCH  /api/v1/edge-hub/alerts/{alert_id}/resolve — 标记告警已解决

  GET  /api/v1/edge-hub/bindings/{store_id}     — 门店耳机绑定列表
  POST /api/v1/edge-hub/bindings/{store_id}     — 创建绑定
  PUT  /api/v1/edge-hub/bindings/{binding_id}   — 更新绑定
  DELETE /api/v1/edge-hub/bindings/{binding_id} — 解绑
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.edge_hub import (
    AlertStatus,
    BindingStatus,
    DeviceStatus,
    EdgeAlert,
    EdgeDevice,
    EdgeHub,
    HeadsetBinding,
    HubStatus,
)
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/edge-hub", tags=["edge_hub"])


# ── 请求 / 响应模型 ────────────────────────────────────────────────────────────


class BindingCreate(BaseModel):
    device_id: str
    position: str
    employee_id: Optional[str] = None
    channel: Optional[int] = None


class HeartbeatPayload(BaseModel):
    status: Optional[str] = None  # "online" | "degraded" | "upgrading"
    runtime_version: Optional[str] = None
    ip_address: Optional[str] = None
    cpu_pct: Optional[float] = None
    mem_pct: Optional[float] = None
    disk_pct: Optional[float] = None
    devices: Optional[List[Dict[str, Any]]] = None  # [{device_code, status, firmware_ver}]


class BindingUpdate(BaseModel):
    position: Optional[str] = None
    employee_id: Optional[str] = None
    channel: Optional[int] = None
    status: Optional[str] = None


# ── 内部辅助 ──────────────────────────────────────────────────────────────────


def _hub_row(h: EdgeHub) -> Dict[str, Any]:
    return {
        "id": h.id,
        "storeId": h.store_id,
        "hubCode": h.hub_code,
        "name": h.name,
        "status": h.status,
        "runtimeVersion": h.runtime_version,
        "ipAddress": h.ip_address,
        "lastHeartbeat": h.last_heartbeat.isoformat() if h.last_heartbeat else None,
        "cpuPct": h.cpu_pct,
        "memPct": h.mem_pct,
        "diskPct": h.disk_pct,
    }


def _device_row(d: EdgeDevice) -> Dict[str, Any]:
    return {
        "id": d.id,
        "hubId": d.hub_id,
        "storeId": d.store_id,
        "deviceCode": d.device_code,
        "deviceType": d.device_type,
        "name": d.name,
        "status": d.status,
        "lastSeen": d.last_seen.isoformat() if d.last_seen else None,
        "firmwareVer": d.firmware_ver,
    }


def _alert_row(a: EdgeAlert) -> Dict[str, Any]:
    return {
        "id": a.id,
        "storeId": a.store_id,
        "hubId": a.hub_id,
        "deviceId": a.device_id,
        "level": a.level,
        "alertType": a.alert_type,
        "message": a.message,
        "status": a.status,
        "resolvedAt": a.resolved_at.isoformat() if a.resolved_at else None,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
    }


def _binding_row(b: HeadsetBinding, device: Optional[EdgeDevice] = None) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": b.id,
        "storeId": b.store_id,
        "deviceId": b.device_id,
        "position": b.position,
        "employeeId": b.employee_id,
        "channel": b.channel,
        "status": b.status,
        "boundAt": b.bound_at.isoformat() if b.bound_at else None,
        "unboundAt": b.unbound_at.isoformat() if b.unbound_at else None,
    }
    if device:
        row["deviceCode"] = device.device_code
        row["deviceName"] = device.name
        row["deviceStatus"] = device.status
    return row


# ── Dashboard 接口 ─────────────────────────────────────────────────────────────


@router.get("/dashboard/summary")
async def dashboard_summary(
    dateRange: str = Query("today"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """总览指标卡"""
    total_hubs = (await db.execute(select(func.count(EdgeHub.id)))).scalar_one()
    online_hubs = (await db.execute(select(func.count(EdgeHub.id)).where(EdgeHub.status == HubStatus.ONLINE))).scalar_one()
    total_devices = (await db.execute(select(func.count(EdgeDevice.id)))).scalar_one()
    online_devices = (
        await db.execute(select(func.count(EdgeDevice.id)).where(EdgeDevice.status == DeviceStatus.ONLINE))
    ).scalar_one()

    since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_alerts = (await db.execute(select(func.count(EdgeAlert.id)).where(EdgeAlert.created_at >= since))).scalar_one()
    open_alerts = (await db.execute(select(func.count(EdgeAlert.id)).where(EdgeAlert.status == AlertStatus.OPEN))).scalar_one()
    p1_alerts = (
        await db.execute(
            select(func.count(EdgeAlert.id)).where(
                EdgeAlert.status == AlertStatus.OPEN,
                EdgeAlert.level == "p1",
            )
        )
    ).scalar_one()

    hub_online_rate = round(online_hubs / total_hubs * 100, 1) if total_hubs else 0.0
    device_online_rate = round(online_devices / total_devices * 100, 1) if total_devices else 0.0

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "refreshedAt": datetime.utcnow().isoformat() + "Z",
            "cards": {
                "totalHubCount": total_hubs,
                "onlineHubCount": online_hubs,
                "hubOnlineRate": hub_online_rate,
                "hubStatusLevel": "normal" if hub_online_rate >= 95 else "warning" if hub_online_rate >= 80 else "critical",
                "totalDeviceCount": total_devices,
                "onlineDeviceCount": online_devices,
                "deviceOnlineRate": device_online_rate,
                "deviceStatusLevel": "normal" if device_online_rate >= 90 else "warning",
                "todayAlertCount": today_alerts,
                "todayP1AlertCount": p1_alerts,
                "openAlertCount": open_alerts,
            },
        },
    }


@router.get("/dashboard/risk-stores")
async def dashboard_risk_stores(
    dateRange: str = Query("today"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """异常门店排行（有开放告警的门店）"""
    offset = (page - 1) * pageSize

    rows = (
        await db.execute(
            select(
                EdgeAlert.store_id,
                func.count(EdgeAlert.id).label("alert_count"),
            )
            .where(EdgeAlert.status == AlertStatus.OPEN)
            .group_by(EdgeAlert.store_id)
            .order_by(func.count(EdgeAlert.id).desc())
            .offset(offset)
            .limit(pageSize)
        )
    ).all()

    total = (
        await db.execute(select(func.count(func.distinct(EdgeAlert.store_id))).where(EdgeAlert.status == AlertStatus.OPEN))
    ).scalar_one()

    items = []
    for store_id, alert_count in rows:
        hub = (
            await db.execute(
                select(EdgeHub)
                .where(EdgeHub.store_id == store_id)
                .order_by(EdgeHub.last_heartbeat.desc().nullslast())
                .limit(1)
            )
        ).scalar_one_or_none()

        items.append(
            {
                "storeId": store_id,
                "storeName": store_id,
                "edgeHubId": hub.id if hub else None,
                "runtimeStatus": hub.status if hub else "offline",
                "alertCount": alert_count,
                "lastHeartbeatAt": hub.last_heartbeat.isoformat() if hub and hub.last_heartbeat else None,
            }
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {"list": items},
        "meta": {
            "page": page,
            "pageSize": pageSize,
            "total": total,
            "hasMore": offset + pageSize < total,
        },
    }


@router.get("/dashboard/recent-alerts")
async def dashboard_recent_alerts(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """今日告警列表"""
    since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    alerts = (
        (
            await db.execute(
                select(EdgeAlert).where(EdgeAlert.created_at >= since).order_by(EdgeAlert.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {"list": [_alert_row(a) for a in alerts]},
    }


# ── 门店边缘详情 ───────────────────────────────────────────────────────────────


@router.get("/stores/{store_id}")
async def store_edge_detail(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """门店边缘主机概要"""
    hubs = (await db.execute(select(EdgeHub).where(EdgeHub.store_id == store_id, EdgeHub.is_active == True))).scalars().all()

    if not hubs:
        raise HTTPException(status_code=404, detail="store edge hub not found")

    return {
        "code": 0,
        "message": "ok",
        "data": {"hubs": [_hub_row(h) for h in hubs]},
    }


@router.get("/stores/{store_id}/devices")
async def store_devices(
    store_id: str,
    device_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """门店设备列表"""
    q = select(EdgeDevice).where(EdgeDevice.store_id == store_id)
    if device_type:
        q = q.where(EdgeDevice.device_type == device_type)
    devices = (await db.execute(q.order_by(EdgeDevice.device_type, EdgeDevice.name))).scalars().all()

    return {
        "code": 0,
        "message": "ok",
        "data": {"devices": [_device_row(d) for d in devices]},
    }


@router.get("/stores/{store_id}/alerts")
async def store_alerts(
    store_id: str,
    status: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """门店告警列表"""
    q = select(EdgeAlert).where(EdgeAlert.store_id == store_id)
    if status:
        q = q.where(EdgeAlert.status == status)
    if level:
        q = q.where(EdgeAlert.level == level)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * pageSize
    alerts = (await db.execute(q.order_by(EdgeAlert.created_at.desc()).offset(offset).limit(pageSize))).scalars().all()

    return {
        "code": 0,
        "message": "ok",
        "data": {"list": [_alert_row(a) for a in alerts]},
        "meta": {
            "page": page,
            "pageSize": pageSize,
            "total": total,
            "hasMore": offset + pageSize < total,
        },
    }


# ── 全局节点列表 ───────────────────────────────────────────────────────────────

# ── 全局节点列表 ───────────────────────────────────────────────────────────────


@router.get("/nodes/{hub_id}")
async def get_node_detail(
    hub_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """单个边缘节点详情（含设备列表 + 最近10条告警）"""
    hub = (await db.execute(select(EdgeHub).where(EdgeHub.id == hub_id))).scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="hub not found")

    devices = (
        (await db.execute(select(EdgeDevice).where(EdgeDevice.hub_id == hub_id).order_by(EdgeDevice.device_type)))
        .scalars()
        .all()
    )

    recent_alerts = (
        (await db.execute(select(EdgeAlert).where(EdgeAlert.hub_id == hub_id).order_by(EdgeAlert.created_at.desc()).limit(10)))
        .scalars()
        .all()
    )

    row = _hub_row(hub)
    row["devices"] = [_device_row(d) for d in devices]
    row["recentAlerts"] = [_alert_row(a) for a in recent_alerts]
    return {"code": 0, "message": "ok", "data": row}


@router.get("/nodes")
async def list_nodes(
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """全局边缘节点列表（支持状态/关键词筛选）"""
    q = select(EdgeHub).where(EdgeHub.is_active == True)
    if status:
        q = q.where(EdgeHub.status == status)
    if keyword:
        like = f"%{keyword}%"
        q = q.where((EdgeHub.hub_code.ilike(like)) | (EdgeHub.name.ilike(like)) | (EdgeHub.store_id.ilike(like)))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * pageSize
    hubs = (
        (await db.execute(q.order_by(EdgeHub.last_heartbeat.desc().nullslast()).offset(offset).limit(pageSize)))
        .scalars()
        .all()
    )

    # 按节点批量查询设备数和未解决告警数
    hub_ids = [h.id for h in hubs]
    device_counts: Dict[str, int] = {}
    alert_counts: Dict[str, int] = {}
    if hub_ids:
        dev_rows = (
            await db.execute(
                select(EdgeDevice.hub_id, func.count(EdgeDevice.id).label("cnt"))
                .where(EdgeDevice.hub_id.in_(hub_ids))
                .group_by(EdgeDevice.hub_id)
            )
        ).all()
        device_counts = {r.hub_id: r.cnt for r in dev_rows}

        alert_rows = (
            await db.execute(
                select(EdgeAlert.hub_id, func.count(EdgeAlert.id).label("cnt"))
                .where(EdgeAlert.hub_id.in_(hub_ids), EdgeAlert.status == AlertStatus.OPEN)
                .group_by(EdgeAlert.hub_id)
            )
        ).all()
        alert_counts = {r.hub_id: r.cnt for r in alert_rows}

    items = []
    for h in hubs:
        row = _hub_row(h)
        row["deviceCount"] = device_counts.get(h.id, 0)
        row["openAlertCount"] = alert_counts.get(h.id, 0)
        items.append(row)

    return {
        "code": 0,
        "message": "ok",
        "data": {"nodes": items},
        "meta": {
            "page": page,
            "pageSize": pageSize,
            "total": total,
            "hasMore": offset + pageSize < total,
        },
    }


# ── 全局告警管理 ───────────────────────────────────────────────────────────────


@router.get("/alerts")
async def list_all_alerts(
    status: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """全局告警列表（支持多维筛选）"""
    q = select(EdgeAlert)
    if status:
        q = q.where(EdgeAlert.status == status)
    if level:
        q = q.where(EdgeAlert.level == level)
    if store_id:
        q = q.where(EdgeAlert.store_id == store_id)
    if alert_type:
        q = q.where(EdgeAlert.alert_type == alert_type)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * pageSize
    alerts = (await db.execute(q.order_by(EdgeAlert.created_at.desc()).offset(offset).limit(pageSize))).scalars().all()

    return {
        "code": 0,
        "message": "ok",
        "data": {"list": [_alert_row(a) for a in alerts]},
        "meta": {
            "page": page,
            "pageSize": pageSize,
            "total": total,
            "hasMore": offset + pageSize < total,
        },
    }


class BulkAlertAction(BaseModel):
    alert_ids: List[str]
    action: str  # "resolve" | "ignore"


@router.post("/alerts/bulk-action")
async def bulk_alert_action(
    body: BulkAlertAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """批量操作告警（批量解决 / 批量忽略）"""
    if body.action not in ("resolve", "ignore"):
        raise HTTPException(status_code=422, detail="action must be 'resolve' or 'ignore'")
    if not body.alert_ids:
        return {"code": 0, "message": "no alerts", "data": {"affected": 0}}

    target_status = AlertStatus.RESOLVED if body.action == "resolve" else AlertStatus.IGNORED
    now = datetime.utcnow()
    resolved_by = str(getattr(current_user, "username", current_user.id))

    alerts = (
        (
            await db.execute(
                select(EdgeAlert).where(
                    EdgeAlert.id.in_(body.alert_ids),
                    EdgeAlert.status == AlertStatus.OPEN,
                )
            )
        )
        .scalars()
        .all()
    )

    for alert in alerts:
        alert.status = target_status
        alert.resolved_at = now
        alert.resolved_by = resolved_by

    await db.commit()
    return {
        "code": 0,
        "message": "ok",
        "data": {"affected": len(alerts)},
    }


@router.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """标记告警已解决"""
    alert = (await db.execute(select(EdgeAlert).where(EdgeAlert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    if alert.status == AlertStatus.RESOLVED:
        return {"code": 0, "message": "already resolved", "data": _alert_row(alert)}

    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = str(getattr(current_user, "username", current_user.id))
    await db.commit()
    await db.refresh(alert)

    return {"code": 0, "message": "ok", "data": _alert_row(alert)}


@router.patch("/alerts/{alert_id}/ignore")
async def ignore_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """忽略告警（状态置为 ignored）"""
    alert = (await db.execute(select(EdgeAlert).where(EdgeAlert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")

    alert.status = AlertStatus.IGNORED
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = str(getattr(current_user, "username", current_user.id))
    await db.commit()
    await db.refresh(alert)
    return {"code": 0, "message": "ok", "data": _alert_row(alert)}


@router.patch("/alerts/{alert_id}/escalate")
async def escalate_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """升级告警级别（P3→P2→P1）"""
    alert = (await db.execute(select(EdgeAlert).where(EdgeAlert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")

    level_order = ["p3", "p2", "p1"]
    current_idx = level_order.index(alert.level) if alert.level in level_order else 0
    alert.level = level_order[min(current_idx + 1, len(level_order) - 1)]
    await db.commit()
    await db.refresh(alert)
    return {"code": 0, "message": "ok", "data": _alert_row(alert)}


@router.post("/nodes/{hub_id}/inspect")
async def inspect_node(
    hub_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """触发节点巡检（更新 last_heartbeat 记录，实际硬件层命令由边缘主机处理）"""
    hub = (await db.execute(select(EdgeHub).where(EdgeHub.id == hub_id))).scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="hub not found")

    # 记录巡检时间戳（真实场景会推送指令到边缘，此处记录触发）
    hub.last_heartbeat = datetime.utcnow()
    await db.commit()
    await db.refresh(hub)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "hubId": hub.id,
            "inspectedAt": hub.last_heartbeat.isoformat() + "Z",
            "status": hub.status,
        },
    }


_HUB_SECRET = os.getenv("EDGE_HUB_SECRET", "")


@router.post("/nodes/{hub_id}/heartbeat")
async def receive_heartbeat(
    hub_id: str,
    body: HeartbeatPayload,
    db: AsyncSession = Depends(get_db),
    x_hub_secret: Optional[str] = Header(None, alias="X-Hub-Secret"),
) -> Dict[str, Any]:
    """
    边缘主机心跳上报（硬件专用，不要求 JWT）。

    认证：请求头 X-Hub-Secret 必须匹配环境变量 EDGE_HUB_SECRET（非空时启用）。

    接受字段：status / runtime_version / ip_address / cpu_pct / mem_pct / disk_pct /
              devices[{device_code, status, firmware_ver}]
    """
    if _HUB_SECRET and x_hub_secret != _HUB_SECRET:
        raise HTTPException(status_code=401, detail="invalid hub secret")

    hub = (await db.execute(select(EdgeHub).where(EdgeHub.id == hub_id))).scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="hub not found")

    now = datetime.utcnow()
    hub.last_heartbeat = now

    if body.status is not None:
        hub.status = body.status
    elif hub.status != HubStatus.ONLINE:
        hub.status = HubStatus.ONLINE  # implicitly online if sending heartbeat

    if body.runtime_version is not None:
        hub.runtime_version = body.runtime_version
    if body.ip_address is not None:
        hub.ip_address = body.ip_address
    if body.cpu_pct is not None:
        hub.cpu_pct = body.cpu_pct
    if body.mem_pct is not None:
        hub.mem_pct = body.mem_pct
    if body.disk_pct is not None:
        hub.disk_pct = body.disk_pct

    # Update per-device status if provided
    device_results: List[Dict[str, Any]] = []
    if body.devices:
        for d in body.devices:
            code = d.get("device_code")
            status = d.get("status")
            fw_ver = d.get("firmware_ver")
            if not code:
                continue
            device = (
                await db.execute(select(EdgeDevice).where(EdgeDevice.hub_id == hub.id, EdgeDevice.device_code == code))
            ).scalar_one_or_none()
            if device:
                if status:
                    device.status = status
                if fw_ver:
                    device.firmware_ver = fw_ver
                device.last_seen = now
                device_results.append({"device_code": code, "updated": True})

    await db.commit()

    logger.debug(
        "edge_hub.heartbeat_received",
        hub_id=hub_id,
        hub_code=hub.hub_code,
        status=hub.status,
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "hubId": hub.id,
            "receivedAt": now.isoformat() + "Z",
            "status": hub.status,
            "devicesUpdated": len(device_results),
        },
    }


@router.get("/nodes/{hub_id}/metrics")
async def node_metrics(
    hub_id: str,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """节点资源趋势（近 N 小时，每小时一个采样点）
    当前版本基于最新快照生成演示数据；真实场景由边缘主机定时上报存储。
    """
    import math
    import random

    hub = (await db.execute(select(EdgeHub).where(EdgeHub.id == hub_id))).scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="hub not found")

    base_cpu = hub.cpu_pct if hub.cpu_pct is not None else 40.0
    base_mem = hub.mem_pct if hub.mem_pct is not None else 55.0
    base_disk = hub.disk_pct if hub.disk_pct is not None else 30.0

    now = datetime.utcnow()
    points = []
    for i in range(hours, 0, -1):
        ts = now - timedelta(hours=i)
        # 用正弦波 + 少量随机扰动模拟波动
        phase = (i / hours) * 2 * math.pi
        cpu = round(min(100, max(0, base_cpu + 10 * math.sin(phase) + random.uniform(-3, 3))), 1)
        mem = round(min(100, max(0, base_mem + 5 * math.sin(phase + 1) + random.uniform(-2, 2))), 1)
        disk = round(min(100, max(0, base_disk + 2 * math.sin(phase + 2) + random.uniform(-1, 1))), 1)
        points.append(
            {
                "time": ts.strftime("%Y-%m-%dT%H:00:00Z"),
                "timeLabel": ts.strftime("%m-%d %H:%M"),
                "cpuPct": cpu,
                "memPct": mem,
                "diskPct": disk,
            }
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "hubId": hub_id,
            "hours": hours,
            "points": points,
        },
    }


# ── 耳机绑定管理 ───────────────────────────────────────────────────────────────


@router.get("/bindings/{store_id}")
async def list_bindings(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """门店耳机绑定列表"""
    bindings = (
        (await db.execute(select(HeadsetBinding).where(HeadsetBinding.store_id == store_id).order_by(HeadsetBinding.position)))
        .scalars()
        .all()
    )

    device_ids = list({b.device_id for b in bindings})
    devices_map: Dict[str, EdgeDevice] = {}
    if device_ids:
        devs = (await db.execute(select(EdgeDevice).where(EdgeDevice.id.in_(device_ids)))).scalars().all()
        devices_map = {d.id: d for d in devs}

    return {
        "code": 0,
        "message": "ok",
        "data": {"bindings": [_binding_row(b, devices_map.get(b.device_id)) for b in bindings]},
    }


@router.post("/bindings/{store_id}")
async def create_binding(
    store_id: str,
    body: BindingCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """创建耳机绑定"""
    device = (await db.execute(select(EdgeDevice).where(EdgeDevice.id == body.device_id))).scalar_one_or_none()
    if not device or device.store_id != store_id:
        raise HTTPException(status_code=404, detail="device not found in this store")

    binding = HeadsetBinding(
        id=str(uuid.uuid4()),
        store_id=store_id,
        device_id=body.device_id,
        position=body.position,
        employee_id=body.employee_id,
        channel=body.channel,
        status=BindingStatus.ACTIVE,
        bound_at=datetime.utcnow(),
    )
    db.add(binding)
    await db.commit()
    await db.refresh(binding)

    return {"code": 0, "message": "ok", "data": _binding_row(binding, device)}


@router.put("/bindings/item/{binding_id}")
async def update_binding(
    binding_id: str,
    body: BindingUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """更新绑定（换人/换频道/解绑）"""
    binding = (await db.execute(select(HeadsetBinding).where(HeadsetBinding.id == binding_id))).scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="binding not found")

    if body.position is not None:
        binding.position = body.position
    if body.employee_id is not None:
        binding.employee_id = body.employee_id
    if body.channel is not None:
        binding.channel = body.channel
    if body.status == BindingStatus.INACTIVE:
        binding.status = BindingStatus.INACTIVE
        binding.unbound_at = datetime.utcnow()
    elif body.status == BindingStatus.ACTIVE:
        binding.status = BindingStatus.ACTIVE
        binding.unbound_at = None

    await db.commit()
    await db.refresh(binding)
    return {"code": 0, "message": "ok", "data": _binding_row(binding)}


@router.delete("/bindings/item/{binding_id}")
async def delete_binding(
    binding_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """解除绑定（软删除：设为 inactive）"""
    binding = (await db.execute(select(HeadsetBinding).where(HeadsetBinding.id == binding_id))).scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="binding not found")

    binding.status = BindingStatus.INACTIVE
    binding.unbound_at = datetime.utcnow()
    await db.commit()

    return {"code": 0, "message": "ok", "data": None}
