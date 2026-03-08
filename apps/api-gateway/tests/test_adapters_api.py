import pytest

from fastapi import HTTPException

from src.api.adapters import (
    DishSyncRequest,
    OrderSyncRequest,
    integration_service,
    sync_all,
    sync_dishes,
    sync_order,
)


@pytest.mark.asyncio
async def test_sync_order_supports_pinzhi(monkeypatch):
    async def _mock_sync(order_id: str, store_id: str):
        return {"status": "success", "order": {"order_id": order_id, "store_id": store_id}}

    monkeypatch.setattr(integration_service, "sync_order_from_pinzhi", _mock_sync)

    result = await sync_order(
        OrderSyncRequest(order_id="B001", store_id="STORE001", source_system="pinzhi")
    )

    assert result.status == "success"
    assert result.data["order"]["order_id"] == "B001"


@pytest.mark.asyncio
async def test_sync_order_unsupported_source_returns_400():
    with pytest.raises(HTTPException) as exc:
        await sync_order(
            OrderSyncRequest(order_id="X", store_id="STORE001", source_system="unknown")
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_sync_dishes_supports_pinzhi(monkeypatch):
    async def _mock_sync(store_id: str):
        return {"status": "success", "synced_count": 3, "store_id": store_id}

    monkeypatch.setattr(integration_service, "sync_dishes_from_pinzhi", _mock_sync)

    result = await sync_dishes(DishSyncRequest(store_id="STORE001", source_system="pinzhi"))

    assert result.status == "success"
    assert result.data["synced_count"] == 3


@pytest.mark.asyncio
async def test_sync_all_supports_pinzhi(monkeypatch):
    async def _mock_sync_all(store_id: str):
        return {"status": "success", "results": {"dishes": {"synced_count": 2}}, "store_id": store_id}

    monkeypatch.setattr(integration_service, "sync_all_from_pinzhi", _mock_sync_all)

    result = await sync_all("pinzhi", "STORE001")

    assert result.status == "success"
    assert result.data["results"]["dishes"]["synced_count"] == 2
