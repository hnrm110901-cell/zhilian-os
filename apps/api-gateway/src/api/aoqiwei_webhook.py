"""
奥琦玮 POS 实时 Webhook 推送接收端点

路由前缀: /api/v1/webhooks/aoqiwei
接收奥琦玮 POS 系统的实时事件推送（订单/会员/库存/菜品变更），
验证签名后写入事件总线，触发影子同步。

签名验证方式：MD5(body + secret) 或 HMAC-SHA256(secret, body)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from ..services.webhook_event_bus import webhook_event_bus

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/webhooks/aoqiwei",
    tags=["aoqiwei-webhook"],
)

# 签名密钥，从环境变量读取
_WEBHOOK_SECRET = os.getenv("AOQIWEI_WEBHOOK_SECRET", "")

# 签名验证模式：md5 或 hmac-sha256
_SIGN_MODE = os.getenv("AOQIWEI_WEBHOOK_SIGN_MODE", "md5")


# ── 签名验证 ──────────────────────────────────────────────────────────────────

def _verify_signature(
    body: bytes,
    signature: Optional[str],
    secret: str,
    sign_mode: str = "md5",
) -> bool:
    """
    验证 Webhook 请求签名

    支持两种模式：
    - md5: MD5(body + secret)
    - hmac-sha256: HMAC-SHA256(secret, body)

    如果未配置密钥（空字符串），跳过验证（开发环境）。
    """
    if not secret:
        # 未配置密钥，跳过验证（仅限开发环境）
        return True

    if not signature:
        return False

    if sign_mode == "hmac-sha256":
        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    else:
        # 默认 MD5 模式
        expected = hashlib.md5(body + secret.encode("utf-8")).hexdigest()

    return hmac.compare_digest(expected, signature)


# ── 通用 Webhook 处理逻辑 ────────────────────────────────────────────────────

async def _handle_webhook(
    request: Request,
    event_type: str,
    x_aoqiwei_signature: Optional[str] = None,
) -> Dict[str, Any]:
    """
    通用 Webhook 处理流程：
    1. 读取请求体
    2. 验证签名
    3. 解析 JSON
    4. 幂等检查 + 事件发布
    5. 触发影子同步
    """
    # 1. 读取原始请求体
    body = await request.body()

    # 2. 签名验证
    if not _verify_signature(body, x_aoqiwei_signature, _WEBHOOK_SECRET, _SIGN_MODE):
        logger.warning(
            "奥琦玮Webhook签名验证失败",
            event_type=event_type,
            remote=request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=401, detail="签名验证失败")

    # 3. 解析 JSON
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体非有效JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体必须是JSON对象")

    # 4. 提取 event_id（幂等键），未提供则自动生成
    event_id = str(payload.get("event_id") or payload.get("id") or uuid.uuid4())

    # 发布到事件总线（内含去重逻辑）
    result = await webhook_event_bus.publish(
        event_type=event_type,
        event_id=event_id,
        payload=payload,
        source="aoqiwei",
    )

    # 5. 触发影子同步（异步，不阻塞响应）
    if result["accepted"] and not result["duplicate"]:
        await _trigger_shadow_sync(event_type, payload)

    logger.info(
        "奥琦玮Webhook已处理",
        event_type=event_type,
        event_id=event_id,
        accepted=result["accepted"],
        duplicate=result["duplicate"],
    )

    return {"code": 0, "msg": "success"}


async def _trigger_shadow_sync(
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """
    触发影子同步

    尝试调用 shadow_sync_service，如果服务不可用则跳过（降级）。
    """
    try:
        from ..services.shadow_sync_service import shadow_sync_service
        await shadow_sync_service.sync_event(
            source="aoqiwei",
            event_type=event_type,
            payload=payload,
        )
    except ImportError:
        logger.debug("shadow_sync_service 未加载，跳过影子同步")
    except Exception as exc:
        # 影子同步失败不阻塞主流程
        logger.warning(
            "影子同步失败",
            event_type=event_type,
            error=str(exc),
        )


# ── 路由端点 ──────────────────────────────────────────────────────────────────

@router.post("/order/created")
async def order_created(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """新订单推送"""
    return await _handle_webhook(request, "order.created", x_aoqiwei_signature)


@router.post("/order/updated")
async def order_updated(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """订单变更推送"""
    return await _handle_webhook(request, "order.updated", x_aoqiwei_signature)


@router.post("/order/settled")
async def order_settled(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """结账推送"""
    return await _handle_webhook(request, "order.settled", x_aoqiwei_signature)


@router.post("/order/refunded")
async def order_refunded(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """退单推送"""
    return await _handle_webhook(request, "order.refunded", x_aoqiwei_signature)


@router.post("/member/updated")
async def member_updated(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """会员变更推送"""
    return await _handle_webhook(request, "member.updated", x_aoqiwei_signature)


@router.post("/inventory/changed")
async def inventory_changed(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """库存变更推送"""
    return await _handle_webhook(request, "inventory.changed", x_aoqiwei_signature)


@router.post("/dish/updated")
async def dish_updated(
    request: Request,
    x_aoqiwei_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """菜品变更推送"""
    return await _handle_webhook(request, "dish.updated", x_aoqiwei_signature)
