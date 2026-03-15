from src.api.hardware_integration import _build_commissioning_summary


def test_build_commissioning_summary_marks_ready_when_edge_and_shokz_are_healthy(monkeypatch):
    monkeypatch.setenv(
        "SHOKZ_TARGET_MACS",
        "A0:0C:E2:8C:E3:C2,A0:0C:E2:9E:2D:58",
    )

    commissioning = _build_commissioning_summary(
        nodes=[
            {
                "node_id": "edge_CZYZ-2461_01",
                "status": "online",
                "credential_ok": True,
                "pending_status_queue": 0,
            }
        ],
        devices=[
            {
                "device_id": "shokz_01",
                "status": "connected",
                "mac_address": "a0:0c:e2:8c:e3:c2",
            },
            {
                "device_id": "shokz_02",
                "status": "connected",
                "mac_address": "A0:0C:E2:9E:2D:58",
            },
        ],
    )

    assert commissioning["ready"] is True
    assert commissioning["missing_target_macs"] == []
    assert commissioning["summary"]["target_macs_registered"] == 2
    assert all(item["passed"] for item in commissioning["checklist"])


def test_build_commissioning_summary_reports_missing_targets_and_backlog(monkeypatch):
    monkeypatch.setenv(
        "SHOKZ_TARGET_MACS",
        "A0:0C:E2:8C:E3:C2,A0:0C:E2:9E:2D:58",
    )

    commissioning = _build_commissioning_summary(
        nodes=[
            {
                "node_id": "edge_CZYZ-2461_01",
                "status": "offline",
                "credential_ok": False,
                "pending_status_queue": 3,
            }
        ],
        devices=[
            {
                "device_id": "shokz_01",
                "status": "low_battery",
                "mac_address": "A0:0C:E2:8C:E3:C2",
            }
        ],
    )

    assert commissioning["ready"] is False
    assert commissioning["missing_target_macs"] == ["A0:0C:E2:9E:2D:58"]

    checklist = {item["key"]: item for item in commissioning["checklist"]}
    assert checklist["edge_online"]["passed"] is False
    assert checklist["credential_ready"]["passed"] is False
    assert checklist["queue_clean"]["passed"] is False
    assert checklist["headset_connected"]["passed"] is False
    assert checklist["headset_battery"]["passed"] is False
    assert checklist["target_mac_registered"]["passed"] is False
