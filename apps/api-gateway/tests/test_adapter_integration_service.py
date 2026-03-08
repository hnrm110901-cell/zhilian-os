import pytest
from unittest.mock import AsyncMock

from src.services.adapter_integration_service import AdapterIntegrationService


@pytest.mark.asyncio
async def test_sync_order_from_pinzhi_success():
    svc = AdapterIntegrationService(neural_system=AsyncMock())
    pinzhi_adapter = AsyncMock()
    pinzhi_adapter.query_order_list.return_value = [
        {
            "billId": "B001",
            "billNo": "NO001",
            "billStatus": 1,
            "dishPriceTotal": 12000,
            "specialOfferPrice": 1000,
            "realPrice": 11000,
            "dishList": [{"dishId": "D1", "dishName": "鱼香肉丝", "dishPrice": 5500, "dishNum": 2}],
        }
    ]
    svc.register_adapter("pinzhi", pinzhi_adapter, {})

    result = await svc.sync_order_from_pinzhi(order_id="B001", store_id="STORE001")

    assert result["status"] == "success"
    assert result["order"]["source_system"] == "pinzhi"
    assert result["order"]["order_id"] == "B001"
    svc.neural_system.emit_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_order_from_pinzhi_not_found():
    svc = AdapterIntegrationService(neural_system=None)
    pinzhi_adapter = AsyncMock()
    pinzhi_adapter.query_order_list.return_value = []
    svc.register_adapter("pinzhi", pinzhi_adapter, {})

    with pytest.raises(ValueError, match="品智订单不存在"):
        await svc.sync_order_from_pinzhi(order_id="NOT-EXIST", store_id="STORE001")
