"""Tests for KnowledgeCaptureService — WF-4 知识采集触发流."""
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 注入必要环境变量（L002：pydantic_settings 在 import 时校验）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

from src.services.hr.knowledge_capture_service import (
    KnowledgeCaptureService,
    _build_question_template,
    _parse_dialogue,
    _score_quality,
)


# ──────────────────────────────────────────────────────────────────────
# 纯函数测试
# ──────────────────────────────────────────────────────────────────────

class TestScoreQuality:
    """_score_quality 质量评分纯函数."""

    def test_all_fields_full_score(self):
        score = _score_quality("这是背景信息超过十个字符", "采取了某个处理动作超过十字", "结果反馈超过十个字符")
        assert score == 1.0

    def test_only_context(self):
        score = _score_quality("背景信息足够长度超过十字", None, None)
        assert score == 0.3

    def test_only_action(self):
        score = _score_quality(None, "处理动作足够长度超过十字", None)
        assert score == 0.4

    def test_only_result(self):
        score = _score_quality(None, None, "结果反馈足够长度超过十字")
        assert score == 0.3

    def test_all_none(self):
        assert _score_quality(None, None, None) == 0.0

    def test_too_short_fields_not_counted(self):
        # 少于10字不计分
        assert _score_quality("短", "短", "短") == 0.0

    def test_context_and_action(self):
        score = _score_quality("背景信息足够长度超过十字", "处理动作足够长度超过十字", None)
        assert score == 0.7

    def test_score_clamped_max_1(self):
        # 即使所有字段都超长，最多1.0
        score = _score_quality("A" * 100, "B" * 100, "C" * 100)
        assert score == 1.0


class TestBuildQuestionTemplate:
    """_build_question_template 提问模板纯函数."""

    def test_exit_type(self):
        template = _build_question_template("exit")
        assert "离职" in template or "付出" in template

    def test_monthly_review_type(self):
        template = _build_question_template("monthly_review")
        assert "月" in template

    def test_incident_type(self):
        template = _build_question_template("incident")
        assert "Context" in template or "情况" in template

    def test_unknown_type_fallbacks_to_incident(self):
        template = _build_question_template("unknown_type")
        # 降级到 incident 模板
        assert template == _build_question_template("incident")

    def test_all_valid_types_return_nonempty(self):
        types = ["exit", "monthly_review", "incident", "onboarding",
                 "growth_review", "talent_assessment", "legacy_import"]
        for t in types:
            assert len(_build_question_template(t)) > 20


class TestParseDialogue:
    """_parse_dialogue 对话解析纯函数."""

    def test_full_car_structure(self):
        dialogue = "背景是这样的\n采取了以下处理动作\n最终结果如下"
        parsed = _parse_dialogue(dialogue)
        assert parsed["context"] is not None
        assert parsed["structured_output"]["parse_method"] in ("keyword_heuristic", "fallback_full_context")

    def test_empty_dialogue_fallback(self):
        parsed = _parse_dialogue("这是一段没有任何关键词的纯文本描述内容")
        # 退化：全部放入 context
        assert parsed["context"] is not None
        assert parsed["structured_output"]["parse_method"] == "fallback_full_context"

    def test_returns_all_keys(self):
        parsed = _parse_dialogue("任意内容")
        assert "context" in parsed
        assert "action" in parsed
        assert "result" in parsed
        assert "structured_output" in parsed


# ──────────────────────────────────────────────────────────────────────
# 服务层测试（mock DB）
# ──────────────────────────────────────────────────────────────────────

def _make_session():
    """构造一个 mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


class TestTriggerCapture:
    """KnowledgeCaptureService.trigger_capture."""

    @pytest.mark.asyncio
    async def test_trigger_returns_template(self):
        session = _make_session()
        # person 无企微，企微推送路径跳过
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        session.execute.return_value = mock_result

        svc = KnowledgeCaptureService(session=session)
        result = await svc.trigger_capture(str(uuid.uuid4()), "exit")

        assert "trigger_type" in result
        assert result["trigger_type"] == "exit"
        assert "question_template" in result
        assert len(result["question_template"]) > 0

    @pytest.mark.asyncio
    async def test_wechat_failure_degrades_silently(self):
        """企微推送失败时不抛异常，返回 wechat_sent=False."""
        session = _make_session()
        mock_row = MagicMock()
        mock_row.phone = "13800138000"
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute.return_value = mock_result

        # patch WeChatService.send_text_to_user 使其抛异常
        with patch(
            "src.services.wechat_service.WeChatService.send_text_message",
            side_effect=ConnectionError("企微不可达"),
        ):
            svc = KnowledgeCaptureService(session=session)
            result = await svc.trigger_capture(str(uuid.uuid4()), "monthly_review")
            # 推送失败时 wechat_sent=False，不抛异常
            assert "wechat_sent" in result
            assert result["wechat_sent"] is False

    @pytest.mark.asyncio
    async def test_all_trigger_types_work(self):
        session = _make_session()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        session.execute.return_value = mock_result

        svc = KnowledgeCaptureService(session=session)
        for trigger_type in ["exit", "monthly_review", "incident", "onboarding"]:
            result = await svc.trigger_capture(str(uuid.uuid4()), trigger_type)
            assert result["trigger_type"] == trigger_type


class TestSubmitCapture:
    """KnowledgeCaptureService.submit_capture."""

    @pytest.mark.asyncio
    async def test_submit_returns_id_and_quality(self):
        session = _make_session()
        mock_result = MagicMock()
        session.execute.return_value = mock_result

        svc = KnowledgeCaptureService(session=session)
        person_id = str(uuid.uuid4())
        result = await svc.submit_capture(
            person_id,
            "incident",
            "背景是某次投诉事件\n采取处理方式是立即道歉并补偿\n最终结果是顾客满意离开",
        )

        assert "id" in result
        assert result["person_id"] == person_id
        assert "quality_score" in result
        assert 0.0 <= result["quality_score"] <= 1.0
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_calls_db_insert(self):
        session = _make_session()
        mock_result = MagicMock()
        session.execute.return_value = mock_result

        svc = KnowledgeCaptureService(session=session)
        await svc.submit_capture(str(uuid.uuid4()), "exit", "随便写一段对话内容")

        # 确认执行了 DB 写入（execute + commit 均被调用）
        assert session.execute.called
        assert session.commit.called
        # 验证 SQL 文本对象包含 INSERT 语句
        first_call_sql = session.execute.call_args_list[0][0][0].text
        assert "INSERT" in first_call_sql

    @pytest.mark.asyncio
    async def test_submit_high_quality_dialogue(self):
        session = _make_session()
        session.execute.return_value = MagicMock()

        svc = KnowledgeCaptureService(session=session)
        result = await svc.submit_capture(
            str(uuid.uuid4()),
            "monthly_review",
            "背景是这个月的高峰期遇到了食材短缺\n"
            "采取了紧急联系备用供应商并调整菜单的处理方式\n"
            "最终结果是损耗减少了30%，顾客满意度提升",
        )
        # 完整 CAR 应拿到较高分
        assert result["quality_score"] >= 0.6

    @pytest.mark.asyncio
    async def test_submit_empty_dialogue_low_quality(self):
        session = _make_session()
        session.execute.return_value = MagicMock()

        svc = KnowledgeCaptureService(session=session)
        result = await svc.submit_capture(str(uuid.uuid4()), "incident", "无")
        # 太短的内容质量分低
        assert result["quality_score"] < 0.5
