"""
Edge Hub Heartbeat Monitor — Celery Task Tests

覆盖 tasks.check_edge_hub_heartbeats 的核心逻辑：
  1. 心跳超时  → hub.status 改为 offline，创建 P1 EdgeAlert
  2. 心跳超时但告警已存在 → 不重复创建告警
  3. 心跳恢复  → hub.status 改为 online，open hub_offline 告警自动 RESOLVED
  4. 所有心跳正常 → 无变更
  5. 任务注册名称正确
  6. 新 P1 告警且门店有店长 → 企微推送被调用
  7. 新 P1 告警但门店无有效店长 → 企微推送不被调用
"""

import os

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
    "EDGE_HUB_OFFLINE_THRESHOLD_MIN": "5",
}.items():
    os.environ.setdefault(_k, _v)

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.utcnow()


def _hub(hub_id="H1", hub_code="HUB-001", store_id="S001",
         status="online", last_heartbeat=None):
    h = MagicMock()
    h.id             = hub_id
    h.hub_code       = hub_code
    h.store_id       = store_id
    h.status         = status
    h.last_heartbeat = last_heartbeat
    return h


def _alert(alert_id="A1", hub_id="H1", alert_type="hub_offline", status="open"):
    a = MagicMock()
    a.id         = alert_id
    a.hub_id     = hub_id
    a.alert_type = alert_type
    a.status     = status
    a.resolved_at = None
    a.resolved_by = None
    return a


def _build_session(*responses):
    """
    Build an AsyncMock session with sequential execute() responses.
    Each response is a pre-built MagicMock with the needed .scalar*/scalars() methods.
    """
    session = AsyncMock()
    session.add    = MagicMock()
    session.commit = AsyncMock()

    resp_list = list(responses)
    idx = [0]

    async def _execute(stmt, *a, **kw):
        r = resp_list[idx[0]] if idx[0] < len(resp_list) else resp_list[-1]
        idx[0] += 1
        return r

    session.execute = _execute
    return session


def _hubs_result(hub_list):
    r = MagicMock()
    r.scalars.return_value.all.return_value = hub_list
    return r


def _scalar_one_or_none_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_all_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _manager(wechat_user_id="WX001"):
    m = MagicMock()
    m.wechat_user_id = wechat_user_id
    return m


class _FakeCtx:
    """Simulates `async with AsyncSessionLocal() as db:`."""
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass


def _run_task_inner(session, mock_send_hardware=None):
    """
    Run the inner _run() coroutine of check_edge_hub_heartbeats in a fresh
    event loop, bypassing Celery machinery entirely.

    Returns (session, mock_send_hardware) so callers can assert on push calls.
    """
    def fake_asyncio_run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    if mock_send_hardware is None:
        mock_send_hardware = AsyncMock(return_value={"success": True})

    with patch("src.core.celery_tasks.asyncio.run", side_effect=fake_asyncio_run), \
         patch("src.core.database.AsyncSessionLocal", return_value=_FakeCtx(session)), \
         patch("src.models.edge_hub.HubStatus") as mock_hs, \
         patch("src.models.edge_hub.AlertStatus") as mock_as, \
         patch("src.models.edge_hub.AlertLevel") as mock_al, \
         patch(
             "src.services.wechat_alert_service.wechat_alert_service.send_hardware_alert",
             new=mock_send_hardware,
         ):

        mock_hs.OFFLINE = "offline"
        mock_hs.ONLINE  = "online"
        mock_as.OPEN     = "open"
        mock_as.RESOLVED = "resolved"
        mock_al.P1       = "p1"

        from src.core.celery_tasks import check_edge_hub_heartbeats
        # .apply() works with real Celery; if FakeCelery stripped it, call directly
        if hasattr(check_edge_hub_heartbeats, 'apply'):
            check_edge_hub_heartbeats.apply()
        else:
            # bind=True → first arg is self (mock it)
            check_edge_hub_heartbeats(MagicMock())

    return session, mock_send_hardware


# ════════════════════════════════════════════════════════════════════════════════
# Tests — all synchronous (Celery tasks are sync wrappers over asyncio.run)
# ════════════════════════════════════════════════════════════════════════════════

class TestCheckEdgeHubHeartbeats:

    def test_stale_hub_marked_offline_and_alert_created(self):
        """Hub with no heartbeat → status=offline, new P1 alert added via session.add."""
        stale_hub = _hub(status="online", last_heartbeat=None)
        # execute calls: [all_hubs, no_existing_alert, managers(empty fallback)]
        session = _build_session(
            _hubs_result([stale_hub]),
            _scalar_one_or_none_result(None),    # no existing open alert
            _scalars_all_result([]),             # no managers → no push
        )
        session, _ = _run_task_inner(session)

        assert stale_hub.status == "offline"
        assert session.add.called
        assert session.commit.called

    def test_stale_hub_no_duplicate_alert(self):
        """Existing open hub_offline alert → session.add NOT called again."""
        stale_hub  = _hub(status="online", last_heartbeat=None)
        open_alert = _alert(alert_type="hub_offline", status="open")
        session = _build_session(
            _hubs_result([stale_hub]),
            _scalar_one_or_none_result(open_alert),  # alert already exists
        )
        session, _ = _run_task_inner(session)

        assert stale_hub.status == "offline"
        session.add.assert_not_called()

    def test_recovered_hub_status_and_alert_resolved(self):
        """Fresh heartbeat on offline hub → status=online, alert.status=resolved."""
        fresh_time  = _now() - timedelta(seconds=30)
        offline_hub = _hub(status="offline", last_heartbeat=fresh_time)
        open_alert  = _alert(alert_type="hub_offline", status="open")
        # execute calls: [all_hubs, open_alerts_to_resolve]
        session = _build_session(
            _hubs_result([offline_hub]),
            _scalars_all_result([open_alert]),   # open alerts to auto-resolve
        )
        session, _ = _run_task_inner(session)

        assert offline_hub.status == "online"
        assert open_alert.status     == "resolved"
        assert open_alert.resolved_by == "system"
        assert open_alert.resolved_at is not None
        assert session.commit.called

    def test_healthy_hub_no_changes(self):
        """Online hub with recent heartbeat → no status change, no alert added."""
        fresh_time  = _now() - timedelta(seconds=60)
        healthy_hub = _hub(status="online", last_heartbeat=fresh_time)
        session = _build_session(_hubs_result([healthy_hub]))
        session, _ = _run_task_inner(session)

        assert healthy_hub.status == "online"
        session.add.assert_not_called()

    def test_task_name_registered(self):
        """Celery task must be registered with the expected name."""
        from src.core.celery_tasks import check_edge_hub_heartbeats
        # When real Celery is available, .name exists; with FakeCelery it may not
        if hasattr(check_edge_hub_heartbeats, 'name'):
            assert check_edge_hub_heartbeats.name == "tasks.check_edge_hub_heartbeats"
        else:
            assert check_edge_hub_heartbeats.__name__ == "check_edge_hub_heartbeats"


# ════════════════════════════════════════════════════════════════════════════════
# Tests — WeChat push on new P1 alert
# ════════════════════════════════════════════════════════════════════════════════

class TestCheckEdgeHubHeartbeatWeChatPush:

    def test_wechat_push_called_when_managers_exist(self):
        """新 P1 告警 + 门店有店长 → send_hardware_alert 被调用一次。"""
        stale_hub = _hub(status="online", last_heartbeat=None)
        manager   = _manager(wechat_user_id="WX001")
        session   = _build_session(
            _hubs_result([stale_hub]),
            _scalar_one_or_none_result(None),    # no existing alert
            _scalars_all_result([manager]),      # one manager with wechat id
        )
        mock_push = AsyncMock(return_value={"success": True})
        _, mock_push = _run_task_inner(session, mock_send_hardware=mock_push)

        mock_push.assert_called_once()
        call_kwargs = mock_push.call_args.kwargs
        assert call_kwargs["hub_id"]      == stale_hub.id
        assert call_kwargs["hub_code"]    == stale_hub.hub_code
        assert call_kwargs["store_id"]    == stale_hub.store_id
        assert call_kwargs["alert_type"]  == "hub_offline"
        assert call_kwargs["recipient_ids"] == ["WX001"]

    def test_wechat_push_not_called_when_no_managers(self):
        """新 P1 告警但门店无有效店长 → send_hardware_alert 不被调用。"""
        stale_hub = _hub(status="online", last_heartbeat=None)
        session   = _build_session(
            _hubs_result([stale_hub]),
            _scalar_one_or_none_result(None),    # no existing alert
            _scalars_all_result([]),             # no managers
        )
        mock_push = AsyncMock(return_value={"success": True})
        _, mock_push = _run_task_inner(session, mock_send_hardware=mock_push)

        mock_push.assert_not_called()

    def test_wechat_push_not_called_when_alert_already_exists(self):
        """已有 open 告警（去重）→ 不创建新告警 → send_hardware_alert 不被调用。"""
        stale_hub  = _hub(status="online", last_heartbeat=None)
        open_alert = _alert(alert_type="hub_offline", status="open")
        session    = _build_session(
            _hubs_result([stale_hub]),
            _scalar_one_or_none_result(open_alert),  # existing alert
        )
        mock_push = AsyncMock(return_value={"success": True})
        _, mock_push = _run_task_inner(session, mock_send_hardware=mock_push)

        mock_push.assert_not_called()
