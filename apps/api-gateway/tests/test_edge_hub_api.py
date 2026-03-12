"""
Edge Hub API 测试

覆盖：
  GET  /api/v1/edge-hub/dashboard/summary        — 指标卡（总数/在线数/告警数）
  GET  /api/v1/edge-hub/nodes                    — 全局节点列表（happy + 筛选 + 空）
  GET  /api/v1/edge-hub/nodes/{hub_id}           — 节点详情（happy + 404）
  POST /api/v1/edge-hub/nodes/{hub_id}/inspect   — 触发巡检（happy + 404）
  GET  /api/v1/edge-hub/nodes/{hub_id}/metrics   — 资源趋势（happy + 404 + 点数正确）
  GET  /api/v1/edge-hub/alerts                   — 全局告警列表（分页 + 按 level/status 筛选）
  PATCH /api/v1/edge-hub/alerts/{id}/resolve     — 解决告警（happy + already-resolved + 404）
  PATCH /api/v1/edge-hub/alerts/{id}/ignore      — 忽略告警（happy + 404）
  PATCH /api/v1/edge-hub/alerts/{id}/escalate    — 升级告警（P3→P2, P2→P1, P1 保持, 404）
  GET  /api/v1/edge-hub/bindings/{store_id}      — 绑定列表（happy + 空）
  POST /api/v1/edge-hub/bindings/{store_id}      — 创建绑定（happy + 设备不存在）
  DELETE /api/v1/edge-hub/bindings/item/{id}     — 解绑（soft-delete + 404）
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_hub(
    hub_id="hub-001", store_id="S001", hub_code="HUB-S001",
    status="online", cpu_pct=45.0, mem_pct=60.0, disk_pct=30.0,
    runtime_version="1.2.3", ip_address="192.168.1.10",
    last_heartbeat=None, is_active=True, name="主机1",
):
    h = MagicMock()
    h.id              = hub_id
    h.store_id        = store_id
    h.hub_code        = hub_code
    h.name            = name
    h.status          = status
    h.runtime_version = runtime_version
    h.ip_address      = ip_address
    h.last_heartbeat  = last_heartbeat or datetime(2026, 3, 11, 10, 0, 0)
    h.cpu_pct         = cpu_pct
    h.mem_pct         = mem_pct
    h.disk_pct        = disk_pct
    h.is_active       = is_active
    return h


def _make_device(
    device_id="dev-001", hub_id="hub-001", store_id="S001",
    device_code="DEV-001", device_type="headset",
    status="online", name="耳机1", firmware_ver="2.0",
    last_seen=None,
):
    d = MagicMock()
    d.id          = device_id
    d.hub_id      = hub_id
    d.store_id    = store_id
    d.device_code = device_code
    d.device_type = device_type
    d.name        = name
    d.status      = status
    d.firmware_ver = firmware_ver
    d.last_seen   = last_seen or datetime(2026, 3, 11, 9, 0, 0)
    return d


def _make_alert(
    alert_id="alert-001", store_id="S001", hub_id="hub-001",
    level="p2", alert_type="hub_disconnect", status="open",
    message="连接断开", device_id=None,
    created_at=None, resolved_at=None,
):
    a = MagicMock()
    a.id          = alert_id
    a.store_id    = store_id
    a.hub_id      = hub_id
    a.device_id   = device_id
    a.level       = level
    a.alert_type  = alert_type
    a.message     = message
    a.status      = status
    a.resolved_at = resolved_at
    a.resolved_by = None
    a.created_at  = created_at or datetime(2026, 3, 11, 8, 0, 0)
    return a


def _make_binding(
    binding_id="bind-001", store_id="S001", device_id="dev-001",
    position="store_manager", status="active",
    employee_id="EMP001", channel=1,
    bound_at=None, unbound_at=None,
):
    b = MagicMock()
    b.id          = binding_id
    b.store_id    = store_id
    b.device_id   = device_id
    b.position    = position
    b.employee_id = employee_id
    b.channel     = channel
    b.status      = status
    b.bound_at    = bound_at or datetime(2026, 3, 1, 0, 0, 0)
    b.unbound_at  = unbound_at
    return b


def _make_db(*side_effects):
    """Build AsyncSession mock where each execute() call returns the next side_effect."""
    db = AsyncMock()
    db.add    = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    results = list(side_effects)
    call_idx = [0]

    async def execute(stmt, *args, **kwargs):
        if call_idx[0] < len(results):
            r = results[call_idx[0]]
        else:
            r = results[-1]  # repeat last
        call_idx[0] += 1
        return r

    db.execute = execute
    return db


def _scalar_one(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_all(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _all(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _mock_user(username="admin"):
    u = MagicMock()
    u.id       = "user-001"
    u.username = username
    return u


# ── dashboard_summary ─────────────────────────────────────────────────────────

class TestDashboardSummary:

    @pytest.mark.asyncio
    async def test_returns_all_kpi_cards(self):
        from src.api.edge_hub import dashboard_summary

        db = _make_db(
            _scalar_one(5),   # total_hubs
            _scalar_one(4),   # online_hubs
            _scalar_one(20),  # total_devices
            _scalar_one(18),  # online_devices
            _scalar_one(3),   # today_alerts
            _scalar_one(2),   # open_alerts
            _scalar_one(1),   # p1_alerts
        )
        result = await dashboard_summary(dateRange="today", db=db, _=_mock_user())

        assert result["code"] == 0
        cards = result["data"]["cards"]
        assert cards["totalHubCount"]   == 5
        assert cards["onlineHubCount"]  == 4
        assert cards["hubOnlineRate"]   == 80.0
        assert cards["hubStatusLevel"]  == "warning"   # 80% → warning
        assert cards["totalDeviceCount"]  == 20
        assert cards["onlineDeviceCount"] == 18
        assert cards["deviceOnlineRate"]  == 90.0
        assert cards["todayAlertCount"]   == 3
        assert cards["openAlertCount"]    == 2
        assert cards["todayP1AlertCount"] == 1

    @pytest.mark.asyncio
    async def test_zero_hubs_returns_zero_rate(self):
        from src.api.edge_hub import dashboard_summary

        db = _make_db(
            _scalar_one(0), _scalar_one(0),
            _scalar_one(0), _scalar_one(0),
            _scalar_one(0), _scalar_one(0), _scalar_one(0),
        )
        result = await dashboard_summary(dateRange="today", db=db, _=_mock_user())

        cards = result["data"]["cards"]
        assert cards["hubOnlineRate"]    == 0.0
        assert cards["deviceOnlineRate"] == 0.0

    @pytest.mark.asyncio
    async def test_full_online_rate_is_normal(self):
        from src.api.edge_hub import dashboard_summary

        db = _make_db(
            _scalar_one(10), _scalar_one(10),
            _scalar_one(50), _scalar_one(50),
            _scalar_one(0),  _scalar_one(0), _scalar_one(0),
        )
        result = await dashboard_summary(dateRange="today", db=db, _=_mock_user())

        cards = result["data"]["cards"]
        assert cards["hubOnlineRate"]  == 100.0
        assert cards["hubStatusLevel"] == "normal"


# ── list_nodes ────────────────────────────────────────────────────────────────

class TestListNodes:

    @pytest.mark.asyncio
    async def test_returns_paginated_nodes(self):
        from src.api.edge_hub import list_nodes

        hub = _make_hub()
        dev_row = MagicMock(); dev_row.hub_id = "hub-001"; dev_row.cnt = 2
        alert_row = MagicMock(); alert_row.hub_id = "hub-001"; alert_row.cnt = 1

        db = _make_db(
            _scalar_one(1),          # total count
            _scalars_all([hub]),     # hubs list
            _all([dev_row]),         # device counts
            _all([alert_row]),       # alert counts
        )
        result = await list_nodes(
            status=None, keyword=None, page=1, pageSize=20,
            db=db, _=_mock_user(),
        )

        assert result["code"] == 0
        assert result["meta"]["total"] == 1
        nodes = result["data"]["nodes"]
        assert len(nodes) == 1
        assert nodes[0]["hubCode"]        == "HUB-S001"
        assert nodes[0]["deviceCount"]    == 2
        assert nodes[0]["openAlertCount"] == 1

    @pytest.mark.asyncio
    async def test_empty_list(self):
        from src.api.edge_hub import list_nodes

        db = _make_db(
            _scalar_one(0),
            _scalars_all([]),
        )
        result = await list_nodes(
            status=None, keyword=None, page=1, pageSize=20,
            db=db, _=_mock_user(),
        )

        assert result["data"]["nodes"] == []
        assert result["meta"]["total"] == 0
        assert result["meta"]["hasMore"] is False

    @pytest.mark.asyncio
    async def test_pagination_has_more(self):
        from src.api.edge_hub import list_nodes

        hubs = [_make_hub(hub_id=f"hub-{i:03d}", hub_code=f"HUB-{i:03d}") for i in range(5)]
        db = _make_db(
            _scalar_one(25),         # total = 25, page 1 of 5 (pageSize=5)
            _scalars_all(hubs),
        )
        result = await list_nodes(
            status=None, keyword=None, page=1, pageSize=5,
            db=db, _=_mock_user(),
        )

        assert result["meta"]["hasMore"] is True
        assert len(result["data"]["nodes"]) == 5


# ── get_node_detail ────────────────────────────────────────────────────────────

class TestGetNodeDetail:

    @pytest.mark.asyncio
    async def test_returns_hub_with_devices_and_alerts(self):
        from src.api.edge_hub import get_node_detail

        hub    = _make_hub()
        device = _make_device()
        alert  = _make_alert()

        db = _make_db(
            _scalar_one_or_none(hub),
            _scalars_all([device]),
            _scalars_all([alert]),
        )
        result = await get_node_detail(hub_id="hub-001", db=db, _=_mock_user())

        assert result["code"] == 0
        assert result["data"]["hubCode"] == "HUB-S001"
        assert len(result["data"]["devices"])      == 1
        assert len(result["data"]["recentAlerts"]) == 1
        assert result["data"]["devices"][0]["deviceCode"] == "DEV-001"

    @pytest.mark.asyncio
    async def test_404_when_not_found(self):
        from src.api.edge_hub import get_node_detail
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await get_node_detail(hub_id="ghost", db=db, _=_mock_user())
        assert exc_info.value.status_code == 404


# ── inspect_node ──────────────────────────────────────────────────────────────

class TestInspectNode:

    @pytest.mark.asyncio
    async def test_updates_heartbeat_and_returns_ok(self):
        from src.api.edge_hub import inspect_node

        hub = _make_hub()
        db  = _make_db(_scalar_one_or_none(hub))

        result = await inspect_node(hub_id="hub-001", db=db, _=_mock_user())

        assert result["code"] == 0
        assert "inspectedAt" in result["data"]
        assert result["data"]["status"] == "online"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_404_when_hub_not_found(self):
        from src.api.edge_hub import inspect_node
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await inspect_node(hub_id="ghost", db=db, _=_mock_user())
        assert exc_info.value.status_code == 404


# ── node_metrics ──────────────────────────────────────────────────────────────

class TestNodeMetrics:

    @pytest.mark.asyncio
    async def test_returns_correct_number_of_points(self):
        from src.api.edge_hub import node_metrics

        hub = _make_hub(cpu_pct=50.0, mem_pct=60.0, disk_pct=40.0)
        db  = _make_db(_scalar_one_or_none(hub))

        result = await node_metrics(hub_id="hub-001", hours=12, db=db, _=_mock_user())

        assert result["code"] == 0
        assert result["data"]["hours"] == 12
        points = result["data"]["points"]
        assert len(points) == 12
        # 每个点都有必要字段
        p = points[0]
        assert "cpuPct" in p
        assert "memPct" in p
        assert "diskPct" in p
        assert "timeLabel" in p

    @pytest.mark.asyncio
    async def test_values_within_0_to_100(self):
        from src.api.edge_hub import node_metrics

        hub = _make_hub(cpu_pct=95.0, mem_pct=5.0, disk_pct=50.0)
        db  = _make_db(_scalar_one_or_none(hub))

        result = await node_metrics(hub_id="hub-001", hours=24, db=db, _=_mock_user())

        for p in result["data"]["points"]:
            assert 0 <= p["cpuPct"]  <= 100
            assert 0 <= p["memPct"]  <= 100
            assert 0 <= p["diskPct"] <= 100

    @pytest.mark.asyncio
    async def test_404_when_hub_not_found(self):
        from src.api.edge_hub import node_metrics
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await node_metrics(hub_id="ghost", hours=24, db=db, _=_mock_user())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_uses_default_baselines_when_null_metrics(self):
        """hub.cpu_pct 为 None 时使用默认基准值 40/55/30，不应抛出异常。"""
        from src.api.edge_hub import node_metrics

        hub = _make_hub(cpu_pct=None, mem_pct=None, disk_pct=None)
        db  = _make_db(_scalar_one_or_none(hub))

        result = await node_metrics(hub_id="hub-001", hours=6, db=db, _=_mock_user())
        assert len(result["data"]["points"]) == 6


# ── list_all_alerts ────────────────────────────────────────────────────────────

class TestListAllAlerts:

    @pytest.mark.asyncio
    async def test_returns_alert_list(self):
        from src.api.edge_hub import list_all_alerts

        alert = _make_alert()
        db = _make_db(
            _scalar_one(1),
            _scalars_all([alert]),
        )
        result = await list_all_alerts(
            status=None, level=None, store_id=None, alert_type=None,
            page=1, pageSize=20, db=db, _=_mock_user(),
        )

        assert result["code"] == 0
        items = result["data"]["list"]
        assert len(items) == 1
        assert items[0]["alertType"] == "hub_disconnect"
        assert items[0]["level"]     == "p2"
        assert result["meta"]["total"] == 1

    @pytest.mark.asyncio
    async def test_empty_result(self):
        from src.api.edge_hub import list_all_alerts

        db = _make_db(_scalar_one(0), _scalars_all([]))
        result = await list_all_alerts(
            status=None, level=None, store_id=None, alert_type=None,
            page=1, pageSize=20, db=db, _=_mock_user(),
        )

        assert result["data"]["list"] == []
        assert result["meta"]["hasMore"] is False

    @pytest.mark.asyncio
    async def test_filters_are_passed_without_error(self):
        """status/level/store_id 筛选参数被传入时，正常执行不抛异常。"""
        from src.api.edge_hub import list_all_alerts

        alert = _make_alert(level="p1", status="open")
        db = _make_db(_scalar_one(1), _scalars_all([alert]))

        result = await list_all_alerts(
            status="open", level="p1", store_id="S001", alert_type=None,
            page=1, pageSize=20, db=db, _=_mock_user(),
        )
        assert result["data"]["list"][0]["level"] == "p1"


# ── resolve_alert ─────────────────────────────────────────────────────────────

class TestResolveAlert:

    @pytest.mark.asyncio
    async def test_resolves_open_alert(self):
        from src.api.edge_hub import resolve_alert

        alert = _make_alert(status="open")
        db    = _make_db(_scalar_one_or_none(alert))

        result = await resolve_alert(alert_id="alert-001", db=db, current_user=_mock_user())

        assert result["code"] == 0
        assert alert.status == "resolved"
        assert alert.resolved_by == "admin"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_already_resolved_returns_ok_without_commit(self):
        from src.api.edge_hub import resolve_alert
        from src.models.edge_hub import AlertStatus

        alert = _make_alert(status=AlertStatus.RESOLVED)
        db    = _make_db(_scalar_one_or_none(alert))

        result = await resolve_alert(alert_id="alert-001", db=db, current_user=_mock_user())

        assert result["code"] == 0
        assert result["message"] == "already resolved"
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_404_when_not_found(self):
        from src.api.edge_hub import resolve_alert
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await resolve_alert(alert_id="ghost", db=db, current_user=_mock_user())
        assert exc_info.value.status_code == 404


# ── ignore_alert ──────────────────────────────────────────────────────────────

class TestIgnoreAlert:

    @pytest.mark.asyncio
    async def test_ignores_open_alert(self):
        from src.api.edge_hub import ignore_alert
        from src.models.edge_hub import AlertStatus

        alert = _make_alert(status="open")
        db    = _make_db(_scalar_one_or_none(alert))

        result = await ignore_alert(alert_id="alert-001", db=db, current_user=_mock_user())

        assert result["code"] == 0
        assert alert.status == AlertStatus.IGNORED
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_404_when_not_found(self):
        from src.api.edge_hub import ignore_alert
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await ignore_alert(alert_id="ghost", db=db, current_user=_mock_user())
        assert exc_info.value.status_code == 404


# ── escalate_alert ────────────────────────────────────────────────────────────

class TestEscalateAlert:

    @pytest.mark.asyncio
    async def test_p3_escalates_to_p2(self):
        from src.api.edge_hub import escalate_alert

        alert = _make_alert(level="p3")
        db    = _make_db(_scalar_one_or_none(alert))

        await escalate_alert(alert_id="alert-001", db=db, current_user=_mock_user())

        assert alert.level == "p2"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_p2_escalates_to_p1(self):
        from src.api.edge_hub import escalate_alert

        alert = _make_alert(level="p2")
        db    = _make_db(_scalar_one_or_none(alert))

        await escalate_alert(alert_id="alert-001", db=db, current_user=_mock_user())

        assert alert.level == "p1"

    @pytest.mark.asyncio
    async def test_p1_stays_p1(self):
        from src.api.edge_hub import escalate_alert

        alert = _make_alert(level="p1")
        db    = _make_db(_scalar_one_or_none(alert))

        await escalate_alert(alert_id="alert-001", db=db, current_user=_mock_user())

        assert alert.level == "p1"   # ceiling

    @pytest.mark.asyncio
    async def test_404_when_not_found(self):
        from src.api.edge_hub import escalate_alert
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await escalate_alert(alert_id="ghost", db=db, current_user=_mock_user())
        assert exc_info.value.status_code == 404


# ── list_bindings ─────────────────────────────────────────────────────────────

class TestListBindings:

    @pytest.mark.asyncio
    async def test_returns_bindings_with_device_info(self):
        from src.api.edge_hub import list_bindings

        binding = _make_binding()
        device  = _make_device()

        db = _make_db(
            _scalars_all([binding]),
            _scalars_all([device]),
        )
        result = await list_bindings(store_id="S001", db=db, _=_mock_user())

        assert result["code"] == 0
        items = result["data"]["bindings"]
        assert len(items) == 1
        assert items[0]["position"]   == "store_manager"
        assert items[0]["deviceCode"] == "DEV-001"

    @pytest.mark.asyncio
    async def test_empty_bindings(self):
        from src.api.edge_hub import list_bindings

        db = _make_db(_scalars_all([]))
        result = await list_bindings(store_id="S001", db=db, _=_mock_user())

        assert result["data"]["bindings"] == []


# ── create_binding ─────────────────────────────────────────────────────────────

class TestCreateBinding:

    @pytest.mark.asyncio
    async def test_creates_binding_successfully(self):
        from src.api.edge_hub import create_binding, BindingCreate

        device = _make_device(store_id="S001")
        db     = _make_db(_scalar_one_or_none(device))

        body = BindingCreate(device_id="dev-001", position="cashier", channel=2)
        result = await create_binding(
            store_id="S001", body=body, db=db, _=_mock_user(),
        )

        assert result["code"] == 0
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_404_when_device_not_in_store(self):
        from src.api.edge_hub import create_binding, BindingCreate
        from fastapi import HTTPException

        # device belongs to a different store
        device = _make_device(store_id="S999")
        db     = _make_db(_scalar_one_or_none(device))

        body = BindingCreate(device_id="dev-001", position="cashier")
        with pytest.raises(HTTPException) as exc_info:
            await create_binding(store_id="S001", body=body, db=db, _=_mock_user())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_404_when_device_not_found(self):
        from src.api.edge_hub import create_binding, BindingCreate
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        body = BindingCreate(device_id="ghost", position="waiter")
        with pytest.raises(HTTPException) as exc_info:
            await create_binding(store_id="S001", body=body, db=db, _=_mock_user())
        assert exc_info.value.status_code == 404


# ── delete_binding ─────────────────────────────────────────────────────────────

class TestDeleteBinding:

    @pytest.mark.asyncio
    async def test_soft_deletes_binding(self):
        from src.api.edge_hub import delete_binding
        from src.models.edge_hub import BindingStatus

        binding = _make_binding(status="active")
        db      = _make_db(_scalar_one_or_none(binding))

        result = await delete_binding(binding_id="bind-001", db=db, _=_mock_user())

        assert result["code"] == 0
        assert binding.status == BindingStatus.INACTIVE
        assert binding.unbound_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_404_when_not_found(self):
        from src.api.edge_hub import delete_binding
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        with pytest.raises(HTTPException) as exc_info:
            await delete_binding(binding_id="ghost", db=db, _=_mock_user())
        assert exc_info.value.status_code == 404


# ── bulk_alert_action ─────────────────────────────────────────────────────────

class TestBulkAlertAction:

    @pytest.mark.asyncio
    async def test_bulk_resolve_open_alerts(self):
        from src.api.edge_hub import bulk_alert_action, BulkAlertAction
        from src.models.edge_hub import AlertStatus

        a1 = _make_alert(alert_id="a1", status="open")
        a2 = _make_alert(alert_id="a2", status="open")
        db = _make_db(_scalars_all([a1, a2]))

        body = BulkAlertAction(alert_ids=["a1", "a2"], action="resolve")
        result = await bulk_alert_action(body=body, db=db, current_user=_mock_user())

        assert result["code"] == 0
        assert result["data"]["affected"] == 2
        assert a1.status == AlertStatus.RESOLVED
        assert a2.status == AlertStatus.RESOLVED
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bulk_ignore_open_alerts(self):
        from src.api.edge_hub import bulk_alert_action, BulkAlertAction
        from src.models.edge_hub import AlertStatus

        alert = _make_alert(status="open")
        db = _make_db(_scalars_all([alert]))

        body = BulkAlertAction(alert_ids=["alert-001"], action="ignore")
        result = await bulk_alert_action(body=body, db=db, current_user=_mock_user())

        assert result["data"]["affected"] == 1
        assert alert.status == AlertStatus.IGNORED

    @pytest.mark.asyncio
    async def test_empty_ids_returns_zero_affected(self):
        from src.api.edge_hub import bulk_alert_action, BulkAlertAction

        db = _make_db()
        body = BulkAlertAction(alert_ids=[], action="resolve")
        result = await bulk_alert_action(body=body, db=db, current_user=_mock_user())

        assert result["data"]["affected"] == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_action_raises_422(self):
        from src.api.edge_hub import bulk_alert_action, BulkAlertAction
        from fastapi import HTTPException

        db = _make_db()
        body = BulkAlertAction(alert_ids=["a1"], action="delete")
        with pytest.raises(HTTPException) as exc_info:
            await bulk_alert_action(body=body, db=db, current_user=_mock_user())
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_only_open_alerts_are_affected(self):
        """已解决或已忽略的告警不应被批量操作修改（后端 WHERE status=open 过滤）。"""
        from src.api.edge_hub import bulk_alert_action, BulkAlertAction
        from src.models.edge_hub import AlertStatus

        # 模拟 DB 只返回 open 的那条（已解决的被 WHERE 过滤掉）
        open_alert = _make_alert(alert_id="open-1", status="open")
        db = _make_db(_scalars_all([open_alert]))

        body = BulkAlertAction(alert_ids=["open-1", "resolved-2"], action="resolve")
        result = await bulk_alert_action(body=body, db=db, current_user=_mock_user())

        assert result["data"]["affected"] == 1
        assert open_alert.status == AlertStatus.RESOLVED


# ════════════════════════════════════════════════════════════════════════════════
# POST /api/v1/edge-hub/nodes/{hub_id}/heartbeat
# ════════════════════════════════════════════════════════════════════════════════

class TestReceiveHeartbeat:

    @pytest.mark.asyncio
    async def test_happy_path_updates_hub_fields(self):
        """Heartbeat updates last_heartbeat, status, cpu/mem/disk and commits."""
        from src.api.edge_hub import receive_heartbeat, HeartbeatPayload

        hub = _make_hub(status="offline")
        db  = _make_db(
            _scalar_one_or_none(hub),   # hub lookup
        )
        db.commit = AsyncMock()

        payload = HeartbeatPayload(
            status="online",
            runtime_version="1.5.0",
            ip_address="10.0.0.1",
            cpu_pct=55.5,
            mem_pct=70.0,
            disk_pct=40.0,
        )

        result = await receive_heartbeat(
            hub_id="hub-001", body=payload, db=db, x_hub_secret=None,
        )

        assert hub.status          == "online"
        assert hub.runtime_version == "1.5.0"
        assert hub.ip_address      == "10.0.0.1"
        assert hub.cpu_pct         == 55.5
        assert hub.mem_pct         == 70.0
        assert hub.disk_pct        == 40.0
        assert hub.last_heartbeat  is not None
        assert result["code"] == 0
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_status_in_body_implicitly_sets_online(self):
        """If body.status is None, hub gets status=online (it's sending a heartbeat)."""
        from src.api.edge_hub import receive_heartbeat, HeartbeatPayload
        from src.models.edge_hub import HubStatus

        hub = _make_hub(status="offline")
        db  = _make_db(_scalar_one_or_none(hub))
        db.commit = AsyncMock()

        await receive_heartbeat(
            hub_id="hub-001", body=HeartbeatPayload(), db=db, x_hub_secret=None,
        )

        assert hub.status == HubStatus.ONLINE

    @pytest.mark.asyncio
    async def test_hub_not_found_raises_404(self):
        """Unknown hub_id returns 404."""
        from src.api.edge_hub import receive_heartbeat, HeartbeatPayload
        from fastapi import HTTPException

        db = _make_db(_scalar_one_or_none(None))
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await receive_heartbeat(
                hub_id="missing", body=HeartbeatPayload(), db=db, x_hub_secret=None,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_secret_raises_401(self):
        """Mismatched X-Hub-Secret header rejects request with 401."""
        import os as _os
        from src.api.edge_hub import receive_heartbeat, HeartbeatPayload
        from fastapi import HTTPException
        import src.api.edge_hub as eh_module

        original_secret = eh_module._HUB_SECRET
        eh_module._HUB_SECRET = "correct-secret"
        try:
            db = _make_db()
            db.commit = AsyncMock()
            with pytest.raises(HTTPException) as exc_info:
                await receive_heartbeat(
                    hub_id="hub-001", body=HeartbeatPayload(),
                    db=db, x_hub_secret="wrong-secret",
                )
            assert exc_info.value.status_code == 401
        finally:
            eh_module._HUB_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_device_status_updated_when_provided(self):
        """Heartbeat with devices[] updates matching EdgeDevice records."""
        from src.api.edge_hub import receive_heartbeat, HeartbeatPayload

        hub    = _make_hub()
        device = _make_device(device_code="DEV-001", status="offline")

        db = _make_db(
            _scalar_one_or_none(hub),     # hub lookup
            _scalar_one_or_none(device),  # device lookup
        )
        db.commit = AsyncMock()

        payload = HeartbeatPayload(
            devices=[{"device_code": "DEV-001", "status": "online", "firmware_ver": "3.0"}],
        )

        result = await receive_heartbeat(
            hub_id="hub-001", body=payload, db=db, x_hub_secret=None,
        )

        assert device.status      == "online"
        assert device.firmware_ver == "3.0"
        assert device.last_seen   is not None
        assert result["data"]["devicesUpdated"] == 1
