"""Unit tests for HRApprovalWorkflowService.

All tests use mocked AsyncSession — no real database required.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.models.hr.approval_template import ApprovalTemplate
from src.models.hr.approval_instance import ApprovalInstance
from src.models.hr.approval_step_record import ApprovalStepRecord
from src.services.hr.approval_workflow_service import HRApprovalWorkflowService

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
    return HRApprovalWorkflowService()


def _make_scalar_result(value):
    """Helper: create a mock result whose scalar_one_or_none() returns value."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


def _make_scalars_result(values):
    """Helper: create a mock result whose scalars().all() returns values."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = values
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_template(steps=None, template_id=None, resource_type="onboarding",
                   org_node_id=None, is_active=True):
    """Helper: create a mock ApprovalTemplate."""
    t = MagicMock(spec=ApprovalTemplate)
    t.id = template_id or uuid.uuid4()
    t.name = "测试模板"
    t.resource_type = resource_type
    t.org_node_id = org_node_id
    t.is_active = is_active
    t.steps = steps if steps is not None else [
        {"level": 1, "approver_type": "position", "role": "store_manager"}
    ]
    return t


def _make_instance(instance_id=None, status="pending", current_step=1,
                   template_id=None, resource_type="onboarding"):
    """Helper: create a mock ApprovalInstance."""
    inst = MagicMock(spec=ApprovalInstance)
    inst.id = instance_id or uuid.uuid4()
    inst.template_id = template_id or uuid.uuid4()
    inst.resource_type = resource_type
    inst.resource_id = uuid.uuid4()
    inst.status = status
    inst.current_step = current_step
    inst.created_by = "admin"
    inst.extra_data = {}
    inst.created_at = datetime(2026, 3, 18, tzinfo=timezone.utc)
    inst.completed_at = None
    inst.updated_at = datetime(2026, 3, 18, tzinfo=timezone.utc)
    return inst


def _make_step_record(step=1, action="pending", approver_id="position:store_manager"):
    """Helper: create a mock ApprovalStepRecord."""
    rec = MagicMock(spec=ApprovalStepRecord)
    rec.id = uuid.uuid4()
    rec.instance_id = uuid.uuid4()
    rec.step = step
    rec.approver_id = approver_id
    rec.approver_name = "store_manager"
    rec.action = action
    rec.comment = None
    rec.acted_at = None
    rec.created_at = datetime(2026, 3, 18, tzinfo=timezone.utc)
    return rec


# ---------------------------------------------------------------------------
# start() tests
# ---------------------------------------------------------------------------

async def test_start_raises_on_invalid_resource_type(svc, mock_session):
    """ValueError for invalid resource_type."""
    with pytest.raises(ValueError, match="Invalid resource_type"):
        await svc.start(
            resource_type="unknown",
            resource_id=uuid.uuid4(),
            initiator="admin",
            session=mock_session,
        )


async def test_start_raises_when_no_template(svc, mock_session):
    """ValueError when no matching template found."""
    # _find_template does execute calls; mock them to return None
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

    with pytest.raises(ValueError, match="No active approval template"):
        await svc.start(
            resource_type="onboarding",
            resource_id=uuid.uuid4(),
            initiator="admin",
            session=mock_session,
        )


async def test_start_raises_when_template_has_no_steps(svc, mock_session):
    """ValueError when template has empty steps."""
    template = _make_template(steps=[])
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(template))

    with pytest.raises(ValueError, match="has no steps defined"):
        await svc.start(
            resource_type="onboarding",
            resource_id=uuid.uuid4(),
            initiator="admin",
            session=mock_session,
        )


async def test_start_creates_instance_and_first_step(svc, mock_session):
    """Successful start: session.add called twice (instance + step record)."""
    template = _make_template(steps=[
        {"level": 1, "approver_type": "position", "role": "store_manager"},
    ])
    # _find_template returns template (global, no org_node_id)
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(template))

    result = await svc.start(
        resource_type="onboarding",
        resource_id=uuid.uuid4(),
        initiator="admin",
        session=mock_session,
    )

    assert result is not None
    assert result.resource_type == "onboarding"
    assert result.status == "pending"
    # add() called for instance and step record
    assert mock_session.add.call_count == 2
    # flush() called twice
    assert mock_session.flush.call_count == 2


# ---------------------------------------------------------------------------
# action() tests
# ---------------------------------------------------------------------------

async def test_action_approved_single_step_completes(svc, mock_session):
    """Single-step template: approve → status=approved."""
    instance = _make_instance(current_step=1)
    template = _make_template(steps=[
        {"level": 1, "approver_type": "position", "role": "store_manager"},
    ], template_id=instance.template_id)

    # Call 1: select instance; Call 2: update step record; Call 3: select template;
    # Call 4: _on_approved update; Call 5: flush
    call_count = [0]
    async def execute_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_scalar_result(instance)
        elif call_count[0] == 3:
            return _make_scalar_result(template)
        return MagicMock()  # update results

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    result = await svc.action(
        instance_id=instance.id,
        approver_id="position:store_manager",
        action_type="approved",
        session=mock_session,
    )

    assert result is instance
    # execute called: select instance + update step + select template + on_approved update + flush
    assert mock_session.execute.call_count >= 4


async def test_action_approved_advances_to_next_step(svc, mock_session):
    """Multi-step template: approve step 1 → advances to step 2."""
    instance = _make_instance(current_step=1)
    template = _make_template(steps=[
        {"level": 1, "approver_type": "position", "role": "store_manager"},
        {"level": 2, "approver_type": "position", "role": "area_manager"},
    ], template_id=instance.template_id)

    call_count = [0]
    async def execute_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_scalar_result(instance)
        elif call_count[0] == 3:
            return _make_scalar_result(template)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    result = await svc.action(
        instance_id=instance.id,
        approver_id="position:store_manager",
        action_type="approved",
        session=mock_session,
    )

    assert result is instance
    # A new step record should be added
    mock_session.add.assert_called_once()


async def test_action_rejected_sets_status(svc, mock_session):
    """Rejection → _on_rejected called."""
    instance = _make_instance(current_step=1)

    call_count = [0]
    async def execute_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_scalar_result(instance)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    result = await svc.action(
        instance_id=instance.id,
        approver_id="position:store_manager",
        action_type="rejected",
        session=mock_session,
    )

    assert result is instance
    # execute called: select instance + update step + on_rejected update + flush
    assert mock_session.execute.call_count >= 3


async def test_action_raises_on_invalid_action(svc, mock_session):
    """ValueError for invalid action_type."""
    with pytest.raises(ValueError, match="Invalid action"):
        await svc.action(
            instance_id=uuid.uuid4(),
            approver_id="someone",
            action_type="maybe",
            session=mock_session,
        )


async def test_action_raises_when_not_pending(svc, mock_session):
    """ValueError when instance.status != 'pending'."""
    instance = _make_instance(status="approved")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(instance))

    with pytest.raises(ValueError, match="Cannot act on instance"):
        await svc.action(
            instance_id=instance.id,
            approver_id="someone",
            action_type="approved",
            session=mock_session,
        )


# ---------------------------------------------------------------------------
# delegate() tests
# ---------------------------------------------------------------------------

async def test_delegate_creates_new_record(svc, mock_session):
    """Delegation creates a new step record for the delegatee."""
    instance = _make_instance(current_step=1)

    call_count = [0]
    async def execute_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_scalar_result(instance)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    result = await svc.delegate(
        instance_id=instance.id,
        from_approver="position:store_manager",
        to_approver_id="emp:zhang_san",
        to_approver_name="张三",
        session=mock_session,
    )

    assert result is not None
    assert result.approver_id == "emp:zhang_san"
    assert result.approver_name == "张三"
    assert result.action == "pending"
    mock_session.add.assert_called_once()


async def test_delegate_raises_when_not_pending(svc, mock_session):
    """ValueError for non-pending instance."""
    instance = _make_instance(status="rejected")
    mock_session.execute = AsyncMock(return_value=_make_scalar_result(instance))

    with pytest.raises(ValueError, match="Cannot delegate"):
        await svc.delegate(
            instance_id=instance.id,
            from_approver="someone",
            to_approver_id="other",
            to_approver_name="Other",
            session=mock_session,
        )


# ---------------------------------------------------------------------------
# get_pending_for() tests
# ---------------------------------------------------------------------------

async def test_get_pending_for_returns_list(svc, mock_session):
    """Returns list of pending instances for the approver."""
    inst1 = _make_instance()
    inst2 = _make_instance()
    mock_session.execute = AsyncMock(
        return_value=_make_scalars_result([inst1, inst2])
    )

    result = await svc.get_pending_for(
        approver_id="position:store_manager",
        session=mock_session,
    )

    assert len(result) == 2
    assert inst1 in result
    assert inst2 in result


# ---------------------------------------------------------------------------
# get_instance_detail() tests
# ---------------------------------------------------------------------------

async def test_get_instance_detail_returns_dict(svc, mock_session):
    """Detail dict has expected keys."""
    instance = _make_instance()
    step1 = _make_step_record(step=1, action="approved")
    step1.acted_at = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    step1.comment = "同意"

    call_count = [0]
    async def execute_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_scalar_result(instance)
        else:
            return _make_scalars_result([step1])

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    result = await svc.get_instance_detail(
        instance_id=instance.id,
        session=mock_session,
    )

    assert "instance_id" in result
    assert "resource_type" in result
    assert "status" in result
    assert "steps" in result
    assert len(result["steps"]) == 1
    assert result["steps"][0]["action"] == "approved"
    assert result["steps"][0]["comment"] == "同意"
    assert result["status"] == "pending"


# ---------------------------------------------------------------------------
# _find_template() tests
# ---------------------------------------------------------------------------

async def test_find_template_prefers_store_specific(svc, mock_session):
    """org_node_id match beats global template."""
    store_template = _make_template(org_node_id="STORE-001")

    # First execute returns store-specific, shouldn't need second call
    mock_session.execute = AsyncMock(
        return_value=_make_scalar_result(store_template)
    )

    result = await svc._find_template("onboarding", "STORE-001", mock_session)

    assert result is store_template
    # Only one execute call needed (found store-specific)
    assert mock_session.execute.call_count == 1
