"""Unit tests for PayrollService.

All tests use mocked AsyncSession — no real database required.
"""
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.hr.payroll_service import PayrollService

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
def svc():
    return PayrollService()


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


def _make_batch(
    batch_id=None, org_node_id="ORG-001", year=2026, month=3, status="draft",
):
    batch = MagicMock()
    batch.id = batch_id or uuid.uuid4()
    batch.org_node_id = org_node_id
    batch.period_year = year
    batch.period_month = month
    batch.status = status
    batch.total_gross_fen = 0
    batch.total_net_fen = 0
    batch.approved_by = None
    return batch


def _make_assignment(asn_id=None, org_node_id="ORG-001"):
    asn = MagicMock()
    asn.id = asn_id or uuid.uuid4()
    asn.org_node_id = org_node_id
    asn.status = "active"
    return asn


def _make_attendance(status="normal", overtime_minutes=0):
    att = MagicMock()
    att.status = status
    att.overtime_minutes = overtime_minutes
    return att


def _make_contract(pay_scheme=None):
    """Helper: mock EmploymentContract with pay_scheme."""
    contract = MagicMock()
    contract.pay_scheme = pay_scheme or {"type": "fixed_monthly", "base_salary_fen": 400000}
    return contract


def _make_ytd_result(value=0):
    """Helper: mock scalar result for YTD taxable query."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = value
    return mock_result


def _make_payroll_item(
    item_id=None, batch_id=None, assignment_id=None,
    base=400000, overtime=0, deduction_late=0, deduction_absent=0,
    gross=400000, net=400000,
    social=0, tax=0,
    viewed_at=None, view_expires_at=None,
):
    item = MagicMock()
    item.id = item_id or uuid.uuid4()
    item.batch_id = batch_id or uuid.uuid4()
    item.assignment_id = assignment_id or uuid.uuid4()
    item.base_salary_fen = base
    item.overtime_fen = overtime
    item.deduction_late_fen = deduction_late
    item.deduction_absent_fen = deduction_absent
    item.gross_fen = gross
    item.net_fen = net
    item.social_insurance_fen = social
    item.tax_fen = tax
    item.viewed_at = viewed_at
    item.view_expires_at = view_expires_at
    return item


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_create_batch_returns_draft(svc, mock_session):
    batch = await svc.create_batch("ORG-001", 2026, 3, "admin", mock_session)
    assert batch.status == "draft"
    assert batch.org_node_id == "ORG-001"
    assert batch.period_year == 2026
    assert batch.period_month == 3
    mock_session.add.assert_called_once()
    mock_session.flush.assert_awaited_once()


async def test_calculate_raises_when_batch_not_found(svc, mock_session):
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))
    with pytest.raises(ValueError, match="not found"):
        await svc.calculate(uuid.uuid4(), mock_session)


async def test_calculate_raises_when_wrong_status(svc, mock_session):
    batch = _make_batch(status="approved")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(batch))
    with pytest.raises(ValueError, match="Cannot calculate"):
        await svc.calculate(batch.id, mock_session)


async def test_calculate_returns_items(svc, mock_session):
    batch = _make_batch()
    asn = _make_assignment()
    contract = _make_contract()
    att_rows = [
        _make_attendance("normal", 0),
        _make_attendance("normal", 0),
    ]

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalar_result(batch),       # select batch
        _make_scalars_result([asn]),       # select assignments
        _make_scalar_result(contract),    # select contract
        _make_scalars_result(att_rows),   # select attendance
        _make_ytd_result(0),              # YTD taxable
    ])

    items = await svc.calculate(batch.id, mock_session)
    assert len(items) == 1
    assert items[0].base_salary_fen == 400000
    assert batch.status == "review"


async def test_calculate_overtime_fen_positive(svc, mock_session):
    batch = _make_batch()
    asn = _make_assignment()
    contract = _make_contract()
    # 120 min overtime = 2h => 2 * 2500 = 5000 fen
    att_rows = [_make_attendance("normal", 120)]

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalar_result(batch),
        _make_scalars_result([asn]),
        _make_scalar_result(contract),
        _make_scalars_result(att_rows),
        _make_ytd_result(0),
    ])

    items = await svc.calculate(batch.id, mock_session)
    assert items[0].overtime_fen == 5000


async def test_calculate_deductions_applied(svc, mock_session):
    batch = _make_batch()
    asn = _make_assignment()
    contract = _make_contract()
    att_rows = [
        _make_attendance("late", 0),
        _make_attendance("absent", 0),
        _make_attendance("late", 0),
    ]

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalar_result(batch),
        _make_scalars_result([asn]),
        _make_scalar_result(contract),
        _make_scalars_result(att_rows),
        _make_ytd_result(0),
    ])

    items = await svc.calculate(batch.id, mock_session)
    # 2 late * 5000 + 1 absent * 20000 = 30000
    assert items[0].deduction_late_fen == 10000
    assert items[0].deduction_absent_fen == 20000


async def test_calculate_gross_not_negative(svc, mock_session):
    """大量缺勤时gross不为负"""
    batch = _make_batch()
    asn = _make_assignment()
    contract = _make_contract()
    # 30 absent days => 30 * 20000 = 600000 > 400000 base
    att_rows = [_make_attendance("absent", 0) for _ in range(30)]

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalar_result(batch),
        _make_scalars_result([asn]),
        _make_scalar_result(contract),
        _make_scalars_result(att_rows),
        _make_ytd_result(0),
    ])

    items = await svc.calculate(batch.id, mock_session)
    assert items[0].gross_fen == 0


async def test_approve_sets_status_and_approver(svc, mock_session):
    batch = _make_batch(status="review")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(batch))

    result = await svc.approve(batch.id, "boss-001", mock_session)
    assert result.status == "approved"
    assert result.approved_by == "boss-001"


async def test_approve_raises_when_wrong_status(svc, mock_session):
    batch = _make_batch(status="draft")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(batch))
    with pytest.raises(ValueError, match="Cannot approve"):
        await svc.approve(batch.id, "boss", mock_session)


async def test_get_payslip_returns_yuan_values(svc, mock_session):
    item = _make_payroll_item(
        base=400000, overtime=5000, deduction_late=10000, deduction_absent=20000,
        gross=375000, net=375000, social=0, tax=0,
    )
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(item))

    result = await svc.get_payslip(item.id, "viewer-1", mock_session)
    assert result["base_salary_yuan"] == 4000.0
    assert result["overtime_yuan"] == 50.0
    assert result["deduction_late_yuan"] == 100.0
    assert result["gross_yuan"] == 3750.0
    assert result["net_yuan"] == 3750.0


async def test_get_payslip_expired(svc, mock_session):
    item = _make_payroll_item(
        view_expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(item))

    result = await svc.get_payslip(item.id, "viewer-1", mock_session)
    assert result["expired"] is True


async def test_allocate_cost_splits_by_ratio(svc, mock_session):
    batch_id = uuid.uuid4()
    asn_id = uuid.uuid4()
    item = _make_payroll_item(batch_id=batch_id, assignment_id=asn_id, gross=100000)

    alloc_a = MagicMock()
    alloc_a.org_node_id = "STORE-A"
    alloc_a.ratio = Decimal("0.600")

    alloc_b = MagicMock()
    alloc_b.org_node_id = "STORE-B"
    alloc_b.ratio = Decimal("0.400")

    mock_session.execute = AsyncMock(side_effect=[
        _make_scalars_result([item]),             # select payroll_items
        _make_scalars_result([alloc_a, alloc_b]), # select cost_allocations
    ])

    result = await svc.allocate_cost(batch_id, mock_session)
    allocs = result["allocations"]
    assert len(allocs) == 2
    store_a = next(a for a in allocs if a["org_node_id"] == "STORE-A")
    store_b = next(a for a in allocs if a["org_node_id"] == "STORE-B")
    assert store_a["total_fen"] == 60000
    assert store_b["total_fen"] == 40000
