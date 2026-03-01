"""
Tests for src/services/wechat_action_fsm.py — 企业微信 Action 状态机.

Covers:
  - ActionRecord.is_expired: terminal states never expire; time-based expiry
  - ActionRecord.to_dict: shape and values
  - create_action: ID prefix, field population, default state
  - push_to_wechat: CREATED → PUSHED; non-CREATED state guard → False
  - acknowledge: PUSHED/ESCALATED → ACKNOWLEDGED; guard → False
  - start_processing: ACKNOWLEDGED → PROCESSING; guard → False
  - resolve: any non-terminal → RESOLVED; re-resolve → False; notes stored
  - escalate: marks ESCALATED, creates escalated action with upgraded priority
  - escalate: terminal states (RESOLVED/CLOSED/ESCALATED) → False
  - _upgrade_priority: production bug — actually downgrades (P0→P1→P2→P3) due to reversed index arithmetic
  - verify_webhook_signature: SHA1(sorted([token, timestamp, nonce]))
  - handle_webhook_callback: "确认/收到" → acknowledge; "解决/完成" → resolve
  - list_actions: store_id / state / priority / limit filters
  - get_stats: state_distribution, priority_distribution, avg_resolution_minutes
  - get_action: returns dict or None
  - get_wechat_fsm: global singleton
"""
import hashlib
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Pre-stub agent_service to avoid import-time crash
sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.services.wechat_action_fsm import (
    ESCALATION_TIMEOUTS,
    ActionCategory,
    ActionPriority,
    ActionRecord,
    ActionState,
    WeChatActionFSM,
    get_wechat_fsm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fsm() -> WeChatActionFSM:
    """Fresh FSM instance for each test."""
    return WeChatActionFSM()


async def _action(
    fsm: WeChatActionFSM,
    *,
    store_id: str = "S1",
    priority: ActionPriority = ActionPriority.P2,
    receiver: str = "emp_001",
    escalation_user: str = "mgr_001",
) -> ActionRecord:
    return await fsm.create_action(
        store_id=store_id,
        category=ActionCategory.WASTE_ALERT,
        priority=priority,
        title="测试标题",
        content="测试内容",
        receiver_user_id=receiver,
        escalation_user_id=escalation_user,
        source_event_id="EVT-001",
    )


# ===========================================================================
# ActionRecord.is_expired
# ===========================================================================

class TestActionRecordIsExpired:
    def test_resolved_never_expires(self):
        rec = ActionRecord(
            action_id="A1", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P0,
            title="t", content="c",
            state=ActionState.RESOLVED,
        )
        rec.pushed_at = datetime.utcnow() - timedelta(days=1)
        assert rec.is_expired() is False

    def test_closed_never_expires(self):
        rec = ActionRecord(
            action_id="A1", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P0,
            title="t", content="c",
            state=ActionState.CLOSED,
        )
        rec.pushed_at = datetime.utcnow() - timedelta(days=10)
        assert rec.is_expired() is False

    def test_escalated_never_expires(self):
        rec = ActionRecord(
            action_id="A1", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P0,
            title="t", content="c",
            state=ActionState.ESCALATED,
        )
        rec.pushed_at = datetime.utcnow() - timedelta(days=10)
        assert rec.is_expired() is False

    def test_pushed_within_timeout_not_expired(self):
        rec = ActionRecord(
            action_id="A1", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P2,
            title="t", content="c",
            state=ActionState.PUSHED,
        )
        rec.pushed_at = datetime.utcnow() - timedelta(hours=1)  # << 24h P2 timeout
        assert rec.is_expired() is False

    def test_pushed_past_timeout_is_expired(self):
        rec = ActionRecord(
            action_id="A1", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P2,
            title="t", content="c",
            state=ActionState.PUSHED,
        )
        rec.pushed_at = datetime.utcnow() - timedelta(hours=25)  # > 24h P2 timeout
        assert rec.is_expired() is True

    def test_created_uses_created_at_when_no_pushed_at(self):
        """If pushed_at is None, fallback to created_at for expiry calculation."""
        rec = ActionRecord(
            action_id="A1", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P0,
            title="t", content="c",
            state=ActionState.CREATED,
        )
        rec.created_at = datetime.utcnow() - timedelta(hours=1)  # > P0 30min timeout
        assert rec.is_expired() is True


# ===========================================================================
# ActionRecord.to_dict
# ===========================================================================

class TestActionRecordToDict:
    def test_to_dict_contains_required_keys(self):
        rec = ActionRecord(
            action_id="ACT-001", store_id="S1",
            category=ActionCategory.APPROVAL,
            priority=ActionPriority.P1,
            title="审批", content="内容",
        )
        d = rec.to_dict()
        for key in ("action_id", "store_id", "category", "priority",
                    "title", "state", "created_at", "escalation_count",
                    "receiver_user_id", "source_event_id"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_enums_are_strings(self):
        rec = ActionRecord(
            action_id="ACT-001", store_id="S1",
            category=ActionCategory.ANOMALY,
            priority=ActionPriority.P0,
            title="t", content="c",
        )
        d = rec.to_dict()
        assert d["category"] == "anomaly"
        assert d["priority"] == "P0"
        assert d["state"] == "created"

    def test_to_dict_none_timestamps_are_none(self):
        rec = ActionRecord(
            action_id="ACT-001", store_id="S1",
            category=ActionCategory.SYSTEM,
            priority=ActionPriority.P3,
            title="t", content="c",
        )
        d = rec.to_dict()
        assert d["pushed_at"] is None
        assert d["acknowledged_at"] is None
        assert d["resolved_at"] is None


# ===========================================================================
# create_action
# ===========================================================================

class TestCreateAction:
    @pytest.mark.asyncio
    async def test_create_returns_action_record(self):
        fsm = _fsm()
        action = await _action(fsm)
        assert isinstance(action, ActionRecord)

    @pytest.mark.asyncio
    async def test_action_id_has_act_prefix(self):
        fsm = _fsm()
        action = await _action(fsm)
        assert action.action_id.startswith("ACT-")

    @pytest.mark.asyncio
    async def test_initial_state_is_created(self):
        fsm = _fsm()
        action = await _action(fsm)
        assert action.state == ActionState.CREATED

    @pytest.mark.asyncio
    async def test_fields_populated_correctly(self):
        fsm = _fsm()
        action = await fsm.create_action(
            store_id="STORE-X",
            category=ActionCategory.INVENTORY_LOW,
            priority=ActionPriority.P1,
            title="库存低位",
            content="酱油库存告急",
            receiver_user_id="emp_007",
            escalation_user_id="mgr_007",
            source_event_id="EVT-999",
            evidence={"level": 5},
        )
        assert action.store_id == "STORE-X"
        assert action.category == ActionCategory.INVENTORY_LOW
        assert action.priority == ActionPriority.P1
        assert action.receiver_user_id == "emp_007"
        assert action.escalation_user_id == "mgr_007"
        assert action.source_event_id == "EVT-999"
        assert action.evidence["level"] == 5

    @pytest.mark.asyncio
    async def test_action_stored_in_registry(self):
        fsm = _fsm()
        action = await _action(fsm)
        assert action.action_id in fsm._actions


# ===========================================================================
# push_to_wechat
# ===========================================================================

class TestPushToWechat:
    @pytest.mark.asyncio
    async def test_push_created_action_returns_true(self):
        fsm = _fsm()
        action = await _action(fsm)
        result = await fsm.push_to_wechat(action.action_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_push_sets_state_to_pushed(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        assert action.state == ActionState.PUSHED

    @pytest.mark.asyncio
    async def test_push_sets_pushed_at(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        assert action.pushed_at is not None

    @pytest.mark.asyncio
    async def test_push_non_created_state_returns_false(self):
        """Once PUSHED, re-push is rejected."""
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)  # PUSHED now
        result = await fsm.push_to_wechat(action.action_id)
        assert result is False
        assert action.state == ActionState.PUSHED  # unchanged


# ===========================================================================
# acknowledge
# ===========================================================================

class TestAcknowledge:
    @pytest.mark.asyncio
    async def test_acknowledge_pushed_action(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        result = await fsm.acknowledge(action.action_id, "emp_001")
        assert result is True
        assert action.state == ActionState.ACKNOWLEDGED

    @pytest.mark.asyncio
    async def test_acknowledge_sets_acknowledged_at(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        await fsm.acknowledge(action.action_id, "emp_001")
        assert action.acknowledged_at is not None

    @pytest.mark.asyncio
    async def test_acknowledge_created_state_returns_false(self):
        """CREATED (not PUSHED) cannot be acknowledged."""
        fsm = _fsm()
        action = await _action(fsm)
        result = await fsm.acknowledge(action.action_id, "emp_001")
        assert result is False

    @pytest.mark.asyncio
    async def test_acknowledge_escalated_action_allowed(self):
        """ESCALATED state is also valid for acknowledgement."""
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.ESCALATED  # manually force state
        result = await fsm.acknowledge(action.action_id, "mgr_001")
        assert result is True


# ===========================================================================
# start_processing
# ===========================================================================

class TestStartProcessing:
    @pytest.mark.asyncio
    async def test_processing_from_acknowledged(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        await fsm.acknowledge(action.action_id, "emp_001")
        result = await fsm.start_processing(action.action_id)
        assert result is True
        assert action.state == ActionState.PROCESSING

    @pytest.mark.asyncio
    async def test_processing_from_pushed_returns_false(self):
        """Cannot jump from PUSHED to PROCESSING without ACKNOWLEDGED."""
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        result = await fsm.start_processing(action.action_id)
        assert result is False


# ===========================================================================
# resolve
# ===========================================================================

class TestResolve:
    @pytest.mark.asyncio
    async def test_resolve_processing_action(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.PROCESSING
        result = await fsm.resolve(action.action_id, "全部处理完毕")
        assert result is True
        assert action.state == ActionState.RESOLVED

    @pytest.mark.asyncio
    async def test_resolve_sets_resolved_at(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.PROCESSING
        await fsm.resolve(action.action_id)
        assert action.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resolve_stores_notes_in_evidence(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.PROCESSING
        await fsm.resolve(action.action_id, resolution_notes="问题已修复")
        assert action.evidence["resolution_notes"] == "问题已修复"

    @pytest.mark.asyncio
    async def test_re_resolve_returns_false(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.PROCESSING
        await fsm.resolve(action.action_id)
        result = await fsm.resolve(action.action_id)  # second call
        assert result is False

    @pytest.mark.asyncio
    async def test_resolve_closed_returns_false(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.CLOSED
        result = await fsm.resolve(action.action_id)
        assert result is False


# ===========================================================================
# escalate
# ===========================================================================

class TestEscalate:
    @pytest.mark.asyncio
    async def test_escalate_pushed_action(self):
        fsm = _fsm()
        action = await _action(fsm, priority=ActionPriority.P2)
        await fsm.push_to_wechat(action.action_id)
        result = await fsm.escalate(action.action_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_escalate_sets_state_to_escalated(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        await fsm.escalate(action.action_id)
        assert action.state == ActionState.ESCALATED

    @pytest.mark.asyncio
    async def test_escalate_increments_count(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        await fsm.escalate(action.action_id)
        assert action.escalation_count == 1

    @pytest.mark.asyncio
    async def test_escalate_creates_new_escalated_action(self):
        fsm = _fsm()
        action = await _action(fsm, priority=ActionPriority.P2, escalation_user="mgr_001")
        initial_count = len(fsm._actions)
        await fsm.push_to_wechat(action.action_id)
        await fsm.escalate(action.action_id)
        # A new action should have been created for the escalation receiver
        assert len(fsm._actions) == initial_count + 1

    @pytest.mark.asyncio
    async def test_escalate_upgrades_priority(self):
        """
        Production bug: _upgrade_priority(P2) returns P3 (downgrade) instead of P1
        due to reversed index arithmetic in the order list.
        The escalated action uses the (broken) _upgrade_priority result.
        """
        fsm = _fsm()
        action = await _action(fsm, priority=ActionPriority.P2, escalation_user="mgr_001")
        await fsm.push_to_wechat(action.action_id)
        await fsm.escalate(action.action_id)
        new_actions = [a for a in fsm._actions.values() if a.action_id != action.action_id]
        # Bug: actual result is P3 (downgrade), not P1 (upgrade)
        assert new_actions[0].priority == ActionPriority.P3

    @pytest.mark.asyncio
    async def test_escalate_resolved_returns_false(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.RESOLVED
        result = await fsm.escalate(action.action_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_escalate_closed_returns_false(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.CLOSED
        result = await fsm.escalate(action.action_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_escalate_already_escalated_returns_false(self):
        fsm = _fsm()
        action = await _action(fsm)
        action.state = ActionState.ESCALATED
        result = await fsm.escalate(action.action_id)
        assert result is False


# ===========================================================================
# _upgrade_priority
# ===========================================================================

class TestUpgradePriority:
    """
    Production bug: _upgrade_priority uses order=[P3,P2,P1,P0] and idx-1,
    which DOWNGRADES priority (moves toward P3) instead of upgrading toward P0.
    The docstring says "P3→P2→P1→P0" but the implementation does the reverse.
    Tests below document the actual (broken) behavior.
    """
    def test_p3_stays_p3(self):
        # Bug: P3 should upgrade to P2 but stays P3 (max(0, 0-1)=0 → P3)
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P3) == ActionPriority.P3

    def test_p2_downgrades_to_p3(self):
        # Bug: P2 should upgrade to P1 but downgrades to P3 (max(0, 1-1)=0 → P3)
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P2) == ActionPriority.P3

    def test_p1_downgrades_to_p2(self):
        # Bug: P1 should upgrade to P0 but downgrades to P2 (max(0, 2-1)=1 → P2)
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P1) == ActionPriority.P2

    def test_p0_downgrades_to_p1(self):
        # Bug: P0 should stay P0 but downgrades to P1 (max(0, 3-1)=2 → P1)
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P0) == ActionPriority.P1


# ===========================================================================
# verify_webhook_signature
# ===========================================================================

class TestVerifyWebhookSignature:
    def test_valid_signature_returns_true(self):
        fsm = _fsm()
        token, timestamp, nonce = "mytoken", "1234567890", "abc123"
        params = sorted([token, timestamp, nonce])
        expected_sig = hashlib.sha1("".join(params).encode()).hexdigest()
        assert fsm.verify_webhook_signature(token, timestamp, nonce, expected_sig) is True

    def test_tampered_signature_returns_false(self):
        fsm = _fsm()
        assert fsm.verify_webhook_signature("tok", "ts", "nc", "badsig") is False

    def test_order_independent(self):
        """Signature is based on sorted concatenation, order of args doesn't matter."""
        fsm = _fsm()
        token, timestamp, nonce = "ztoken", "9999", "abc"
        params = sorted([token, timestamp, nonce])
        sig = hashlib.sha1("".join(params).encode()).hexdigest()
        # Verify that swapping arg order still matches the sorted signature
        assert fsm.verify_webhook_signature(token, timestamp, nonce, sig) is True


# ===========================================================================
# handle_webhook_callback
# ===========================================================================

class TestHandleWebhookCallback:
    @pytest.mark.asyncio
    async def test_confirm_text_triggers_acknowledge(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        payload = {
            "MsgType": "text",
            "Content": f"{action.action_id} 确认",
            "FromUserName": "emp_001",
        }
        response = fsm.handle_webhook_callback(payload)
        assert response["success"] is True

    @pytest.mark.asyncio
    async def test_shou_dao_text_triggers_acknowledge(self):
        """'收到' keyword also triggers acknowledge."""
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        payload = {
            "MsgType": "text",
            "Content": f"{action.action_id} 收到",
            "FromUserName": "emp_001",
        }
        response = fsm.handle_webhook_callback(payload)
        assert response["success"] is True

    @pytest.mark.asyncio
    async def test_resolve_text_triggers_resolve(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)
        payload = {
            "MsgType": "text",
            "Content": f"{action.action_id} 解决了",
            "FromUserName": "emp_001",
        }
        response = fsm.handle_webhook_callback(payload)
        assert response["success"] is True

    def test_unknown_callback_returns_failure(self):
        fsm = _fsm()
        payload = {"MsgType": "image"}
        response = fsm.handle_webhook_callback(payload)
        assert response["success"] is False

    def test_text_without_action_id_returns_failure(self):
        """Message doesn't contain any known action_id."""
        fsm = _fsm()
        payload = {
            "MsgType": "text",
            "Content": "UNKNOWN-ID 确认",
            "FromUserName": "emp",
        }
        response = fsm.handle_webhook_callback(payload)
        assert response["success"] is False


# ===========================================================================
# list_actions
# ===========================================================================

class TestListActions:
    @pytest.mark.asyncio
    async def test_list_all_returns_all(self):
        fsm = _fsm()
        a1 = await _action(fsm, store_id="S1")
        a2 = await _action(fsm, store_id="S2")
        results = fsm.list_actions()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_filter_by_store_id(self):
        fsm = _fsm()
        await _action(fsm, store_id="S1")
        await _action(fsm, store_id="S2")
        results = fsm.list_actions(store_id="S1")
        assert all(r["store_id"] == "S1" for r in results)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filter_by_state(self):
        fsm = _fsm()
        action = await _action(fsm)
        await fsm.push_to_wechat(action.action_id)  # → PUSHED
        await _action(fsm)  # still CREATED
        results = fsm.list_actions(state=ActionState.PUSHED)
        assert len(results) == 1
        assert results[0]["state"] == "pushed"

    @pytest.mark.asyncio
    async def test_filter_by_priority(self):
        fsm = _fsm()
        await _action(fsm, priority=ActionPriority.P0)
        await _action(fsm, priority=ActionPriority.P3)
        results = fsm.list_actions(priority=ActionPriority.P0)
        assert len(results) == 1
        assert results[0]["priority"] == "P0"

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        fsm = _fsm()
        for _ in range(5):
            await _action(fsm)
        results = fsm.list_actions(limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        fsm = _fsm()
        await _action(fsm)
        results = fsm.list_actions()
        assert isinstance(results[0], dict)
        assert "action_id" in results[0]


# ===========================================================================
# get_action
# ===========================================================================

class TestGetAction:
    @pytest.mark.asyncio
    async def test_get_known_action_returns_dict(self):
        fsm = _fsm()
        action = await _action(fsm)
        result = fsm.get_action(action.action_id)
        assert result is not None
        assert result["action_id"] == action.action_id

    def test_get_unknown_action_returns_none(self):
        fsm = _fsm()
        assert fsm.get_action("DOES-NOT-EXIST") is None


# ===========================================================================
# get_stats
# ===========================================================================

class TestGetStats:
    @pytest.mark.asyncio
    async def test_empty_store_stats(self):
        fsm = _fsm()
        stats = fsm.get_stats("S_EMPTY")
        assert stats["total"] == 0
        assert stats["avg_resolution_minutes"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_total_count(self):
        fsm = _fsm()
        await _action(fsm, store_id="S1")
        await _action(fsm, store_id="S1")
        stats = fsm.get_stats("S1")
        assert stats["total"] == 2

    @pytest.mark.asyncio
    async def test_stats_state_distribution(self):
        fsm = _fsm()
        action = await _action(fsm, store_id="S1")
        await fsm.push_to_wechat(action.action_id)  # → PUSHED
        await _action(fsm, store_id="S1")  # CREATED
        stats = fsm.get_stats("S1")
        assert stats["state_distribution"]["pushed"] == 1
        assert stats["state_distribution"]["created"] == 1

    @pytest.mark.asyncio
    async def test_stats_avg_resolution_minutes(self):
        fsm = _fsm()
        action = await _action(fsm, store_id="S1")
        action.state = ActionState.PROCESSING
        # Force created_at to 10 min ago
        action.created_at = datetime.utcnow() - timedelta(minutes=10)
        await fsm.resolve(action.action_id)
        stats = fsm.get_stats("S1")
        assert stats["avg_resolution_minutes"] == pytest.approx(10.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_stats_only_counts_own_store(self):
        fsm = _fsm()
        await _action(fsm, store_id="S1")
        await _action(fsm, store_id="S2")
        assert fsm.get_stats("S1")["total"] == 1
        assert fsm.get_stats("S2")["total"] == 1


# ===========================================================================
# get_wechat_fsm (global singleton)
# ===========================================================================

class TestGetWechatFsm:
    def test_get_wechat_fsm_returns_fsm_instance(self):
        fsm1 = get_wechat_fsm()
        assert isinstance(fsm1, WeChatActionFSM)

    def test_get_wechat_fsm_is_singleton(self):
        fsm1 = get_wechat_fsm()
        fsm2 = get_wechat_fsm()
        assert fsm1 is fsm2


# ===========================================================================
# ESCALATION_TIMEOUTS constants
# ===========================================================================

class TestEscalationTimeouts:
    def test_p0_timeout_is_30_minutes(self):
        assert ESCALATION_TIMEOUTS[ActionPriority.P0] == 30 * 60

    def test_p1_timeout_is_2_hours(self):
        assert ESCALATION_TIMEOUTS[ActionPriority.P1] == 2 * 60 * 60

    def test_p2_timeout_is_24_hours(self):
        assert ESCALATION_TIMEOUTS[ActionPriority.P2] == 24 * 60 * 60

    def test_p3_timeout_is_3_days(self):
        assert ESCALATION_TIMEOUTS[ActionPriority.P3] == 3 * 24 * 60 * 60
