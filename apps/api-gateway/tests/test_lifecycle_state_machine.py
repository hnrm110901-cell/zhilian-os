"""
LifecycleStateMachine 单元测试

覆盖：
  - 纯函数：classify_lifecycle（9种状态路径）
  - 纯函数：next_state（合法转移 + 非法转移）
  - 纯函数：is_terminal
  - 服务：LifecycleStateMachine.detect_state（mock DB）
  - 服务：LifecycleStateMachine.apply_trigger（合法 + 非法，mock DB）
  - 服务：LifecycleStateMachine.get_history（mock DB）
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest

from src.services.lifecycle_state_machine import (
    LifecycleStateMachine,
    classify_lifecycle,
    is_terminal,
    next_state,
)
from src.models.member_lifecycle import LifecycleState, StateTransitionTrigger


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：classify_lifecycle
# ════════════════════════════════════════════════════════════════════════════════

class TestClassifyLifecycle:
    def test_unregistered_is_lead(self):
        assert classify_lifecycle(0, 0, 0, is_registered=False) == LifecycleState.LEAD

    def test_registered_no_orders_is_first_order_pending(self):
        assert classify_lifecycle(0, 0, 0, is_registered=True) == LifecycleState.FIRST_ORDER_PENDING

    def test_active_low_frequency_is_repeat(self):
        assert classify_lifecycle(10, 2, 5, is_registered=True) == LifecycleState.REPEAT

    def test_high_frequency_threshold(self):
        # 30天5单 = HIGH_FREQUENCY
        assert classify_lifecycle(5, 5, 10, is_registered=True) == LifecycleState.HIGH_FREQUENCY

    def test_below_high_frequency_threshold(self):
        # 30天4单 = REPEAT
        assert classify_lifecycle(5, 4, 10, is_registered=True) == LifecycleState.REPEAT

    def test_vip_flag(self):
        assert classify_lifecycle(5, 2, 3, is_registered=True, is_vip=True) == LifecycleState.VIP

    def test_churn_warning_boundary(self):
        # recency = 46 > 45 → AT_RISK
        assert classify_lifecycle(46, 0, 5, is_registered=True) == LifecycleState.AT_RISK

    def test_exactly_at_churn_boundary_is_repeat(self):
        # recency = 45 → still AT_RISK (> 45 not met)
        # recency_days=45 is NOT > 45, so active... but 45 > 30 threshold? No, CHURN_WARNING is > 45
        # recency=45: 45 > 90? No. 45 > 45? No. So → REPEAT (if frequency/orders qualify)
        result = classify_lifecycle(45, 2, 5, is_registered=True)
        assert result == LifecycleState.REPEAT

    def test_dormant_boundary(self):
        # recency = 91 → between 90 and 180 → DORMANT
        assert classify_lifecycle(91, 0, 5, is_registered=True) == LifecycleState.DORMANT

    def test_lost(self):
        # recency = 181 > 90*2=180 → LOST
        assert classify_lifecycle(181, 0, 3, is_registered=True) == LifecycleState.LOST


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：next_state
# ════════════════════════════════════════════════════════════════════════════════

class TestNextState:
    def test_lead_register(self):
        assert next_state(LifecycleState.LEAD, StateTransitionTrigger.REGISTER) == LifecycleState.REGISTERED

    def test_registered_first_order(self):
        assert next_state(LifecycleState.REGISTERED, StateTransitionTrigger.FIRST_ORDER) == LifecycleState.REPEAT

    def test_first_order_pending_first_order(self):
        assert next_state(LifecycleState.FIRST_ORDER_PENDING, StateTransitionTrigger.FIRST_ORDER) == LifecycleState.REPEAT

    def test_repeat_high_frequency_milestone(self):
        result = next_state(LifecycleState.REPEAT, StateTransitionTrigger.HIGH_FREQUENCY_MILESTONE)
        assert result == LifecycleState.HIGH_FREQUENCY

    def test_high_frequency_vip_upgrade(self):
        assert next_state(LifecycleState.HIGH_FREQUENCY, StateTransitionTrigger.VIP_UPGRADE) == LifecycleState.VIP

    def test_repeat_churn_warning_to_at_risk(self):
        assert next_state(LifecycleState.REPEAT, StateTransitionTrigger.CHURN_WARNING) == LifecycleState.AT_RISK

    def test_at_risk_repeat_order_recovers(self):
        assert next_state(LifecycleState.AT_RISK, StateTransitionTrigger.REPEAT_ORDER) == LifecycleState.REPEAT

    def test_dormant_inactivity_to_lost(self):
        assert next_state(LifecycleState.DORMANT, StateTransitionTrigger.INACTIVITY_LONG) == LifecycleState.LOST

    def test_dormant_repeat_order_recovers(self):
        assert next_state(LifecycleState.DORMANT, StateTransitionTrigger.REPEAT_ORDER) == LifecycleState.REPEAT

    def test_illegal_transition_returns_none(self):
        # LEAD 不能直接触发 FIRST_ORDER
        assert next_state(LifecycleState.LEAD, StateTransitionTrigger.FIRST_ORDER) is None

    def test_lost_is_terminal_no_transitions(self):
        for trigger in StateTransitionTrigger:
            assert next_state(LifecycleState.LOST, trigger) is None


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：is_terminal
# ════════════════════════════════════════════════════════════════════════════════

class TestIsTerminal:
    def test_lost_is_terminal(self):
        assert is_terminal(LifecycleState.LOST) is True

    def test_other_states_not_terminal(self):
        for state in LifecycleState:
            if state != LifecycleState.LOST:
                assert is_terminal(state) is False


# ════════════════════════════════════════════════════════════════════════════════
# 服务：LifecycleStateMachine（mock DB）
# ════════════════════════════════════════════════════════════════════════════════

def _make_db_row(**kwargs):
    """生成模拟的 DB 行对象（支持属性访问）。"""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


class TestDetectState:
    @pytest.mark.asyncio
    async def test_returns_saved_lifecycle_state(self):
        """若 private_domain_members 已有 lifecycle_state，直接返回。"""
        sm = LifecycleStateMachine()
        db = AsyncMock()

        member_row = _make_db_row(lifecycle_state="vip", recency_days=5, frequency=8, monetary=200000)
        db.execute.return_value.fetchone.return_value = member_row

        result = await sm.detect_state("C001", "S001", db)
        assert result == LifecycleState.VIP

    @pytest.mark.asyncio
    async def test_falls_back_to_rfm_when_no_lifecycle_state(self):
        """member 无 lifecycle_state，从 orders 聚合 RFM。"""
        sm = LifecycleStateMachine()
        db = AsyncMock()

        member_row = _make_db_row(lifecycle_state=None, recency_days=0, frequency=0, monetary=0)
        stats_row  = _make_db_row(total_orders=3, recency_days=10, frequency_30d=2, monetary_fen=50000)

        db.execute.return_value.fetchone.side_effect = [member_row, stats_row]

        result = await sm.detect_state("C001", "S001", db)
        assert result == LifecycleState.REPEAT

    @pytest.mark.asyncio
    async def test_no_member_record_lead(self):
        """无 member 记录 → LEAD。"""
        sm = LifecycleStateMachine()
        db = AsyncMock()

        db.execute.return_value.fetchone.side_effect = [
            None,  # member query
            _make_db_row(total_orders=0, recency_days=9999, frequency_30d=0, monetary_fen=0),
        ]

        result = await sm.detect_state("C999", "S001", db)
        assert result == LifecycleState.LEAD


class TestApplyTrigger:
    @pytest.mark.asyncio
    async def test_legal_transition_succeeds(self):
        """合法转移：REPEAT + CHURN_WARNING → AT_RISK。"""
        sm = LifecycleStateMachine()
        db = AsyncMock()

        # detect_state 返回 REPEAT（已保存）
        db.execute.return_value.fetchone.return_value = _make_db_row(
            lifecycle_state="repeat", recency_days=0, frequency=2, monetary=0
        )

        result = await sm.apply_trigger("C001", "S001", StateTransitionTrigger.CHURN_WARNING, db)

        assert result["transitioned"] is True
        assert result["from_state"] == "repeat"
        assert result["to_state"] == "at_risk"
        assert result["trigger"] == "churn_warning"

    @pytest.mark.asyncio
    async def test_illegal_transition_returns_no_change(self):
        """非法转移：LOST + REGISTER → 无变化。"""
        sm = LifecycleStateMachine()
        db = AsyncMock()

        db.execute.return_value.fetchone.return_value = _make_db_row(
            lifecycle_state="lost", recency_days=200, frequency=0, monetary=0
        )

        result = await sm.apply_trigger("C001", "S001", StateTransitionTrigger.REGISTER, db)

        assert result["transitioned"] is False
        assert result["from_state"] == "lost"
        assert result["to_state"] == "lost"
        # DB 不应有 UPDATE
        db.execute.assert_called_once()  # 只有 detect_state 的那次 execute

    @pytest.mark.asyncio
    async def test_transition_writes_history(self):
        """成功转移必须写入 MemberLifecycleHistory 并 commit。"""
        sm = LifecycleStateMachine()
        db = AsyncMock()

        db.execute.return_value.fetchone.return_value = _make_db_row(
            lifecycle_state="at_risk", recency_days=50, frequency=0, monetary=0
        )

        await sm.apply_trigger("C001", "S001", StateTransitionTrigger.REPEAT_ORDER, db)

        db.add.assert_called_once()
        db.commit.assert_called_once()


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        sm = LifecycleStateMachine()
        db = AsyncMock()

        mock_row = MagicMock()
        mock_row._mapping = {
            "from_state": "repeat", "to_state": "at_risk",
            "trigger": "churn_warning", "changed_by": "system",
            "changed_at": datetime.utcnow(), "reason": None,
        }
        db.execute.return_value.fetchall.return_value = [mock_row]

        history = await sm.get_history("C001", "S001", db)

        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["from_state"] == "repeat"
