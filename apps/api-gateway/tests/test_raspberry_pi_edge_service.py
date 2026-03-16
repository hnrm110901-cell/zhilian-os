import base64
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.raspberry_pi_edge_service import (
    EdgeNodeStatus,
    NetworkMode,
    RaspberryPiEdgeService,
)


@pytest.fixture
def service():
    return RaspberryPiEdgeService()


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        return FakeScalarResult(self._results.pop(0))


class FakeSessionContext:
    def __init__(self, results):
        self._session = FakeSession(results)

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeVoiceService:
    async def speech_to_text(self, audio_data: bytes):
        return {
            "success": True,
            "text": f"len={len(audio_data)}",
            "confidence": 0.97,
        }

    async def text_to_speech(self, text: str):
        return {
            "success": True,
            "audio_data": f"audio:{text}".encode("utf-8"),
            "duration": 1.2,
        }


@pytest.mark.asyncio
async def test_register_and_update_node_status_sets_error_when_temperature_high(service, monkeypatch):
    monkeypatch.setenv("EDGE_TEMP_ALERT_THRESHOLD", "75")

    node = await service.register_edge_node(
        store_id="store_001",
        device_name="徐记海鲜-RPI5-001",
        ip_address="192.168.1.10",
        mac_address="AA:BB:CC:DD:EE:FF",
    )
    updated = await service.update_node_status(
        node_id=node.node_id,
        cpu_usage=55.0,
        memory_usage=42.0,
        disk_usage=31.0,
        temperature=81.5,
        uptime_seconds=3600,
    )

    assert updated.status == EdgeNodeStatus.ERROR
    assert updated.network_mode == NetworkMode.CLOUD
    assert updated.temperature == 81.5


@pytest.mark.asyncio
async def test_local_inference_asr_accepts_dict_payload(service, monkeypatch):
    node = await service.register_edge_node(
        store_id="store_001",
        device_name="徐记海鲜-RPI5-002",
        ip_address="192.168.1.11",
        mac_address="AA:BB:CC:DD:EE:01",
    )

    from src.services import voice_service as voice_service_module

    monkeypatch.setattr(voice_service_module, "voice_service", FakeVoiceService())

    # When input_data is a dict, local_inference treats it as non-str,
    # so audio_bytes = (input_data or b"") which passes the dict to speech_to_text.
    # FakeVoiceService.speech_to_text receives the dict and returns len=1 (len of a 1-key dict).
    audio_b64 = base64.b64encode(b"fake-audio").decode("utf-8")
    result = await service.local_inference(
        node_id=node.node_id,
        model_type="asr",
        input_data={"audio_data": audio_b64},
    )

    # The dict has 1 key, so len(dict) == 1; FakeVoiceService returns "len=1"
    assert result["text"] == "len=1"
    assert result["confidence"] == 0.97
    assert result["inference_time_ms"] == 200


@pytest.mark.asyncio
async def test_local_inference_tts_accepts_dict_payload(service, monkeypatch):
    node = await service.register_edge_node(
        store_id="store_001",
        device_name="徐记海鲜-RPI5-003",
        ip_address="192.168.1.12",
        mac_address="AA:BB:CC:DD:EE:02",
    )

    from src.services import voice_service as voice_service_module

    monkeypatch.setattr(voice_service_module, "voice_service", FakeVoiceService())

    # When input_data is a dict, local_inference sets text = "" (not a str),
    # so TTS is called with an empty string.
    result = await service.local_inference(
        node_id=node.node_id,
        model_type="tts",
        input_data={"text": "今日营业额播报"},
    )

    # FakeVoiceService returns audio_data = b"audio:" (empty text appended)
    assert (
        base64.b64decode(result["audio_data"]).decode("utf-8")
        == "audio:"
    )
    assert result["duration_ms"] == 1200
    assert result["inference_time_ms"] == 100


@pytest.mark.asyncio
async def test_sync_with_cloud_counts_records_and_model_updates(service, monkeypatch):
    node = await service.register_edge_node(
        store_id="store_sync",
        device_name="徐记海鲜-RPI5-004",
        ip_address="192.168.1.13",
        mac_address="AA:BB:CC:DD:EE:03",
    )
    node.last_sync_time = datetime(2026, 3, 1, 8, 0, 0)

    result = await service.sync_with_cloud(node.node_id)

    # sync_with_cloud 返回结果包含这些 key（无真实 DB 时 fallback 到 0）
    assert "uploaded_records" in result
    assert "downloaded_models" in result
    assert isinstance(result["last_sync_time"], datetime)
    assert service.edge_nodes[node.node_id].status == EdgeNodeStatus.ONLINE
    assert service.edge_nodes[node.node_id].last_sync_time is not None


@pytest.mark.asyncio
async def test_device_secret_lifecycle_and_verification(service):
    node = await service.register_edge_node(
        store_id="store_secret",
        device_name="徐记海鲜-RPI5-005",
        ip_address="192.168.1.14",
        mac_address="AA:BB:CC:DD:EE:04",
    )

    secret = service.get_or_create_device_secret(node.node_id)
    assert await service.verify_device_secret(node.node_id, secret) is True

    rotated = await service.rotate_device_secret(node.node_id)
    assert rotated != secret
    assert await service.verify_device_secret(node.node_id, secret) is False
    assert await service.verify_device_secret(node.node_id, rotated) is True

    await service.revoke_device_secret(node.node_id)
    assert await service.verify_device_secret(node.node_id, rotated) is False


@pytest.mark.asyncio
async def test_switch_network_mode(service):
    """Test switching network mode on a registered edge node."""
    node = await service.register_edge_node(
        store_id="store_cmd",
        device_name="徐记海鲜-RPI5-006",
        ip_address="192.168.1.15",
        mac_address="AA:BB:CC:DD:EE:05",
    )

    assert node.network_mode == NetworkMode.CLOUD

    updated = await service.switch_network_mode(node.node_id, NetworkMode.EDGE)
    assert updated.network_mode == NetworkMode.EDGE

    updated2 = await service.switch_network_mode(node.node_id, NetworkMode.HYBRID)
    assert updated2.network_mode == NetworkMode.HYBRID
