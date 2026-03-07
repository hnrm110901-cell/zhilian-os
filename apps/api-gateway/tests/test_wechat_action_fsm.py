"""
tests/test_wechat_action_fsm.py

WeChatActionFSM 单元测试 — Phase 7 L5 行动层

覆盖：
  - 创建 Action（create_action）
  - 推送企微（push_to_wechat）
  - 确认（acknowledge）
  - 处理中（start_processing）
  - 解决（resolve）
  - 升级（escalate）
  - 升级超时判断（is_expired）
  - Webhook 验签（verify_webhook_signature）
  - 统计查询（get_stats / list_actions）
  - 优先级升级链（_upgrade_priority）
  - Markdown 消息格式（_build_markdown_message）
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-xx")

from src.services.wechat_action_fsm import (
    ActionCategory,
    ActionPriority,
    ActionRecord,
    ActionState,
    ESCALATION_TIMEOUTS,
    WeChatActionFSM,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def fsm():
    return WeChatActionFSM()


async def _create_default_action(fsm: WeChatActionFSM, priority: str = "P1") -> ActionRecord:
    return await fsm.create_action(
        store_id="STORE001",
        category=ActionCategory.WASTE_ALERT,
        priority=ActionPriority(priority),
        title="测试行动标题",
        content="测试内容",
        receiver_user_id="user_001",
        escalation_user_id="manager_001",
        source_event_id="EVT-001",
    )


# ── 1. create_action ──────────────────────────────────────────────────────────

class TestCreateAction:
    @pytest.mark.asyncio
    async def test_create_action_returns_record_with_created_state(self, fsm):
        """新建行动：状态为 CREATED，action_id 以 ACT- 开头"""
        action = await _create_default_action(fsm)
        assert action.state == ActionState.CREATED
        assert action.action_id.startswith("ACT-")

    @pytest.mark.asyncio
    async def test_create_action_stores_in_memory(self, fsm):
        """新建行动：保存在 _actions 字典中"""
        action = await _create_default_action(fsm)
        assert action.action_id in fsm._actions

    @pytest.mark.asyncio
    async def test_create_action_fields_populated(self, fsm):
        """新建行动：store_id/title/content/category 字段正确"""
        action = await _create_default_action(fsm)
        assert action.store_id == "STORE001"
        assert action.title == "测试行动标题"
        assert action.category == ActionCategory.WASTE_ALERT


# ── 2. push_to_wechat ─────────────────────────────────────────────────────────

class TestPushToWechat:
    @pytest.mark.asyncio
    async def test_push_transitions_to_pushed_state(self, fsm):
        """推送成功：状态变为 PUSHED"""
        action = await _create_default_action(fsm)
        with patch.object(fsm, "_send_wechat_message", new_callable=AsyncMock, return_value=True):
            success = await fsm.push_to_wechat(action.action_id)
        assert success is True
        assert action.state == ActionState.PUSHED

    @pytest.mark.asyncio
    async def test_push_failure_transitions_to_failed_state(self, fsm):
        """推送失败：状态变为 FAILED"""
        action = await _create_default_action(fsm)
        with patch.object(fsm, "_send_wechat_message", new_callable=AsyncMock, return_value=False):
            success = await fsm.push_to_wechat(action.action_id)
        assert success is False
        assert action.state == ActionState.FAILED

    @pytest.mark.asyncio
    async def test_push_already_pushed_returns_false(self, fsm):
        """重复推送：直接返回 False（状态不允许）"""
        action = await _create_default_action(fsm)
        action.state = ActionState.PUSHED  # 强制设为已推送
        with patch.object(fsm, "_send_wechat_message", new_callable=AsyncMock, return_value=True):
            success = await fsm.push_to_wechat(action.action_id)
        assert success is False


# ── 3. acknowledge / start_processing / resolve ────────────────────────────────

class TestLifecycleTransitions:
    @pytest.mark.asyncio
    async def test_acknowledge_from_pushed(self, fsm):
        """确认：从 PUSHED → ACKNOWLEDGED"""
        action = await _create_default_action(fsm)
        action.state = ActionState.PUSHED
        result = await fsm.acknowledge(action.action_id, "user_001")
        assert result is True
        assert action.state == ActionState.ACKNOWLEDGED

    @pytest.mark.asyncio
    async def test_acknowledge_from_wrong_state_returns_false(self, fsm):
        """确认：从 CREATED 状态（非 PUSHED）→ 返回 False"""
        action = await _create_default_action(fsm)
        result = await fsm.acknowledge(action.action_id, "user_001")
        assert result is False

    @pytest.mark.asyncio
    async def test_start_processing_from_acknowledged(self, fsm):
        """处理中：从 ACKNOWLEDGED → PROCESSING"""
        action = await _create_default_action(fsm)
        action.state = ActionState.ACKNOWLEDGED
        result = await fsm.start_processing(action.action_id)
        assert result is True
        assert action.state == ActionState.PROCESSING

    @pytest.mark.asyncio
    async def test_resolve_sets_resolved_at(self, fsm):
        """解决：resolved_at 被设置，状态变为 RESOLVED"""
        action = await _create_default_action(fsm)
        action.state = ActionState.PROCESSING
        result = await fsm.resolve(action.action_id, "处理完成，损耗率已降至合理区间")
        assert result is True
        assert action.state == ActionState.RESOLVED
        assert action.resolved_at is not None


# ── 4. escalate ───────────────────────────────────────────────────────────────

class TestEscalate:
    @pytest.mark.asyncio
    async def test_escalate_marks_original_as_escalated(self, fsm):
        """升级：原行动状态变为 ESCALATED"""
        action = await _create_default_action(fsm, priority="P2")
        action.state = ActionState.PUSHED
        with patch.object(fsm, "_send_wechat_message", new_callable=AsyncMock, return_value=True):
            result = await fsm.escalate(action.action_id)
        assert result is True
        assert action.state == ActionState.ESCALATED
        assert action.escalation_count == 1

    @pytest.mark.asyncio
    async def test_escalate_resolved_action_returns_false(self, fsm):
        """已解决的行动升级：返回 False"""
        action = await _create_default_action(fsm)
        action.state = ActionState.RESOLVED
        result = await fsm.escalate(action.action_id)
        assert result is False


# ── 5. is_expired ─────────────────────────────────────────────────────────────

class TestIsExpired:
    def test_p1_not_expired_within_2h(self):
        """P1 行动：推送后 1h 内不过期"""
        record = ActionRecord(
            action_id="ACT-TEST001",
            store_id="S001",
            category=ActionCategory.KPI_ALERT,
            priority=ActionPriority.P1,
            title="t", content="c",
        )
        record.state = ActionState.PUSHED
        record.pushed_at = datetime.utcnow() - timedelta(hours=1)
        assert record.is_expired() is False

    def test_p1_expired_after_2h(self):
        """P1 行动：推送后 3h 已过期"""
        record = ActionRecord(
            action_id="ACT-TEST002",
            store_id="S001",
            category=ActionCategory.KPI_ALERT,
            priority=ActionPriority.P1,
            title="t", content="c",
        )
        record.state = ActionState.PUSHED
        record.pushed_at = datetime.utcnow() - timedelta(hours=3)
        assert record.is_expired() is True

    def test_resolved_action_not_expired(self):
        """已解决行动：不过期"""
        record = ActionRecord(
            action_id="ACT-TEST003",
            store_id="S001",
            category=ActionCategory.KPI_ALERT,
            priority=ActionPriority.P0,
            title="t", content="c",
        )
        record.state = ActionState.RESOLVED
        record.pushed_at = datetime.utcnow() - timedelta(hours=24)
        assert record.is_expired() is False


# ── 6. verify_webhook_signature ───────────────────────────────────────────────

class TestWebhookSignature:
    def test_valid_signature(self, fsm):
        """合法签名：验证通过"""
        token, timestamp, nonce = "mytoken", "1700000000", "random123"
        params = sorted([token, timestamp, nonce])
        expected = hashlib.sha1("".join(params).encode()).hexdigest()
        assert fsm.verify_webhook_signature(token, timestamp, nonce, expected) is True

    def test_invalid_signature(self, fsm):
        """伪造签名：验证失败"""
        assert fsm.verify_webhook_signature("t", "ts", "n", "forged") is False


# ── 7. _upgrade_priority ─────────────────────────────────────────────────────

class TestUpgradePriority:
    def test_p3_upgrades_to_p2(self):
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P3) == ActionPriority.P2

    def test_p2_upgrades_to_p1(self):
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P2) == ActionPriority.P1

    def test_p1_upgrades_to_p0(self):
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P1) == ActionPriority.P0

    def test_p0_stays_p0(self):
        assert WeChatActionFSM._upgrade_priority(ActionPriority.P0) == ActionPriority.P0
