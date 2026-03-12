import json

import pytest

from edge.shokz_callback_daemon import ShokzCallbackConfig, ShokzCommandProcessor


def test_shokz_callback_processor_connect_and_voice_output(tmp_path):
    config = ShokzCallbackConfig()
    config.state_dir = tmp_path
    config.state_file = tmp_path / "shokz_state.json"
    processor = ShokzCommandProcessor(config)

    connect = processor.handle(
        "connect_device",
        {
            "action": "connect_device",
            "device_id": "shokz-device-1",
            "store_id": "STORE001",
            "edge_node_id": "edge-1",
            "payload": {},
        },
    )
    assert connect["success"] is True
    assert connect["device_state"]["connected"] is True

    voice = processor.handle(
        "voice_output",
        {
            "action": "voice_output",
            "device_id": "shokz-device-1",
            "store_id": "STORE001",
            "edge_node_id": "edge-1",
            "payload": {"text": "催菜提醒", "priority": "high"},
        },
    )
    assert voice["success"] is True
    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["devices"]["shokz-device-1"]["last_text"] == "催菜提醒"
    assert len(state["history"]) == 2


def test_shokz_callback_processor_rejects_voice_output_when_disconnected(tmp_path):
    config = ShokzCallbackConfig()
    config.state_dir = tmp_path
    config.state_file = tmp_path / "shokz_state.json"
    processor = ShokzCommandProcessor(config)

    with pytest.raises(ValueError, match="device not connected"):
        processor.handle(
            "voice_output",
            {
                "action": "voice_output",
                "device_id": "shokz-device-2",
                "payload": {"text": "测试"},
            },
        )
