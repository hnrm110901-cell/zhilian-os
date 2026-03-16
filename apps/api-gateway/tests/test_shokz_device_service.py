import pytest

from src.services.raspberry_pi_edge_service import get_raspberry_pi_edge_service
from src.services.shokz_device_service import (
    DeviceStatus,
    ShokzDeviceModel,
    get_shokz_device_service,
)


@pytest.mark.asyncio
async def test_shokz_dispatch_falls_back_when_no_callback_url(monkeypatch):
    """When EDGE_SHOKZ_CALLBACK_URL is not set, voice_output succeeds with
    edge_callback reporting not_configured (no command queue fallback)."""
    edge_service = get_raspberry_pi_edge_service()
    edge_service.edge_nodes.clear()
    edge_service.device_secrets.clear()

    shokz_service = get_shokz_device_service()
    shokz_service.devices.clear()
    shokz_service.interactions.clear()

    monkeypatch.delenv("EDGE_SHOKZ_CALLBACK_URL", raising=False)

    node = await edge_service.register_edge_node(
        store_id="store_hw",
        device_name="文化园门店-RPI5-001",
        ip_address="192.168.110.96",
        mac_address="AA:BB:CC:11:22:33",
    )
    device = await shokz_service.register_device(
        device_name="店长-Shokz",
        device_model=ShokzDeviceModel.OPENCOMM2_UC,
        mac_address="00:11:22:33:44:55",
        store_id="store_hw",
        user_id="manager_001",
        user_role="manager",
        edge_node_id=node.node_id,
    )

    # connect_device calls _notify_edge_callback which returns None when URL is empty
    await shokz_service.connect_device(device.device_id)
    assert shokz_service.devices[device.device_id].status == DeviceStatus.CONNECTED

    result = await shokz_service.voice_output(
        device_id=device.device_id,
        text="3号桌需要尽快处理",
        priority="high",
    )

    assert result["success"] is True
    assert result["text"] == "3号桌需要尽快处理"
    # When no callback URL is configured, edge_callback reports not_configured
    assert result["edge_callback"]["success"] is False
    assert result["edge_callback"]["message"] == "not_configured"
