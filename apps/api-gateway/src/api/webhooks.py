"""
Webhook 订阅与分发 API — Phase 4 Month 10

ISV 开发者注册 HTTPS 端点，订阅平台事件，系统异步投递并记录投递日志。

Router prefix: /api/v1/webhooks
Endpoints:
  POST   /subscriptions                    — 注册 webhook
  GET    /subscriptions                    — 列出本开发者的 webhooks
  GET    /subscriptions/{sub_id}           — 订阅详情
  PUT    /subscriptions/{sub_id}           — 更新（URL / events / description / status）
  DELETE /subscriptions/{sub_id}          — 删除
  POST   /subscriptions/{sub_id}/ping     — 发送测试事件
  GET    /subscriptions/{sub_id}/deliveries — 投递历史
  POST   /internal/dispatch               — 内部触发事件（供其他服务调用）
  GET    /events                           — 支持的事件类型清单

支持的事件类型（SUPPORTED_EVENTS）:
  plugin.installed / plugin.uninstalled / plugin.reviewed
  settlement.approved / settlement.paid
  rating.created
  developer.tier_changed
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_EVENTS: List[str] = [
    "plugin.installed",
    "plugin.uninstalled",
    "plugin.reviewed",
    "settlement.approved",
    "settlement.paid",
    "rating.created",
    "developer.tier_changed",
]

MAX_SUBS_PER_DEV = 10  # max webhook subscriptions per developer
MAX_DELIVERY_RETRIES = 5  # max retry attempts before marking failed


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row(row) -> Dict[str, Any]:
    return dict(row._mapping)


def _hash_secret(secret: str) -> str:
    """Store a SHA-256 hash of the secret, not the plaintext."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _sign_payload(secret_hash: str, payload: str) -> str:
    """Generate X-Zhilian-Signature header value (HMAC-SHA256 over payload)."""
    return "sha256=" + hmac.new(secret_hash.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _validate_events(events: List[str]) -> None:
    unknown = [e for e in events if e not in SUPPORTED_EVENTS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的事件类型: {unknown}. 支持: {SUPPORTED_EVENTS}",
        )


async def _get_subscription(sub_id: str, developer_id: str, db: AsyncSession) -> Dict[str, Any]:
    row = await db.execute(
        text("SELECT * FROM webhook_subscriptions WHERE id = :id AND developer_id = :did"),
        {"id": sub_id, "did": developer_id},
    )
    sub = row.fetchone()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook 订阅不存在")
    return _row(sub)


async def _require_developer(developer_id: str, db: AsyncSession) -> None:
    row = await db.execute(
        text("SELECT id FROM isv_developers WHERE id = :id AND status = 'active'"),
        {"id": developer_id},
    )
    if not row.fetchone():
        raise HTTPException(status_code=404, detail="开发者不存在或未激活")


def _format_sub(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Deserialize events JSON and mask secret_hash."""
    events = sub.get("events", "[]")
    if isinstance(events, str):
        try:
            events = json.loads(events)
        except Exception:
            events = []
    return {
        **sub,
        "events": events,
        "secret_hash": sub["secret_hash"][:8] + "…",  # only show prefix
    }


# ── Request schemas ───────────────────────────────────────────────────────────


class CreateSubscriptionRequest(BaseModel):
    developer_id: str
    endpoint_url: str
    secret: str  # plaintext; stored as SHA-256 hash
    events: List[str]
    description: Optional[str] = None


class UpdateSubscriptionRequest(BaseModel):
    endpoint_url: Optional[str] = None
    events: Optional[List[str]] = None
    description: Optional[str] = None
    status: Optional[str] = None  # active / paused


class DispatchEventRequest(BaseModel):
    developer_id: str
    event_type: str
    payload: Dict[str, Any]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/events")
async def list_supported_events() -> Dict[str, Any]:
    """返回平台支持的全部 Webhook 事件类型。"""
    return {
        "events": [
            {"type": "plugin.installed", "description": "店铺安装了您的插件"},
            {"type": "plugin.uninstalled", "description": "店铺卸载了您的插件"},
            {"type": "plugin.reviewed", "description": "插件审核结果（通过/拒绝）"},
            {"type": "settlement.approved", "description": "结算单已审核通过"},
            {"type": "settlement.paid", "description": "结算款项已支付"},
            {"type": "rating.created", "description": "插件收到新评分"},
            {"type": "developer.tier_changed", "description": "开发者套餐等级变更"},
        ]
    }


@router.post("/subscriptions", status_code=201)
async def create_subscription(
    req: CreateSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """注册一个新的 Webhook 订阅。"""
    await _require_developer(req.developer_id, db)
    _validate_events(req.events)

    # Check URL is HTTPS
    if not req.endpoint_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="endpoint_url 必须使用 HTTPS")

    # Enforce per-developer limit
    count_row = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM webhook_subscriptions WHERE developer_id = :did"),
        {"did": req.developer_id},
    )
    if count_row.fetchone().cnt >= MAX_SUBS_PER_DEV:
        raise HTTPException(
            status_code=409,
            detail=f"每个开发者最多注册 {MAX_SUBS_PER_DEV} 个 Webhook",
        )

    # Check duplicate URL+developer
    dup = await db.execute(
        text("SELECT id FROM webhook_subscriptions " "WHERE developer_id = :did AND endpoint_url = :url"),
        {"did": req.developer_id, "url": req.endpoint_url},
    )
    if dup.fetchone():
        raise HTTPException(status_code=409, detail="该端点 URL 已注册")

    sub_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO webhook_subscriptions "
            "(id, developer_id, endpoint_url, secret_hash, events, description) "
            "VALUES (:id, :did, :url, :sh, :ev, :desc)"
        ),
        {
            "id": sub_id,
            "did": req.developer_id,
            "url": req.endpoint_url,
            "sh": _hash_secret(req.secret),
            "ev": json.dumps(req.events),
            "desc": req.description,
        },
    )
    await db.commit()

    row = await db.execute(text("SELECT * FROM webhook_subscriptions WHERE id = :id"), {"id": sub_id})
    return _format_sub(_row(row.fetchone()))


@router.get("/subscriptions")
async def list_subscriptions(
    developer_id: str = Query(..., description="开发者 ID"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """列出开发者的所有 Webhook 订阅。"""
    await _require_developer(developer_id, db)
    rows = await db.execute(
        text("SELECT * FROM webhook_subscriptions " "WHERE developer_id = :did ORDER BY created_at DESC"),
        {"did": developer_id},
    )
    subs = [_format_sub(_row(r)) for r in rows.fetchall()]
    return {"developer_id": developer_id, "subscriptions": subs, "total": len(subs)}


@router.get("/subscriptions/{sub_id}")
async def get_subscription(
    sub_id: str,
    developer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    sub = await _get_subscription(sub_id, developer_id, db)
    return _format_sub(sub)


@router.put("/subscriptions/{sub_id}")
async def update_subscription(
    sub_id: str,
    req: UpdateSubscriptionRequest,
    developer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """更新 Webhook 订阅（URL / 事件列表 / 描述 / 状态）。"""
    sub = await _get_subscription(sub_id, developer_id, db)

    if req.events is not None:
        _validate_events(req.events)
    if req.endpoint_url is not None and not req.endpoint_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="endpoint_url 必须使用 HTTPS")
    if req.status is not None and req.status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="status 必须为 active 或 paused")

    updates: Dict[str, Any] = {}
    if req.endpoint_url is not None:
        updates["endpoint_url"] = req.endpoint_url
    if req.events is not None:
        updates["events"] = json.dumps(req.events)
    if req.description is not None:
        updates["description"] = req.description
    if req.status is not None:
        updates["status"] = req.status

    if not updates:
        return _format_sub(sub)

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = sub_id
    await db.execute(
        text(f"UPDATE webhook_subscriptions SET {set_clause} WHERE id = :id"),
        updates,
    )
    await db.commit()

    row = await db.execute(text("SELECT * FROM webhook_subscriptions WHERE id = :id"), {"id": sub_id})
    return _format_sub(_row(row.fetchone()))


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(
    sub_id: str,
    developer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """删除 Webhook 订阅（同时级联删除投递日志）。"""
    await _get_subscription(sub_id, developer_id, db)
    await db.execute(text("DELETE FROM webhook_subscriptions WHERE id = :id"), {"id": sub_id})
    await db.commit()


@router.post("/subscriptions/{sub_id}/ping", status_code=200)
async def ping_subscription(
    sub_id: str,
    developer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """向该 Webhook 端点发送测试 ping 事件，验证端点可达性。"""
    sub = await _get_subscription(sub_id, developer_id, db)

    delivery_id = str(uuid.uuid4())
    payload = {
        "event": "ping",
        "subscription_id": sub_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "屯象OS Webhook 连通性测试",
    }
    payload_str = json.dumps(payload, ensure_ascii=False)

    await db.execute(
        text(
            "INSERT INTO webhook_delivery_logs "
            "(id, subscription_id, event_type, payload_size, status, attempts) "
            "VALUES (:id, :sid, 'ping', :ps, 'pending', 0)"
        ),
        {"id": delivery_id, "sid": sub_id, "ps": len(payload_str.encode())},
    )
    await db.commit()

    return {
        "delivery_id": delivery_id,
        "endpoint_url": sub["endpoint_url"],
        "event_type": "ping",
        "payload": payload,
        "status": "pending",
        "note": "测试事件已加入投递队列，请检查您的端点日志",
    }


@router.get("/subscriptions/{sub_id}/deliveries")
async def get_delivery_history(
    sub_id: str,
    developer_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """查看 Webhook 投递历史（最近 N 条）。"""
    await _get_subscription(sub_id, developer_id, db)

    rows = await db.execute(
        text("SELECT * FROM webhook_delivery_logs " "WHERE subscription_id = :sid " "ORDER BY created_at DESC LIMIT :lim"),
        {"sid": sub_id, "lim": limit},
    )
    deliveries = [_row(r) for r in rows.fetchall()]

    # Summary counts
    all_rows = await db.execute(
        text("SELECT status, COUNT(*) AS cnt " "FROM webhook_delivery_logs WHERE subscription_id = :sid " "GROUP BY status"),
        {"sid": sub_id},
    )
    summary = {r.status: r.cnt for r in all_rows.fetchall()}

    return {
        "subscription_id": sub_id,
        "deliveries": deliveries,
        "total_shown": len(deliveries),
        "summary": summary,
    }


@router.post("/internal/dispatch", status_code=202)
async def dispatch_event(
    req: DispatchEventRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    内部事件分发接口（供其他服务调用）。
    遍历该开发者订阅了此事件类型且状态为 active 的 webhook，
    创建 delivery_log 记录，等待异步 worker 投递。
    """
    if req.event_type not in SUPPORTED_EVENTS:
        raise HTTPException(status_code=400, detail=f"不支持的事件类型: {req.event_type}")

    # Find active subscriptions for this developer+event
    rows = await db.execute(
        text("SELECT * FROM webhook_subscriptions " "WHERE developer_id = :did AND status = 'active'"),
        {"did": req.developer_id},
    )
    subs = [_row(r) for r in rows.fetchall()]

    # Filter by subscribed events
    matched = []
    for sub in subs:
        events_list = sub.get("events", "[]")
        if isinstance(events_list, str):
            try:
                events_list = json.loads(events_list)
            except Exception:
                events_list = []
        if req.event_type in events_list:
            matched.append(sub)

    if not matched:
        return {"queued": 0, "message": "无匹配的 Webhook 订阅"}

    payload = {
        "event": req.event_type,
        "developer_id": req.developer_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": req.payload,
    }
    payload_str = json.dumps(payload, ensure_ascii=False)
    payload_size = len(payload_str.encode())

    delivery_ids = []
    for sub in matched:
        delivery_id = str(uuid.uuid4())
        await db.execute(
            text(
                "INSERT INTO webhook_delivery_logs "
                "(id, subscription_id, event_type, payload_size, status, attempts) "
                "VALUES (:id, :sid, :et, :ps, 'pending', 0)"
            ),
            {
                "id": delivery_id,
                "sid": sub["id"],
                "et": req.event_type,
                "ps": payload_size,
            },
        )
        # Update last_triggered_at on subscription
        await db.execute(
            text("UPDATE webhook_subscriptions " "SET last_triggered_at = NOW() WHERE id = :id"),
            {"id": sub["id"]},
        )
        delivery_ids.append(delivery_id)

    await db.commit()

    return {
        "queued": len(delivery_ids),
        "delivery_ids": delivery_ids,
        "event_type": req.event_type,
    }
