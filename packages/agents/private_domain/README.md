# 私域运营 Agent (Private Domain Operations Agent)

负责餐饮连锁门店的私域用户运营与用户增长，实现「防损防跑单」与 AARRR 增长能力。

## 原有能力（看板 / RFM / 信号 / 旅程）

| Action | 说明 | 典型入参 |
|--------|------|----------|
| get_dashboard | 私域运营看板 | - |
| analyze_rfm | RFM 用户分层 | days |
| detect_signals / get_signals | 6 类信号检测与列表 | signal_type, limit |
| calculate_store_quadrant | 门店四象限 | competition_density, member_count, estimated_population |
| trigger_journey / get_journeys | 用户旅程触发与列表 | journey_type, customer_id, status |
| segment_users / get_churn_risks | 用户分层与流失风险 | - |
| process_bad_review | 差评处理与修复旅程 | review_id, customer_id, rating, content |

## 用户增长侧 18 项（growth_handlers）

| Action | 说明 | 典型入参 |
|--------|------|----------|
| user_portrait | 用户画像与细分 | segment_id, time_range, context.member_summary |
| funnel_optimize | AARRR 漏斗优化 | funnel_stage |
| ab_test_suggest | A/B 测试建议 | test_goal, channels |
| realtime_metrics | 实时指标 | store_ids, metrics, context.metrics |
| demand_forecast | 需求预测 | store_id, horizon, sku_category |
| anomaly_alert | 异常检测与告警 | scope, sensitivity |
| personalized_recommend | 个性化推荐 | user_id, limit(1-50), context.recommendations |
| social_content_draft | 社媒文案草稿 | platform, theme, tone |
| feedback_analysis | 用户反馈分析 | source, time_range |
| store_location_advice | 门店选址建议 | city, budget, constraints |
| inventory_plan | 库存与采购计划 | store_ids, category, horizon |
| staff_schedule_advice | 排班与培训建议 | store_id, date_range |
| food_safety_alert | 食品安全告警 | store_id, sensor_ids |
| privacy_compliance_check | 数据隐私合规检查 | scope, standard |
| crisis_response_plan | 危机响应方案 | scenario_type, scope |
| product_idea | 新品创意建议 | category, trend_focus |
| integration_advice | 跨平台集成建议 | platform, business_goal |
| nl_query | 自然语言查询 | **query**（必填） |

### context 预填（可选）

调用方可在 `params.context` 中传入预拉取数据，以丰富返回：

- `context.member_summary` / `context.demographics` → user_portrait
- `context.metrics` / `context.metrics_summary` → realtime_metrics
- `context.recommendations` → personalized_recommend

### nl_query 意图关键词

画像/用户构成、漏斗/转化、推荐/吃什么、今日/数据/指标、库存/采购、排班/人手/培训、选址/开店、差评/反馈、合规/隐私、危机/舆情、新品/创意、接入/支付、预测/需求、异常/告警、A/B/测试、文案/社媒、食品安全/温度 等。

## 调用方式

- **统一执行**：POST `/api/v1/private-domain/execute`，Body `{"action": "<action>", "params": {}}`，可选 Query `store_id`。
- **列出 action**：GET `/api/v1/private-domain/actions`。
- 专项接口见 api-gateway `src/api/private_domain.py`（如 `/dashboard/{store_id}`、`/rfm/{store_id}` 等）。

## 测试

```bash
# 在仓库根目录
pytest packages/agents/private_domain/tests/ -v
```

## 业务流程

详见仓库根目录 `docs/private_domain_agent_workflow.md`。
