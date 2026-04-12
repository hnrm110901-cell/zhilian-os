"""
奥琦玮 Webhook + 事件总线测试

覆盖：签名验证、幂等去重、7个端点路由、事件总线分发、重试机制、死信队列
"""

import os
import sys
import hashlib
import hmac as hmac_mod
import json
import uuid

# L002: 测试前设置环境变量
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AOQIWEI_WEBHOOK_SECRET", "")
os.environ.setdefault("AOQIWEI_WEBHOOK_SIGN_MODE", "md5")

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.services.webhook_event_bus import WebhookEventBus, _MAX_RETRIES


# ── 事件总线测试 ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def bus():
    """每个测试用新的事件总线实例"""
    return WebhookEventBus()


@pytest.mark.asyncio
async def test_event_bus_publish_and_dispatch(bus: WebhookEventBus):
    """发布事件，处理器被调用"""
    received = []

    async def handler(event):
        received.append(event)

    bus.register("order.created", handler)
    result = await bus.publish("order.created", event_id="E001", payload={"order_id": "O1"})

    assert result["accepted"] is True
    assert result["duplicate"] is False
    assert result["handlers_count"] == 1

    # 等待异步 task 完成
    await asyncio.sleep(0.1)
    assert len(received) == 1
    assert received[0]["payload"]["order_id"] == "O1"


@pytest.mark.asyncio
async def test_event_bus_dedup(bus: WebhookEventBus):
    """相同 event_id 第二次发布被去重"""
    handler = AsyncMock()
    bus.register("order.created", handler)

    await bus.publish("order.created", event_id="E002", payload={})
    result2 = await bus.publish("order.created", event_id="E002", payload={})

    assert result2["accepted"] is False
    assert result2["duplicate"] is True


@pytest.mark.asyncio
async def test_event_bus_no_handler(bus: WebhookEventBus):
    """无处理器时事件仍被接受"""
    result = await bus.publish("unknown.type", event_id="E003", payload={})
    assert result["accepted"] is True
    assert result["handlers_count"] == 0


@pytest.mark.asyncio
async def test_event_bus_multiple_handlers(bus: WebhookEventBus):
    """同一事件类型多个处理器都被调用"""
    calls = {"a": 0, "b": 0}

    async def handler_a(event):
        calls["a"] += 1

    async def handler_b(event):
        calls["b"] += 1

    bus.register("order.settled", handler_a)
    bus.register("order.settled", handler_b)

    result = await bus.publish("order.settled", event_id="E004", payload={})
    assert result["handlers_count"] == 2

    await asyncio.sleep(0.1)
    assert calls["a"] == 1
    assert calls["b"] == 1


@pytest.mark.asyncio
async def test_event_bus_retry_on_failure(bus: WebhookEventBus):
    """处理器失败后自动重试"""
    call_count = 0

    async def flaky_handler(event):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("模拟失败")

    bus.register("order.created", flaky_handler)
    await bus.publish("order.created", event_id="E005", payload={})

    # 等待重试完成（退避：1s + 2s + ... 实际在测试中较快）
    await asyncio.sleep(5)
    assert call_count >= 3  # 至少重试到成功


@pytest.mark.asyncio
async def test_event_bus_dead_letter(bus: WebhookEventBus):
    """超过重试次数进入死信队列"""
    async def always_fail(event):
        raise RuntimeError("永远失败")

    bus.register("order.created", always_fail)
    await bus.publish("order.created", event_id="E006", payload={"test": True})

    # 等待所有重试完成（1 + 2 + 4 = 7秒，加余量）
    await asyncio.sleep(10)

    dead = bus.get_dead_letters()
    assert len(dead) == 1
    assert dead[0]["handler"] == "always_fail"
    assert dead[0]["retries"] == _MAX_RETRIES


@pytest.mark.asyncio
async def test_event_bus_stats(bus: WebhookEventBus):
    """统计信息正确"""
    handler = AsyncMock()
    bus.register("test.event", handler)

    await bus.publish("test.event", event_id="S1", payload={})
    await bus.publish("test.event", event_id="S1", payload={})  # 重复
    await bus.publish("test.event", event_id="S2", payload={})

    stats = bus.get_stats()
    assert stats["published"] == 2
    assert stats["duplicates"] == 1


@pytest.mark.asyncio
async def test_event_bus_unregister(bus: WebhookEventBus):
    """注销处理器后不再收到事件"""
    handler = AsyncMock()
    bus.register("test.event", handler)
    assert bus.unregister("test.event", handler) is True

    await bus.publish("test.event", event_id="U1", payload={})
    await asyncio.sleep(0.1)
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_event_bus_clear_dead_letters(bus: WebhookEventBus):
    """清空死信队列"""
    bus._dead_letter.append({"test": True})
    assert bus.clear_dead_letters() == 1
    assert len(bus.get_dead_letters()) == 0


# ── 签名验证测试 ──────────────────────────────────────────────────────────────

def test_verify_signature_md5():
    """MD5 签名验证"""
    from src.api.aoqiwei_webhook import _verify_signature

    body = b'{"order_id": "O001"}'
    secret = "test-secret"
    expected = hashlib.md5(body + secret.encode()).hexdigest()

    assert _verify_signature(body, expected, secret, "md5") is True
    assert _verify_signature(body, "wrong-sig", secret, "md5") is False


def test_verify_signature_hmac_sha256():
    """HMAC-SHA256 签名验证"""
    from src.api.aoqiwei_webhook import _verify_signature

    body = b'{"member_id": "M001"}'
    secret = "hmac-secret"
    expected = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert _verify_signature(body, expected, secret, "hmac-sha256") is True
    assert _verify_signature(body, "bad", secret, "hmac-sha256") is False


def test_verify_signature_no_secret():
    """未配置密钥时跳过验证"""
    from src.api.aoqiwei_webhook import _verify_signature

    assert _verify_signature(b"anything", None, "", "md5") is True


def test_verify_signature_missing_header():
    """有密钥但缺少签名头应失败"""
    from src.api.aoqiwei_webhook import _verify_signature

    assert _verify_signature(b"body", None, "some-secret", "md5") is False


# ── Webhook 端点测试（使用 FastAPI TestClient） ──────────────────────────────

@pytest.fixture
def app():
    """构建测试用 FastAPI app"""
    from fastapi import FastAPI
    from src.api.aoqiwei_webhook import router

    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    """同步 TestClient"""
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_order_created_endpoint(client):
    """POST /order/created 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "order_id": "O100", "store_id": "S001"}
    resp = client.post(
        "/api/v1/webhooks/aoqiwei/order/created",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["msg"] == "success"


def test_order_updated_endpoint(client):
    """POST /order/updated 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "status": "paid"}
    resp = client.post("/api/v1/webhooks/aoqiwei/order/updated", json=payload)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_order_settled_endpoint(client):
    """POST /order/settled 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "amount_fen": 12800}
    resp = client.post("/api/v1/webhooks/aoqiwei/order/settled", json=payload)
    assert resp.status_code == 200


def test_order_refunded_endpoint(client):
    """POST /order/refunded 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "refund_amount": 5000}
    resp = client.post("/api/v1/webhooks/aoqiwei/order/refunded", json=payload)
    assert resp.status_code == 200


def test_member_updated_endpoint(client):
    """POST /member/updated 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "member_id": "M001"}
    resp = client.post("/api/v1/webhooks/aoqiwei/member/updated", json=payload)
    assert resp.status_code == 200


def test_inventory_changed_endpoint(client):
    """POST /inventory/changed 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "item_id": "I001"}
    resp = client.post("/api/v1/webhooks/aoqiwei/inventory/changed", json=payload)
    assert resp.status_code == 200


def test_dish_updated_endpoint(client):
    """POST /dish/updated 正常响应"""
    payload = {"event_id": str(uuid.uuid4()), "dish_id": "D001"}
    resp = client.post("/api/v1/webhooks/aoqiwei/dish/updated", json=payload)
    assert resp.status_code == 200


def test_invalid_json_body(client):
    """非 JSON 请求体应返回 400"""
    resp = client.post(
        "/api/v1/webhooks/aoqiwei/order/created",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_idempotency_via_endpoint(client):
    """同一 event_id 的第二次请求仍返回 success（幂等）"""
    event_id = str(uuid.uuid4())
    payload = {"event_id": event_id, "order_id": "O200"}

    resp1 = client.post("/api/v1/webhooks/aoqiwei/order/created", json=payload)
    assert resp1.status_code == 200

    resp2 = client.post("/api/v1/webhooks/aoqiwei/order/created", json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["code"] == 0  # 幂等，不报错


def test_signature_verification_failure(client, monkeypatch):
    """配置密钥后，缺少签名应返回 401"""
    monkeypatch.setattr(
        "src.api.aoqiwei_webhook._WEBHOOK_SECRET", "real-secret"
    )
    payload = {"event_id": str(uuid.uuid4())}
    resp = client.post(
        "/api/v1/webhooks/aoqiwei/order/created",
        json=payload,
        # 不带签名头
    )
    assert resp.status_code == 401


def test_signature_verification_success(client, monkeypatch):
    """正确签名应通过验证"""
    secret = "test-webhook-secret"
    monkeypatch.setattr("src.api.aoqiwei_webhook._WEBHOOK_SECRET", secret)
    monkeypatch.setattr("src.api.aoqiwei_webhook._SIGN_MODE", "md5")

    payload = {"event_id": str(uuid.uuid4()), "data": "test"}
    body = json.dumps(payload).encode()
    sig = hashlib.md5(body + secret.encode()).hexdigest()

    resp = client.post(
        "/api/v1/webhooks/aoqiwei/order/created",
        content=body,
        headers={
            "Content-Type": "application/json",
            "x-aoqiwei-signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
