from unittest.mock import AsyncMock, patch

import pytest

from src.services.shokz_device_service import (
    DeviceStatus,
    ShokzDeviceModel,
    ShokzDeviceService,
)


@pytest.mark.asyncio
async def test_connect_device_calls_edge_callback_when_configured():
    service = ShokzDeviceService()
    device = await service.register_device(
        device_name="店长耳机",
        device_model=ShokzDeviceModel.OPENCOMM2_UC,
        mac_address="00:11:22:33:44:55",
        store_id="STORE001",
        user_id="u1",
        user_role="manager",
        edge_node_id="edge-1",
    )

    with patch.object(service, "_notify_edge_callback", AsyncMock(return_value={"success": True})) as mock_notify:
        result = await service.connect_device(device.device_id)

    assert result.status == DeviceStatus.CONNECTED
    mock_notify.assert_awaited_once()
    assert mock_notify.await_args.args[0] == "connect_device"


@pytest.mark.asyncio
async def test_voice_output_returns_edge_callback_payload():
    service = ShokzDeviceService()
    device = await service.register_device(
        device_name="店长耳机",
        device_model=ShokzDeviceModel.OPENCOMM2_UC,
        mac_address="00:11:22:33:44:55",
        store_id="STORE001",
        user_id="u1",
        user_role="manager",
        edge_node_id="edge-1",
    )

    with patch.object(service, "_notify_edge_callback", AsyncMock(return_value={"success": True})):
        with patch("src.services.voice_service.voice_service.text_to_speech", AsyncMock(return_value={"success": True, "audio_data": b"hello"})):
            await service.connect_device(device.device_id)
            result = await service.voice_output(device.device_id, "测试播报", priority="high")

    assert result["success"] is True
    assert result["edge_callback"]["success"] is True
    assert result["priority"] == "high"
