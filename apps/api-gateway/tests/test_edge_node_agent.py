import importlib.util
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parent.parent / "edge" / "edge_node_agent.py"
SPEC = importlib.util.spec_from_file_location("edge_node_agent", MODULE_PATH)
EDGE_NODE_AGENT = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(EDGE_NODE_AGENT)

EdgeAgentConfig = EDGE_NODE_AGENT.EdgeAgentConfig
EdgeNodeAgent = EDGE_NODE_AGENT.EdgeNodeAgent


def _build_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGE_API_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("EDGE_API_TOKEN", "bootstrap-token")
    monkeypatch.setenv("EDGE_STORE_ID", "STORE001")
    monkeypatch.setenv("EDGE_DEVICE_NAME", "store001-rpi5")
    monkeypatch.setenv("EDGE_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("EDGE_QUEUE_FLUSH_BATCH_SIZE", "10")
    return EdgeAgentConfig()


def test_update_status_queues_payload_when_network_fails(monkeypatch, tmp_path):
    config = _build_config(monkeypatch, tmp_path)
    agent = EdgeNodeAgent(config)

    register_response = {
        "node": {"node_id": "edge_STORE001_aabb"},
        "device_secret": "device-secret-1",
    }
    request_calls = []

    def fake_request(method, path, params=None, use_device_secret=True):
        request_calls.append((method, path, params, use_device_secret))
        if path == "/api/v1/hardware/edge-node/register":
            return register_response
        if path.endswith("/network-mode"):
            return {"success": True}
        if path.endswith("/status"):
            raise RuntimeError("POST /status failed: timed out")
        raise AssertionError(f"unexpected path {path}")

    with patch.object(agent, "_request", side_effect=fake_request), \
         patch.object(agent, "_collect_status", return_value={"cpu_usage": 10, "memory_usage": 20}):
        agent.update_status()

    assert agent.node_id == "edge_STORE001_aabb"
    assert agent._pending_status_count() == 1
    pending = agent._get_pending_updates(limit=10)
    assert pending[0]["payload"] == {"cpu_usage": 10, "memory_usage": 20}
    assert any(call[1].endswith("/status") for call in request_calls)


def test_update_status_flushes_queued_payloads_before_current_payload(monkeypatch, tmp_path):
    config = _build_config(monkeypatch, tmp_path)
    first_agent = EdgeNodeAgent(config)

    register_response = {
        "node": {"node_id": "edge_STORE001_flush"},
        "device_secret": "device-secret-2",
    }

    def fail_status_request(method, path, params=None, use_device_secret=True):
        if path == "/api/v1/hardware/edge-node/register":
            return register_response
        if path.endswith("/network-mode"):
            return {"success": True}
        if path.endswith("/status"):
            raise RuntimeError("POST /status failed: offline")
        raise AssertionError(f"unexpected path {path}")

    with patch.object(first_agent, "_request", side_effect=fail_status_request), \
         patch.object(first_agent, "_collect_status", return_value={"cpu_usage": 11}):
        first_agent.update_status()

    assert first_agent._pending_status_count() == 1

    second_agent = EdgeNodeAgent(config)
    sent_payloads = []

    def succeed_status_request(method, path, params=None, use_device_secret=True):
        if path.endswith("/status"):
            sent_payloads.append(params)
            return {"success": True}
        raise AssertionError(f"unexpected path {path}")

    with patch.object(second_agent, "_request", side_effect=succeed_status_request), \
         patch.object(second_agent, "_collect_status", return_value={"cpu_usage": 22}):
        second_agent.update_status()

    assert sent_payloads == [{"cpu_usage": 11}, {"cpu_usage": 22}]
    assert second_agent._pending_status_count() == 0


def test_collect_status_exposes_queue_observability(monkeypatch, tmp_path):
    config = _build_config(monkeypatch, tmp_path)
    agent = EdgeNodeAgent(config)
    agent.last_queue_error = "temporary network timeout"
    agent._enqueue_status_update({"cpu_usage": 10}, "temporary network timeout")

    with patch.object(agent, "_get_cpu_usage", return_value=1.0), \
         patch.object(agent, "_get_memory_usage", return_value=2.0), \
         patch.object(agent, "_get_disk_usage", return_value=3.0), \
         patch.object(agent, "_get_temperature", return_value=4.0), \
         patch.object(agent, "_get_uptime_seconds", return_value=5.0):
        status = agent._collect_status()

    assert status["pending_status_queue"] == 1
    assert status["last_queue_error"] == "temporary network timeout"
