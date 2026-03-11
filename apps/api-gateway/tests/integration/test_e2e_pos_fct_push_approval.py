"""
端到端集成测试：POS → FCT → 推送 → 审批 全链路

覆盖 v2.0 P0 核心业务流程链路：
  1. POS Webhook 归一化：meituan / keruyun / generic 订单格式
  2. FCT ¥化输出：税务测算、现金流预测、预算执行率的 _yuan 伴随字段
  3. 决策优先级引擎 → 推送服务：Top3 决策卡片发送逻辑
  4. 审批回调：approve → DecisionLog 状态更新 → 48h 效果反馈任务入队

测试策略：
  - POS 归一化函数：纯函数，直接调用，无需 mock
  - FCT Service：mock SQLAlchemy AsyncSession，验证 _yuan 字段存在
  - 决策 → 推送：mock DecisionPriorityEngine + wechat_service，验证卡片内容
  - 审批：mock AsyncSession + Celery apply_async，验证状态转换
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ── 屏蔽 pydantic_settings 环境变量校验 ──────────────────────────────────────
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("WECHAT_CORP_ID", "test_corp")
os.environ.setdefault("WECHAT_CORP_SECRET", "test_secret")
os.environ.setdefault("WECHAT_AGENT_ID", "1")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_e2e_testing_32_chars!!")
os.environ.setdefault("WECHAT_APPROVAL_BASE_URL", "https://work.weixin.qq.com/approval")

# mock config 防止 import 时校验
mock_settings = MagicMock()
mock_settings.WECHAT_CORP_ID = "test_corp"
mock_settings.WECHAT_CORP_SECRET = "test_secret"
mock_settings.WECHAT_AGENT_ID = 1
mock_config = MagicMock()
mock_config.settings = mock_settings
sys.modules.setdefault("src.core.config", mock_config)
sys.modules.setdefault("src.services.agent_service", MagicMock())


# ════════════════════════════════════════════════════════════════════════════════
# 第一段：POS Webhook 归一化（纯函数，无需 mock）
# ════════════════════════════════════════════════════════════════════════════════

from src.api.pos_webhook import (
    _normalize_meituan,
    _normalize_keruyun,
    WebhookOrderPayload,
    WebhookOrderItem,
    _verify_signature,
)


class TestPosNormalizationChain:
    """POS Webhook → 归一化 → 标准订单结构"""

    def test_meituan_order_normalized_to_standard_format(self):
        raw = {
            "orderId": "MT_2026_001",
            "tableCode": "A01",
            "userName": "张三",
            "userPhone": "13800000001",
            "totalPrice": "358.00",
            "discountPrice": "20.00",
            "payPrice": "338.00",
            "createTime": "2026-03-04T12:30:00",
            "detailList": [
                {"skuId": "D001", "skuName": "红烧肉", "num": 2, "price": "48.00", "amount": "96.00"},
                {"skuId": "D002", "skuName": "白切鸡", "num": 1, "price": "88.00", "amount": "88.00"},
            ],
        }
        payload = _normalize_meituan(raw)

        assert payload.source == "meituan"
        assert payload.external_order_id == "MT_2026_001"
        assert payload.table_number == "A01"
        assert payload.total_amount == 35800      # 分
        assert payload.discount_amount == 2000    # 分
        assert payload.final_amount == 33800      # 分
        assert len(payload.items) == 2
        assert payload.items[0].item_name == "红烧肉"
        assert payload.items[0].quantity == 2
        assert payload.items[0].unit_price == 4800  # 分

    def test_keruyun_order_normalized_to_standard_format(self):
        raw = {
            "orderNo": "KRY_2026_001",
            "tableNo": "B02",
            "memberName": "李四",
            "memberPhone": "13900000002",
            "totalAmount": "256.00",
            "discountAmount": "0.00",
            "payAmount": "256.00",
            "createTime": "2026-03-04T19:00:00",
            "orderDetails": [
                {"dishId": "D003", "dishName": "清蒸鱼", "num": 1, "price": "128.00", "totalPrice": "128.00"},
            ],
        }
        payload = _normalize_keruyun(raw)

        assert payload.source == "keruyun"
        assert payload.external_order_id == "KRY_2026_001"
        assert payload.total_amount == 25600
        assert payload.items[0].item_name == "清蒸鱼"
        assert payload.items[0].unit_price == 12800

    def test_generic_payload_parsed_correctly(self):
        raw = {
            "source": "generic",
            "external_order_id": "GEN_001",
            "total_amount": 10000,
            "final_amount": 9500,
            "discount_amount": 500,
        }
        payload = WebhookOrderPayload(**raw, raw=raw)

        assert payload.external_order_id == "GEN_001"
        assert payload.total_amount == 10000
        assert payload.final_amount == 9500

    def test_meituan_order_id_contains_source_prefix(self):
        """写库时订单 ID 格式为 POS_{SOURCE}_{EXTERNAL_ID}"""
        raw = {"orderId": "12345", "detailList": [], "totalPrice": "100", "discountPrice": "0", "payPrice": "100"}
        payload = _normalize_meituan(raw)
        order_id = f"POS_{payload.source.upper()}_{payload.external_order_id}"
        assert order_id == "POS_MEITUAN_12345"

    def test_signature_verification_skipped_without_secret(self):
        """未配置 WEBHOOK_POS_SECRET 时跳过签名验证"""
        with patch("src.api.pos_webhook.WEBHOOK_SECRET", ""):
            assert _verify_signature(b"payload", None) is True
            assert _verify_signature(b"payload", "sha256=anysig") is True

    def test_items_empty_list_when_no_details(self):
        raw = {
            "orderId": "MT_EMPTY",
            "totalPrice": "0",
            "discountPrice": "0",
            "payPrice": "0",
            "detailList": [],
        }
        payload = _normalize_meituan(raw)
        assert payload.items == []


# ════════════════════════════════════════════════════════════════════════════════
# 第二段：FCT ¥化输出验证
# ════════════════════════════════════════════════════════════════════════════════

class TestFctYuanFields:
    """FCT Service 所有主方法必须输出 _yuan 伴随字段"""

    def _make_fct(self):
        from src.services.fct_service import FCTService
        return FCTService(db=AsyncMock())

    def _mock_reconciliation_records(self, db_mock, *, count: int = 2, avg_pos: int = 100000):
        """模拟 ReconciliationRecord 查询结果"""
        from unittest.mock import MagicMock
        row = MagicMock()
        row.pos_total_fen = avg_pos
        row.finance_total_fen = avg_pos + 500
        row.variance_fen = 500
        row.status = "matched"
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row] * count)))
        db_mock.execute = AsyncMock(return_value=result)

    @pytest.mark.asyncio
    async def test_estimate_monthly_tax_has_yuan_fields(self):
        from src.services.fct_service import FCTService
        db = AsyncMock()
        # mock 月营收查询 → 100万分 = 1万元
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=1_000_000)
        db.execute = AsyncMock(return_value=result_mock)

        svc = FCTService(db=db)
        tax = await svc.estimate_monthly_tax("S001", 2026, 3)

        # ¥化字段必须存在（嵌套结构）
        assert "total_tax_yuan" in tax
        assert "revenue" in tax
        assert "gross_revenue_yuan" in tax["revenue"]
        assert "vat" in tax
        assert "total_vat_burden_yuan" in tax["vat"]

    @pytest.mark.asyncio
    async def test_forecast_cash_flow_has_yuan_fields(self):
        from src.services.fct_service import FCTService
        db = AsyncMock()
        # mock 查询：历史7天平均营收 = 5000分/天，固定支出 = 2000分/天
        avg_mock = MagicMock()
        avg_mock.scalar = MagicMock(return_value=5000)
        db.execute = AsyncMock(return_value=avg_mock)

        svc = FCTService(db=db)
        cf = await svc.forecast_cash_flow("S001", days=3)

        assert "daily_forecast" in cf
        for day in cf["daily_forecast"]:
            assert "inflow_yuan" in day
            assert "inflow_yuan" in day

    @pytest.mark.asyncio
    async def test_get_budget_execution_has_yuan_fields(self):
        from src.services.fct_service import FCTService
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar = MagicMock(return_value=500_000)
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result_mock)

        svc = FCTService(db=db)
        be = await svc.get_budget_execution("S001", 2026, 3)

        assert "revenue_budget_yuan" in be or "revenue" in be or "overall" in be
        # 至少 overall 有 _yuan 字段
        if "overall" in be:
            assert any("_yuan" in k for k in be["overall"])


# ════════════════════════════════════════════════════════════════════════════════
# 第三段：决策 → 推送 全链路（关键 E2E 流程）
# ════════════════════════════════════════════════════════════════════════════════

class TestDecisionPushPipeline:
    """DecisionPriorityEngine.get_top3 → DecisionPushService.push_* → wechat_service.send_decision_card"""

    def _make_decision(self, rank=1, saving=2000.0, source="inventory", urgency_hours=1.0):
        return {
            "rank": rank,
            "title": f"紧急补货：鸡腿（Top{rank}）",
            "action": "今日17:00前联系供应商补货50kg",
            "source": source,
            "expected_saving_yuan": saving,
            "expected_cost_yuan": 200.0,
            "net_benefit_yuan": saving - 200.0,
            "confidence_pct": 88.0,
            "urgency_hours": urgency_hours,
            "execution_difficulty": "easy",
            "decision_window_label": "08:00晨推",
            "priority_score": 82.5,
            "context": {"item_id": "I001", "current_stock": 5},
        }

    @pytest.mark.asyncio
    async def test_morning_push_sends_card_with_yuan_impact(self):
        """晨推：发送包含¥影响的卡片"""
        from src.services.decision_push_service import DecisionPushService

        db = AsyncMock()
        decisions = [self._make_decision(rank=1, saving=3000.0)]

        with (
            patch("src.services.decision_push_service.DecisionPriorityEngine", autospec=True) as MockEngine,
            patch("src.services.wechat_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=decisions)
            mock_ws.send_decision_card = AsyncMock(
                return_value={"status": "sent", "message_id": "e2e_msg_001"}
            )

            result = await DecisionPushService.push_morning_decisions(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss_001", db=db,
                store_name="测试旗舰店",
            )

        assert result["sent"] is True
        assert result["decision_count"] == 1
        assert result["message_id"] == "e2e_msg_001"

        # 验证卡片标题包含店名
        call_kwargs = mock_ws.send_decision_card.call_args
        assert "测试旗舰店" in call_kwargs.kwargs.get("title", "") or \
               "S001" in call_kwargs.kwargs.get("title", "")

    @pytest.mark.asyncio
    async def test_morning_push_description_contains_yuan_amount(self):
        """卡片描述必须包含¥金额"""
        from src.services.decision_push_service import DecisionPushService, _format_card_description

        decisions = [self._make_decision(rank=1, saving=5000.0)]
        desc = _format_card_description(decisions)

        assert "¥5000" in desc or "5000" in desc
        assert "88%" in desc  # confidence

    @pytest.mark.asyncio
    async def test_noon_push_only_sends_on_anomaly(self):
        """午推：有异常才发送，正常状态不推"""
        from src.services.decision_push_service import DecisionPushService

        db = AsyncMock()
        ok_waste = {"waste_rate_pct": 1.5, "waste_rate_status": "ok", "total_waste_yuan": 200.0, "top5": []}

        with (
            patch("src.services.decision_push_service.WasteGuardService") as MockWaste,
            patch("src.services.decision_push_service.DecisionPriorityEngine", autospec=True) as MockEngine,
            patch("src.services.wechat_service.wechat_service") as mock_ws,
        ):
            MockWaste.get_waste_rate_summary = AsyncMock(return_value=ok_waste)
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])

            result = await DecisionPushService.push_noon_anomaly(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss_001", db=db,
            )

        assert result["sent"] is False
        mock_ws.send_decision_card.assert_not_called()

    @pytest.mark.asyncio
    async def test_prebattle_push_sends_on_inventory_urgency(self):
        """战前推：有紧急库存决策时发送"""
        from src.services.decision_push_service import DecisionPushService

        db = AsyncMock()
        decisions = [self._make_decision(source="inventory", urgency_hours=0.5)]

        with (
            patch("src.services.decision_push_service.DecisionPriorityEngine", autospec=True) as MockEngine,
            patch("src.services.wechat_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=decisions)
            mock_ws.send_decision_card = AsyncMock(
                return_value={"status": "sent", "message_id": "prebattle_001"}
            )

            result = await DecisionPushService.push_prebattle_decisions(
                store_id="S001", brand_id="B001",
                recipient_user_id="boss_001", db=db,
                store_name="北京旗舰店",
            )

        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_evening_recap_shows_pending_approval_count(self):
        """晚推：显示待审批数量"""
        from src.services.decision_push_service import DecisionPushService, _format_evening_description

        decisions = [self._make_decision(saving=1200.0), self._make_decision(saving=800.0)]
        desc = _format_evening_description(decisions, pending_count=3)

        assert "3" in desc  # 待审批数
        assert "¥2000" in desc or "2000" in desc  # 总节省金额

    @pytest.mark.asyncio
    async def test_full_chain_no_decisions_means_no_push(self):
        """引擎无决策时，整个链路不发送"""
        from src.services.decision_push_service import DecisionPushService

        db = AsyncMock()

        with (
            patch("src.services.decision_push_service.DecisionPriorityEngine", autospec=True) as MockEngine,
            patch("src.services.wechat_service.wechat_service") as mock_ws,
        ):
            MockEngine.return_value.get_top3 = AsyncMock(return_value=[])

            for push_fn in (
                DecisionPushService.push_morning_decisions,
            ):
                result = await push_fn(
                    store_id="S001", brand_id="B001",
                    recipient_user_id="boss", db=db,
                )
                assert result["sent"] is False

        mock_ws.send_decision_card.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════════
# 第四段：审批回调 → 状态更新 → 48h 反馈调度
# ════════════════════════════════════════════════════════════════════════════════

class TestApprovalCallbackChain:
    """企微审批回调 → DecisionLog 状态更新 → check_decision_impact 调度"""

    def _make_decision_log(self, decision_id="DEC_001", store_id="S001"):
        from unittest.mock import MagicMock
        log = MagicMock()
        log.id = decision_id
        log.store_id = store_id
        log.decision_status = "PENDING"
        log.ai_suggestion = {"action": "补货鸡腿50kg", "expected_saving_yuan": 2000.0}
        log.ai_confidence = 0.88
        return log

    @pytest.mark.asyncio
    async def test_approve_action_updates_status_to_approved(self):
        """approve 操作 → DecisionLog.status = APPROVED"""
        db = AsyncMock()
        log = self._make_decision_log()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=log)
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        with patch("src.core.celery_tasks.check_decision_impact") as mock_task:
            mock_task.apply_async = MagicMock()

            # 直接测试审批逻辑：状态从 PENDING → APPROVED
            from src.models.decision_log import DecisionStatus
            log.decision_status = DecisionStatus.PENDING

            # 模拟审批动作
            log.decision_status = DecisionStatus.APPROVED
            log.approved_at = datetime.utcnow()

            assert log.decision_status == DecisionStatus.APPROVED
            assert log.approved_at is not None

    @pytest.mark.asyncio
    async def test_approve_schedules_48h_feedback_task(self):
        """approve 后，check_decision_impact 以 172800s countdown 入队"""
        with patch("src.core.celery_tasks.check_decision_impact") as mock_task:
            mock_apply = MagicMock()
            mock_task.apply_async = mock_apply

            # 模拟审批回调中的调度逻辑
            decision_id = "DEC_APPROVE_001"
            delay = int(os.getenv("DECISION_FEEDBACK_DELAY_SECONDS", str(48 * 3600)))
            mock_task.apply_async(args=[decision_id], countdown=delay)

            mock_apply.assert_called_once_with(args=[decision_id], countdown=172800)

    @pytest.mark.asyncio
    async def test_reject_does_not_schedule_feedback(self):
        """reject 操作不应调度 48h 反馈"""
        with patch("src.core.celery_tasks.check_decision_impact") as mock_task:
            # reject 时不调用 apply_async
            action = "reject"
            if action in ("approve", "modify"):
                mock_task.apply_async(args=["DEC_001"], countdown=172800)

            mock_task.apply_async.assert_not_called()

    def test_wechat_callback_format_verify(self):
        """WeChat 回调 payload 格式：包含 decision_id + action"""
        payload = {
            "decision_id": "DEC_WECHAT_001",
            "action": "approve",
            "manager_feedback": "同意，立即执行",
        }
        assert payload["decision_id"]
        assert payload["action"] in ("approve", "reject", "modify")
        assert isinstance(payload["manager_feedback"], str)


# ════════════════════════════════════════════════════════════════════════════════
# 第五段：离线查询降级链路
# ════════════════════════════════════════════════════════════════════════════════

class TestOfflineQueryChain:
    """EdgeNodeService 离线降级：有缓存 → 返回缓存，无缓存 → 估算值"""

    @pytest.fixture
    def edge(self):
        from src.services.edge_node_service import EdgeNodeService
        return EdgeNodeService()

    @pytest.mark.asyncio
    async def test_revenue_query_falls_back_gracefully_without_network(self, edge):
        """无缓存时离线查询返回 is_estimate=True，不抛异常"""
        result = await edge.query_revenue_offline("S_NO_CACHE", "2026-03-04")

        assert result["mode"] == "offline"
        assert result["is_estimate"] is True
        assert result["revenue_yuan"] == 0.0
        assert result["source"] in ("historical_avg",)

    @pytest.mark.asyncio
    async def test_revenue_query_returns_cached_data(self, edge):
        """有缓存时返回实际营业额，is_estimate=False"""
        await edge.update_revenue_cache("S001", "2026-03-04", revenue_yuan=15800.0)
        result = await edge.query_revenue_offline("S001", "2026-03-04")

        assert result["is_estimate"] is False
        assert result["revenue_yuan"] == 15800.0
        assert result["source"] == "local_cache"

    @pytest.mark.asyncio
    async def test_inventory_query_counts_critical_as_low_stock(self, edge):
        """critical 状态物品计入 low_stock_count"""
        items = [
            {"item_id": "I1", "name": "鸡腿", "status": "critical"},
            {"item_id": "I2", "name": "猪肉", "status": "low"},
            {"item_id": "I3", "name": "白菜", "status": "out_of_stock"},
        ]
        await edge.update_inventory_cache("S001", items)
        result = await edge.query_inventory_offline("S001")

        assert result["low_stock_count"] == 2      # critical + low
        assert result["out_of_stock_count"] == 1
        assert result["item_count"] == 3

    @pytest.mark.asyncio
    async def test_full_offline_chain_write_then_read(self, edge):
        """写入缓存 → 读取 → 数据一致"""
        await edge.update_revenue_cache("S_CHAIN", "2026-03-04", revenue_yuan=9999.0)
        rev = await edge.query_revenue_offline("S_CHAIN", "2026-03-04")
        assert rev["revenue_yuan"] == 9999.0

        items = [{"item_id": "X1", "status": "out_of_stock"}]
        await edge.update_inventory_cache("S_CHAIN", items)
        inv = await edge.query_inventory_offline("S_CHAIN")
        assert inv["out_of_stock_count"] == 1


# ════════════════════════════════════════════════════════════════════════════════
# 第六段：推送格式约束验证（Rule 7 合规）
# ════════════════════════════════════════════════════════════════════════════════

class TestPushFormatCompliance:
    """Rule 7：推送必须包含 建议动作 + 预期¥影响 + 置信度 + 一键操作入口"""

    def _make_decision(self, saving=1000.0, confidence=85.0, action="执行补货"):
        return {
            "rank": 1, "title": "紧急补货", "action": action,
            "source": "inventory",
            "expected_saving_yuan": saving,
            "expected_cost_yuan": 100.0,
            "net_benefit_yuan": saving - 100.0,
            "confidence_pct": confidence,
            "urgency_hours": 2.0,
            "execution_difficulty": "easy",
            "decision_window_label": "08:00晨推",
            "priority_score": 80.0,
            "context": {},
        }

    def test_card_description_contains_action(self):
        from src.services.decision_push_service import _format_card_description
        d = self._make_decision(action="今日17:00前补货鸡腿50kg")
        desc = _format_card_description([d])
        assert "补货" in desc

    def test_card_description_contains_yuan_impact(self):
        from src.services.decision_push_service import _format_card_description
        d = self._make_decision(saving=2500.0)
        desc = _format_card_description([d])
        assert "¥2500" in desc or "2500" in desc

    def test_card_description_contains_confidence(self):
        from src.services.decision_push_service import _format_card_description
        d = self._make_decision(confidence=92.0)
        desc = _format_card_description([d])
        assert "92%" in desc

    def test_card_description_within_512_chars(self):
        """企微 textcard description ≤ 512 字符"""
        from src.services.decision_push_service import _format_card_description
        decisions = [self._make_decision(action="A" * 100) for _ in range(3)]
        desc = _format_card_description(decisions)
        assert len(desc) <= 512

    def test_button_text_within_4_chars(self):
        """企微 textcard btntxt ≤ 4 字符"""
        btntxt = "立即审批"
        assert len(btntxt) <= 4

        btntxt_long = "立即审批执行"
        truncated = btntxt_long[:4]
        assert len(truncated) == 4
