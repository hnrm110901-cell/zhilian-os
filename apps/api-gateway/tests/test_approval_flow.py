"""
决策审批流完整测试套件
覆盖 AGENT_INTEGRATION_GUIDE.md 测试清单全部16项：
  - 基本流程（6项）
  - 异常流程（4项）
  - 性能测试（3项）
  - 数据完整性（3项）
"""
import asyncio
import time
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.decision_log import (
    DecisionLog,
    DecisionOutcome,
    DecisionStatus,
    DecisionType,
)
from src.services.approval_service import ApprovalService


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_decision_log(
    status: DecisionStatus = DecisionStatus.PENDING,
    outcome: DecisionOutcome = None,
    ai_confidence: float = 0.85,
    result_deviation: float = None,
    approval_chain=None,
) -> DecisionLog:
    """构造一个 DecisionLog 测试对象（不依赖 DB）"""
    log = DecisionLog(
        id=str(uuid.uuid4()),
        decision_type=DecisionType.INVENTORY_ALERT,
        agent_type="inventory_agent",
        agent_method="check_stock_level",
        store_id="STORE001",
        ai_suggestion={"action": "reorder", "sku": "PORK001", "quantity": 50},
        ai_confidence=ai_confidence,
        ai_reasoning="当前库存8kg，3日内到期，日均消耗12kg，预计损耗¥480",
        ai_alternatives=[{"action": "transfer", "from_store": "STORE002"}],
        decision_status=status,
        outcome=outcome,
        result_deviation=result_deviation,
        approval_chain=approval_chain or [],
        created_at=datetime.utcnow(),
    )
    return log


def _mock_db_with_log(decision_log: DecisionLog) -> AsyncMock:
    """返回已预置 decision_log 的 mock DB session"""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = decision_log
    mock_db.execute.return_value = mock_result
    return mock_db


# ─── 1. 基本流程测试 ──────────────────────────────────────────────────────────

class TestBasicFlow:
    """基本流程测试（6项）"""

    @pytest.mark.asyncio
    async def test_agent_generates_decision_suggestion(self):
        """① Agent生成决策建议：create_approval_request 返回 PENDING 状态的决策日志"""
        service = ApprovalService()
        service.wechat_service = MagicMock()
        service.wechat_service.send_approval_card = AsyncMock(return_value=True)

        mock_db = AsyncMock(spec=AsyncSession)
        # _send_approval_notification 需要查 store + user，这里统一返回 None（走警告分支）
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        log = await service.create_approval_request(
            decision_type=DecisionType.INVENTORY_ALERT,
            agent_type="inventory_agent",
            agent_method="check_stock_level",
            store_id="STORE001",
            ai_suggestion={"action": "reorder", "sku": "PORK001", "quantity": 50},
            ai_confidence=0.85,
            ai_reasoning="库存不足，建议补货",
            db=mock_db,
        )

        assert log is not None
        assert log.decision_status == DecisionStatus.PENDING
        assert log.agent_type == "inventory_agent"
        assert log.ai_confidence == 0.85

    @pytest.mark.asyncio
    async def test_create_approval_request_succeeds(self):
        """② 创建审批请求成功：DecisionLog 正确持久化到 DB"""
        service = ApprovalService()
        service.wechat_service = MagicMock()
        service.wechat_service.send_approval_card = AsyncMock(return_value=True)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await service.create_approval_request(
            decision_type=DecisionType.PURCHASE_SUGGESTION,
            agent_type="inventory_agent",
            agent_method="suggest_purchase",
            store_id="STORE001",
            ai_suggestion={"items": [{"sku": "BEEF001", "qty": 30}]},
            ai_confidence=0.92,
            ai_reasoning="本周末预计客流+30%，牛肉库存需提前备货",
            db=mock_db,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_wechat_notification_sent(self):
        """③ 企微通知发送成功：send_approval_card 被调用"""
        service = ApprovalService()
        service.wechat_service = MagicMock()
        service.wechat_service.send_approval_card = AsyncMock(return_value=True)

        mock_store = MagicMock()
        mock_store.name = "太白路旗舰店"
        mock_manager = MagicMock()
        mock_manager.wechat_user_id = "wx_mgr_001"

        mock_db = AsyncMock(spec=AsyncSession)
        store_result = MagicMock()
        store_result.scalar_one_or_none.return_value = mock_store
        manager_result = MagicMock()
        manager_result.scalars.return_value.all.return_value = [mock_manager]
        mock_db.execute.side_effect = [store_result, manager_result]

        decision_log = _make_decision_log()
        await service._send_approval_notification(decision_log, mock_db)

        service.wechat_service.send_approval_card.assert_called_once_with(
            user_id="wx_mgr_001",
            message=service._build_approval_card(decision_log, mock_store),
            decision_id=decision_log.id,
        )

    @pytest.mark.asyncio
    async def test_manager_approves_decision(self):
        """④ 店长批准决策：状态变为 APPROVED，approval_chain 有记录"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)

        # _execute_decision 内部会查 notification model，patch 掉
        with patch.object(service, "_execute_decision", new=AsyncMock()):
            result = await service.approve_decision(
                decision_id=decision_log.id,
                manager_id="MGR001",
                manager_feedback="建议合理，立即执行",
                db=mock_db,
            )

        assert result.decision_status == DecisionStatus.APPROVED
        assert result.manager_id == "MGR001"
        assert len(result.approval_chain) == 1
        assert result.approval_chain[0]["action"] == "approved"

    @pytest.mark.asyncio
    async def test_decision_execution_triggered_after_approval(self):
        """⑤ 决策执行成功：approve_decision 后 _execute_decision 被调用"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)

        with patch.object(service, "_execute_decision", new=AsyncMock()) as mock_exec:
            await service.approve_decision(
                decision_id=decision_log.id,
                manager_id="MGR001",
                db=mock_db,
            )
            mock_exec.assert_awaited_once_with(decision_log, mock_db)

    @pytest.mark.asyncio
    async def test_record_outcome_succeeds(self):
        """⑥ 结果记录成功：outcome/actual_result/trust_score 均被写入"""
        service = ApprovalService()
        decision_log = _make_decision_log(status=DecisionStatus.APPROVED)
        mock_db = _mock_db_with_log(decision_log)

        result = await service.record_decision_outcome(
            decision_id=decision_log.id,
            outcome=DecisionOutcome.SUCCESS,
            actual_result={"value": 95, "cost_saved_yuan": 480.00},
            expected_result={"value": 100},
            business_impact={"cost_reduction_pct": 0.038},
            db=mock_db,
        )

        assert result.outcome == DecisionOutcome.SUCCESS
        assert result.actual_result["cost_saved_yuan"] == 480.00
        assert result.trust_score is not None
        assert result.is_training_data == 1


# ─── 2. 异常流程测试 ──────────────────────────────────────────────────────────

class TestExceptionFlow:
    """异常流程测试（4项）"""

    @pytest.mark.asyncio
    async def test_manager_rejects_decision(self):
        """⑦ 店长拒绝决策：状态变为 REJECTED，is_training_data=1"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)

        result = await service.reject_decision(
            decision_id=decision_log.id,
            manager_id="MGR001",
            manager_feedback="备货时机不对，节假日前3天再补",
            db=mock_db,
        )

        assert result.decision_status == DecisionStatus.REJECTED
        assert result.is_training_data == 1
        assert result.approval_chain[0]["action"] == "rejected"
        assert "备货时机不对" in result.approval_chain[0]["feedback"]

    @pytest.mark.asyncio
    async def test_manager_modifies_decision(self):
        """⑧ 店长修改决策：状态变为 MODIFIED，manager_decision 写入修改内容"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)

        modified = {"action": "reorder", "sku": "PORK001", "quantity": 30}  # 数量从50改30
        with patch.object(service, "_execute_decision", new=AsyncMock()):
            result = await service.modify_decision(
                decision_id=decision_log.id,
                manager_id="MGR001",
                modified_decision=modified,
                manager_feedback="数量调少一点，近期客流不稳",
                db=mock_db,
            )

        assert result.decision_status == DecisionStatus.MODIFIED
        assert result.manager_decision["quantity"] == 30
        assert result.approval_chain[0]["action"] == "modified"
        assert result.approval_chain[0]["original"]["quantity"] == 50
        assert result.is_training_data == 1

    @pytest.mark.asyncio
    async def test_execution_failure_raises_and_rolls_back(self):
        """⑨ 决策执行失败：异常向上传播，DB rollback 被调用"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)
        mock_db.commit.side_effect = Exception("DB connection lost")

        with pytest.raises(Exception, match="DB connection lost"):
            await service.approve_decision(
                decision_id=decision_log.id,
                manager_id="MGR001",
                db=mock_db,
            )

        mock_db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_network_exception_in_wechat_notification(self):
        """⑩ 网络异常处理：企微推送失败时不影响主流程，只记录 error log"""
        service = ApprovalService()
        service.wechat_service = MagicMock()
        service.wechat_service.send_approval_card = AsyncMock(
            side_effect=ConnectionError("WeChat API timeout")
        )

        mock_store = MagicMock()
        mock_store.name = "IFS店"
        mock_manager = MagicMock()
        mock_manager.wechat_user_id = "wx_mgr_002"

        mock_db = AsyncMock(spec=AsyncSession)
        store_result = MagicMock()
        store_result.scalar_one_or_none.return_value = mock_store
        manager_result = MagicMock()
        manager_result.scalars.return_value.all.return_value = [mock_manager]
        mock_db.execute.side_effect = [store_result, manager_result]

        decision_log = _make_decision_log()
        # 不应抛出异常，企微失败静默处理
        await service._send_approval_notification(decision_log, mock_db)


# ─── 3. 性能测试 ──────────────────────────────────────────────────────────────

class TestPerformance:
    """性能测试（3项）"""

    @pytest.mark.asyncio
    async def test_create_approval_request_under_1s(self):
        """⑪ 审批请求响应时间 < 1s（service层，不含网络IO）"""
        service = ApprovalService()
        service.wechat_service = MagicMock()
        service.wechat_service.send_approval_card = AsyncMock(return_value=True)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        start = time.perf_counter()
        await service.create_approval_request(
            decision_type=DecisionType.SCHEDULE_OPTIMIZATION,
            agent_type="schedule_agent",
            agent_method="optimize_schedule",
            store_id="STORE001",
            ai_suggestion={"shifts": []},
            ai_confidence=0.78,
            ai_reasoning="节假日排班优化",
            db=mock_db,
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"响应时间 {elapsed:.3f}s 超过 1s 阈值"

    @pytest.mark.asyncio
    async def test_wechat_notification_completes_under_5s(self):
        """⑫ 企微通知送达时间 < 5s（mock 网络延迟0.1s模拟）"""
        service = ApprovalService()
        service.wechat_service = MagicMock()

        async def _slow_send(**kwargs):
            await asyncio.sleep(0.1)  # 模拟100ms网络延迟
            return True

        service.wechat_service.send_approval_card = AsyncMock(side_effect=_slow_send)

        mock_store = MagicMock()
        mock_store.name = "五一广场店"
        mock_manager = MagicMock()
        mock_manager.wechat_user_id = "wx_mgr_003"

        mock_db = AsyncMock(spec=AsyncSession)
        store_result = MagicMock()
        store_result.scalar_one_or_none.return_value = mock_store
        manager_result = MagicMock()
        manager_result.scalars.return_value.all.return_value = [mock_manager]
        mock_db.execute.side_effect = [store_result, manager_result]

        decision_log = _make_decision_log()

        start = time.perf_counter()
        await service._send_approval_notification(decision_log, mock_db)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"通知送达时间 {elapsed:.3f}s 超过 5s 阈值"

    @pytest.mark.asyncio
    async def test_decision_execution_time_reasonable(self):
        """⑬ 决策执行时间合理：approve→execute 整体 < 2s（mock DB）"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)

        with patch.object(service, "_execute_decision", new=AsyncMock()):
            start = time.perf_counter()
            await service.approve_decision(
                decision_id=decision_log.id,
                manager_id="MGR001",
                db=mock_db,
            )
            elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"执行时间 {elapsed:.3f}s 超过 2s 阈值"


# ─── 4. 数据完整性测试 ────────────────────────────────────────────────────────

class TestDataIntegrity:
    """数据完整性测试（3项）"""

    @pytest.mark.asyncio
    async def test_decision_log_completely_recorded(self):
        """⑭ 决策日志完整记录：所有必填字段均不为 None"""
        service = ApprovalService()
        service.wechat_service = MagicMock()
        service.wechat_service.send_approval_card = AsyncMock(return_value=True)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        log = await service.create_approval_request(
            decision_type=DecisionType.COST_OPTIMIZATION,
            agent_type="decision_agent",
            agent_method="optimize_cost",
            store_id="STORE001",
            ai_suggestion={"reduce_portion_pct": 5, "expected_saving_yuan": 1200.00},
            ai_confidence=0.80,
            ai_reasoning="通过微调份量减少食材损耗，预计节省¥1,200/月",
            context_data={"current_cost_rate": 0.38, "target_cost_rate": 0.36},
            db=mock_db,
        )

        required_fields = [
            "id", "decision_type", "agent_type", "agent_method",
            "store_id", "ai_suggestion", "ai_confidence",
            "ai_reasoning", "decision_status", "created_at",
        ]
        for field in required_fields:
            assert getattr(log, field) is not None, f"字段 {field} 不应为 None"

    @pytest.mark.asyncio
    async def test_approval_chain_correctly_recorded(self):
        """⑮ 审批链正确记录：每次操作在 approval_chain 中追加正确的条目"""
        service = ApprovalService()
        decision_log = _make_decision_log()
        mock_db = _mock_db_with_log(decision_log)

        with patch.object(service, "_execute_decision", new=AsyncMock()):
            result = await service.approve_decision(
                decision_id=decision_log.id,
                manager_id="MGR001",
                manager_feedback="同意执行",
                db=mock_db,
            )

        chain = result.approval_chain
        assert len(chain) == 1
        entry = chain[0]
        assert entry["action"] == "approved"
        assert entry["manager_id"] == "MGR001"
        assert entry["feedback"] == "同意执行"
        assert "timestamp" in entry

    def test_trust_score_calculation_correct(self):
        """⑯ 信任度评分正确计算：权重公式验证（AI置信度30% + 采纳40% + 偏差30%）"""
        service = ApprovalService()

        # 场景A：完全采纳 + 置信度0.9 + 偏差5%（低偏差）
        # 预期 = 0.9×30 + 40 + 30 = 97
        log_a = _make_decision_log(
            status=DecisionStatus.APPROVED,
            ai_confidence=0.9,
            result_deviation=5.0,
        )
        score_a = service._calculate_trust_score(log_a)
        assert 90 <= score_a <= 100, f"场景A信任度 {score_a} 不在预期范围 [90, 100]"

        # 场景B：部分采纳（MODIFIED）+ 置信度0.7 + 偏差15%（中等偏差）
        # 预期 = 0.7×30 + 20 + 20 = 61
        log_b = _make_decision_log(
            status=DecisionStatus.MODIFIED,
            ai_confidence=0.7,
            result_deviation=15.0,
        )
        score_b = service._calculate_trust_score(log_b)
        assert 55 <= score_b <= 70, f"场景B信任度 {score_b} 不在预期范围 [55, 70]"

        # 场景C：被拒绝（REJECTED）+ 置信度0.6 + 无结果偏差
        # 预期 = 0.6×30 + 0 = 18
        log_c = _make_decision_log(
            status=DecisionStatus.REJECTED,
            ai_confidence=0.6,
            result_deviation=None,
        )
        score_c = service._calculate_trust_score(log_c)
        assert 15 <= score_c <= 25, f"场景C信任度 {score_c} 不在预期范围 [15, 25]"

        # 低置信度得分 < 高置信度得分（单调性检验）
        assert score_c < score_b < score_a
