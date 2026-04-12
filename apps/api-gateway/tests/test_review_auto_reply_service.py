"""
大众点评评价自动回复服务测试
"""

import pytest

from src.services.review_auto_reply_service import (
    ReviewAutoReplyService,
    ReviewData,
    ClassificationResult,
)


@pytest.fixture
def service():
    return ReviewAutoReplyService()


def _make_review(review_id="R001", content="", rating=5):
    return ReviewData(
        review_id=review_id,
        content=content,
        rating=rating,
        customer_name="测试用户",
        platform="大众点评",
    )


class TestClassifyReview:
    def test_positive_review(self, service):
        result = service.classify_review("菜品好吃，味道新鲜，服务热情", 5)
        assert result.classification == "好评"
        assert result.sentiment_score > 0
        assert len(result.positive_keywords) > 0

    def test_negative_review(self, service):
        result = service.classify_review("难吃，服务差，不会再来", 1)
        assert result.classification == "差评"
        assert result.sentiment_score < 0
        assert len(result.negative_keywords) > 0

    def test_neutral_review(self, service):
        result = service.classify_review("一般般，中规中矩", 3)
        assert result.classification in ("中评", "好评", "差评")

    def test_malicious_review(self, service):
        result = service.classify_review("同行刷差评，敲诈勒索", 1)
        assert result.classification == "恶意"

    def test_category_detection_food(self, service):
        result = service.classify_review("菜的味道很好，食材新鲜", 5)
        assert result.category == "菜品"

    def test_category_detection_service(self, service):
        result = service.classify_review("服务员态度很热情", 5)
        assert result.category == "服务"

    def test_category_detection_hygiene(self, service):
        result = service.classify_review("不太卫生，桌上不干净", 2)
        assert result.category == "卫生"


class TestGenerateReplyDraft:
    def test_positive_reply_contains_store_name(self, service):
        review = _make_review(content="好吃推荐", rating=5)
        cls = service.classify_review(review.content, review.rating)
        draft = service.generate_reply_draft(review, "湘菜馆", cls)
        assert "湘菜馆" in draft.draft_text
        assert draft.review_id == "R001"

    def test_negative_reply_has_apology(self, service):
        review = _make_review(content="难吃失望不会再来", rating=1)
        cls = service.classify_review(review.content, review.rating)
        draft = service.generate_reply_draft(review, "湘菜馆", cls)
        assert "抱歉" in draft.draft_text or "歉" in draft.draft_text

    def test_draft_template_source_recorded(self, service):
        review = _make_review(content="环境好", rating=4)
        cls = service.classify_review(review.content, review.rating)
        draft = service.generate_reply_draft(review, "测试店", cls)
        assert "4星" in draft.template_source


class TestCheckUrgency:
    def test_one_star_is_p1(self, service):
        review = _make_review(rating=1, content="太差了")
        result = service.check_urgency(review)
        assert result["urgency"] == "P1"
        assert result["deadline_hours"] == 1

    def test_two_star_is_p2(self, service):
        review = _make_review(rating=2, content="不太好")
        result = service.check_urgency(review)
        assert result["urgency"] == "P2"

    def test_five_star_is_p4(self, service):
        review = _make_review(rating=5, content="好吃")
        result = service.check_urgency(review)
        assert result["urgency"] == "P4"

    def test_food_safety_escalates_to_p1(self, service):
        """食品安全关键词自动升级到P1"""
        review = _make_review(rating=3, content="吃完拉肚子了")
        result = service.check_urgency(review)
        assert result["urgency"] == "P1"
        assert result["is_food_safety"] is True


class TestCreateAlert:
    def test_p1_alert_multiple_channels(self, service):
        review = _make_review(rating=1, content="太难吃了")
        alert = service.create_alert(review, "P1", "湘菜馆")
        assert "企业微信" in alert.notify_channels
        assert "短信" in alert.notify_channels
        assert alert.urgency == "P1"
        assert "紧急" in alert.suggested_action

    def test_alert_stores_in_memory(self, service):
        review = _make_review(rating=2, content="服务差")
        alert = service.create_alert(review, "P2", "测试店")
        assert alert.alert_id in service._alerts


class TestApproveReply:
    def test_approve_success(self, service):
        result = service.approve_reply("R001", "MGR01", "感谢您的反馈")
        assert result["status"] == "approved"
        assert result["approver_id"] == "MGR01"

    def test_approve_empty_text_fails(self, service):
        result = service.approve_reply("R001", "MGR01", "")
        assert "error" in result

    def test_approve_too_long_fails(self, service):
        result = service.approve_reply("R001", "MGR01", "x" * 501)
        assert "error" in result


class TestGetReplyStats:
    def test_empty_reviews(self, service):
        stats = service.get_reply_stats([], "7d")
        assert stats.total_reviews == 0
        assert stats.reply_rate == 0.0

    def test_stats_classification_counts(self, service):
        reviews = [
            _make_review("R1", "好吃推荐", 5),
            _make_review("R2", "好吃美味", 5),
            _make_review("R3", "一般般", 3),
            _make_review("R4", "难吃失望", 1),
        ]
        stats = service.get_reply_stats(reviews, "7d")
        assert stats.total_reviews == 4
        assert stats.positive_count >= 2
        assert stats.negative_count >= 1
