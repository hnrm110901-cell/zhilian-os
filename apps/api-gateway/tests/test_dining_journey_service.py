"""
全链路用餐旅程服务 — 单元测试

测试内容：
- Phase 1: CDP自动关联 + 等位→预订转换
- Phase 2: 智能桌台推荐 + 到店前推送
- Phase 3: 老客识别 + 生日场景 + 自动标签
- Phase 4: 巡台检查 + 问题识别 + 知识学习
- Phase 5: 满意度调查 + 营销触达
- Phase 6: 评价管理 + 售后跟进
"""
import os
for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import builtins
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import uuid

_real_import = builtins.__import__


def _block_sentiment_import(name, *args, **kwargs):
    """阻止 CustomerSentimentService 导入，强制走关键词降级。"""
    if "customer_sentiment_service" in name:
        raise ImportError("Mocked: CustomerSentimentService not available in test")
    return _real_import(name, *args, **kwargs)

from src.models.reservation import Reservation, ReservationStatus, ReservationType
from src.models.queue import Queue, QueueStatus


# ── Phase 1: CDP自动关联 ──────────────────────────────────────────

class TestLinkConsumerToReservation:

    @pytest.mark.asyncio
    async def test_links_consumer_id(self):
        from src.services.dining_journey_service import link_consumer_to_reservation

        reservation = MagicMock()
        reservation.consumer_id = None
        reservation.customer_phone = "13800138000"
        reservation.customer_name = "张三"
        reservation.id = "RES_001"

        mock_session = AsyncMock()
        test_uuid = uuid.uuid4()

        with patch("src.services.identity_resolution_service.identity_resolution_service") as mock_irs:
            mock_irs.resolve = AsyncMock(return_value=test_uuid)
            result = await link_consumer_to_reservation(mock_session, reservation)
            # verify resolve was called with db session as first arg
            mock_irs.resolve.assert_awaited_once()
            call_args = mock_irs.resolve.call_args
            assert call_args[0][0] is mock_session

    @pytest.mark.asyncio
    async def test_skips_if_already_linked(self):
        from src.services.dining_journey_service import link_consumer_to_reservation

        existing_id = uuid.uuid4()
        reservation = MagicMock()
        reservation.consumer_id = existing_id

        mock_session = AsyncMock()
        result = await link_consumer_to_reservation(mock_session, reservation)
        assert result == str(existing_id)

    @pytest.mark.asyncio
    async def test_handles_resolution_failure(self):
        from src.services.dining_journey_service import link_consumer_to_reservation

        reservation = MagicMock()
        reservation.consumer_id = None
        reservation.customer_phone = "13800138000"
        reservation.customer_name = "张三"

        mock_session = AsyncMock()

        # Mock identity_resolution_service.resolve to raise, should return None
        with patch("src.services.identity_resolution_service.identity_resolution_service") as mock_irs:
            mock_irs.resolve = AsyncMock(side_effect=ValueError("resolution failed"))
            result = await link_consumer_to_reservation(mock_session, reservation)
            assert result is None


class TestConvertQueueToReservation:

    @pytest.mark.asyncio
    async def test_converts_seated_queue(self):
        from src.services.dining_journey_service import convert_queue_to_reservation

        mock_queue = MagicMock()
        mock_queue.queue_id = "Q001"
        mock_queue.store_id = "S001"
        mock_queue.customer_name = "李四"
        mock_queue.customer_phone = "13900139000"
        mock_queue.consumer_id = None
        mock_queue.party_size = 4
        mock_queue.status = QueueStatus.SEATED
        mock_queue.table_number = "A05"
        mock_queue.queue_number = 15
        mock_queue.special_requests = "靠窗"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_queue

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        reservation = await convert_queue_to_reservation(mock_session, "Q001")

        assert reservation.status == ReservationStatus.SEATED
        assert reservation.customer_name == "李四"
        assert reservation.table_number == "A05"
        assert reservation.party_size == 4
        assert "排队号: 15" in reservation.notes

    @pytest.mark.asyncio
    async def test_converts_called_queue(self):
        from src.services.dining_journey_service import convert_queue_to_reservation

        mock_queue = MagicMock()
        mock_queue.queue_id = "Q002"
        mock_queue.store_id = "S001"
        mock_queue.customer_name = "王五"
        mock_queue.customer_phone = "13700137000"
        mock_queue.consumer_id = None
        mock_queue.party_size = 2
        mock_queue.status = QueueStatus.CALLED
        mock_queue.table_number = None
        mock_queue.queue_number = 20
        mock_queue.special_requests = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_queue
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        reservation = await convert_queue_to_reservation(mock_session, "Q002", table_number="B03")
        assert reservation.status == ReservationStatus.ARRIVED
        assert reservation.table_number == "B03"

    @pytest.mark.asyncio
    async def test_rejects_waiting_queue(self):
        from src.services.dining_journey_service import convert_queue_to_reservation

        mock_queue = MagicMock()
        mock_queue.status = QueueStatus.WAITING
        mock_queue.queue_id = "Q003"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_queue
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="不允许转换"):
            await convert_queue_to_reservation(mock_session, "Q003")

    @pytest.mark.asyncio
    async def test_rejects_nonexistent_queue(self):
        from src.services.dining_journey_service import convert_queue_to_reservation

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="不存在"):
            await convert_queue_to_reservation(mock_session, "Q999")


# ── Phase 2: 智能桌台推荐 ────────────────────────────────────────

class TestRecommendTable:

    @pytest.mark.asyncio
    async def test_recommends_matching_tables(self):
        from src.services.dining_journey_service import recommend_table

        # Mock tables
        table1 = MagicMock()
        table1.table_number = "A01"
        table1.table_type = "大厅"
        table1.min_capacity = 2
        table1.max_capacity = 4
        table1.floor = 1
        table1.area_name = "A区"

        table2 = MagicMock()
        table2.table_number = "VIP01"
        table2.table_type = "包厢VIP"
        table2.min_capacity = 4
        table2.max_capacity = 8
        table2.floor = 2
        table2.area_name = "VIP区"

        # Tables query
        table_result = MagicMock()
        table_result.scalars.return_value.all.return_value = [table1, table2]

        # Occupied tables query (none occupied)
        occupied_result = MagicMock()
        occupied_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[table_result, occupied_result])

        candidates = await recommend_table(
            mock_session, "S001", party_size=4,
            reservation_date=date(2026, 3, 20),
            reservation_time=time(18, 0),
        )

        assert len(candidates) >= 1
        # VIP should score higher due to type_bonus
        vip = next((c for c in candidates if c["table_number"] == "VIP01"), None)
        if vip:
            assert vip["score"] > 0

    @pytest.mark.asyncio
    async def test_filters_by_preference(self):
        from src.services.dining_journey_service import recommend_table

        table1 = MagicMock()
        table1.table_number = "A01"
        table1.table_type = "大厅"
        table1.min_capacity = 2
        table1.max_capacity = 4
        table1.floor = 1
        table1.area_name = "A区"

        table2 = MagicMock()
        table2.table_number = "B01"
        table2.table_type = "包厢"
        table2.min_capacity = 4
        table2.max_capacity = 8
        table2.floor = 2
        table2.area_name = "B区"

        table_result = MagicMock()
        table_result.scalars.return_value.all.return_value = [table1, table2]
        occupied_result = MagicMock()
        occupied_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[table_result, occupied_result])

        candidates = await recommend_table(
            mock_session, "S001", party_size=4,
            reservation_date=date(2026, 3, 20),
            reservation_time=time(18, 0),
            preference="包厢",
        )

        # Should only include 包厢
        for c in candidates:
            assert "包厢" in c["table_type"]

    @pytest.mark.asyncio
    async def test_excludes_occupied_tables(self):
        from src.services.dining_journey_service import recommend_table

        table1 = MagicMock()
        table1.table_number = "A01"
        table1.table_type = "大厅"
        table1.min_capacity = 2
        table1.max_capacity = 4
        table1.floor = 1
        table1.area_name = "A区"

        table_result = MagicMock()
        table_result.scalars.return_value.all.return_value = [table1]
        # A01 is occupied
        occupied_result = MagicMock()
        occupied_result.all.return_value = [("A01",)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[table_result, occupied_result])

        candidates = await recommend_table(
            mock_session, "S001", party_size=3,
            reservation_date=date(2026, 3, 20),
            reservation_time=time(18, 0),
        )

        assert len(candidates) == 0


# ── Phase 2: 到店前推送 ──────────────────────────────────────────

class TestPreArrivalPush:

    @pytest.mark.asyncio
    async def test_generates_push_content(self):
        from src.services.dining_journey_service import generate_pre_arrival_push

        mock_res = MagicMock()
        mock_res.id = "RES_001"
        mock_res.customer_name = "张三"
        mock_res.customer_phone = "13800138000"
        mock_res.consumer_id = None
        mock_res.reservation_date = date(2026, 3, 20)
        mock_res.reservation_time = time(18, 0)
        mock_res.party_size = 4
        mock_res.store_id = "S001"
        mock_res.table_number = "A01"
        mock_res.room_name = None
        mock_res.reservation_type = ReservationType.REGULAR

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_res
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_profile = {
            "consumer_id": None, "display_name": None, "tags": [],
            "total_order_count": 0, "total_order_amount_fen": 0, "rfm_level": "S3",
        }
        with patch("src.services.dining_journey_service._get_consumer_profile", new_callable=AsyncMock, return_value=mock_profile):
            content = await generate_pre_arrival_push(mock_session, "RES_001")
        assert content["reservation_id"] == "RES_001"
        assert content["customer_name"] == "张三"
        assert "scene" in content
        assert "push_message" in content
        assert "预订提醒" in content["push_message"]

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_reservation(self):
        from src.services.dining_journey_service import generate_pre_arrival_push

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        content = await generate_pre_arrival_push(mock_session, "RES_999")
        assert content.get("error") == "预订不存在"


# ── Phase 3: 老客识别 ────────────────────────────────────────────

class TestRecognizeReturningCustomer:

    @pytest.mark.asyncio
    async def test_recognizes_returning_customer(self):
        from src.services.dining_journey_service import recognize_returning_customer

        # Past reservations
        past_res = MagicMock()
        past_res.store_id = "S001"
        past_res.reservation_date = date(2026, 3, 10)
        past_res.reservation_time = time(18, 0)
        past_res.reservation_type = ReservationType.REGULAR

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [past_res]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_profile = {
            "consumer_id": None, "display_name": None, "tags": [],
            "total_order_count": 0, "total_order_amount_fen": 0, "rfm_level": "S3",
        }
        with patch("src.services.dining_journey_service._get_consumer_profile", new_callable=AsyncMock, return_value=mock_profile):
            result = await recognize_returning_customer(mock_session, "13800138000", "S001")
        assert result["is_returning"] is True
        assert result["total_visits"] == 1
        assert "recommended_actions" in result

    @pytest.mark.asyncio
    async def test_new_customer(self):
        from src.services.dining_journey_service import recognize_returning_customer

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_profile = {
            "consumer_id": None, "display_name": None, "tags": [],
            "total_order_count": 0, "total_order_amount_fen": 0, "rfm_level": "S3",
        }
        with patch("src.services.dining_journey_service._get_consumer_profile", new_callable=AsyncMock, return_value=mock_profile):
            result = await recognize_returning_customer(mock_session, "13000000000", "S001")
        assert result["is_returning"] is False
        assert result["total_visits"] == 0


class TestAutoTags:

    def test_high_frequency_tag(self):
        from src.services.dining_journey_service import _generate_auto_tags

        profile = {"total_order_amount_fen": 300000, "birth_date": "1990-05-15"}
        past = [MagicMock(reservation_type=ReservationType.REGULAR)] * 6
        tags = _generate_auto_tags(profile, 6, past)
        assert "高频客户" in tags
        assert "中高消费" in tags
        assert "生日已录入" in tags

    def test_vip_tag(self):
        from src.services.dining_journey_service import _generate_auto_tags

        profile = {"total_order_amount_fen": 600000}
        past = [MagicMock(reservation_type=ReservationType.REGULAR)] * 12
        tags = _generate_auto_tags(profile, 12, past)
        assert "铂金常客" in tags
        assert "高消费" in tags

    def test_banquet_tag(self):
        from src.services.dining_journey_service import _generate_auto_tags

        profile = {"total_order_amount_fen": 100000}
        past = [MagicMock(reservation_type=ReservationType.BANQUET)] * 3
        tags = _generate_auto_tags(profile, 3, past)
        assert "宴会客户" in tags


class TestConsumptionScene:

    def test_birthday_scene(self):
        from src.services.dining_journey_service import _detect_consumption_scene

        res = MagicMock()
        res.reservation_type = ReservationType.REGULAR
        res.party_size = 4
        today = date.today()
        birth = today + timedelta(days=2)
        profile = {"birth_date": birth.isoformat()}

        scene = _detect_consumption_scene(res, profile)
        assert scene["type"] == "birthday"

    def test_banquet_scene(self):
        from src.services.dining_journey_service import _detect_consumption_scene

        res = MagicMock()
        res.reservation_type = ReservationType.BANQUET
        res.party_size = 20
        profile = {}

        scene = _detect_consumption_scene(res, profile)
        assert scene["type"] == "banquet"

    def test_business_scene(self):
        from src.services.dining_journey_service import _detect_consumption_scene

        res = MagicMock()
        res.reservation_type = ReservationType.PRIVATE_ROOM
        res.party_size = 8
        profile = {}

        scene = _detect_consumption_scene(res, profile)
        assert scene["type"] == "business"

    def test_regular_scene(self):
        from src.services.dining_journey_service import _detect_consumption_scene

        res = MagicMock()
        res.reservation_type = ReservationType.REGULAR
        res.party_size = 2
        profile = {}

        scene = _detect_consumption_scene(res, profile)
        assert scene["type"] == "regular"


# ── Phase 4: 巡台检查 ────────────────────────────────────────────

class TestPatrolRecord:

    @pytest.mark.asyncio
    async def test_creates_patrol_record(self):
        from src.services.dining_journey_service import create_patrol_record

        mock_session = AsyncMock()

        result = await create_patrol_record(
            mock_session,
            store_id="S001",
            table_number="A01",
            patrol_by="manager_01",
            checklist_results={"food_quality": 90, "service_speed": 85, "environment": 95},
        )

        assert result["store_id"] == "S001"
        assert result["table_number"] == "A01"
        assert result["total_score"] == 90.0
        assert result["has_critical"] is False

    @pytest.mark.asyncio
    async def test_detects_critical_issues(self):
        from src.services.dining_journey_service import create_patrol_record

        mock_session = AsyncMock()

        result = await create_patrol_record(
            mock_session,
            store_id="S001",
            table_number="A03",
            patrol_by="manager_01",
            checklist_results={"food_quality": 40, "service_speed": 60},
            issues=[{"type": "菜品", "description": "发现异物", "severity": "critical"}],
        )

        assert result["has_critical"] is True
        assert result["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_generates_learning_suggestions(self):
        from src.services.dining_journey_service import create_patrol_record

        mock_session = AsyncMock()

        result = await create_patrol_record(
            mock_session,
            store_id="S001",
            table_number="A02",
            patrol_by="manager_01",
            checklist_results={"food_quality": 50, "service_speed": 60},
        )

        suggestions = result["learning_suggestions"]
        assert len(suggestions) >= 1
        # Low scores should generate suggestions
        food_suggestion = next((s for s in suggestions if s["category"] == "food_quality"), None)
        assert food_suggestion is not None
        assert food_suggestion["priority"] == "medium"


class TestLearning:

    def test_learning_suggestions_for_low_scores(self):
        from src.services.dining_journey_service import _generate_learning_suggestions

        scores = {"food_quality": 40, "service_speed": 80, "environment": 60}
        issues = []
        suggestions = _generate_learning_suggestions(scores, issues)

        assert any(s["category"] == "food_quality" for s in suggestions)
        assert any(s["priority"] == "high" for s in suggestions)  # 40 < 50

    def test_learning_from_issues(self):
        from src.services.dining_journey_service import _generate_learning_suggestions

        scores = {"food_quality": 90}
        issues = [{"type": "服务", "description": "服务员态度冷淡", "severity": "medium"}]
        suggestions = _generate_learning_suggestions(scores, issues)

        service_sug = [s for s in suggestions if s["category"] == "service_training"]
        assert len(service_sug) >= 1


# ── Phase 5: 满意度调查 ──────────────────────────────────────────

class TestSatisfactionSurvey:

    @pytest.mark.asyncio
    async def test_generates_survey(self):
        from src.services.dining_journey_service import trigger_satisfaction_survey

        mock_res = MagicMock()
        mock_res.id = "RES_001"
        mock_res.customer_name = "张三"
        mock_res.customer_phone = "13800138000"
        mock_res.consumer_id = None
        mock_res.store_id = "S001"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_res
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_profile = {
            "consumer_id": None, "display_name": None, "tags": [],
            "total_order_count": 0, "total_order_amount_fen": 0, "rfm_level": "S3",
        }
        with patch("src.services.dining_journey_service._get_consumer_profile", new_callable=AsyncMock, return_value=mock_profile), \
             patch("src.services.dining_journey_service._send_push", new_callable=AsyncMock):
            survey = await trigger_satisfaction_survey(mock_session, "RES_001")

        assert survey["reservation_id"] == "RES_001"
        assert len(survey["questions"]) == 5
        assert survey["questions"][0]["id"] == "nps"
        assert "marketing" in survey
        assert len(survey["marketing"]) >= 1

    @pytest.mark.asyncio
    async def test_vip_marketing(self):
        from src.services.dining_journey_service import trigger_satisfaction_survey

        mock_res = MagicMock()
        mock_res.id = "RES_002"
        mock_res.customer_name = "VIP客户"
        mock_res.customer_phone = "13800138001"
        mock_res.consumer_id = None
        mock_res.store_id = "S001"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_res
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_profile = {
            "consumer_id": None, "display_name": None, "tags": [],
            "total_order_count": 0, "total_order_amount_fen": 0, "rfm_level": "S3",
        }
        with patch("src.services.dining_journey_service._get_consumer_profile", new_callable=AsyncMock, return_value=mock_profile), \
             patch("src.services.dining_journey_service._send_push", new_callable=AsyncMock):
            survey = await trigger_satisfaction_survey(mock_session, "RES_002")
        assert "marketing" in survey


# ── Phase 6: 评价管理 ────────────────────────────────────────────

class TestReviewProcessing:

    @pytest.mark.asyncio
    async def test_positive_review(self):
        from src.services.dining_journey_service import process_post_dining_review

        mock_res = MagicMock()
        mock_res.store_id = "S001"
        mock_res.customer_name = "好评客户"
        mock_res.customer_phone = "13800138000"
        mock_res.consumer_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_res
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        positive_sentiment = {"sentiment": "positive", "confidence": 0.6, "key_points": ["关键词匹配：正面"]}
        with patch("src.services.dining_journey_service._analyze_sentiment", new_callable=AsyncMock, return_value=positive_sentiment):
            result = await process_post_dining_review(
                mock_session, "RES_001", "meituan",
                "菜品非常好吃，服务态度好，环境好！强烈推荐！",
                platform_rating=5,
            )

        assert result["sentiment"]["sentiment"] == "positive"
        assert any(a["action"] == "thank_and_promote" for a in result["actions"])

    @pytest.mark.asyncio
    async def test_negative_review(self):
        from src.services.dining_journey_service import process_post_dining_review

        mock_res = MagicMock()
        mock_res.store_id = "S001"
        mock_res.customer_name = "差评客户"
        mock_res.customer_phone = "13800138000"
        mock_res.consumer_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_res
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        negative_sentiment = {"sentiment": "negative", "confidence": 0.6, "key_points": ["关键词匹配：负面"]}
        with patch("src.services.dining_journey_service._analyze_sentiment", new_callable=AsyncMock, return_value=negative_sentiment):
            result = await process_post_dining_review(
                mock_session, "RES_002", "dianping",
                "太差了，菜难吃，服务慢，环境脏，价格贵，非常失望",
                platform_rating=1,
            )

        assert result["sentiment"]["sentiment"] == "negative"
        assert any(a["action"] == "review_repair" for a in result["actions"])

    @pytest.mark.asyncio
    async def test_review_auto_response(self):
        from src.services.dining_journey_service import _generate_review_response

        sentiment = {"key_points": ["上菜慢"]}
        response = _generate_review_response(sentiment, "negative")
        assert "抱歉" in response
        assert "上菜慢" in response or "【上菜慢】" in response

        response_positive = _generate_review_response({}, "positive")
        assert "感谢" in response_positive


class TestSentimentAnalysis:
    """测试情感分析关键词降级逻辑（mock掉LLM服务，强制走keyword fallback）。"""

    @pytest.mark.asyncio
    async def test_keyword_fallback(self):
        from src.services.dining_journey_service import _analyze_sentiment

        # Force keyword fallback by making CustomerSentimentService raise on import
        with patch("builtins.__import__", side_effect=_block_sentiment_import):
            result = await _analyze_sentiment("菜太难吃了，服务差，很失望")
        assert result["sentiment"] == "negative"

    @pytest.mark.asyncio
    async def test_positive_keywords(self):
        from src.services.dining_journey_service import _analyze_sentiment

        with patch("builtins.__import__", side_effect=_block_sentiment_import):
            result = await _analyze_sentiment("非常好吃，服务好，环境棒，推荐！")
        assert result["sentiment"] == "positive"

    @pytest.mark.asyncio
    async def test_neutral(self):
        from src.services.dining_journey_service import _analyze_sentiment

        with patch("builtins.__import__", side_effect=_block_sentiment_import):
            result = await _analyze_sentiment("一般般吧")
        assert result["sentiment"] == "neutral"


# ── 辅助函数测试 ──────────────────────────────────────────────────

class TestRFMLevel:

    def test_s1_vip(self):
        from src.services.dining_journey_service import _calc_rfm_level
        # R=5 (3d), F=5 (25x), M=5 (¥6000)
        assert _calc_rfm_level(3, 25, 600000) == "S1"

    def test_s3_regular(self):
        from src.services.dining_journey_service import _calc_rfm_level
        # R=3 (20d), F=3 (5x), M=3 (¥1000)
        assert _calc_rfm_level(20, 5, 100000) == "S3"

    def test_s5_lost(self):
        from src.services.dining_journey_service import _calc_rfm_level
        # R=1 (90d), F=1 (1x), M=1 (¥100)
        assert _calc_rfm_level(90, 1, 10000) == "S5"


class TestBirthdayProximity:

    def test_upcoming_birthday(self):
        from src.services.dining_journey_service import _check_birthday_proximity

        today = date.today()
        birth = date(1990, today.month, today.day) + timedelta(days=3)
        # Adjust to current year
        profile = {"birth_date": birth.replace(year=1990).isoformat()}
        result = _check_birthday_proximity(profile)
        assert result is not None
        assert result["days_until"] <= 7

    def test_no_birthday(self):
        from src.services.dining_journey_service import _check_birthday_proximity

        profile = {}
        result = _check_birthday_proximity(profile)
        assert result is None


class TestPreArrivalMessage:

    def test_formats_message(self):
        from src.services.dining_journey_service import _format_pre_arrival_message

        res = MagicMock()
        res.customer_name = "张三"
        res.reservation_date = date(2026, 3, 20)
        res.reservation_time = time(18, 0)
        res.party_size = 4
        res.table_number = "VIP01"
        res.room_name = None

        profile = {"rfm_level": "S1", "total_order_count": 10}
        scene = {"type": "regular", "label": "日常"}

        msg = _format_pre_arrival_message(res, profile, scene)
        assert "VIP客户张三" in msg
        assert "18:00" in msg
        assert "第11次光临" in msg

    def test_birthday_message(self):
        from src.services.dining_journey_service import _format_pre_arrival_message

        res = MagicMock()
        res.customer_name = "李四"
        res.reservation_date = date(2026, 3, 20)
        res.reservation_time = time(12, 0)
        res.party_size = 8
        res.table_number = None
        res.room_name = "梅花厅"

        profile = {"rfm_level": "S3", "total_order_count": 2}
        scene = {"type": "birthday", "label": "生日"}

        msg = _format_pre_arrival_message(res, profile, scene)
        assert "生日" in msg


class TestPatrolChecklist:

    def test_checklist_structure(self):
        from src.services.dining_journey_service import PATROL_CHECKLIST

        assert len(PATROL_CHECKLIST) == 5
        categories = {c["id"] for c in PATROL_CHECKLIST}
        assert "food_quality" in categories
        assert "service_speed" in categories
        assert "environment" in categories
        assert "customer_mood" in categories
        assert "special_needs" in categories
