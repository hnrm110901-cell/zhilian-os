"""
Phase 4 测试套件：AI 预测标签 + 客户旅程自动化引擎

覆盖：
- ConsumerPredictionService: churn / upgrade / CLV 算法
- CustomerJourneyEngine: 步骤执行 / 条件分支 / seed 模板
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.consumer_prediction_service import (
    ConsumerPredictionService,
    _LEVEL_ORDER,
    _LIFECYCLE_CHURN_WEIGHT,
)
from src.services.customer_journey_engine import (
    CustomerJourneyEngine,
    DEFAULT_JOURNEY_TEMPLATES,
)


# ── 测试辅助 ─────────────────────────────────────────────────────────────────


def _make_profile(
    order_count: int = 5,
    order_amount_fen: int = 50_000,
    days_since_last: int = 10,
    days_since_first: int = 90,
    lifecycle_state: str = "repeat",
    brand_level: str = "普通",
    brand_points: int = 200,
    group_id: str = "g001",
) -> Dict[str, Any]:
    """构造一条 brand_consumer_profiles 字典"""
    now = datetime.utcnow()
    return {
        "id": str(uuid.uuid4()),
        "brand_level": brand_level,
        "brand_points": brand_points,
        "brand_order_count": order_count,
        "brand_order_amount_fen": order_amount_fen,
        "brand_first_order_at": now - timedelta(days=days_since_first),
        "brand_last_order_at": now - timedelta(days=days_since_last),
        "lifecycle_state": lifecycle_state,
        "group_id": group_id,
    }


def _mock_session_with_profile(profile: Optional[Dict]) -> AsyncMock:
    """构造返回指定档案的 AsyncSession mock"""
    session = AsyncMock()
    if profile is None:
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        session.execute.return_value = result_mock
    else:
        row_mock = MagicMock()
        row_mock._mapping = profile
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row_mock
        session.execute.return_value = result_mock
    return session


# ── ConsumerPredictionService 测试 ───────────────────────────────────────────


class TestChurnScoreIncreasesWithDormancy:
    """流失分随停止消费天数增加而升高"""

    @pytest.mark.asyncio
    async def test_churn_score_increases_with_dormancy(self):
        svc = ConsumerPredictionService()
        consumer_id = str(uuid.uuid4())
        brand_id = "brand_001"

        # 场景 A：10天未消费（正常）
        profile_active = _make_profile(days_since_last=10, lifecycle_state="repeat")
        session_a = _mock_session_with_profile(profile_active)
        result_a = await svc.predict_churn_risk(consumer_id, brand_id, session_a)
        score_a = result_a["churn_score"]

        # 场景 B：60天未消费（高危）
        profile_dormant = _make_profile(days_since_last=60, lifecycle_state="at_risk")
        session_b = _mock_session_with_profile(profile_dormant)
        result_b = await svc.predict_churn_risk(consumer_id, brand_id, session_b)
        score_b = result_b["churn_score"]

        assert score_b > score_a, f"60天分({score_b})应高于10天分({score_a})"
        assert 0.0 <= score_a <= 1.0, "分数必须在[0, 1]"
        assert 0.0 <= score_b <= 1.0, "分数必须在[0, 1]"

    @pytest.mark.asyncio
    async def test_churn_risk_level_critical_for_dormant(self):
        svc = ConsumerPredictionService()
        profile = _make_profile(days_since_last=120, lifecycle_state="dormant")
        session = _mock_session_with_profile(profile)
        result = await svc.predict_churn_risk(str(uuid.uuid4()), "brand_001", session)
        assert result["risk_level"] in ("high", "critical")

    @pytest.mark.asyncio
    async def test_churn_score_clipped_to_one(self):
        svc = ConsumerPredictionService()
        profile = _make_profile(days_since_last=999, lifecycle_state="lost")
        session = _mock_session_with_profile(profile)
        result = await svc.predict_churn_risk(str(uuid.uuid4()), "brand_001", session)
        assert result["churn_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_churn_returns_empty_when_profile_missing(self):
        svc = ConsumerPredictionService()
        session = _mock_session_with_profile(None)
        result = await svc.predict_churn_risk(str(uuid.uuid4()), "brand_001", session)
        assert result["churn_score"] == 0.0
        assert result["risk_level"] == "low"


class TestUpgradeProbabilityBasedOnSpendVelocity:
    """升级概率与消费速率成正比"""

    @pytest.mark.asyncio
    async def test_high_spender_has_higher_upgrade_probability(self):
        svc = ConsumerPredictionService()
        brand_id = "brand_002"

        # 高消费速率：3个月花了10万分=1000元
        profile_high = _make_profile(
            order_count=10,
            order_amount_fen=100_000,
            days_since_first=90,
            brand_level="普通",
            brand_points=800,
        )
        session_h = _mock_session_with_profile(profile_high)
        result_h = await svc.predict_upgrade_probability(str(uuid.uuid4()), brand_id, session_h)

        # 低消费速率：3个月花了2000分=20元
        profile_low = _make_profile(
            order_count=2,
            order_amount_fen=2_000,
            days_since_first=90,
            brand_level="普通",
            brand_points=100,
        )
        session_l = _mock_session_with_profile(profile_low)
        result_l = await svc.predict_upgrade_probability(str(uuid.uuid4()), brand_id, session_l)

        assert result_h["upgrade_probability_30d"] >= result_l["upgrade_probability_30d"]
        assert 0.0 <= result_h["upgrade_probability_30d"] <= 1.0
        assert 0.0 <= result_l["upgrade_probability_30d"] <= 1.0

    @pytest.mark.asyncio
    async def test_top_level_member_returns_no_next_level(self):
        svc = ConsumerPredictionService()
        profile = _make_profile(brand_level="钻石", brand_points=50_000)
        session = _mock_session_with_profile(profile)
        result = await svc.predict_upgrade_probability(str(uuid.uuid4()), "brand_002", session)
        assert result["next_level"] is None
        assert result["upgrade_probability_30d"] == 0.0


class TestClvCalculationVipThreshold:
    """CLV 分段：超过50万分(5000元)应为 vip"""

    @pytest.mark.asyncio
    async def test_high_clv_consumer_classified_as_vip(self):
        svc = ConsumerPredictionService()
        # 每月花5万分=500元，活跃24个月 → CLV = 500*12/月×24 ≈ 很高
        profile = _make_profile(
            order_count=100,
            order_amount_fen=1_200_000,  # 12000元总消费
            days_since_first=365,
            lifecycle_state="vip",
        )
        session = _mock_session_with_profile(profile)
        result = await svc.estimate_clv(str(uuid.uuid4()), "brand_003", session)
        assert result["clv_segment"] in ("high", "vip")
        assert result["clv_fen"] > 0

    @pytest.mark.asyncio
    async def test_low_spend_consumer_classified_as_low_clv(self):
        svc = ConsumerPredictionService()
        profile = _make_profile(
            order_count=1,
            order_amount_fen=5_000,  # 50元
            days_since_first=30,
            lifecycle_state="registered",
        )
        session = _mock_session_with_profile(profile)
        result = await svc.estimate_clv(str(uuid.uuid4()), "brand_003", session)
        assert result["clv_segment"] in ("low", "medium")
        assert result["clv_yuan"] is not None

    @pytest.mark.asyncio
    async def test_clv_yuan_matches_fen_conversion(self):
        svc = ConsumerPredictionService()
        profile = _make_profile(order_count=5, order_amount_fen=50_000, days_since_first=90)
        session = _mock_session_with_profile(profile)
        result = await svc.estimate_clv(str(uuid.uuid4()), "brand_003", session)
        assert float(result["clv_yuan"]) == result["clv_fen"] / 100


# ── CustomerJourneyEngine 测试 ────────────────────────────────────────────────


def _make_journey_template(step_type: str = "send_wecom") -> Dict[str, Any]:
    """构造单步旅程模板 dict（不含 DB id）"""
    return {
        "template_name": f"测试旅程_{step_type}",
        "trigger_event": "member_registered",
        "steps": [
            {
                "step_id": "s1",
                "step_type": step_type,
                "config": {"template_id": "journey_welcome", "message": "欢迎"},
                "next_step_id": "END",
            }
        ],
    }


def _mock_engine_session(
    template: Optional[Dict] = None,
    instance: Optional[Dict] = None,
    order_count: int = 0,
) -> AsyncMock:
    """构造支持多次 execute 调用的 session mock"""
    session = AsyncMock()
    session.commit = AsyncMock()

    template_row = None
    if template is not None:
        template_row = MagicMock()
        template_row._mapping = {
            "id": str(uuid.uuid4()),
            "brand_id": "brand_test",
            "group_id": "g_test",
            "template_name": template.get("template_name", "test"),
            "trigger_event": template.get("trigger_event", "member_registered"),
            "steps": json.dumps(template.get("steps", []), ensure_ascii=False),
            "is_active": True,
            "is_default": False,
        }

    instance_row = None
    if instance is not None:
        instance_row = MagicMock()
        instance_row._mapping = instance

    cnt_row = MagicMock()
    cnt_row.cnt = order_count

    call_count = 0

    async def side_effect(query, params=None):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        # 第1次 → 加载模板 / 创建实例 / 列表
        if template_row is not None and call_count <= 2:
            result.fetchone.return_value = template_row
            result.fetchall.return_value = [template_row]
        elif instance_row is not None and call_count == 3:
            result.fetchone.return_value = instance_row
        else:
            result.fetchone.return_value = cnt_row
            result.fetchall.return_value = []
        return result

    session.execute.side_effect = side_effect
    return session


class TestJourneyStepExecutionSendWecom:
    """send_wecom 步骤正确调用 wecom_scrm_service"""

    @pytest.mark.asyncio
    async def test_send_wecom_step_invoked(self):
        engine = CustomerJourneyEngine()
        template = _make_journey_template("send_wecom")
        instance_id = str(uuid.uuid4())
        template_id = str(uuid.uuid4())

        instance_data = {
            "id": instance_id,
            "template_id": template_id,
            "consumer_id": str(uuid.uuid4()),
            "brand_id": "brand_test",
            "current_step_id": "s1",
            "status": "running",
            "trigger_data": "{}",
            "step_history": "[]",
            "started_at": datetime.utcnow(),
            "next_action_at": datetime.utcnow(),
            "completed_at": None,
        }

        template_data = {
            "id": template_id,
            "brand_id": "brand_test",
            "group_id": "g_test",
            "template_name": template["template_name"],
            "trigger_event": template["trigger_event"],
            "steps": template["steps"],
            "is_active": True,
            "is_default": False,
        }

        session = AsyncMock()
        session.commit = AsyncMock()

        call_count = 0

        async def execute_side(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # _load_instance
                row = MagicMock()
                row._mapping = instance_data
                result.fetchone.return_value = row
            elif call_count == 2:
                # _load_template
                row = MagicMock()
                row._mapping = {**template_data, "steps": json.dumps(template["steps"])}
                result.fetchone.return_value = row
            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []
            return result

        session.execute.side_effect = execute_side

        with patch.object(engine, "_execute_send_wecom", new_callable=AsyncMock) as mock_wecom:
            with patch.object(engine, "_append_step_history", new_callable=AsyncMock):
                with patch.object(engine, "_complete_instance", new_callable=AsyncMock):
                    next_step = await engine.execute_step(instance_id, "s1", session)

        mock_wecom.assert_called_once()
        assert next_step == "END"


class TestJourneyConditionBranchTrueFalse:
    """condition 步骤按条件结果走不同分支"""

    @pytest.mark.asyncio
    async def test_condition_true_branch_when_no_orders(self):
        engine = CustomerJourneyEngine()
        step = {
            "step_id": "cond",
            "step_type": "condition",
            "config": {"condition_type": "no_order_since_start"},
            "on_condition_true": "step_true",
            "on_condition_false": "step_false",
        }
        session = AsyncMock()
        cnt_row = MagicMock()
        cnt_row.cnt = 0
        result = MagicMock()
        result.fetchone.return_value = cnt_row
        session.execute.return_value = result

        next_id = await engine._execute_condition(
            str(uuid.uuid4()), "brand_test", step["config"], step,
            datetime.utcnow().isoformat(), session
        )
        assert next_id == "step_true"

    @pytest.mark.asyncio
    async def test_condition_false_branch_when_has_orders(self):
        engine = CustomerJourneyEngine()
        step = {
            "step_id": "cond",
            "step_type": "condition",
            "config": {"condition_type": "no_order_since_start"},
            "on_condition_true": "step_true",
            "on_condition_false": "step_false",
        }
        session = AsyncMock()
        cnt_row = MagicMock()
        cnt_row.cnt = 3  # 有3笔新订单
        result = MagicMock()
        result.fetchone.return_value = cnt_row
        session.execute.return_value = result

        next_id = await engine._execute_condition(
            str(uuid.uuid4()), "brand_test", step["config"], step,
            datetime.utcnow().isoformat(), session
        )
        assert next_id == "step_false"


class TestSeedDefaultJourneysCreatesFourTemplates:
    """seed_default_journeys 应创建4条预置旅程"""

    @pytest.mark.asyncio
    async def test_seed_creates_four_templates(self):
        engine = CustomerJourneyEngine()
        brand_id = "brand_seed_test"
        created_ids = []

        session = AsyncMock()
        session.commit = AsyncMock()

        # 所有 SELECT 返回 None（无已存在模板），INSERT 正常
        async def execute_side(query, params=None):
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            return result

        session.execute.side_effect = execute_side

        template_ids = await engine.seed_default_journeys(brand_id, session)
        assert len(template_ids) == 4, f"期望4条，实际{len(template_ids)}条"

    @pytest.mark.asyncio
    async def test_seed_is_idempotent_when_templates_exist(self):
        engine = CustomerJourneyEngine()
        brand_id = "brand_seed_test"

        session = AsyncMock()
        session.commit = AsyncMock()

        # 所有 SELECT 返回已存在行
        async def execute_side(query, params=None):
            result = MagicMock()
            existing_row = MagicMock()
            existing_row.id = str(uuid.uuid4())
            result.fetchone.return_value = existing_row
            return result

        session.execute.side_effect = execute_side

        template_ids = await engine.seed_default_journeys(brand_id, session)
        assert len(template_ids) == 0, "已存在时应跳过，不重复创建"

    def test_default_templates_have_required_fields(self):
        """验证4条预置模板的结构完整性"""
        assert len(DEFAULT_JOURNEY_TEMPLATES) == 4
        expected_triggers = {
            "member_registered",
            "churn_risk_high",
            "upgrade_ready",
            "birthday_approaching",
        }
        actual_triggers = {t["trigger_event"] for t in DEFAULT_JOURNEY_TEMPLATES}
        assert actual_triggers == expected_triggers

        for tpl in DEFAULT_JOURNEY_TEMPLATES:
            assert "template_name" in tpl
            assert "trigger_event" in tpl
            assert len(tpl["steps"]) > 0
            for step in tpl["steps"]:
                assert "step_id" in step
                assert "step_type" in step
                assert "config" in step


class TestJourneyStatsCompletionRate:
    """旅程效果统计完成率计算"""

    @pytest.mark.asyncio
    async def test_completion_rate_calculation(self):
        engine = CustomerJourneyEngine()
        template_id = str(uuid.uuid4())
        session = AsyncMock()

        # 模拟：10条完成，5条运行中，2条失败 → 完成率 = 10/17 ≈ 0.588
        rows = [
            MagicMock(status="completed", cnt=10),
            MagicMock(status="running", cnt=5),
            MagicMock(status="failed", cnt=2),
        ]
        result = MagicMock()
        result.fetchall.return_value = rows
        session.execute.return_value = result

        stats = await engine.get_journey_stats(template_id, session, period_days=30)

        assert stats["total_triggered"] == 17
        assert stats["completed"] == 10
        assert stats["completion_rate"] == round(10 / 17, 3)

    @pytest.mark.asyncio
    async def test_completion_rate_zero_when_no_instances(self):
        engine = CustomerJourneyEngine()
        template_id = str(uuid.uuid4())
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = []
        session.execute.return_value = result

        stats = await engine.get_journey_stats(template_id, session, period_days=30)
        assert stats["total_triggered"] == 0
        assert stats["completion_rate"] == 0.0
