"""KnowledgeService 单元测试 — 知识OS层核心服务"""
import os

for _k, _v in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret",
    "JWT_SECRET": "test-jwt",
}.items():
    os.environ.setdefault(_k, _v)

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from src.services.knowledge_service import KnowledgeService


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_db():
    """构造一个模拟的 AsyncSession"""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_scalars_result(items):
    """构造 db.execute().scalars().all() 的结果"""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_scalar_one_result(item):
    """构造 db.execute().scalar_one_or_none() 的结果"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    return mock_result


# ── 技能节点测试 ──────────────────────────────────────────────


class TestCreateSkillNode:
    @pytest.mark.asyncio
    async def test_create_skill_node_returns_dict(self):
        db = _mock_db()

        async def fake_refresh(obj):
            obj.id = uuid4()

        db.refresh = fake_refresh

        data = {
            "skill_id": "SKILL_COOK_001",
            "name": "川菜颠锅",
            "category": "cooking",
            "max_level": 5,
            "kpi_impact": {"speed_of_service": 10},
            "estimated_revenue_lift": 5000.0,
        }
        result = await KnowledgeService.create_skill_node(db, data)

        assert result["skill_id"] == "SKILL_COOK_001"
        assert result["name"] == "川菜颠锅"
        assert result["category"] == "cooking"
        assert result["max_level"] == 5
        assert result["is_active"] is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skill_node_defaults(self):
        db = _mock_db()
        db.refresh = AsyncMock()

        data = {"skill_id": "SKILL_002", "name": "食材验收"}
        result = await KnowledgeService.create_skill_node(db, data)

        assert result["name"] == "食材验收"
        assert result["max_level"] == 5


class TestListSkillNodes:
    @pytest.mark.asyncio
    async def test_list_all(self):
        db = _mock_db()
        node = MagicMock()
        node.id = uuid4()
        node.skill_id = "S001"
        node.name = "技能A"
        node.category = "cooking"
        node.max_level = 5
        node.kpi_impact = {}
        node.estimated_revenue_lift = 0.0

        db.execute = AsyncMock(return_value=_make_scalars_result([node]))

        result = await KnowledgeService.list_skill_nodes(db)
        assert len(result) == 1
        assert result[0]["skill_id"] == "S001"

    @pytest.mark.asyncio
    async def test_list_with_category_filter(self):
        db = _mock_db()
        db.execute = AsyncMock(return_value=_make_scalars_result([]))

        result = await KnowledgeService.list_skill_nodes(db, category="cooking")
        assert result == []


# ── 知识采集测试 ──────────────────────────────────────────────


class TestCaptureKnowledge:
    @pytest.mark.asyncio
    async def test_capture_status_is_draft(self):
        db = _mock_db()

        async def fake_refresh(obj):
            obj.id = uuid4()

        db.refresh = fake_refresh

        data = {
            "person_id": str(uuid4()),
            "trigger_type": "exit",
            "context": "离职面谈",
            "action": "记录经验",
            "result": "已采集",
        }
        result = await KnowledgeService.capture_knowledge(db, data)
        assert result["status"] == "draft"
        assert result["trigger_type"] == "exit"


class TestReviewKnowledge:
    @pytest.mark.asyncio
    async def test_review_updates_status(self):
        db = _mock_db()
        capture_id = uuid4()
        capture = MagicMock()
        capture.id = capture_id
        capture.status = "draft"
        capture.quality_score = None
        capture.reviewed_by = None
        capture.reviewed_at = None

        db.execute = AsyncMock(return_value=_make_scalar_one_result(capture))
        db.refresh = AsyncMock()

        result = await KnowledgeService.review_knowledge(
            db, str(capture_id), "A", str(uuid4())
        )
        assert capture.status == "reviewed"
        assert capture.quality_score == "A"

    @pytest.mark.asyncio
    async def test_review_not_found_raises(self):
        db = _mock_db()
        db.execute = AsyncMock(return_value=_make_scalar_one_result(None))

        with pytest.raises(ValueError, match="not found"):
            await KnowledgeService.review_knowledge(db, str(uuid4()), "B", str(uuid4()))


# ── 技能认证测试 ──────────────────────────────────────────────


class TestRecordAchievement:
    @pytest.mark.asyncio
    async def test_record_returns_valid(self):
        db = _mock_db()

        async def fake_refresh(obj):
            obj.id = uuid4()

        db.refresh = fake_refresh

        data = {
            "person_id": str(uuid4()),
            "skill_node_id": str(uuid4()),
            "level": 3,
            "evidence": {"type": "exam", "score": 95},
        }
        result = await KnowledgeService.record_achievement(db, data)
        assert result["level"] == 3
        assert result["is_valid"] == "valid"


class TestGetPersonSkillPassport:
    @pytest.mark.asyncio
    async def test_passport_with_achievements(self):
        db = _mock_db()
        person_id = uuid4()
        ach = MagicMock()
        ach.id = uuid4()
        ach.skill_node_id = uuid4()
        ach.level = 2
        ach.achieved_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
        ach.evidence = {"type": "observation"}
        ach.is_valid = "valid"

        db.execute = AsyncMock(return_value=_make_scalars_result([ach]))

        result = await KnowledgeService.get_person_skill_passport(db, str(person_id))
        assert result["total_achievements"] == 1
        assert result["achievements"][0]["level"] == 2

    @pytest.mark.asyncio
    async def test_passport_empty(self):
        db = _mock_db()
        db.execute = AsyncMock(return_value=_make_scalars_result([]))

        result = await KnowledgeService.get_person_skill_passport(db, str(uuid4()))
        assert result["total_achievements"] == 0
        assert result["achievements"] == []


# ── 行为模式测试 ──────────────────────────────────────────────


class TestDetectBehaviorPattern:
    @pytest.mark.asyncio
    async def test_detect_returns_active(self):
        db = _mock_db()

        async def fake_refresh(obj):
            obj.id = uuid4()

        db.refresh = fake_refresh

        data = {
            "pattern_type": "high_performer",
            "name": "高效厨师模式",
            "feature_vector": {"speed": 0.8, "quality": 0.9},
            "confidence": 0.85,
            "sample_size": 50,
        }
        result = await KnowledgeService.detect_behavior_pattern(db, data)
        assert result["pattern_type"] == "high_performer"
        assert result["confidence"] == 0.85
        assert result["is_active"] is True


# ── 离职风险信号测试 ──────────────────────────────────────────


class TestCreateRetentionSignal:
    @pytest.mark.asyncio
    async def test_create_signal(self):
        db = _mock_db()

        async def fake_refresh(obj):
            obj.id = uuid4()

        db.refresh = fake_refresh

        data = {
            "assignment_id": str(uuid4()),
            "risk_score": 75,
            "risk_level": "high",
            "risk_factors": {"attendance_anomaly": 0.3},
        }
        result = await KnowledgeService.create_retention_signal(db, data)
        assert result["risk_score"] == 75
        assert result["risk_level"] == "high"
        assert result["intervention_status"] == "none"
