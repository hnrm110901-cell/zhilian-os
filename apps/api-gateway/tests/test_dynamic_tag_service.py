import pytest
from src.services.dynamic_tag_service import infer_tags


def test_high_monetary():
    tags = infer_tags({"monetary": 10000, "frequency": 1, "recency_days": 30})
    assert "高消费" in tags


def test_high_frequency():
    tags = infer_tags({"monetary": 100, "frequency": 10, "recency_days": 30})
    assert "高频" in tags


def test_recent_active():
    tags = infer_tags({"monetary": 100, "frequency": 1, "recency_days": 3})
    assert "近期活跃" in tags


def test_lunch_preference():
    tags = infer_tags({"monetary": 100, "frequency": 1, "avg_order_time": 12})
    assert "午餐偏好" in tags


def test_dinner_preference():
    tags = infer_tags({"monetary": 100, "frequency": 1, "avg_order_time": 19})
    assert "晚餐偏好" in tags


def test_family_dining():
    tags = infer_tags({"monetary": 3000, "frequency": 5, "recency_days": 3, "avg_party_size": 4.5})
    assert "家庭聚餐" in tags


def test_rising_trend():
    tags = infer_tags({"monetary": 2000, "frequency": 8, "recency_days": 5,
                       "monthly_amounts": [300, 400, 500, 600, 800]})
    assert "消费上升" in tags


def test_declining_trend():
    tags = infer_tags({"monetary": 2000, "frequency": 8, "recency_days": 5,
                       "monthly_amounts": [800, 600, 200, 100, 100]})
    assert "消费下降" in tags


def test_cross_store():
    tags = infer_tags({"monetary": 5000, "frequency": 15, "recency_days": 2, "store_count": 3})
    assert "跨店活跃" in tags


def test_default_tag():
    tags = infer_tags({"monetary": 50, "frequency": 1, "recency_days": 90})
    assert tags == ["普通用户"]


def test_multiple_tags():
    tags = infer_tags({"monetary": 10000, "frequency": 20, "recency_days": 1,
                       "avg_order_time": 19, "store_count": 3})
    assert "高消费" in tags
    assert "高频" in tags
    assert "近期活跃" in tags
    assert "晚餐偏好" in tags
    assert "跨店活跃" in tags
