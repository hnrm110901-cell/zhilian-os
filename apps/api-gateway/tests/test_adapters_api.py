import pytest

from fastapi import HTTPException

from src.api.adapters import OrderSyncRequest, sync_order, integration_service


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
