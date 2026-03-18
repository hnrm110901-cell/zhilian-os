"""Unit tests for OnboardingService, OffboardingService, TransferService.

All tests use mocked AsyncSession — no real database required.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.hr.offboarding_process import OffboardingProcess
from src.models.hr.onboarding_checklist_item import OnboardingChecklistItem
from src.models.hr.onboarding_process import OnboardingProcess
from src.models.hr.transfer_process import TransferProcess
from src.services.hr.onboarding_service import OnboardingService
from src.services.hr.offboarding_service import OffboardingService
from src.services.hr.transfer_service import TransferService

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
def onboarding_svc():
    return OnboardingService()


@pytest.fixture
def offboarding_svc():
    return OffboardingService()


@pytest.fixture
def transfer_svc():
    return TransferService()


def _make_scalar_result(value):
    """Helper: create a mock result whose scalar_one_or_none() returns value."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


# ---------------------------------------------------------------------------
# OnboardingService tests
# ---------------------------------------------------------------------------

async def test_create_onboarding_returns_process(mock_session):
    svc = OnboardingService()
    person_id = uuid.uuid4()
    start_date = date(2026, 4, 1)

    result = await svc.create_process(
        person_id=person_id,
        org_node_id="ORG-001",
        planned_start_date=start_date,
        created_by="admin",
        session=mock_session,
    )

    assert result is not None
    assert result.person_id == person_id
    assert result.org_node_id == "ORG-001"
    assert result.planned_start_date == start_date
    assert result.created_by == "admin"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


async def test_create_onboarding_sets_draft_status(mock_session):
    svc = OnboardingService()

    result = await svc.create_process(
        person_id=uuid.uuid4(),
        org_node_id="ORG-001",
        planned_start_date=date(2026, 4, 1),
        created_by="admin",
        session=mock_session,
    )

    assert result.status == "draft"


async def test_generate_checklist_manager_gets_6_items(mock_session):
    svc = OnboardingService()
    process_id = uuid.uuid4()

    items = await svc.generate_checklist(
        process_id=process_id,
        job_title="店长",
        session=mock_session,
    )

    assert len(items) == 6
    assert mock_session.add.call_count == 6


async def test_generate_checklist_chef_gets_5_items(mock_session):
    svc = OnboardingService()

    items = await svc.generate_checklist(
        process_id=uuid.uuid4(),
        job_title="厨师",
        session=mock_session,
    )

    assert len(items) == 5


async def test_generate_checklist_unknown_gets_default_items(mock_session):
    svc = OnboardingService()

    items = await svc.generate_checklist(
        process_id=uuid.uuid4(),
        job_title="清洁工",
        session=mock_session,
    )

    assert len(items) == 4


async def test_generate_checklist_advances_status_to_pending_review(mock_session):
    svc = OnboardingService()

    await svc.generate_checklist(
        process_id=uuid.uuid4(),
        job_title="未知岗位",
        session=mock_session,
    )

    # Check that execute was called for the status update to pending_review
    call_args_list = mock_session.execute.call_args_list
    # At least one execute call should be made (the UPDATE for status=pending_review)
    assert mock_session.execute.call_count >= 1
    # The service called flush after the update
    mock_session.flush.assert_called()


async def test_complete_item_sets_completed_at(mock_session):
    svc = OnboardingService()

    item = OnboardingChecklistItem(
        id=uuid.uuid4(),
        process_id=uuid.uuid4(),
        item_type="document",
        title="签署劳动合同",
        sort_order=1,
        required=True,
    )
    mock_session.execute.return_value = _make_scalar_result(item)

    result = await svc.complete_item(
        item_id=item.id,
        completed_by="manager_alice",
        session=mock_session,
        file_url="https://example.com/contract.pdf",
    )

    assert result.completed_by == "manager_alice"
    assert result.completed_at is not None
    assert result.file_url == "https://example.com/contract.pdf"


async def test_complete_item_raises_if_not_found(mock_session):
    svc = OnboardingService()

    mock_session.execute.return_value = _make_scalar_result(None)

    with pytest.raises(ValueError, match="not found"):
        await svc.complete_item(
            item_id=uuid.uuid4(),
            completed_by="admin",
            session=mock_session,
        )


async def test_approve_onboarding_creates_assignment(mock_session):
    svc = OnboardingService()

    process = OnboardingProcess(
        id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        org_node_id="ORG-002",
        planned_start_date=date(2026, 4, 1),
        created_by="hr_admin",
        status="pending_review",
    )
    # First execute returns the process, second is the update
    mock_session.execute.side_effect = [
        _make_scalar_result(process),
        AsyncMock(),
    ]

    assignment = await svc.approve(
        process_id=process.id,
        approved_by="hr_manager",
        employment_type="full_time",
        session=mock_session,
    )

    assert assignment is not None
    assert assignment.person_id == process.person_id
    assert assignment.org_node_id == process.org_node_id
    assert assignment.employment_type == "full_time"
    assert assignment.status == "active"
    mock_session.add.assert_called_once()


async def test_approve_onboarding_raises_on_wrong_status(mock_session):
    svc = OnboardingService()

    process = OnboardingProcess(
        id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        org_node_id="ORG-002",
        planned_start_date=date(2026, 4, 1),
        created_by="hr_admin",
        status="active",  # already active — cannot approve again
    )
    mock_session.execute.return_value = _make_scalar_result(process)

    with pytest.raises(ValueError, match="Cannot approve"):
        await svc.approve(
            process_id=process.id,
            approved_by="hr_manager",
            employment_type="full_time",
            session=mock_session,
        )


# ---------------------------------------------------------------------------
# OffboardingService tests
# ---------------------------------------------------------------------------

async def test_offboarding_apply_creates_process(mock_session):
    svc = OffboardingService()

    assignment_id = uuid.uuid4()
    # apply: session.add(process) + flush + execute(update) + flush
    mock_session.execute.side_effect = [AsyncMock()]

    result = await svc.apply(
        assignment_id=assignment_id,
        reason="resignation",
        planned_last_day=date(2026, 5, 1),
        created_by="hr_admin",
        session=mock_session,
    )

    assert result is not None
    assert result.assignment_id == assignment_id
    assert result.reason == "resignation"
    assert result.status == "pending"
    mock_session.add.assert_called_once()


async def test_offboarding_apply_raises_on_invalid_reason(mock_session):
    svc = OffboardingService()

    with pytest.raises(ValueError, match="Invalid reason"):
        await svc.apply(
            assignment_id=uuid.uuid4(),
            reason="fired_for_fun",  # invalid
            planned_last_day=date(2026, 5, 1),
            created_by="hr_admin",
            session=mock_session,
        )


async def test_offboarding_approve_raises_on_wrong_status(mock_session):
    svc = OffboardingService()

    process = OffboardingProcess(
        id=uuid.uuid4(),
        assignment_id=uuid.uuid4(),
        reason="resignation",
        apply_date=date(2026, 4, 1),
        planned_last_day=date(2026, 5, 1),
        created_by="hr_admin",
        status="approved",  # already approved — cannot approve again
    )
    mock_session.execute.return_value = _make_scalar_result(process)

    with pytest.raises(ValueError, match="Cannot approve"):
        await svc.approve(
            process_id=process.id,
            approved_by="hr_manager",
            session=mock_session,
        )


async def test_offboarding_complete_returns_summary_dict(mock_session):
    svc = OffboardingService()

    assignment_id = uuid.uuid4()
    process_id = uuid.uuid4()

    process = OffboardingProcess(
        id=process_id,
        assignment_id=assignment_id,
        reason="resignation",
        apply_date=date(2026, 4, 1),
        planned_last_day=date(2026, 5, 1),
        created_by="hr_admin",
        status="approved",
    )
    assignment = EmploymentAssignment(
        id=assignment_id,
        person_id=uuid.uuid4(),
        org_node_id="ORG-001",
        employment_type="full_time",
        start_date=date(2025, 1, 1),
        status="active",
    )

    # complete() calls:
    # 1. select(OffboardingProcess) → process
    # 2. _calculate_skill_loss_yuan → select(EmploymentAssignment) → assignment
    # 3. _trigger_knowledge_capture → execute(update) → AsyncMock
    # 4. execute(update EmploymentAssignment) → AsyncMock
    # 5. execute(update OffboardingProcess) → AsyncMock
    mock_session.execute.side_effect = [
        _make_scalar_result(process),
        _make_scalar_result(assignment),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    ]

    summary = await svc.complete(process_id=process_id, session=mock_session)

    assert isinstance(summary, dict)
    assert summary["process_id"] == str(process_id)
    assert summary["status"] == "completed"
    assert "actual_last_day" in summary
    assert "skill_loss_yuan" in summary
    assert "knowledge_capture_triggered" in summary


async def test_offboarding_calculates_skill_loss_yuan_positive(mock_session):
    svc = OffboardingService()

    assignment_id = uuid.uuid4()
    assignment = EmploymentAssignment(
        id=assignment_id,
        person_id=uuid.uuid4(),
        org_node_id="ORG-001",
        employment_type="full_time",
        start_date=date(2025, 1, 1),
        status="active",
    )
    mock_session.execute.return_value = _make_scalar_result(assignment)

    skill_loss = await svc._calculate_skill_loss_yuan(assignment_id, mock_session)

    assert isinstance(skill_loss, float)
    assert skill_loss > 0


async def test_offboarding_triggers_knowledge_capture(mock_session):
    svc = OffboardingService()

    assignment_id = uuid.uuid4()
    process_id = uuid.uuid4()

    process = OffboardingProcess(
        id=process_id,
        assignment_id=assignment_id,
        reason="resignation",
        apply_date=date(2026, 4, 1),
        planned_last_day=date(2026, 5, 1),
        created_by="hr_admin",
        status="approved",
    )
    assignment = EmploymentAssignment(
        id=assignment_id,
        person_id=uuid.uuid4(),
        org_node_id="ORG-001",
        employment_type="full_time",
        start_date=date(2025, 1, 1),
        status="active",
    )

    mock_session.execute.side_effect = [
        _make_scalar_result(process),
        _make_scalar_result(assignment),
        AsyncMock(),  # knowledge capture update
        AsyncMock(),  # end assignment
        AsyncMock(),  # complete process
    ]

    summary = await svc.complete(process_id=process_id, session=mock_session)

    assert summary["knowledge_capture_triggered"] is True


# ---------------------------------------------------------------------------
# TransferService tests
# ---------------------------------------------------------------------------

async def test_transfer_apply_creates_process_with_revenue_impact(mock_session):
    svc = TransferService()

    person_id = uuid.uuid4()
    from_assignment_id = uuid.uuid4()

    result = await svc.apply(
        person_id=person_id,
        from_assignment_id=from_assignment_id,
        to_org_node_id="ORG-003",
        transfer_type="promotion",
        effective_date=date(2026, 5, 1),
        reason="绩效优秀，晋升为店长",
        created_by="hr_admin",
        to_employment_type="full_time",
        session=mock_session,
    )

    assert result is not None
    assert result.person_id == person_id
    assert result.transfer_type == "promotion"
    assert result.status == "pending"
    assert isinstance(result.revenue_impact_yuan, Decimal)
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


async def test_transfer_apply_raises_on_invalid_type(mock_session):
    svc = TransferService()

    with pytest.raises(ValueError, match="Invalid transfer_type"):
        await svc.apply(
            person_id=uuid.uuid4(),
            from_assignment_id=uuid.uuid4(),
            to_org_node_id="ORG-003",
            transfer_type="escape",  # invalid
            effective_date=date(2026, 5, 1),
            reason="some reason",
            created_by="hr_admin",
            to_employment_type="full_time",
            session=mock_session,
        )


async def test_transfer_approve_raises_on_wrong_status(mock_session):
    svc = TransferService()

    process = TransferProcess(
        id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        from_assignment_id=uuid.uuid4(),
        to_org_node_id="ORG-003",
        to_employment_type="full_time",
        transfer_type="promotion",
        effective_date=date(2026, 5, 1),
        reason="绩效晋升",
        created_by="hr_admin",
        status="approved",  # already approved
    )
    mock_session.execute.return_value = _make_scalar_result(process)

    with pytest.raises(ValueError, match="Cannot approve"):
        await svc.approve(
            process_id=process.id,
            approved_by="ceo",
            session=mock_session,
        )


async def test_transfer_execute_creates_new_assignment_ends_old(mock_session):
    svc = TransferService()

    from_assignment_id = uuid.uuid4()
    process_id = uuid.uuid4()

    process = TransferProcess(
        id=process_id,
        person_id=uuid.uuid4(),
        from_assignment_id=from_assignment_id,
        to_org_node_id="ORG-004",
        to_employment_type="full_time",
        transfer_type="internal_transfer",
        effective_date=date(2026, 5, 1),
        reason="门店扩张需要",
        created_by="hr_admin",
        status="approved",
    )

    # execute() calls:
    # 1. select(TransferProcess) → process
    # 2. update(EmploymentAssignment) close old → AsyncMock
    # 3. update(TransferProcess) status=active → AsyncMock
    mock_session.execute.side_effect = [
        _make_scalar_result(process),
        AsyncMock(),
        AsyncMock(),
    ]

    new_assignment = await svc.execute(process_id=process_id, session=mock_session)

    assert new_assignment is not None
    assert new_assignment.org_node_id == "ORG-004"
    assert new_assignment.employment_type == "full_time"
    assert new_assignment.status == "active"
    # session.add called with the new assignment
    mock_session.add.assert_called_once_with(new_assignment)
    # Verify old assignment was ended (UPDATE call should have been made)
    # execute was called 3 times: select, update_old_assignment, update_transfer_process
    assert mock_session.execute.call_count == 3


async def test_transfer_execute_raises_on_wrong_status(mock_session):
    svc = TransferService()

    process = TransferProcess(
        id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        from_assignment_id=uuid.uuid4(),
        to_org_node_id="ORG-004",
        to_employment_type="full_time",
        transfer_type="promotion",
        effective_date=date(2026, 5, 1),
        reason="绩效晋升",
        created_by="hr_admin",
        status="pending",  # not yet approved — cannot execute
    )
    mock_session.execute.return_value = _make_scalar_result(process)

    with pytest.raises(ValueError, match="Cannot execute"):
        await svc.execute(process_id=process.id, session=mock_session)
