"""
用户增长侧 growth_handlers 单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from growth_handlers import (
    GROWTH_ACTIONS,
    run_growth_action,
)


@pytest.fixture
def store_id():
    return "S001"


@pytest.mark.asyncio
async def test_growth_actions_count():
    assert len(GROWTH_ACTIONS) == 18
    assert "nl_query" in GROWTH_ACTIONS
    assert "user_portrait" in GROWTH_ACTIONS


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    out = await run_growth_action("unknown_action", {}, "")
    assert "error" in out
    assert "supported" in out


@pytest.mark.asyncio
async def test_user_portrait_returns_summary_and_demographics(store_id):
    out = await run_growth_action("user_portrait", {"segment_id": "vip"}, store_id)
    assert "error" not in out
    assert "summary" in out
    assert "demographics" in out
    assert out.get("store_id") == store_id


@pytest.mark.asyncio
async def test_user_portrait_uses_context():
    ctx = {"member_summary": "自定义画像摘要", "demographics": {"custom": 1}}
    out = await run_growth_action("user_portrait", {"context": ctx}, "")
    assert out.get("summary") == "自定义画像摘要"
    assert out.get("demographics", {}).get("custom") == 1


@pytest.mark.asyncio
async def test_realtime_metrics_uses_context():
    ctx = {"metrics_summary": "今日增长10%", "metrics": {"dau_growth_pct": 10}}
    out = await run_growth_action("realtime_metrics", {"context": ctx}, "S002")
    assert out.get("summary") == "今日增长10%"
    assert out.get("metrics", {}).get("dau_growth_pct") == 10
    assert out.get("store_id") == "S002"


@pytest.mark.asyncio
async def test_personalized_recommend_limit_bounded():
    out = await run_growth_action("personalized_recommend", {"user_id": "U1", "limit": 3}, "")
    assert len(out.get("items", [])) <= 3
    assert out.get("limit") == 3


@pytest.mark.asyncio
async def test_personalized_recommend_uses_context():
    ctx = {"recommendations": [{"type": "menu", "name": "A", "reason": "因为A"}]}
    out = await run_growth_action("personalized_recommend", {"context": ctx, "limit": 5}, "")
    assert out["items"][0]["name"] == "A"
    assert out["items"][0]["reason"] == "因为A"


@pytest.mark.asyncio
async def test_nl_query_requires_query():
    out = await run_growth_action("nl_query", {}, "")
    # 参数校验失败时返回 error，未进入 handler 故无 answer
    assert "error" in out
    assert "query" in out.get("error", "").lower() or "query" in str(out)


@pytest.mark.asyncio
async def test_nl_query_intent_user_portrait():
    out = await run_growth_action("nl_query", {"query": "用户画像怎么样"}, "")
    assert out.get("resolved_actions") == ["user_portrait"]
    assert "data" in out
    assert "summary" in out.get("data", {})


@pytest.mark.asyncio
async def test_nl_query_intent_inventory():
    out = await run_growth_action("nl_query", {"query": "库存和采购计划"}, "")
    assert "inventory_plan" in out.get("resolved_actions", [])


@pytest.mark.asyncio
async def test_nl_query_intent_staff_schedule():
    out = await run_growth_action("nl_query", {"query": "下周排班人手不够"}, "")
    assert "staff_schedule_advice" in out.get("resolved_actions", [])


@pytest.mark.asyncio
async def test_nl_query_intent_store_location():
    out = await run_growth_action("nl_query", {"query": "想开新店选址"}, "")
    assert "store_location_advice" in out.get("resolved_actions", [])


@pytest.mark.asyncio
async def test_validation_personalized_recommend_limit_invalid():
    out = await run_growth_action("personalized_recommend", {"limit": 100}, "")
    assert "error" in out


@pytest.mark.asyncio
async def test_funnel_optimize_returns_suggestions():
    out = await run_growth_action("funnel_optimize", {"funnel_stage": "retention"}, "")
    assert "bottleneck" in out
    assert "suggestions" in out
    assert len(out["suggestions"]) >= 1


@pytest.mark.asyncio
async def test_demand_forecast_returns_horizon():
    out = await run_growth_action("demand_forecast", {"horizon": "14d"}, "")
    assert out.get("horizon") == "14d"
    assert "forecast_growth_pct" in out
    assert "inventory_suggestion_pct" in out


@pytest.mark.asyncio
async def test_food_safety_alert_returns_alerts():
    out = await run_growth_action("food_safety_alert", {"store_id": "S1"}, "")
    assert "alerts" in out
    assert len(out["alerts"]) >= 1
    assert out.get("store_id") == "S1"
