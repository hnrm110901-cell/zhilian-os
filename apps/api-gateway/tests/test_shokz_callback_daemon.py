import importlib.util
from pathlib import Path

import pytest


SHOKZ_DAEMON_PATH = Path(__file__).resolve().parents[1] / "edge" / "shokz_callback_daemon.py"
SHOKZ_DAEMON_SPEC = importlib.util.spec_from_file_location("shokz_callback_daemon", SHOKZ_DAEMON_PATH)
assert SHOKZ_DAEMON_SPEC and SHOKZ_DAEMON_SPEC.loader
shokz_callback_daemon = importlib.util.module_from_spec(SHOKZ_DAEMON_SPEC)
SHOKZ_DAEMON_SPEC.loader.exec_module(shokz_callback_daemon)

ShokzCallbackConfig = shokz_callback_daemon.ShokzCallbackConfig
ShokzCommandProcessor = shokz_callback_daemon.ShokzCommandProcessor


def _build_processor(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGE_STATE_DIR", str(tmp_path))
    return ShokzCommandProcessor(ShokzCallbackConfig())


def test_shokz_processor_updates_connection_and_history(monkeypatch, tmp_path):
    processor = _build_processor(monkeypatch, tmp_path)

    connect_result = processor.handle(
        "connect_device",
        {
            "device_id": "shokz_001",
            "store_id": "STORE001",
            "edge_node_id": "edge_001",
            "payload": {},
        },
    )
    voice_result = processor.handle(
        "voice_output",
        {
            "device_id": "shokz_001",
            "store_id": "STORE001",
            "edge_node_id": "edge_001",
            "payload": {"text": "3号桌催单", "priority": "high"},
        },
    )

    assert connect_result["device_state"]["connected"] is True
    assert voice_result["device_state"]["last_text"] == "3号桌催单"
    assert voice_result["device_state"]["last_priority"] == "high"
    assert voice_result["history_size"] == 2
    assert (tmp_path / "shokz_state.json").exists()


def test_shokz_processor_rejects_voice_output_for_disconnected_device(monkeypatch, tmp_path):
    processor = _build_processor(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="device not connected"):
        processor.handle(
            "voice_output",
            {
                "device_id": "shokz_002",
                "store_id": "STORE001",
                "edge_node_id": "edge_001",
                "payload": {"text": "请安抚客户"},
            },
        )


def test_shokz_callback_config_accepts_legacy_env_names(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGE_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("EDGE_SHOKZ_CALLBACK_PORT", raising=False)
    monkeypatch.delenv("EDGE_SHOKZ_CALLBACK_SECRET", raising=False)
    monkeypatch.setenv("SHOKZ_CALLBACK_PORT", "9798")
    monkeypatch.setenv("SHOKZ_CALLBACK_SECRET", "legacy-callback-secret")

    config = ShokzCallbackConfig()

    assert config.port == 9798
    assert config.secret == "legacy-callback-secret"
