import importlib.util
from pathlib import Path


EDGE_AGENT_PATH = Path(__file__).resolve().parents[1] / "edge" / "edge_node_agent.py"
EDGE_AGENT_SPEC = importlib.util.spec_from_file_location("edge_node_agent", EDGE_AGENT_PATH)
assert EDGE_AGENT_SPEC and EDGE_AGENT_SPEC.loader
edge_node_agent = importlib.util.module_from_spec(EDGE_AGENT_SPEC)
EDGE_AGENT_SPEC.loader.exec_module(edge_node_agent)

EdgeAgentConfig = edge_node_agent.EdgeAgentConfig
EdgeNodeAgent = edge_node_agent.EdgeNodeAgent


def _configure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGE_API_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("EDGE_API_TOKEN", "bootstrap-token")
    monkeypatch.setenv("EDGE_STORE_ID", "STORE001")
    monkeypatch.setenv("EDGE_DEVICE_NAME", "store001-rpi5")
    monkeypatch.setenv("EDGE_STATE_DIR", str(tmp_path))


def test_post_status_payload_re_registers_after_device_secret_rejection(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    agent = EdgeNodeAgent(EdgeAgentConfig())
    agent.node_id = "edge_old"
    agent.device_secret = "expired-secret"
    agent._save_state()

    calls = []
    saved_states = []

    def fake_save_state():
        saved_states.append((agent.node_id, agent.device_secret))

    def fake_register():
        agent.node_id = "edge_new"
        agent.device_secret = "fresh-secret"
        return "edge_new"

    def fake_request(method, path, params=None, use_device_secret=True, json_body=None):
        calls.append((method, path, params, json_body))
        if path == "/api/v1/hardware/edge-node/edge_old/status":
            raise RuntimeError("POST /api/v1/hardware/edge-node/edge_old/status failed: 401 forbidden")
        return {"success": True}

    monkeypatch.setattr(agent, "_save_state", fake_save_state)
    monkeypatch.setattr(agent, "register", fake_register)
    monkeypatch.setattr(agent, "_request", fake_request)

    agent._post_status_payload({"cpu_usage": 10})

    assert saved_states == [(None, None)]
    assert calls[-1][1] == "/api/v1/hardware/edge-node/edge_new/status"
    assert agent.node_id == "edge_new"
    assert agent.device_secret == "fresh-secret"


def test_process_command_queue_acknowledges_completed_and_failed_commands(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    agent = EdgeNodeAgent(EdgeAgentConfig())
    agent.node_id = "edge_store001"
    agent.device_secret = "device-secret"

    ack_bodies = []
    commands = [
        {
            "command_id": "cmd_success",
            "command_type": "voice_output",
            "payload": {"device_id": "shokz_001", "text": "请处理催单"},
        },
        {
            "command_id": "cmd_failed",
            "command_type": "disconnect_device",
            "payload": {"device_id": "shokz_002"},
        },
    ]

    def fake_request(method, path, params=None, use_device_secret=True, json_body=None):
        if method == "GET":
            return {"commands": commands}
        ack_bodies.append((path, json_body))
        return {"success": True}

    def fake_execute(command):
        if command["command_id"] == "cmd_failed":
            raise RuntimeError("bluetooth unavailable")
        return {"success": True, "action": command["command_type"]}

    monkeypatch.setattr(agent, "_request", fake_request)
    monkeypatch.setattr(agent, "_execute_edge_command", fake_execute)

    completed = agent.process_command_queue()

    assert completed == 1
    assert ack_bodies == [
        (
            "/api/v1/hardware/edge-node/edge_store001/commands/cmd_success/ack",
            {"status": "completed", "result": {"success": True, "action": "voice_output"}},
        ),
        (
            "/api/v1/hardware/edge-node/edge_store001/commands/cmd_failed/ack",
            {"status": "failed", "last_error": "bluetooth unavailable"},
        ),
    ]


def test_config_accepts_legacy_shokz_env_names(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.delenv("EDGE_SHOKZ_CALLBACK_PORT", raising=False)
    monkeypatch.delenv("EDGE_SHOKZ_CALLBACK_SECRET", raising=False)
    monkeypatch.setenv("SHOKZ_CALLBACK_PORT", "9799")
    monkeypatch.setenv("SHOKZ_CALLBACK_SECRET", "legacy-secret")

    config = EdgeAgentConfig()

    assert config.shokz_callback_port == 9799
    assert config.shokz_callback_secret == "legacy-secret"
