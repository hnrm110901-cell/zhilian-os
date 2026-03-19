"""Unit tests for AttendanceService + LeaveService.

All tests use mocked AsyncSession — no real database required.
"""
import uuid
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.hr.attendance_service import AttendanceService
from src.services.hr.leave_service import LeaveService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def att_svc():
    return AttendanceService()


@pytest.fixture
def leave_svc():
    return LeaveService()


def _make_scalar_result(value):
    """Helper: mock result whose scalar_one_or_none() returns value."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


def _make_scalars_result(values):
    """Helper: mock result whose scalars().all() returns values."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = values
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_clock(clock_type: str, hour: int, minute: int = 0,
                target_date: date | None = None, is_anomaly: bool = False,
                source: str = "manual") -> MagicMock:
    """Create a mock ClockRecord with clock_type, clock_time, source, is_anomaly."""
    d = target_date or date(2026, 3, 10)
    mock = MagicMock()
    mock.clock_type = clock_type
    mock.clock_time = datetime.combine(d, time(hour, minute), tzinfo=timezone.utc)
    mock.source = source
    mock.is_anomaly = is_anomaly
    return mock


# ---------------------------------------------------------------------------
# AttendanceService — record_clock
# ---------------------------------------------------------------------------

async def test_record_clock_creates_record(att_svc, mock_session):
    aid = uuid.uuid4()
    ct = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)
    record = await att_svc.record_clock(aid, "in", ct, "manual", mock_session)
    mock_session.add.assert_called_once()
    assert record.clock_type == "in"
    assert record.is_anomaly is False


async def test_record_clock_marks_anomaly_at_2am(att_svc, mock_session):
    aid = uuid.uuid4()
    ct = datetime(2026, 3, 10, 2, 30, tzinfo=timezone.utc)
    record = await att_svc.record_clock(aid, "in", ct, "wechat_work", mock_session)
    assert record.is_anomaly is True


async def test_record_clock_raises_on_invalid_type(att_svc, mock_session):
    with pytest.raises(ValueError, match="Invalid clock_type"):
        await att_svc.record_clock(
            uuid.uuid4(), "lunch", datetime.now(timezone.utc), "manual", mock_session
        )


async def test_record_clock_raises_on_invalid_source(att_svc, mock_session):
    with pytest.raises(ValueError, match="Invalid source"):
        await att_svc.record_clock(
            uuid.uuid4(), "in", datetime.now(timezone.utc), "gps_tracker", mock_session
        )


# ---------------------------------------------------------------------------
# AttendanceService — _compute_attendance (pure function)
# ---------------------------------------------------------------------------

async def test_compute_attendance_no_records_absent(att_svc):
    status, work, late, early, ot = att_svc._compute_attendance([], date(2026, 3, 10))
    assert status == "absent"
    assert work == 0


async def test_compute_attendance_normal(att_svc):
    """in 09:00 + out 22:00 → 13h work, on time, no early leave → overtime (full shift)
    For true 'normal': in 14:00 + out 22:00 = 480 min exactly, no late (after threshold), no early."""
    records = [
        _make_clock("in", 9, 0),
        _make_clock("out", 22, 0),
    ]
    status, work, late, early, ot = att_svc._compute_attendance(records, date(2026, 3, 10))
    # Full shift: 9:00-22:00 = 780 min, no late, no early leave → overtime
    assert status == "overtime"
    assert work == 780
    assert late == 0
    assert early == 0
    assert ot == 300  # 780 - 480


async def test_compute_attendance_late(att_svc):
    """in 09:30 + out 22:00 → late (30 min past threshold)"""
    records = [
        _make_clock("in", 9, 30),
        _make_clock("out", 22, 0),
    ]
    status, work, late, early, ot = att_svc._compute_attendance(records, date(2026, 3, 10))
    assert status == "late"
    assert late == 30


async def test_compute_attendance_early_leave(att_svc):
    """in 09:00 + out 18:00 → early_leave (left 4h before 22:00)"""
    records = [
        _make_clock("in", 9, 0),
        _make_clock("out", 18, 0),
    ]
    status, work, late, early, ot = att_svc._compute_attendance(records, date(2026, 3, 10))
    assert status == "early_leave"
    # out at 18:00 vs scheduled end 22:00 → 240 min early
    assert early == 240
    assert work == 540


async def test_compute_attendance_overtime(att_svc):
    """in 09:00 + out 23:00 → 14h work → overtime (no late, no early leave)"""
    records = [
        _make_clock("in", 9, 0),
        _make_clock("out", 23, 0),
    ]
    status, work, late, early, ot = att_svc._compute_attendance(records, date(2026, 3, 10))
    assert status == "overtime"
    assert work == 840  # 14 hours
    assert ot == 360  # 840 - 480
    assert early == 0  # left after 22:00


# ---------------------------------------------------------------------------
# AttendanceService — get_monthly_summary
# ---------------------------------------------------------------------------

async def test_monthly_summary_returns_correct_counts(att_svc, mock_session):
    # Simulate 3 daily attendance rows
    row_normal = MagicMock(status="normal", work_minutes=540, overtime_minutes=60)
    row_late = MagicMock(status="late", work_minutes=480, overtime_minutes=0)
    row_absent = MagicMock(status="absent", work_minutes=0, overtime_minutes=0)

    mock_session.execute = AsyncMock(return_value=_make_scalars_result(
        [row_normal, row_late, row_absent]
    ))

    aid = uuid.uuid4()
    summary = await att_svc.get_monthly_summary(aid, 2026, 3, mock_session)

    assert summary["total_days"] == 3
    assert summary["normal_days"] == 1
    assert summary["late_count"] == 1
    assert summary["absent_count"] == 1
    assert summary["total_work_hours"] == round((540 + 480 + 0) / 60, 1)


# ---------------------------------------------------------------------------
# AttendanceService — detect_anomalies
# ---------------------------------------------------------------------------

async def test_detect_anomalies_returns_list(att_svc, mock_session):
    anomaly = _make_clock("in", 2, 30, is_anomaly=True, source="wechat_work")
    mock_session.execute = AsyncMock(return_value=_make_scalars_result([anomaly]))

    aid = uuid.uuid4()
    msgs = await att_svc.detect_anomalies(aid, date(2026, 3, 10), mock_session)
    assert len(msgs) == 1
    assert "异常打卡" in msgs[0]
    assert "02:30" in msgs[0]


# ---------------------------------------------------------------------------
# LeaveService — apply
# ---------------------------------------------------------------------------

async def test_leave_apply_creates_request(leave_svc, mock_session):
    aid = uuid.uuid4()
    start = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)

    req = await leave_svc.apply(aid, "annual", start, end, 1.0, "休息", "张三", mock_session)
    mock_session.add.assert_called_once()
    assert req.leave_type == "annual"
    assert req.status == "pending"
    assert req.days == Decimal("1.0")


async def test_leave_apply_raises_on_invalid_type(leave_svc, mock_session):
    start = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Invalid leave_type"):
        await leave_svc.apply(uuid.uuid4(), "vacation", start, end, 1.0, "r", "u", mock_session)


# ---------------------------------------------------------------------------
# LeaveService — approve
# ---------------------------------------------------------------------------

async def test_leave_approve_deducts_balance(leave_svc, mock_session):
    aid = uuid.uuid4()
    req_id = uuid.uuid4()

    # Mock the leave request
    mock_request = MagicMock()
    mock_request.id = req_id
    mock_request.status = "pending"
    mock_request.assignment_id = aid
    mock_request.leave_type = "annual"
    mock_request.days = Decimal("2.0")
    mock_request.start_datetime = datetime(2026, 3, 15, tzinfo=timezone.utc)

    # Mock the balance
    mock_balance = MagicMock()
    mock_balance.total_days = Decimal("5.0")
    mock_balance.used_days = Decimal("1.0")
    mock_balance.remaining_days = Decimal("4.0")

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalar_result(mock_request),   # fetch request
        _make_scalar_result(mock_balance),   # fetch balance
    ])

    result = await leave_svc.approve(req_id, "李经理", mock_session)
    assert result.status == "approved"
    assert result.approved_by == "李经理"
    assert mock_balance.used_days == Decimal("3.0")
    assert mock_balance.remaining_days == Decimal("2.0")


async def test_leave_approve_raises_when_insufficient(leave_svc, mock_session):
    aid = uuid.uuid4()
    req_id = uuid.uuid4()

    mock_request = MagicMock()
    mock_request.id = req_id
    mock_request.status = "pending"
    mock_request.assignment_id = aid
    mock_request.leave_type = "annual"
    mock_request.days = Decimal("5.0")
    mock_request.start_datetime = datetime(2026, 3, 15, tzinfo=timezone.utc)

    mock_balance = MagicMock()
    mock_balance.total_days = Decimal("5.0")
    mock_balance.used_days = Decimal("3.0")
    mock_balance.remaining_days = Decimal("2.0")

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalar_result(mock_request),
        _make_scalar_result(mock_balance),
    ])

    with pytest.raises(ValueError, match="余额不足"):
        await leave_svc.approve(req_id, "李经理", mock_session)


# ---------------------------------------------------------------------------
# LeaveService — accrue_annual_leave
# ---------------------------------------------------------------------------

async def test_leave_accrue_creates_balance(leave_svc, mock_session):
    aid = uuid.uuid4()
    # get_balance returns None (no existing balance)
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

    balance = await leave_svc.accrue_annual_leave(aid, 2026, mock_session)
    mock_session.add.assert_called_once()
    assert balance.total_days == Decimal("5.0")
    assert balance.remaining_days == Decimal("5.0")
    assert balance.used_days == Decimal("0")


# ---------------------------------------------------------------------------
# LeaveService — simulate
# ---------------------------------------------------------------------------

async def test_leave_simulate_sufficient(leave_svc, mock_session):
    mock_balance = MagicMock()
    mock_balance.remaining_days = Decimal("4.0")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_balance))

    result = await leave_svc.simulate(uuid.uuid4(), "annual", 2.0, 2026, mock_session)
    assert result["sufficient"] is True
    assert result["shortfall"] == 0


async def test_leave_simulate_insufficient(leave_svc, mock_session):
    mock_balance = MagicMock()
    mock_balance.remaining_days = Decimal("1.0")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_balance))

    result = await leave_svc.simulate(uuid.uuid4(), "annual", 3.0, 2026, mock_session)
    assert result["sufficient"] is False
    assert result["shortfall"] == 2.0
