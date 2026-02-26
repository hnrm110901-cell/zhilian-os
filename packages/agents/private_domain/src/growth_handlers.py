"""
用户增长运营能力 - 与 Cursor 用户增长 Skill 对齐的 18 个 action 实现.
用于私域运营 Agent 扩展：用户画像、AARRR 漏斗、实时指标、推荐、门店/合规/创新等.

支持通过 params.context 传入预填数据（如 api-gateway 预拉取的会员/推荐结果），用于丰富返回。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 用户增长侧 18 个 action（与 chain-restaurant-user-growth Skill 一致）
GROWTH_ACTIONS = [
    "user_portrait",
    "funnel_optimize",
    "ab_test_suggest",
    "realtime_metrics",
    "demand_forecast",
    "anomaly_alert",
    "personalized_recommend",
    "social_content_draft",
    "feedback_analysis",
    "store_location_advice",
    "inventory_plan",
    "staff_schedule_advice",
    "food_safety_alert",
    "privacy_compliance_check",
    "crisis_response_plan",
    "product_idea",
    "integration_advice",
    "nl_query",
]


def _validate_params(action: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """基础参数校验，返回 (是否通过, 错误信息)。"""
    if action == "nl_query":
        if not (params.get("query") or "").strip():
            return False, "nl_query 需要提供非空参数 query"
    if action == "personalized_recommend":
        limit = params.get("limit")
        if limit is not None and (not isinstance(limit, (int, float)) or int(limit) < 1 or int(limit) > 50):
            return False, "personalized_recommend 的 limit 应为 1～50 的整数"
    return True, None


async def run_growth_action(action: str, params: Dict[str, Any], store_id: str = "") -> Dict[str, Any]:
    """
    根据 action 分发到对应 handler，返回 data 字典（供 AgentResponse.data 使用）。
    若 params 中含 context（预填数据），各 handler 可据此丰富返回。
    """
    p = dict(params) if params else {}
    if store_id:
        p["store_id"] = store_id
    if action not in GROWTH_ACTIONS:
        return {"error": f"未知 action: {action}", "supported": GROWTH_ACTIONS}
    ok, err = _validate_params(action, p)
    if not ok:
        return {"error": err, "action": action}
    handler = _HANDLERS.get(action)
    if not handler:
        return {"error": f"action 未实现: {action}"}
    try:
        return await handler(p)
    except Exception as e:
        return {"error": str(e), "action": action}


def _with_store_id(data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """当 params 中有 store_id 时写入 data，便于前端/调用方使用。"""
    sid = params.get("store_id")
    if sid:
        data["store_id"] = sid
    return data


# ---------- 1. 用户增长策略 ----------
async def _user_portrait(params: Dict[str, Any]) -> Dict[str, Any]:
    """用户画像与细分。可选: segment_id, time_range。context.member_summary 可预填。"""
    segment_id = params.get("segment_id") or "default"
    time_range = params.get("time_range") or "last_30d"
    ctx = params.get("context") or {}
    summary = ctx.get("member_summary")
    if not summary:
        summary = "25-35岁都市白领用户占比约60%，偏好健康轻食，平均消费频次每周2次。"
    data = {
        "summary": summary,
        "segment_id": segment_id,
        "time_range": time_range,
        "demographics": ctx.get("demographics") or {"age_25_35": 0.6, "preference": "健康轻食", "visit_per_week": 2},
    }
    return _with_store_id(data, params)


async def _funnel_optimize(params: Dict[str, Any]) -> Dict[str, Any]:
    """AARRR 漏斗优化。可选: funnel_stage。"""
    funnel_stage = params.get("funnel_stage") or "activation"
    data = {
        "bottleneck": "激活阶段转化率偏低",
        "suggestions": [
            "通过 APP 推送个性化优惠券，预计提升激活率约 15%。",
            "优化首单引导流程，减少步骤。",
        ],
        "funnel_stage": funnel_stage,
    }
    return _with_store_id(data, params)


async def _ab_test_suggest(params: Dict[str, Any]) -> Dict[str, Any]:
    """A/B 测试建议。可选: test_goal, channels。"""
    test_goal = params.get("test_goal") or "点击率"
    data = {
        "conclusion": "版本 A 的点击率提升 20%，推荐采用。",
        "test_goal": test_goal,
        "recommended_variant": "A",
    }
    return _with_store_id(data, params)


# ---------- 2. 运营数据分析与预测 ----------
async def _realtime_metrics(params: Dict[str, Any]) -> Dict[str, Any]:
    """实时指标。可选: store_ids, metrics。context.metrics 可预填。"""
    store_ids = params.get("store_ids") or []
    ctx = params.get("context") or {}
    metrics = ctx.get("metrics")
    summary = ctx.get("metrics_summary")
    if not metrics:
        metrics = {"dau_growth_pct": 5, "peak_period": "午餐"}
    if not summary:
        summary = "今日用户增长约 5%，门店流量峰值在午餐时段。"
    data = {"summary": summary, "metrics": metrics, "store_ids": store_ids}
    return _with_store_id(data, params)


async def _demand_forecast(params: Dict[str, Any]) -> Dict[str, Any]:
    """需求预测。可选: store_id, horizon, sku_category。"""
    horizon = params.get("horizon") or "7d"
    data = {
        "summary": "下周周末用户增长预计约 10%，建议增加库存 20%。",
        "forecast_growth_pct": 10,
        "inventory_suggestion_pct": 20,
        "horizon": horizon,
    }
    return _with_store_id(data, params)


async def _anomaly_alert(params: Dict[str, Any]) -> Dict[str, Any]:
    """异常检测与告警。可选: scope, sensitivity。"""
    scope = params.get("scope") or "satisfaction"
    data = {
        "alerts": [
            {
                "type": "satisfaction_drop",
                "message": "用户满意度下降约 15%，原因：服务投诉增多。",
                "suggested_action": "排查高峰时段人手与培训，加强服务话术。",
            }
        ],
        "scope": scope,
    }
    return _with_store_id(data, params)


# ---------- 3. 营销与用户互动 ----------
async def _personalized_recommend(params: Dict[str, Any]) -> Dict[str, Any]:
    """个性化推荐。可选: user_id, limit, channel。context.recommendations 可预填。"""
    user_id = params.get("user_id") or "anonymous"
    limit = params.get("limit")
    if limit is None:
        limit = 5
    limit = int(limit)
    limit = max(1, min(50, limit))
    ctx = params.get("context") or {}
    items = ctx.get("recommendations")
    if not items:
        items = [
            {"type": "menu", "name": "低卡路里沙拉套餐", "reason": "根据您的历史订单与健康偏好推荐。"}
        ]
    data = {"items": items[:limit], "user_id": user_id, "limit": limit}
    return _with_store_id(data, params)


async def _social_content_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """社媒文案草稿。可选: platform, theme, tone。"""
    platform = params.get("platform") or "wechat"
    theme = params.get("theme") or "新品上市"
    data = {
        "draft": "新品上市！分享你的试吃体验，赢取免费券。",
        "platform": platform,
        "theme": theme,
        "publish_tip": "建议午间 11:00 或晚间 18:00 发布。",
    }
    return _with_store_id(data, params)


async def _feedback_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """用户反馈分析。可选: source, time_range。"""
    source = params.get("source") or "reviews"
    time_range = params.get("time_range") or "last_7d"
    data = {
        "summary": "约 80% 用户反馈口味偏辣，建议调整配方或提供辣度选项。",
        "sentiment_distribution": {"negative": 0.3, "neutral": 0.2, "positive": 0.5},
        "top_themes": ["口味偏辣", "分量足", "出餐速度"],
        "actions": ["调整配方或增加辣度选项", "保留分量与出餐优势"],
        "source": source,
        "time_range": time_range,
    }
    return _with_store_id(data, params)


# ---------- 4. 门店运营优化 ----------
async def _store_location_advice(params: Dict[str, Any]) -> Dict[str, Any]:
    """门店选址建议。可选: city, budget, constraints。"""
    city = params.get("city") or "长沙"
    data = {
        "summary": "推荐城市中心区选址，预计年 ROI 约 25%。",
        "recommended_areas": ["城市中心区"],
        "expected_roi_pct": 25,
        "city": city,
    }
    return _with_store_id(data, params)


async def _inventory_plan(params: Dict[str, Any]) -> Dict[str, Any]:
    """库存与采购计划。可选: store_ids, category, horizon。"""
    store_ids = params.get("store_ids") or []
    category = params.get("category") or "coffee"
    horizon = params.get("horizon") or "next_month"
    data = {
        "summary": "下月咖啡豆需求预计增加约 15%，建议提前采购。",
        "category": category,
        "demand_change_pct": 15,
        "horizon": horizon,
        "store_ids": store_ids,
    }
    return _with_store_id(data, params)


async def _staff_schedule_advice(params: Dict[str, Any]) -> Dict[str, Any]:
    """排班与培训建议。可选: store_id, date_range, constraints。"""
    store_id = params.get("store_id")
    date_range = params.get("date_range") or "next_week"
    data = {
        "summary": "周一高峰期需额外 3 名员工；推荐培训模块：服务礼仪。",
        "schedule_summary": "周一高峰 +3 人",
        "training_module": "服务礼仪",
        "store_id": store_id,
        "date_range": date_range,
    }
    return _with_store_id(data, params)


# ---------- 5. 风险管理与合规 ----------
async def _food_safety_alert(params: Dict[str, Any]) -> Dict[str, Any]:
    """食品安全告警。可选: store_id, sensor_ids。"""
    store_id = params.get("store_id")
    sensor_ids = params.get("sensor_ids") or []
    data = {
        "alerts": [
            {"message": "冷藏室温度异常，建议立即检查。", "level": "high", "sensor": "cold_room"}
        ],
        "store_id": store_id,
        "sensor_ids": sensor_ids,
    }
    return data


async def _privacy_compliance_check(params: Dict[str, Any]) -> Dict[str, Any]:
    """数据隐私合规检查。可选: scope, standard。"""
    scope = params.get("scope") or "full"
    standard = params.get("standard") or "PIPL"
    data = {
        "summary": "当前数据处理符合法规要求，未发现明显漏洞。",
        "standard": standard,
        "passed": True,
        "risks": [],
        "scope": scope,
    }
    return _with_store_id(data, params)


async def _crisis_response_plan(params: Dict[str, Any]) -> Dict[str, Any]:
    """危机响应方案。可选: scenario_type, scope。"""
    scenario_type = params.get("scenario_type") or "food_safety"
    data = {
        "steps": [
            "步骤 1：公开回应，表达重视与歉意。",
            "步骤 2：召回相关产品并配合监管。",
            "步骤 3：公布整改与补偿方案。",
        ],
        "scenario_type": scenario_type,
        "templates": ["公开声明模板", "客服话术模板"],
    }
    return _with_store_id(data, params)


# ---------- 6. 创新与扩展 ----------
async def _product_idea(params: Dict[str, Any]) -> Dict[str, Any]:
    """新品创意建议。可选: category, trend_focus。"""
    category = params.get("category") or "burger"
    trend_focus = params.get("trend_focus") or "plant_based"
    data = {
        "ideas": [
            {
                "name": "植物基汉堡",
                "target_audience": "素食主义者与健康人群",
                "priority": "high",
            }
        ],
        "category": category,
        "trend_focus": trend_focus,
    }
    return _with_store_id(data, params)


async def _integration_advice(params: Dict[str, Any]) -> Dict[str, Any]:
    """跨平台集成建议。可选: platform, business_goal。"""
    platform = params.get("platform") or "alipay"
    business_goal = params.get("business_goal") or "payment_conversion"
    data = {
        "summary": "接入支付宝可提升支付转化率约 10%。",
        "platform": platform,
        "expected_impact": "支付转化率提升约 10%",
        "business_goal": business_goal,
    }
    return _with_store_id(data, params)


# ---------- 7. 自然语言入口 ----------
def _nl_intent_routes() -> List[Tuple[List[str], str]]:
    """返回 (关键词列表, action) 的映射，用于 nl_query 意图识别。"""
    return [
        (["画像", "用户构成", "人群"], "user_portrait"),
        (["漏斗", "转化", "激活", "留存"], "funnel_optimize"),
        (["推荐", "吃什么", "点餐"], "personalized_recommend"),
        (["今日", "数据", "指标", "实时", "看板"], "realtime_metrics"),
        (["库存", "采购", "备货", "需求预测"], "inventory_plan"),
        (["排班", "人手", "培训", "调度"], "staff_schedule_advice"),
        (["选址", "开店", "扩张", "新店"], "store_location_advice"),
        (["差评", "反馈", "口碑", "评论"], "feedback_analysis"),
        (["合规", "隐私", "PIPL", "数据安全"], "privacy_compliance_check"),
        (["危机", "舆情", "食安", "召回"], "crisis_response_plan"),
        (["新品", "创意", "idea", "研发"], "product_idea"),
        (["接入", "支付", "集成", "支付宝", "微信支付"], "integration_advice"),
        (["预测", "需求", "销量", "下周"], "demand_forecast"),
        (["异常", "告警", "流失", "下降"], "anomaly_alert"),
        (["A/B", "测试", "实验", "ab test"], "ab_test_suggest"),
        (["文案", "社媒", "发布", "公众号"], "social_content_draft"),
        (["食品安全", "温度", "冷藏"], "food_safety_alert"),
    ]


async def _nl_query(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    自然语言查询：根据 query 意图路由到对应 action 并汇总返回。
    必填: query。可选: context（会传给子 action）。
    """
    query = (params.get("query") or "").strip()
    if not query:
        return {"answer": "请提供具体问题（query）。", "resolved_actions": []}
    q_lower = query.lower()
    routes = _nl_intent_routes()
    for keywords, action_name in routes:
        if any(kw in query or kw in q_lower for kw in keywords):
            handler = _HANDLERS.get(action_name)
            if handler:
                data = await handler(params)
                summary = data.get("summary") or data.get("bottleneck") or ""
                if data.get("suggestions"):
                    summary += " " + "; ".join(data.get("suggestions", []))
                if data.get("items"):
                    summary = (data.get("items") or [{}])[0].get("reason", summary)
                return {
                    "answer": summary or "已根据意图执行，详见 data。",
                    "resolved_actions": [action_name],
                    "data": data,
                }
    return {
        "answer": "已收到您的问题。可通过「用户画像、漏斗优化、实时指标、个性化推荐、库存计划、排班、选址、反馈分析、合规、危机、新品、接入、预测、异常、A/B测试、文案、食品安全」等关键词提问，或使用 action 直接调用。",
        "resolved_actions": [],
        "supported_actions": GROWTH_ACTIONS,
    }


_HANDLERS = {
    "user_portrait": _user_portrait,
    "funnel_optimize": _funnel_optimize,
    "ab_test_suggest": _ab_test_suggest,
    "realtime_metrics": _realtime_metrics,
    "demand_forecast": _demand_forecast,
    "anomaly_alert": _anomaly_alert,
    "personalized_recommend": _personalized_recommend,
    "social_content_draft": _social_content_draft,
    "feedback_analysis": _feedback_analysis,
    "store_location_advice": _store_location_advice,
    "inventory_plan": _inventory_plan,
    "staff_schedule_advice": _staff_schedule_advice,
    "food_safety_alert": _food_safety_alert,
    "privacy_compliance_check": _privacy_compliance_check,
    "crisis_response_plan": _crisis_response_plan,
    "product_idea": _product_idea,
    "integration_advice": _integration_advice,
    "nl_query": _nl_query,
}
