"""
Tests for WorkflowEngine
"""
import uuid
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.workflow_engine import (
    WorkflowEngine,
    PHASE_CONFIG,
)
from src.models.workflow import (
    ALL_PHASES,
    PHASE_INITIAL_PLAN, PHASE_PROCUREMENT, PHASE_SCHEDULING,
    PHASE_MENU, PHASE_MENU_SYNC, PHASE_MARKETING,
    DailyWorkflow, DecisionVersion, WorkflowPhase,
    PhaseStatus, WorkflowStatus, GenerationMode,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_workflow(
    store_id="STORE001",
    plan_date=None,
    status=WorkflowStatus.RUNNING.value,
    current_phase=PHASE_INITIAL_PLAN,
) -> DailyWorkflow:
    wf = MagicMock(spec=DailyWorkflow)
    wf.id            = uuid.uuid4()
    wf.store_id      = store_id
    wf.plan_date     = plan_date or date(2026, 3, 2)
    wf.status        = status
    wf.current_phase = current_phase
    wf.store_config  = {}
    return wf


def make_phase(
    phase_name=PHASE_INITIAL_PLAN,
    status=PhaseStatus.RUNNING.value,
    phase_order=1,
    workflow_id=None,
    current_version_id=None,
) -> WorkflowPhase:
    p = MagicMock(spec=WorkflowPhase)
    p.id                 = uuid.uuid4()
    p.workflow_id        = workflow_id or uuid.uuid4()
    p.phase_name         = phase_name
    p.phase_order        = phase_order
    p.status             = status
    p.current_version_id = current_version_id
    p.deadline           = datetime.utcnow() + timedelta(hours=1)
    p.started_at         = datetime.utcnow()
    p.locked_at          = None
    p.locked_by          = None
    return p


def make_version(phase_id=None, version_number=1, content=None) -> DecisionVersion:
    v = MagicMock(spec=DecisionVersion)
    v.id             = uuid.uuid4()
    v.phase_id       = phase_id or uuid.uuid4()
    v.version_number = version_number
    v.content        = content or {"items": []}
    v.is_final       = False
    return v


def _mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.add    = MagicMock()
    db.flush  = AsyncMock()
    return db


# ── start_daily_workflow ───────────────────────────────────────────────────

class TestStartDailyWorkflow:

    @pytest.mark.asyncio
    async def test_creates_new_workflow_when_not_exists(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None   # no existing wf
        db.execute.return_value = result_mock

        engine = WorkflowEngine(db)
        wf = await engine.start_daily_workflow("STORE001", date(2026, 3, 2))

        assert db.add.called
        assert db.flush.called

    @pytest.mark.asyncio
    async def test_idempotent_returns_existing_workflow(self):
        existing = make_workflow()
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute.return_value = result_mock

        engine = WorkflowEngine(db)
        wf = await engine.start_daily_workflow("STORE001", date(2026, 3, 2))

        assert wf is existing
        # Should NOT add a new workflow
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_initializes_6_phases(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        engine = WorkflowEngine(db)
        await engine.start_daily_workflow("STORE001", date(2026, 3, 2))

        # 1 DailyWorkflow + 6 WorkflowPhase = 7 add calls
        assert db.add.call_count == 7

    @pytest.mark.asyncio
    async def test_first_phase_starts_running(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        engine = WorkflowEngine(db)
        engine._calc_deadline = MagicMock(return_value=datetime.utcnow() + timedelta(hours=1))

        added_objects = []
        original_add = db.add.side_effect
        def capture_add(obj):
            added_objects.append(obj)
        db.add.side_effect = capture_add

        await engine.start_daily_workflow("STORE001", date(2026, 3, 2))

        phases = [o for o in added_objects if isinstance(o, WorkflowPhase)]
        # Exactly 6 phases
        assert len(phases) == 6


# ── submit_decision ────────────────────────────────────────────────────────

class TestSubmitDecision:

    @pytest.mark.asyncio
    async def test_submit_sets_version_number(self):
        phase   = make_phase(status=PhaseStatus.RUNNING.value)
        db      = _mock_db()
        wf      = make_workflow()

        # execute call 1: get phase
        phase_result = MagicMock(); phase_result.scalar_one_or_none.return_value = phase
        # execute call 2: count existing versions
        count_result = MagicMock(); count_result.scalar.return_value = 0
        # execute call 3: get workflow context
        wf_result    = MagicMock(); wf_result.scalar_one_or_none.return_value = wf
        db.execute.side_effect = [phase_result, count_result, wf_result]

        engine  = WorkflowEngine(db)
        version = await engine.submit_decision(phase.id, {"items": []}, "mgr")

        assert db.add.called
        # Phase status should change to REVIEWING
        assert phase.status == PhaseStatus.REVIEWING.value

    @pytest.mark.asyncio
    async def test_submit_to_locked_phase_raises(self):
        phase        = make_phase(status=PhaseStatus.LOCKED.value)
        db           = _mock_db()
        phase_result = MagicMock(); phase_result.scalar_one_or_none.return_value = phase
        db.execute.return_value = phase_result

        engine = WorkflowEngine(db)
        with pytest.raises(ValueError, match="已锁定"):
            await engine.submit_decision(phase.id, {"items": []})

    @pytest.mark.asyncio
    async def test_second_version_increments_number(self):
        phase   = make_phase(status=PhaseStatus.REVIEWING.value)
        db      = _mock_db()
        wf      = make_workflow()
        prev_v  = make_version(phase_id=phase.id, version_number=1, content={"a": 1})

        phase_result  = MagicMock(); phase_result.scalar_one_or_none.return_value = phase
        count_result  = MagicMock(); count_result.scalar.return_value = 1   # already 1 version
        prev_result   = MagicMock(); prev_result.scalar_one_or_none.return_value = prev_v
        wf_result     = MagicMock(); wf_result.scalar_one_or_none.return_value = wf
        db.execute.side_effect = [phase_result, count_result, prev_result, wf_result]

        added = []
        db.add.side_effect = lambda o: added.append(o)

        engine  = WorkflowEngine(db)
        version = await engine.submit_decision(phase.id, {"a": 2}, "mgr")

        new_versions = [o for o in added if isinstance(o, DecisionVersion)]
        assert len(new_versions) == 1
        assert new_versions[0].version_number == 2


# ── lock_phase ─────────────────────────────────────────────────────────────

class TestLockPhase:

    @pytest.mark.asyncio
    async def test_lock_changes_status(self):
        phase    = make_phase(status=PhaseStatus.REVIEWING.value)
        version  = make_version(phase_id=phase.id)
        phase.current_version_id = version.id

        db = _mock_db()
        phase_result   = MagicMock(); phase_result.scalar_one_or_none.return_value = phase
        version_result = MagicMock(); version_result.scalar_one_or_none.return_value = version

        # advance_to_next_phase will call get_all_phases → scalars().all()
        phases_result  = MagicMock()
        phases_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [phase_result, version_result, phases_result]

        engine = WorkflowEngine(db)
        result = await engine.lock_phase(phase.id, locked_by="manager")

        assert phase.status  == PhaseStatus.LOCKED.value
        assert version.is_final is True

    @pytest.mark.asyncio
    async def test_lock_idempotent(self):
        phase = make_phase(status=PhaseStatus.LOCKED.value)
        db    = _mock_db()
        phase_result = MagicMock(); phase_result.scalar_one_or_none.return_value = phase
        db.execute.return_value = phase_result

        engine = WorkflowEngine(db)
        result = await engine.lock_phase(phase.id)

        assert result is phase
        # should NOT modify or add anything
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_auto_advances_to_next_phase(self):
        wf_id   = uuid.uuid4()
        phase1  = make_phase(phase_name=PHASE_INITIAL_PLAN, phase_order=1,
                              status=PhaseStatus.REVIEWING.value, workflow_id=wf_id)
        phase2  = make_phase(phase_name=PHASE_PROCUREMENT,  phase_order=2,
                              status=PhaseStatus.PENDING.value, workflow_id=wf_id)
        phase1.current_version_id = None

        db = _mock_db()
        phase_result  = MagicMock(); phase_result.scalar_one_or_none.return_value = phase1
        phases_result = MagicMock(); phases_result.scalars.return_value.all.return_value = [phase1, phase2]
        wf            = make_workflow(current_phase=PHASE_INITIAL_PLAN)
        wf_result     = MagicMock(); wf_result.scalar_one_or_none.return_value = wf
        db.execute.side_effect = [phase_result, phases_result, wf_result]

        engine = WorkflowEngine(db)
        await engine.lock_phase(phase1.id)

        # phase2 should now be RUNNING
        assert phase2.status == PhaseStatus.RUNNING.value


# ── advance_to_next_phase ──────────────────────────────────────────────────

class TestAdvanceToNextPhase:

    @pytest.mark.asyncio
    async def test_advances_pending_to_running(self):
        wf_id  = uuid.uuid4()
        phase1 = make_phase(phase_name=PHASE_INITIAL_PLAN, phase_order=1,
                             status=PhaseStatus.RUNNING.value, workflow_id=wf_id)
        phase2 = make_phase(phase_name=PHASE_PROCUREMENT,  phase_order=2,
                             status=PhaseStatus.PENDING.value, workflow_id=wf_id)
        wf     = make_workflow()

        db = _mock_db()
        phases_result = MagicMock(); phases_result.scalars.return_value.all.return_value = [phase1, phase2]
        wf_result     = MagicMock(); wf_result.scalar_one_or_none.return_value = wf
        db.execute.side_effect = [phases_result, wf_result]

        engine = WorkflowEngine(db)
        result = await engine.advance_to_next_phase(wf_id)

        assert result is phase2
        assert phase2.status == PhaseStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_returns_none_at_last_phase(self):
        wf_id  = uuid.uuid4()
        last_phase = make_phase(phase_name=PHASE_MARKETING, phase_order=6,
                                 status=PhaseStatus.RUNNING.value, workflow_id=wf_id)

        db = _mock_db()
        phases_result = MagicMock(); phases_result.scalars.return_value.all.return_value = [last_phase]
        db.execute.return_value = phases_result

        engine = WorkflowEngine(db)
        result = await engine.advance_to_next_phase(wf_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_running_phase(self):
        wf_id  = uuid.uuid4()
        phases = [make_phase(phase_name=n, phase_order=i+1,
                              status=PhaseStatus.LOCKED.value, workflow_id=wf_id)
                  for i, n in enumerate([PHASE_INITIAL_PLAN, PHASE_PROCUREMENT])]

        db = _mock_db()
        phases_result = MagicMock(); phases_result.scalars.return_value.all.return_value = phases
        db.execute.return_value = phases_result

        engine = WorkflowEngine(db)
        result = await engine.advance_to_next_phase(wf_id)
        assert result is None


# ── check_expired_phases ────────────────────────────────────────────────────

class TestCheckExpiredPhases:

    @pytest.mark.asyncio
    async def test_expired_running_phase_gets_auto_locked(self):
        """Phases past their deadline should be auto-locked by check_expired_phases."""
        wf_id  = uuid.uuid4()
        expired = make_phase(phase_name=PHASE_PROCUREMENT, phase_order=2,
                              status=PhaseStatus.RUNNING.value, workflow_id=wf_id)
        expired.deadline = datetime.utcnow() - timedelta(minutes=5)  # past deadline

        db = _mock_db()
        expired_result = MagicMock(); expired_result.scalars.return_value.all.return_value = [expired]

        # lock_phase calls: _get_phase, then version lookup, then advance
        phase_result  = MagicMock(); phase_result.scalar_one_or_none.return_value = expired
        phases_result = MagicMock(); phases_result.scalars.return_value.all.return_value = []
        wf_result     = MagicMock(); wf_result.scalar_one_or_none.return_value = make_workflow()
        db.execute.side_effect = [expired_result, phase_result, phases_result, wf_result]

        engine = WorkflowEngine(db)
        locked = await engine.check_expired_phases()

        assert len(locked) == 1


# ── PHASE_CONFIG completeness ──────────────────────────────────────────────

class TestPhaseConfigCompleteness:

    def test_all_6_phases_configured(self):
        assert set(PHASE_CONFIG.keys()) == set(ALL_PHASES)

    def test_phase_orders_are_sequential(self):
        orders = sorted(cfg["order"] for cfg in PHASE_CONFIG.values())
        assert orders == list(range(1, 7))

    def test_deadlines_are_strictly_increasing(self):
        ordered = sorted(PHASE_CONFIG.values(), key=lambda c: c["order"])
        for i in range(len(ordered) - 1):
            this_h, this_m = ordered[i]["deadline_hour"],   ordered[i]["deadline_minute"]
            next_h, next_m = ordered[i+1]["deadline_hour"], ordered[i+1]["deadline_minute"]
            this_t = this_h * 60 + this_m
            next_t = next_h * 60 + next_m
            assert next_t > this_t, \
                f"Phase {ordered[i+1]} deadline not after {ordered[i]}"

    def test_menu_sync_is_auto(self):
        assert PHASE_CONFIG[PHASE_MENU_SYNC]["is_auto"] is True

    def test_user_phases_not_auto(self):
        user_phases = [
            PHASE_INITIAL_PLAN, PHASE_PROCUREMENT,
            PHASE_SCHEDULING, PHASE_MENU, PHASE_MARKETING
        ]
        for phase in user_phases:
            assert PHASE_CONFIG[phase]["is_auto"] is False, \
                f"{phase} should require human confirmation"


# ── _calc_deadline ─────────────────────────────────────────────────────────

class TestCalcDeadline:

    def test_default_deadline_uses_config_time(self):
        db     = _mock_db()
        engine = WorkflowEngine(db)
        cfg    = PHASE_CONFIG[PHASE_PROCUREMENT]
        dl     = engine._calc_deadline(date(2026, 3, 2), cfg, None)

        assert dl.hour   == cfg["deadline_hour"]
        assert dl.minute == cfg["deadline_minute"]

    def test_deadline_on_trigger_date(self):
        db     = _mock_db()
        engine = WorkflowEngine(db)
        cfg    = PHASE_CONFIG[PHASE_INITIAL_PLAN]
        td     = date(2026, 4, 1)
        dl     = engine._calc_deadline(td, cfg, None)

        assert dl.date() == td


# ── version diff ─────────────────────────────────────────────────────────────

class TestVersionDiff:
    """Test _simple_diff helper (if exported)."""

    def test_diff_detects_changed_keys(self):
        from src.services.workflow_engine import _simple_diff
        old = {"a": 1, "b": 2}
        new = {"a": 1, "b": 3}
        diff = _simple_diff(old, new)
        assert "b" in diff["modified"]

    def test_diff_detects_added_keys(self):
        from src.services.workflow_engine import _simple_diff
        diff = _simple_diff({"a": 1}, {"a": 1, "c": 3})
        assert "c" in diff["added"]

    def test_diff_detects_removed_keys(self):
        from src.services.workflow_engine import _simple_diff
        diff = _simple_diff({"a": 1, "b": 2}, {"a": 1})
        assert "b" in diff["removed"]

    def test_identical_dicts_empty_diff(self):
        from src.services.workflow_engine import _simple_diff
        diff = _simple_diff({"a": 1}, {"a": 1})
        assert not any(diff.values())
