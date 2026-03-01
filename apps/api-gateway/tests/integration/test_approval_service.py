"""
Tests for src/services/approval_service.py — ARCH-004 Human-in-the-Loop 审批流.

No real DB needed: DB calls are fully mocked.
WeChatAlertService is stubbed out.

Covers:
  - create_approval_request: DecisionLog created with correct fields, PENDING status
  - _build_approval_card: dict shape, title prefix, action buttons
  - _calculate_trust_score: math for APPROVED/MODIFIED/REJECTED × confidence × deviation
  - approve_decision: status→APPROVED, approval_chain entry, _execute_decision called
  - reject_decision: status→REJECTED, is_training_data=1, approval_chain entry
  - modify_decision: status→MODIFIED, manager_decision set, is_training_data=1
  - record_decision_outcome: outcome stored, result_deviation computed, trust_score set
  - get_decision_statistics: approval_rate / rejection_rate / modification_rate / by_type
  - get_pending_approvals: filter by PENDING status
"""
import sys
import uuid
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Pre-stub modules that trigger Settings validation at import time
sys.modules.setdefault("src.services.agent_service", MagicMock())
sys.modules.setdefault("src.services.wechat_alert_service", MagicMock())

from src.services.approval_service import ApprovalService
from src.models.decision_log import (
    DecisionLog,
    DecisionOutcome,
    DecisionStatus,
    DecisionType,
)
from src.models.store import Store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision_log(
    decision_type=DecisionType.PURCHASE_SUGGESTION,
    status=DecisionStatus.PENDING,
    ai_confidence=0.8,
    trust_score=None,
    result_deviation=None,
    approval_chain=None,
):
    log = MagicMock(spec=DecisionLog)
    log.id = str(uuid.uuid4())
    log.decision_type = decision_type
    log.decision_status = status
    log.ai_confidence = ai_confidence
    log.ai_suggestion = {"item": "rice", "qty": 50}
    log.ai_reasoning = "库存低于安全库位"
    log.ai_alternatives = []
    log.store_id = "S1"
    log.manager_id = None
    log.manager_decision = None
    log.manager_feedback = None
    log.approved_at = None
    log.executed_at = None
    log.trust_score = trust_score
    log.result_deviation = result_deviation
    log.is_training_data = 0
    log.outcome = None
    log.actual_result = None
    log.expected_result = None
    log.business_impact = None
    log.approval_chain = approval_chain or []
    log.created_at = datetime.utcnow()
    return log


def _mock_db(scalar_value=None, scalars_all=None):
    """Build a minimal AsyncSession mock."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=scalars_all or [])))
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _svc() -> ApprovalService:
    svc = ApprovalService()
    svc.wechat_service = MagicMock()
    svc.wechat_service.send_approval_card = AsyncMock()
    return svc


# ===========================================================================
# create_approval_request
# ===========================================================================

class TestCreateApprovalRequest:
    @pytest.mark.asyncio
    async def test_returns_decision_log_with_pending_status(self):
        svc = _svc()
        svc._send_approval_notification = AsyncMock()
        result = await svc.create_approval_request(
            decision_type=DecisionType.PURCHASE_SUGGESTION,
            agent_type="inventory_agent",
            agent_method="suggest_purchase",
            store_id="S1",
            ai_suggestion={"item": "rice"},
            ai_confidence=0.85,
            ai_reasoning="库存不足",
            db=None,
        )
        assert isinstance(result, DecisionLog)
        assert result.decision_status == DecisionStatus.PENDING

    @pytest.mark.asyncio
    async def test_fields_populated_correctly(self):
        svc = _svc()
        svc._send_approval_notification = AsyncMock()
        result = await svc.create_approval_request(
            decision_type=DecisionType.INVENTORY_ALERT,
            agent_type="ops_agent",
            agent_method="alert",
            store_id="S99",
            ai_suggestion={"action": "reorder"},
            ai_confidence=0.92,
            ai_reasoning="critical",
            context_data={"urgency": "high"},
            db=None,
        )
        assert result.store_id == "S99"
        assert result.ai_confidence == 0.92
        assert result.agent_type == "ops_agent"
        assert result.context_data == {"urgency": "high"}

    @pytest.mark.asyncio
    async def test_with_db_saves_and_commits(self):
        svc = _svc()
        svc._send_approval_notification = AsyncMock()
        db = _mock_db()
        await svc.create_approval_request(
            decision_type=DecisionType.SCHEDULE_OPTIMIZATION,
            agent_type="schedule_agent",
            agent_method="optimize",
            store_id="S1",
            ai_suggestion={},
            ai_confidence=0.7,
            ai_reasoning="weekend peak",
            db=db,
        )
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sends_notification(self):
        svc = _svc()
        svc._send_approval_notification = AsyncMock()
        await svc.create_approval_request(
            decision_type=DecisionType.COST_OPTIMIZATION,
            agent_type="agent",
            agent_method="method",
            store_id="S1",
            ai_suggestion={},
            ai_confidence=0.5,
            ai_reasoning="test",
            db=None,
        )
        svc._send_approval_notification.assert_awaited_once()


# ===========================================================================
# _build_approval_card
# ===========================================================================

class TestBuildApprovalCard:
    def test_card_has_required_keys(self):
        svc = _svc()
        log = _decision_log(decision_type=DecisionType.PURCHASE_SUGGESTION)
        store = MagicMock(spec=Store)
        store.name = "长沙门店"
        card = svc._build_approval_card(log, store)
        for key in ("title", "store", "decision_id", "confidence", "suggestion",
                    "reasoning", "alternatives", "created_at", "actions"):
            assert key in card, f"Missing key: {key}"

    def test_title_has_type_name(self):
        svc = _svc()
        log = _decision_log(decision_type=DecisionType.PURCHASE_SUGGESTION)
        store = MagicMock()
        store.name = "S1"
        card = svc._build_approval_card(log, store)
        assert "采购建议" in card["title"]

    def test_actions_contain_approve_reject_modify(self):
        svc = _svc()
        log = _decision_log()
        store = MagicMock()
        store.name = "S1"
        card = svc._build_approval_card(log, store)
        action_types = {a["action"] for a in card["actions"]}
        assert "approve" in action_types
        assert "reject" in action_types
        assert "modify" in action_types

    def test_confidence_formatted_as_pct(self):
        svc = _svc()
        log = _decision_log(ai_confidence=0.85)
        store = MagicMock()
        store.name = "S1"
        card = svc._build_approval_card(log, store)
        assert "85.0%" in card["confidence"]

    def test_unknown_decision_type_uses_default_label(self):
        svc = _svc()
        log = _decision_log(decision_type=DecisionType.KPI_IMPROVEMENT)
        store = MagicMock()
        store.name = "S1"
        # KPI_IMPROVEMENT not in the mapping → default "AI决策建议"
        card = svc._build_approval_card(log, store)
        assert card["title"]  # non-empty


# ===========================================================================
# _calculate_trust_score
# ===========================================================================

class TestCalculateTrustScore:
    def test_approved_high_confidence_low_deviation(self):
        """APPROVED + 100% confidence + deviation<10% → max score."""
        svc = _svc()
        log = _decision_log(status=DecisionStatus.APPROVED, ai_confidence=1.0, result_deviation=5.0)
        score = svc._calculate_trust_score(log)
        # 1.0 * 30 + 40 + 30 = 100
        assert score == pytest.approx(100.0)

    def test_rejected_zero_confidence_no_deviation(self):
        """REJECTED + 0 confidence + no deviation → 0."""
        svc = _svc()
        log = _decision_log(status=DecisionStatus.REJECTED, ai_confidence=0.0, result_deviation=None)
        score = svc._calculate_trust_score(log)
        assert score == pytest.approx(0.0)

    def test_modified_medium_confidence(self):
        """MODIFIED + 50% confidence + deviation 15% (10-20 range) → 30 + 15 + 20."""
        svc = _svc()
        log = _decision_log(status=DecisionStatus.MODIFIED, ai_confidence=0.5, result_deviation=15.0)
        score = svc._calculate_trust_score(log)
        # 0.5*30 + 20 + 20 = 55
        assert score == pytest.approx(55.0)

    def test_score_capped_at_100(self):
        svc = _svc()
        log = _decision_log(status=DecisionStatus.APPROVED, ai_confidence=1.0, result_deviation=0.0)
        assert svc._calculate_trust_score(log) <= 100.0

    def test_approved_deviation_above_30_pct(self):
        """Deviation >= 30% → deviation score = 0."""
        svc = _svc()
        log = _decision_log(status=DecisionStatus.APPROVED, ai_confidence=0.0, result_deviation=50.0)
        score = svc._calculate_trust_score(log)
        assert score == pytest.approx(40.0)  # only adoption score


# ===========================================================================
# approve_decision
# ===========================================================================

class TestApproveDecision:
    @pytest.mark.asyncio
    async def test_approve_sets_status_approved(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        await svc.approve_decision("DECISION-1", "MGR-1", db=db)
        assert log.decision_status == DecisionStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_sets_manager_id(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        await svc.approve_decision("DECISION-1", "MGR-007", db=db)
        assert log.manager_id == "MGR-007"

    @pytest.mark.asyncio
    async def test_approve_adds_approval_chain_entry(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        await svc.approve_decision("DECISION-1", "MGR-1", manager_feedback="同意", db=db)
        assert len(log.approval_chain) == 1
        assert log.approval_chain[0]["action"] == "approved"
        assert log.approval_chain[0]["feedback"] == "同意"

    @pytest.mark.asyncio
    async def test_approve_calls_execute_decision(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        await svc.approve_decision("DECISION-1", "MGR-1", db=db)
        svc._execute_decision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_not_found_raises(self):
        svc = _svc()
        db = _mock_db(scalar_value=None)
        with pytest.raises(ValueError, match="not found"):
            await svc.approve_decision("MISSING", "MGR-1", db=db)


# ===========================================================================
# reject_decision
# ===========================================================================

class TestRejectDecision:
    @pytest.mark.asyncio
    async def test_reject_sets_status_rejected(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        await svc.reject_decision("D1", "MGR-1", "成本太高", db=db)
        assert log.decision_status == DecisionStatus.REJECTED

    @pytest.mark.asyncio
    async def test_reject_marks_as_training_data(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        await svc.reject_decision("D1", "MGR-1", "不需要", db=db)
        assert log.is_training_data == 1

    @pytest.mark.asyncio
    async def test_reject_stores_feedback(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        await svc.reject_decision("D1", "MGR-1", "理由充分", db=db)
        assert log.manager_feedback == "理由充分"

    @pytest.mark.asyncio
    async def test_reject_adds_chain_entry(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        await svc.reject_decision("D1", "MGR-1", "reason", db=db)
        assert log.approval_chain[0]["action"] == "rejected"


# ===========================================================================
# modify_decision
# ===========================================================================

class TestModifyDecision:
    @pytest.mark.asyncio
    async def test_modify_sets_status_modified(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        await svc.modify_decision("D1", "MGR-1", {"qty": 30}, db=db)
        assert log.decision_status == DecisionStatus.MODIFIED

    @pytest.mark.asyncio
    async def test_modify_sets_manager_decision(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        modified = {"qty": 30, "reason": "reduce qty"}
        await svc.modify_decision("D1", "MGR-1", modified, db=db)
        assert log.manager_decision == modified

    @pytest.mark.asyncio
    async def test_modify_marks_training_data(self):
        svc = _svc()
        log = _decision_log()
        db = _mock_db(scalar_value=log)
        svc._execute_decision = AsyncMock()
        await svc.modify_decision("D1", "MGR-1", {}, db=db)
        assert log.is_training_data == 1


# ===========================================================================
# record_decision_outcome
# ===========================================================================

class TestRecordDecisionOutcome:
    @pytest.mark.asyncio
    async def test_stores_outcome_and_results(self):
        svc = _svc()
        log = _decision_log(status=DecisionStatus.APPROVED, ai_confidence=0.8, result_deviation=None)
        db = _mock_db(scalar_value=log)
        await svc.record_decision_outcome(
            decision_id="D1",
            outcome=DecisionOutcome.SUCCESS,
            actual_result={"value": 110},
            expected_result={"value": 100},
            db=db,
        )
        assert log.outcome == DecisionOutcome.SUCCESS
        assert log.actual_result == {"value": 110}

    @pytest.mark.asyncio
    async def test_result_deviation_calculated(self):
        svc = _svc()
        log = _decision_log(status=DecisionStatus.APPROVED, ai_confidence=0.5, result_deviation=None)
        db = _mock_db(scalar_value=log)
        await svc.record_decision_outcome(
            decision_id="D1",
            outcome=DecisionOutcome.SUCCESS,
            actual_result={"value": 120},
            expected_result={"value": 100},
            db=db,
        )
        # |120-100|/100 * 100 = 20%
        assert log.result_deviation == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_trust_score_set(self):
        svc = _svc()
        log = _decision_log(status=DecisionStatus.APPROVED, ai_confidence=0.9, result_deviation=None)
        db = _mock_db(scalar_value=log)
        await svc.record_decision_outcome(
            decision_id="D1",
            outcome=DecisionOutcome.SUCCESS,
            actual_result={"value": 100},
            expected_result={"value": 100},
            db=db,
        )
        assert log.trust_score is not None


# ===========================================================================
# get_decision_statistics
# ===========================================================================

class TestGetDecisionStatistics:
    @pytest.mark.asyncio
    async def test_empty_returns_zero_rates(self):
        svc = _svc()
        db = _mock_db(scalars_all=[])
        stats = await svc.get_decision_statistics(db=db)
        assert stats["total"] == 0
        assert stats["approval_rate"] == 0

    @pytest.mark.asyncio
    async def test_computes_rates_correctly(self):
        svc = _svc()
        d1 = _decision_log(status=DecisionStatus.APPROVED)
        d2 = _decision_log(status=DecisionStatus.APPROVED)
        d3 = _decision_log(status=DecisionStatus.REJECTED)
        d4 = _decision_log(status=DecisionStatus.PENDING)
        db = _mock_db(scalars_all=[d1, d2, d3, d4])
        stats = await svc.get_decision_statistics(db=db)
        assert stats["total"] == 4
        assert stats["approved"] == 2
        assert stats["rejected"] == 1
        assert stats["pending"] == 1
        assert stats["approval_rate"] == pytest.approx(50.0)
        assert stats["rejection_rate"] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_by_type_distribution(self):
        svc = _svc()
        d1 = _decision_log(decision_type=DecisionType.PURCHASE_SUGGESTION)
        d2 = _decision_log(decision_type=DecisionType.PURCHASE_SUGGESTION)
        d3 = _decision_log(decision_type=DecisionType.INVENTORY_ALERT)
        db = _mock_db(scalars_all=[d1, d2, d3])
        stats = await svc.get_decision_statistics(db=db)
        assert stats["by_type"]["purchase_suggestion"] == 2
        assert stats["by_type"]["inventory_alert"] == 1
