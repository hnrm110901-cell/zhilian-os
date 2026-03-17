import pytest
from src.services.lifecycle_action_service import LifecycleActionService


@pytest.fixture
def svc():
    return LifecycleActionService()


def test_vip_upgrade_generates_welcome(svc):
    action = svc.get_action("HIGH_FREQUENCY", "VIP", "S001", "C001")
    assert action is not None
    assert action["type"] == "wechat_push"
    assert action["template"] == "vip_welcome"
    assert action["priority"] == "high"
    assert action["store_id"] == "S001"


def test_at_risk_generates_retention(svc):
    action = svc.get_action("VIP", "AT_RISK", "S001", "C001")
    assert action["type"] == "journey_trigger"
    assert action["journey"] == "vip_retention"


def test_no_action_for_same_state(svc):
    action = svc.get_action("REPEAT", "REPEAT", "S001", "C001")
    assert action is None


def test_dormant_generates_reactivation(svc):
    action = svc.get_action("AT_RISK", "DORMANT", "S001", "C001")
    assert action["type"] == "journey_trigger"
    assert action["journey"] == "dormant_reactivation"


def test_repeat_celebration(svc):
    action = svc.get_action("FIRST_ORDER_PENDING", "REPEAT", "S001", "C001")
    assert action["type"] == "wechat_push"
    assert action["template"] == "repeat_celebration"


def test_unknown_transition_returns_none(svc):
    action = svc.get_action("LEAD", "LOST", "S001", "C001")
    assert action is None
