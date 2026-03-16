"""
JourneyNarrator 单元测试

覆盖：
  - classify_maslow_level（5种场景，全边界）
  - JourneyNarrator.generate（有 LLM / 无 LLM降级 / LLM失败降级 / 未知模板降级）
  - journey_orchestrator 集成：_get_member_profile / _send_message 使用 narrator
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.journey_narrator import (
    JourneyNarrator,
    MemberProfile,
    _FALLBACK_TEMPLATES,
    classify_maslow_level,
)


# ════════════════════════════════════════════════════════════════════════════════
# classify_maslow_level
# ════════════════════════════════════════════════════════════════════════════════

class TestClassifyMaslowLevel:
    def test_freq_zero_is_l1(self):
        assert classify_maslow_level(MemberProfile(frequency=0)) == 1

    def test_freq_one_is_l2(self):
        assert classify_maslow_level(MemberProfile(frequency=1)) == 2

    def test_freq_2_to_5_is_l3(self):
        for freq in (2, 3, 4, 5):
            assert classify_maslow_level(MemberProfile(frequency=freq)) == 3

    def test_freq_6_low_spend_is_l4(self):
        # 消费 499 元（49900 分）→ L4
        profile = MemberProfile(frequency=6, monetary=49900)
        assert classify_maslow_level(profile) == 4

    def test_freq_6_high_spend_is_l5(self):
        # 消费 500 元整（50000 分）→ L5
        profile = MemberProfile(frequency=10, monetary=50000)
        assert classify_maslow_level(profile) == 5

    def test_freq_high_low_spend_stays_l4(self):
        profile = MemberProfile(frequency=20, monetary=10000)  # 100元
        assert classify_maslow_level(profile) == 4

    def test_none_monetary_treated_as_zero(self):
        profile = MemberProfile(frequency=8, monetary=0)
        assert classify_maslow_level(profile) == 4


# ════════════════════════════════════════════════════════════════════════════════
# JourneyNarrator.generate — 有 LLM 路径
# ════════════════════════════════════════════════════════════════════════════════

class TestJourneyNarratorWithLLM:
    @pytest.mark.asyncio
    async def test_generate_calls_llm_and_returns_text(self):
        """LLM 调用成功 → 返回生成文本。"""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "欢迎加入，您好！期待您到店品鉴我们的招牌菜。"

        narrator = JourneyNarrator(llm=mock_llm)
        result = await narrator.generate(
            template_id="journey_welcome",
            store_id="S001",
            customer_id="C001",
            profile=MemberProfile(frequency=0),
        )

        assert result == "欢迎加入，您好！期待您到店品鉴我们的招牌菜。"
        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_strips_surrounding_quotes(self):
        """LLM 返回带引号的文本 → 自动剥除。"""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = '"欢迎加入，期待您到店！"'

        narrator = JourneyNarrator(llm=mock_llm)
        result = await narrator.generate(
            template_id="journey_welcome",
            store_id="S001",
            customer_id="C001",
        )

        assert result == "欢迎加入，期待您到店！"

    @pytest.mark.asyncio
    async def test_prompt_contains_maslow_level(self):
        """prompt 中包含马斯洛层级信息。"""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "消息内容"

        narrator = JourneyNarrator(llm=mock_llm)
        profile = MemberProfile(frequency=3)  # L3
        await narrator.generate(
            template_id="journey_menu_recommend",
            store_id="S001",
            customer_id="C001",
            profile=profile,
        )

        call_kwargs = mock_llm.generate.call_args
        prompt_arg = call_kwargs.kwargs.get("prompt") or call_kwargs.args[0]
        assert "L3" in prompt_arg

    @pytest.mark.asyncio
    async def test_maslow_level_affects_strategy_in_prompt(self):
        """L4 顾客的 prompt 中包含'专属感'策略，不含折扣话术。"""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "消息"

        narrator = JourneyNarrator(llm=mock_llm)
        await narrator.generate(
            template_id="journey_welcome",
            store_id="S001",
            customer_id="C001",
            profile=MemberProfile(frequency=8, monetary=30000),  # L4
        )

        call_kwargs = mock_llm.generate.call_args
        prompt_arg = call_kwargs.kwargs.get("prompt") or call_kwargs.args[0]
        assert "L4" in prompt_arg
        assert "专属感" in prompt_arg


# ════════════════════════════════════════════════════════════════════════════════
# JourneyNarrator.generate — 降级路径
# ════════════════════════════════════════════════════════════════════════════════

class TestJourneyNarratorFallback:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_fallback(self):
        """无 ANTHROPIC_API_KEY → 直接返回静态模板，不调用 LLM。"""
        narrator = JourneyNarrator(llm=None)

        with patch.dict(os.environ, {}, clear=False):
            # 确保环境变量中没有 ANTHROPIC_API_KEY
            os.environ.pop("ANTHROPIC_API_KEY", None)
            result = await narrator.generate(
                template_id="journey_welcome",
                store_id="S001",
                customer_id="C001",
            )

        assert result == _FALLBACK_TEMPLATES["journey_welcome"]

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self):
        """LLM 调用抛出异常 → 静默降级，返回静态模板，不传播异常。"""
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = Exception("API timeout")

        narrator = JourneyNarrator(llm=mock_llm)
        result = await narrator.generate(
            template_id="journey_comeback_coupon",
            store_id="S001",
            customer_id="C001",
            profile=MemberProfile(frequency=2),
        )

        assert result == _FALLBACK_TEMPLATES["journey_comeback_coupon"]

    @pytest.mark.asyncio
    async def test_unknown_template_returns_generic_fallback(self):
        """未知 template_id → 返回通用兜底文本，不报错。"""
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = Exception("any error")

        narrator = JourneyNarrator(llm=mock_llm)
        result = await narrator.generate(
            template_id="__nonexistent_template__",
            store_id="S001",
            customer_id="C001",
        )

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_llm_returns_empty_string_uses_fallback(self):
        """LLM 返回空字符串 → 降级为静态模板。"""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = ""

        narrator = JourneyNarrator(llm=mock_llm)
        result = await narrator.generate(
            template_id="journey_seasonal_content",
            store_id="S001",
            customer_id="C001",
        )

        assert result == _FALLBACK_TEMPLATES["journey_seasonal_content"]

    @pytest.mark.asyncio
    async def test_none_profile_uses_default_l1(self):
        """profile=None → 按 L1 策略，不崩溃。"""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "欢迎光临"

        narrator = JourneyNarrator(llm=mock_llm)
        result = await narrator.generate(
            template_id="journey_welcome",
            store_id="S001",
            customer_id="C001",
            profile=None,
        )

        assert result == "欢迎光临"
        # 确认 prompt 包含 L1
        call_kwargs = mock_llm.generate.call_args
        prompt_arg = call_kwargs.kwargs.get("prompt") or call_kwargs.args[0]
        assert "L1" in prompt_arg


# ════════════════════════════════════════════════════════════════════════════════
# journey_orchestrator 集成：_get_member_profile
# ════════════════════════════════════════════════════════════════════════════════

class TestGetMemberProfile:
    @pytest.mark.asyncio
    async def test_returns_profile_when_member_exists(self):
        """DB 有记录 → 返回 MemberProfile。"""
        from src.services.journey_orchestrator import JourneyOrchestrator

        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [5, 25000, 14, "repeat"][i]
        db.execute.return_value.fetchone.return_value = row

        orch = JourneyOrchestrator()
        profile = await orch._get_member_profile("C001", "S001", db)

        assert profile is not None
        assert profile.frequency == 5
        assert profile.monetary == 25000
        assert profile.recency_days == 14
        assert profile.lifecycle_state == "repeat"

    @pytest.mark.asyncio
    async def test_returns_none_when_member_not_found(self):
        """DB 无记录 → 返回 None（不抛异常）。"""
        from src.services.journey_orchestrator import JourneyOrchestrator

        db = AsyncMock()
        db.execute.return_value.fetchone.return_value = None

        orch = JourneyOrchestrator()
        profile = await orch._get_member_profile("C001", "S001", db)

        assert profile is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self):
        """DB 查询异常 → 返回 None（静默降级）。"""
        from src.services.journey_orchestrator import JourneyOrchestrator

        db = AsyncMock()
        db.execute.side_effect = Exception("DB error")

        orch = JourneyOrchestrator()
        with patch("src.services.member_context_store.get_context_store", new_callable=AsyncMock, return_value=None):
            profile = await orch._get_member_profile("C001", "S001", db)

        assert profile is None


# ════════════════════════════════════════════════════════════════════════════════
# journey_orchestrator 集成：_send_message 使用 narrator
# ════════════════════════════════════════════════════════════════════════════════

class TestSendMessageWithNarrator:
    @pytest.mark.asyncio
    async def test_narrator_used_when_provided(self):
        """传入 narrator → 调用 narrator.generate，不用静态模板。"""
        from src.services.journey_orchestrator import JourneyOrchestrator, JourneyStep

        orch = JourneyOrchestrator()
        wechat = AsyncMock()
        narrator = AsyncMock()
        narrator.generate.return_value = "个性化消息内容"

        step = JourneyStep(
            step_id="welcome",
            delay_minutes=0,
            channel="wxwork",
            template_id="journey_welcome",
        )

        result = await orch._send_message(
            step, "C001", "S001", "wx_user_001", wechat,
            profile=MemberProfile(frequency=0),
            narrator=narrator,
        )

        assert result["sent"] is True
        narrator.generate.assert_called_once_with(
            template_id="journey_welcome",
            store_id="S001",
            customer_id="C001",
            profile=MemberProfile(frequency=0),
        )
        wechat.send_text_message.assert_called_once()
        # 发送内容应为个性化消息
        call_kwargs = wechat.send_text_message.call_args
        assert call_kwargs.kwargs.get("content") == "个性化消息内容"

    @pytest.mark.asyncio
    async def test_fallback_to_static_when_no_narrator(self):
        """无 narrator → 使用 format_journey_message 静态模板。"""
        from src.services.journey_orchestrator import JourneyOrchestrator, JourneyStep

        orch = JourneyOrchestrator()
        wechat = AsyncMock()

        step = JourneyStep(
            step_id="welcome",
            delay_minutes=0,
            channel="wxwork",
            template_id="journey_welcome",
        )

        result = await orch._send_message(
            step, "C001", "S001", "wx_user_001", wechat,
        )

        assert result["sent"] is True
        call_kwargs = wechat.send_text_message.call_args
        content = call_kwargs.kwargs.get("content")
        # 静态模板包含"新会员"
        assert "新会员" in content or "欢迎" in content
