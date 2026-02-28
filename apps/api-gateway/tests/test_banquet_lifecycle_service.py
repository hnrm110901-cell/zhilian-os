"""
Tests for BanquetLifecycleService
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.banquet_lifecycle_service import (
    BanquetLifecycleService,
    StageTransitionError,
    RoomConflictError,
)
from src.models.reservation import Reservation, ReservationType
from src.models.banquet_lifecycle import BanquetStage, STAGE_TRANSITIONS, ROOM_LOCK_TIMEOUT_DAYS


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_reservation(
    rid="RES001",
    store_id="STORE001",
    banquet_stage=None,
    party_size=50,
    reservation_date=None,
    estimated_budget=500000,
    reservation_type=ReservationType.BANQUET,
) -> Reservation:
    r = Reservation()
    r.id               = rid
    r.store_id         = store_id
    r.banquet_stage    = banquet_stage
    r.party_size       = party_size
    r.reservation_date = reservation_date or date(2026, 6, 15)
    r.estimated_budget = estimated_budget
    r.reservation_type = reservation_type
    r.customer_name    = "测试客户"
    r.customer_phone   = "13800138000"
    r.room_name        = "宴会厅A"
    r.room_locked_at   = None
    r.signed_at        = None
    r.banquet_stage_updated_at = None
    return r


def _mock_db_with_reservation(reservation: Reservation) -> AsyncMock:
    """Return a mocked DB session that returns 'reservation' on scalar_one_or_none()."""
    db = AsyncMock(spec=AsyncSession)
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = reservation
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = []
    db.execute.return_value = scalar_result
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


# ── _validate_transition ───────────────────────────────────────────────────────

class TestValidateTransition:
    """Tests for the static _validate_transition helper."""

    def test_init_to_lead_ok(self):
        BanquetLifecycleService._validate_transition(None, BanquetStage.LEAD.value)

    def test_init_to_non_lead_raises(self):
        with pytest.raises(StageTransitionError):
            BanquetLifecycleService._validate_transition(None, BanquetStage.INTENT.value)

    def test_lead_to_intent_ok(self):
        BanquetLifecycleService._validate_transition(
            BanquetStage.LEAD.value, BanquetStage.INTENT.value
        )

    def test_lead_to_cancelled_ok(self):
        BanquetLifecycleService._validate_transition(
            BanquetStage.LEAD.value, BanquetStage.CANCELLED.value
        )

    def test_lead_to_signed_invalid(self):
        with pytest.raises(StageTransitionError):
            BanquetLifecycleService._validate_transition(
                BanquetStage.LEAD.value, BanquetStage.SIGNED.value
            )

    def test_intent_to_room_lock_ok(self):
        BanquetLifecycleService._validate_transition(
            BanquetStage.INTENT.value, BanquetStage.ROOM_LOCK.value
        )

    def test_room_lock_to_signed_ok(self):
        BanquetLifecycleService._validate_transition(
            BanquetStage.ROOM_LOCK.value, BanquetStage.SIGNED.value
        )

    def test_room_lock_to_lead_ok(self):
        """room_lock can fall back to lead (timeout)."""
        BanquetLifecycleService._validate_transition(
            BanquetStage.ROOM_LOCK.value, BanquetStage.LEAD.value
        )

    def test_signed_to_preparation_ok(self):
        BanquetLifecycleService._validate_transition(
            BanquetStage.SIGNED.value, BanquetStage.PREPARATION.value
        )

    def test_service_to_completed_ok(self):
        BanquetLifecycleService._validate_transition(
            BanquetStage.SERVICE.value, BanquetStage.COMPLETED.value
        )

    def test_completed_is_terminal(self):
        """From completed, no transitions should be allowed."""
        with pytest.raises(StageTransitionError):
            BanquetLifecycleService._validate_transition(
                BanquetStage.COMPLETED.value, BanquetStage.SERVICE.value
            )

    def test_cancelled_is_terminal(self):
        with pytest.raises(StageTransitionError):
            BanquetLifecycleService._validate_transition(
                BanquetStage.CANCELLED.value, BanquetStage.LEAD.value
            )

    def test_any_stage_to_cancelled_ok(self):
        """Any non-terminal stage can transition to cancelled."""
        for stage in (BanquetStage.LEAD, BanquetStage.INTENT,
                      BanquetStage.ROOM_LOCK, BanquetStage.SIGNED,
                      BanquetStage.PREPARATION, BanquetStage.SERVICE):
            BanquetLifecycleService._validate_transition(
                stage.value, BanquetStage.CANCELLED.value
            )


# ── initialize_stage ──────────────────────────────────────────────────────────

class TestInitializeStage:

    @pytest.mark.asyncio
    async def test_initialize_sets_lead(self):
        r   = make_reservation(banquet_stage=None)
        db  = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)

        # _apply_stage_change writes back to the reservation, mock it
        svc._apply_stage_change = AsyncMock(return_value=r)
        await svc.initialize_stage("RES001", operator="manager")

        svc._apply_stage_change.assert_awaited_once()
        call_kwargs = svc._apply_stage_change.call_args.kwargs
        assert call_kwargs["to_stage"] == BanquetStage.LEAD.value
        assert call_kwargs["from_stage"] is None

    @pytest.mark.asyncio
    async def test_already_has_stage_raises(self):
        r   = make_reservation(banquet_stage=BanquetStage.INTENT.value)
        db  = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)

        with pytest.raises(StageTransitionError, match="已有阶段"):
            await svc.initialize_stage("RES001")

    @pytest.mark.asyncio
    async def test_non_banquet_type_raises(self):
        r   = make_reservation(banquet_stage=None, reservation_type=ReservationType.REGULAR)
        db  = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)

        with pytest.raises(StageTransitionError, match="不是宴会类型"):
            await svc.initialize_stage("RES001")

    @pytest.mark.asyncio
    async def test_reservation_not_found_raises(self):
        db = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        svc = BanquetLifecycleService(db)

        with pytest.raises(ValueError, match="预约不存在"):
            await svc.initialize_stage("NONEXISTENT")


# ── advance_stage ─────────────────────────────────────────────────────────────

class TestAdvanceStage:

    @pytest.mark.asyncio
    async def test_lead_to_intent_succeeds(self):
        r = make_reservation(banquet_stage=BanquetStage.LEAD.value)
        db = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)
        svc._apply_stage_change = AsyncMock(return_value=r)

        result = await svc.advance_stage(
            "RES001", BanquetStage.INTENT, operator="mgr"
        )
        assert result is r
        svc._apply_stage_change.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        r = make_reservation(banquet_stage=BanquetStage.LEAD.value)
        db = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)

        with pytest.raises(StageTransitionError):
            await svc.advance_stage("RES001", BanquetStage.SIGNED, operator="mgr")

    @pytest.mark.asyncio
    async def test_room_lock_checks_conflicts(self):
        r = make_reservation(banquet_stage=BanquetStage.INTENT.value)
        db = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)
        svc._check_room_lock_conflict = AsyncMock()
        svc._apply_stage_change       = AsyncMock(return_value=r)

        await svc.advance_stage("RES001", BanquetStage.ROOM_LOCK, store_id="STORE001")
        svc._check_room_lock_conflict.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_signed_triggers_beo(self):
        r = make_reservation(banquet_stage=BanquetStage.ROOM_LOCK.value)
        r.room_locked_at = datetime.utcnow() - timedelta(hours=1)
        db = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)
        svc._check_room_lock_conflict = AsyncMock()
        svc._apply_stage_change       = AsyncMock(return_value=r)
        svc._trigger_beo_on_signed    = AsyncMock()

        await svc.advance_stage("RES001", BanquetStage.SIGNED, store_id="STORE001")
        svc._trigger_beo_on_signed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_signed_does_not_trigger_beo(self):
        r = make_reservation(banquet_stage=BanquetStage.LEAD.value)
        db = _mock_db_with_reservation(r)
        svc = BanquetLifecycleService(db)
        svc._apply_stage_change    = AsyncMock(return_value=r)
        svc._trigger_beo_on_signed = AsyncMock()

        await svc.advance_stage("RES001", BanquetStage.INTENT)
        svc._trigger_beo_on_signed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_any_stage_can_cancel(self):
        for stage in (BanquetStage.LEAD, BanquetStage.INTENT,
                      BanquetStage.ROOM_LOCK, BanquetStage.SIGNED,
                      BanquetStage.PREPARATION, BanquetStage.SERVICE):
            r = make_reservation(banquet_stage=stage.value)
            db = _mock_db_with_reservation(r)
            svc = BanquetLifecycleService(db)
            svc._check_room_lock_conflict = AsyncMock()
            svc._apply_stage_change       = AsyncMock(return_value=r)
            svc._trigger_beo_on_signed    = AsyncMock()

            result = await svc.advance_stage("RES001", BanquetStage.CANCELLED)
            assert result is r


# ── release_expired_locks ─────────────────────────────────────────────────────

class TestReleaseExpiredLocks:

    @pytest.mark.asyncio
    async def test_releases_overdue_locks(self):
        overdue_r = make_reservation(banquet_stage=BanquetStage.ROOM_LOCK.value)
        overdue_r.room_locked_at = datetime.utcnow() - timedelta(days=ROOM_LOCK_TIMEOUT_DAYS + 1)

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [overdue_r]
        db.execute.return_value = exec_result
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = BanquetLifecycleService(db)
        svc._apply_stage_change = AsyncMock(return_value=overdue_r)

        released = await svc.release_expired_locks()
        assert overdue_r.id in released
        # Should revert to INTENT
        call_kwargs = svc._apply_stage_change.call_args.kwargs
        assert call_kwargs["to_stage"] == BanquetStage.INTENT.value

    @pytest.mark.asyncio
    async def test_no_overdue_locks_returns_empty(self):
        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        db.execute.return_value = exec_result

        svc = BanquetLifecycleService(db)
        released = await svc.release_expired_locks()
        assert released == []

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self):
        """Even if one revert fails, others should still be released."""
        r1 = make_reservation(rid="R1", banquet_stage=BanquetStage.ROOM_LOCK.value)
        r1.room_locked_at = datetime.utcnow() - timedelta(days=ROOM_LOCK_TIMEOUT_DAYS + 2)
        r2 = make_reservation(rid="R2", banquet_stage=BanquetStage.ROOM_LOCK.value)
        r2.room_locked_at = datetime.utcnow() - timedelta(days=ROOM_LOCK_TIMEOUT_DAYS + 2)

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [r1, r2]
        db.execute.return_value = exec_result

        svc = BanquetLifecycleService(db)
        # First call fails, second succeeds
        svc._apply_stage_change = AsyncMock(
            side_effect=[Exception("DB error"), r2]
        )
        released = await svc.release_expired_locks()
        assert "R1" not in released
        assert "R2" in released


# ── get_pipeline ──────────────────────────────────────────────────────────────

class TestGetPipeline:

    @pytest.mark.asyncio
    async def test_pipeline_groups_by_stage(self):
        lead_r   = make_reservation(rid="R1", banquet_stage=BanquetStage.LEAD.value,
                                    estimated_budget=0)
        signed_r = make_reservation(rid="R2", banquet_stage=BanquetStage.SIGNED.value,
                                    estimated_budget=100000)

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [lead_r, signed_r]
        db.execute.return_value = exec_result

        svc    = BanquetLifecycleService(db)
        result = await svc.get_pipeline("STORE001")

        assert result["total_banquets"] == 2
        assert len(result["stages"][BanquetStage.LEAD.value]) == 1
        assert len(result["stages"][BanquetStage.SIGNED.value]) == 1
        # signed budget contributes to confirmed revenue
        assert result["total_confirmed_revenue"] > 0

    @pytest.mark.asyncio
    async def test_pipeline_empty_store(self):
        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        db.execute.return_value = exec_result

        svc    = BanquetLifecycleService(db)
        result = await svc.get_pipeline("EMPTY_STORE")

        assert result["total_banquets"] == 0
        assert result["total_confirmed_revenue"] == 0.0

    @pytest.mark.asyncio
    async def test_pipeline_stage_counts(self):
        reservations = [
            make_reservation(rid=f"R{i}", banquet_stage=BanquetStage.INTENT.value)
            for i in range(3)
        ]

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = reservations
        db.execute.return_value = exec_result

        svc    = BanquetLifecycleService(db)
        result = await svc.get_pipeline("STORE001")

        assert result["stage_counts"][BanquetStage.INTENT.value] == 3


# ── get_funnel_stats ──────────────────────────────────────────────────────────

class TestGetFunnelStats:

    @pytest.mark.asyncio
    async def test_conversion_rates_calculated(self):
        # Simulate DB returning stage counts
        db = AsyncMock(spec=AsyncSession)
        rows = [
            (BanquetStage.LEAD.value,   10),
            (BanquetStage.INTENT.value,  5),
        ]
        exec_results = [
            MagicMock(all=MagicMock(return_value=rows)),      # stage counts query
            MagicMock(all=MagicMock(return_value=[])),        # avg_days_to_signed query
        ]
        db.execute.side_effect = exec_results

        svc    = BanquetLifecycleService(db)
        result = await svc.get_funnel_stats("STORE001", days_back=90)

        assert result["stage_counts"][BanquetStage.LEAD.value]   == 10
        assert result["stage_counts"][BanquetStage.INTENT.value] == 5
        # lead → intent conversion: 5/10 = 50%
        assert result["conversion_rates"].get("lead→intent") == 50.0

    @pytest.mark.asyncio
    async def test_no_leads_skips_conversion(self):
        db = AsyncMock(spec=AsyncSession)
        rows = [(BanquetStage.SIGNED.value, 2)]
        exec_results = [
            MagicMock(all=MagicMock(return_value=rows)),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        db.execute.side_effect = exec_results

        svc    = BanquetLifecycleService(db)
        result = await svc.get_funnel_stats("STORE001")

        # lead→intent rate should not appear (no leads)
        assert "lead→intent" not in result["conversion_rates"]


# ── get_availability_calendar ─────────────────────────────────────────────────

class TestGetAvailabilityCalendar:

    @pytest.mark.asyncio
    @patch("src.services.banquet_lifecycle_service.AuspiciousDateService")
    async def test_calendar_has_all_days(self, mock_ausp_cls):
        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=False, demand_factor=1.0, label=None
        )
        mock_ausp_cls.return_value = mock_ausp

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.all.return_value = []
        db.execute.return_value = exec_result

        svc    = BanquetLifecycleService(db)
        result = await svc.get_availability_calendar("STORE001", 2026, 5)

        # May has 31 days
        assert len(result["calendar"]) == 31
        assert result["year"] == 2026
        assert result["month"] == 5

    @pytest.mark.asyncio
    @patch("src.services.banquet_lifecycle_service.AuspiciousDateService")
    async def test_calendar_marks_auspicious_day(self, mock_ausp_cls):
        mock_ausp = MagicMock()
        def _get_info(d: date):
            info = MagicMock()
            info.is_auspicious = (d.month == 5 and d.day == 20)
            info.demand_factor  = 2.2 if info.is_auspicious else 1.0
            info.label          = "5/20表白日" if info.is_auspicious else None
            return info
        mock_ausp.get_info.side_effect = _get_info
        mock_ausp_cls.return_value = mock_ausp

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.all.return_value = []
        db.execute.return_value = exec_result

        svc    = BanquetLifecycleService(db)
        result = await svc.get_availability_calendar("STORE001", 2026, 5)

        may20 = next(d for d in result["calendar"] if d["date"] == "2026-05-20")
        assert may20["is_auspicious"] is True
        assert may20["demand_factor"] == 2.2
        assert result["auspicious_days"] >= 1

    @pytest.mark.asyncio
    @patch("src.services.banquet_lifecycle_service.AuspiciousDateService")
    async def test_calendar_marks_fully_booked(self, mock_ausp_cls):
        mock_ausp = MagicMock()
        mock_ausp.get_info.return_value = MagicMock(
            is_auspicious=False, demand_factor=1.0, label=None
        )
        mock_ausp_cls.return_value = mock_ausp

        # Simulate 210 guests on 2026-06-15 (> max_capacity=200)
        row = MagicMock()
        row.reservation_date = date(2026, 6, 15)
        row.banquet_stage    = BanquetStage.SIGNED.value
        row.party_size       = 210
        row.room_name        = "宴会厅A"

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.all.return_value = [row]
        db.execute.return_value = exec_result

        svc    = BanquetLifecycleService(db)
        result = await svc.get_availability_calendar("STORE001", 2026, 6, max_capacity=200)

        june15 = next(d for d in result["calendar"] if d["date"] == "2026-06-15")
        assert june15["available"] is False
        assert june15["total_guests"] == 210
        assert result["fully_booked_days"] >= 1


# ── get_stage_history ─────────────────────────────────────────────────────────

class TestGetStageHistory:

    @pytest.mark.asyncio
    async def test_returns_ordered_history(self):
        from src.models.banquet_lifecycle import BanquetStageHistory
        h1 = MagicMock(spec=BanquetStageHistory)
        h1.id         = "H1"
        h1.from_stage = None
        h1.to_stage   = BanquetStage.LEAD.value
        h1.changed_by = "system"
        h1.changed_at = datetime(2026, 1, 1, 10, 0)
        h1.reason     = "初始化"
        h1.metadata_  = {}

        h2 = MagicMock(spec=BanquetStageHistory)
        h2.id         = "H2"
        h2.from_stage = BanquetStage.LEAD.value
        h2.to_stage   = BanquetStage.INTENT.value
        h2.changed_by = "mgr_01"
        h2.changed_at = datetime(2026, 1, 2, 14, 0)
        h2.reason     = "客户表示有意向"
        h2.metadata_  = {}

        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [h1, h2]
        db.execute.return_value = exec_result

        svc     = BanquetLifecycleService(db)
        history = await svc.get_stage_history("RES001")

        assert len(history) == 2
        assert history[0]["to_stage"]   == BanquetStage.LEAD.value
        assert history[1]["from_stage"] == BanquetStage.LEAD.value
        assert history[1]["changed_by"] == "mgr_01"

    @pytest.mark.asyncio
    async def test_empty_history(self):
        db = AsyncMock(spec=AsyncSession)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        db.execute.return_value = exec_result

        svc     = BanquetLifecycleService(db)
        history = await svc.get_stage_history("RES_UNKNOWN")
        assert history == []


# ── stage_transitions completeness ────────────────────────────────────────────

class TestStageTransitionsCompleteness:
    """Verify STAGE_TRANSITIONS covers all non-terminal stages."""

    def test_all_active_stages_have_transitions(self):
        terminal = {BanquetStage.COMPLETED, BanquetStage.CANCELLED}
        for stage in BanquetStage:
            if stage in terminal:
                assert stage.value not in STAGE_TRANSITIONS or STAGE_TRANSITIONS[stage.value] == [], \
                    f"Terminal stage {stage} should have no outgoing transitions"
            else:
                assert stage.value in STAGE_TRANSITIONS, \
                    f"Active stage {stage} missing from STAGE_TRANSITIONS"
                assert len(STAGE_TRANSITIONS[stage.value]) > 0, \
                    f"Active stage {stage} has empty transitions"

    def test_cancelled_reachable_from_any_active_stage(self):
        active = [s for s in BanquetStage
                  if s not in (BanquetStage.COMPLETED, BanquetStage.CANCELLED)]
        for stage in active:
            allowed_values = [
                s.value if isinstance(s, BanquetStage) else s
                for s in STAGE_TRANSITIONS.get(stage.value, [])
            ]
            assert BanquetStage.CANCELLED.value in allowed_values, \
                f"CANCELLED not reachable from {stage}"
