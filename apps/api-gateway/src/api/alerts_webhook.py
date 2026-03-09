"""
AlertManager Webhook 接收端点

用于接收 Prometheus Alertmanager 推送，并可选转发到企业微信。
"""

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from ..core.database import get_db_session
from ..models.ops import OpsEvent, OpsEventStatus
from ..services.redis_cache_service import redis_cache
from ..services.wechat_alert_service import wechat_alert_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
_DEDUP_CACHE: Dict[str, float] = {}


def _require_webhook_token(x_alert_token: Optional[str]) -> None:
    required = os.getenv("ALERT_WEBHOOK_TOKEN", "").strip()
    if not required:
        return
    if (x_alert_token or "").strip() != required:
        raise HTTPException(status_code=401, detail="Invalid alert webhook token")


def _extract_alerts(payload: Any) -> Tuple[List[Dict[str, Any]], str]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)], "firing"

    if isinstance(payload, dict):
        if isinstance(payload.get("alerts"), list):
            alerts = [x for x in payload["alerts"] if isinstance(x, dict)]
            status = str(payload.get("status", "firing"))
            return alerts, status
        if "labels" in payload or "alertname" in payload:
            return [payload], str(payload.get("status", "firing"))

    return [], "unknown"


def _pick_severity(alerts: List[Dict[str, Any]], default: str) -> str:
    priority = {"critical": 4, "error": 3, "warning": 2, "info": 1}
    current = default
    best = priority.get(default, 0)
    for alert in alerts:
        labels = alert.get("labels") or {}
        sev = str(labels.get("severity") or alert.get("severity") or "").lower()
        if priority.get(sev, 0) > best:
            best = priority[sev]
            current = sev
    return current


def _collect_recipients() -> List[str]:
    raw = os.getenv("ALERT_RECIPIENTS", "").strip()
    if raw:
        recipients = [x.strip() for x in raw.split(",") if x.strip()]
        if recipients:
            return recipients

    fallback = os.getenv("WECHAT_DEFAULT_RECIPIENT", "").strip()
    return [fallback] if fallback else []


def _alert_line(alert: Dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    name = labels.get("alertname") or alert.get("alertname") or "unknown"
    sev = labels.get("severity") or alert.get("severity") or "unknown"
    instance = labels.get("instance") or "n/a"
    summary = annotations.get("summary") or annotations.get("description") or ""
    if summary:
        return f"- {name} [{sev}] @ {instance}: {summary}"
    return f"- {name} [{sev}] @ {instance}"


def _dedupe_enabled() -> bool:
    return os.getenv("ALERT_DEDUPE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _dedupe_ttl_seconds() -> int:
    raw = os.getenv("ALERT_DEDUPE_TTL_SECONDS", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        return 300
    return max(1, value)


def _dedupe_backend() -> str:
    backend = os.getenv("ALERT_DEDUPE_BACKEND", "memory").strip().lower()
    if backend not in {"memory", "redis", "hybrid"}:
        return "memory"
    return backend


def _alert_dedupe_key(alert: Dict[str, Any], channel: str, status: str) -> str:
    labels = alert.get("labels") or {}
    name = str(labels.get("alertname") or alert.get("alertname") or "unknown")
    severity = str(labels.get("severity") or alert.get("severity") or "unknown")
    instance = str(labels.get("instance") or "n/a")
    store_id = str(labels.get("store_id") or labels.get("store") or "")
    return f"{channel}|{status}|{store_id}|{name}|{severity}|{instance}"


async def _filter_deduplicated_alerts(
    alerts: List[Dict[str, Any]],
    *,
    channel: str,
    status: str,
) -> Tuple[List[Dict[str, Any]], int]:
    if not alerts:
        return [], 0
    if not _dedupe_enabled():
        return alerts, 0

    now = time.time()
    ttl = _dedupe_ttl_seconds()
    backend = _dedupe_backend()
    fresh: List[Dict[str, Any]] = []
    suppressed = 0

    # opportunistic cleanup
    expired_keys = [k for k, exp in _DEDUP_CACHE.items() if exp <= now]
    for key in expired_keys[:500]:
        _DEDUP_CACHE.pop(key, None)

    for alert in alerts:
        key = _alert_dedupe_key(alert, channel, status)
        cache_key = f"alert_dedupe:{key}"

        # 1) in-process memory dedupe
        mem_hit = False
        if backend in {"memory", "hybrid"}:
            expires_at = _DEDUP_CACHE.get(key, 0.0)
            if expires_at > now:
                mem_hit = True
            else:
                _DEDUP_CACHE[key] = now + ttl

        # 2) cross-instance redis dedupe (best effort)
        redis_hit = False
        if backend in {"redis", "hybrid"}:
            try:
                redis_hit = await redis_cache.exists(cache_key)
                if not redis_hit:
                    await redis_cache.set(cache_key, "1", expire=ttl)
            except Exception as exc:  # noqa: BLE001
                logger.warning("alert_dedupe_redis_failed", error=str(exc), key=cache_key)

        if mem_hit or redis_hit:
            suppressed += 1
            continue
        fresh.append(alert)

    return fresh, suppressed


def _extract_store_id(alert: Dict[str, Any]) -> Optional[str]:
    labels = alert.get("labels") or {}
    candidates = [
        labels.get("store_id"),
        labels.get("store"),
        labels.get("storeId"),
        os.getenv("ALERT_DEFAULT_STORE_ID", "").strip(),
    ]
    for value in candidates:
        if value:
            return str(value)
    return None


def _to_ops_severity(severity: str) -> str:
    sev = severity.lower()
    if sev in {"critical"}:
        return "critical"
    if sev in {"error", "high"}:
        return "high"
    if sev in {"warning", "medium"}:
        return "medium"
    return "low"


async def _persist_ops_events(alerts: List[Dict[str, Any]], *, channel: str, status: str, severity: str) -> int:
    if not alerts:
        return 0
    if os.getenv("ALERT_PERSIST_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return 0

    persisted = 0
    async with get_db_session(enable_tenant_isolation=False) as session:
        for alert in alerts[:50]:
            store_id = _extract_store_id(alert)
            if not store_id:
                continue

            labels = alert.get("labels") or {}
            name = str(labels.get("alertname") or alert.get("alertname") or "unknown")
            description = _alert_line(alert)
            session.add(
                OpsEvent(
                    id=uuid.uuid4(),
                    store_id=store_id,
                    event_type=f"alertmanager_{channel}",
                    severity=_to_ops_severity(severity),
                    component=str(labels.get("service") or labels.get("job") or "monitoring"),
                    description=description,
                    raw_data={
                        "status": status,
                        "channel": channel,
                        "alertname": name,
                        "labels": labels,
                        "annotations": alert.get("annotations") or {},
                    },
                    status=OpsEventStatus.OPEN.value,
                    created_at=datetime.now(timezone.utc),
                )
            )
            persisted += 1
    return persisted


async def _handle_alert_payload(
    payload: Any,
    *,
    channel: str,
    forced_severity: Optional[str] = None,
) -> Dict[str, Any]:
    alerts, status = _extract_alerts(payload)
    deduped_alerts, suppressed = await _filter_deduplicated_alerts(alerts, channel=channel, status=status)
    severity = (forced_severity or _pick_severity(deduped_alerts or alerts, "warning")).lower()

    logger.info(
        "alertmanager_webhook_received",
        channel=channel,
        status=status,
        severity=severity,
        alert_count=len(alerts),
        deduped_count=len(deduped_alerts),
        suppressed=suppressed,
    )

    recipients = _collect_recipients()
    forwarded = False
    send_result: Dict[str, Any] = {"success": False, "reason": "no_recipients"}

    if recipients and deduped_alerts:
        lines = [_alert_line(a) for a in deduped_alerts[:5]]
        extra = max(0, len(deduped_alerts) - 5)
        if extra:
            lines.append(f"- ... and {extra} more alerts")

        title = f"AlertManager {channel} [{severity.upper()}]"
        message = (
            f"status={status}\n"
            f"alerts={len(deduped_alerts)}\n"
            f"suppressed={suppressed}\n\n"
            + "\n".join(lines)
        )
        send_result = await wechat_alert_service.send_system_alert(
            alert_type=f"alertmanager_{channel}",
            title=title,
            message=message,
            severity=severity,
            recipient_ids=recipients,
        )
        forwarded = bool(send_result.get("success"))

    persisted = 0
    persist_error: Optional[str] = None
    try:
        persisted = await _persist_ops_events(
            deduped_alerts,
            channel=channel,
            status=status,
            severity=severity,
        )
    except Exception as exc:  # noqa: BLE001
        persist_error = str(exc)
        logger.error(
            "alertmanager_persist_ops_event_failed",
            channel=channel,
            error=persist_error,
        )

    return {
        "ok": True,
        "channel": channel,
        "status": status,
        "severity": severity,
        "received": len(alerts),
        "deduped": len(deduped_alerts),
        "suppressed": suppressed,
        "persisted": persisted,
        "persist_error": persist_error,
        "forwarded": forwarded,
        "recipients": len(recipients),
        "send_result": send_result,
    }


@router.get("/health")
async def alerts_health() -> Dict[str, Any]:
    return {"status": "ok", "service": "alert_webhook"}


@router.post("/webhook")
async def alertmanager_webhook(
    request: Request,
    x_alert_token: Optional[str] = Header(default=None, alias="X-Alert-Token"),
) -> Dict[str, Any]:
    _require_webhook_token(x_alert_token)
    payload = await request.json()
    return await _handle_alert_payload(payload, channel="default")


@router.post("/critical")
async def alertmanager_critical(
    request: Request,
    x_alert_token: Optional[str] = Header(default=None, alias="X-Alert-Token"),
) -> Dict[str, Any]:
    _require_webhook_token(x_alert_token)
    payload = await request.json()
    return await _handle_alert_payload(payload, channel="critical", forced_severity="critical")


@router.post("/warning")
async def alertmanager_warning(
    request: Request,
    x_alert_token: Optional[str] = Header(default=None, alias="X-Alert-Token"),
) -> Dict[str, Any]:
    _require_webhook_token(x_alert_token)
    payload = await request.json()
    return await _handle_alert_payload(payload, channel="warning", forced_severity="warning")
