# 智链OS 私域运营 Agent 业务流程

私域运营 Agent（PrivateDomainAgent）面向连锁餐饮的**用户增长与私域流量运营**，与 OpsAgent（IT 运维）形成双轮：运维保障系统稳定，私域运营驱动获客、留存与转化。

## 一、业务定位与边界

| 维度 | 说明 |
|------|------|
| **私域范围** | 微信/企微、小程序、APP、会员体系、社群与客服触达 |
| **核心目标** | 提升 AARRR 各环节转化：获客 → 激活 → 留存 → 收入 → 推荐 |
| **与运维协同** | 依赖 OpsAgent 保障 POS/会员/营销规则引擎可用；运营数据反哺运维优先级（高流水门店优先保障） |

## 二、主流程概览

```
请求入口 (POST /api/v1/private-domain/execute 或 各专项 GET/POST)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Body: { action, params }  或  Query: store_id                    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  路由层：根据 action 分发到对应能力 handler                        │
└─────────────────────────────────────────────────────────────────┘
    │
    ├── 原有能力 → get_dashboard | analyze_rfm | detect_signals | ...
    ├── 用户增长策略 → user_portrait | funnel_optimize | ab_test_suggest
    ├── 运营数据     → realtime_metrics | demand_forecast | anomaly_alert
    ├── 营销互动     → personalized_recommend | social_content_draft | feedback_analysis
    ├── 门店运营     → store_location_advice | inventory_plan | staff_schedule_advice
    ├── 风险合规     → food_safety_alert | privacy_compliance_check | crisis_response_plan
    ├── 创新扩展     → product_idea | integration_advice
    └── 自然语言     → nl_query（意图识别后内部再路由到上述 action）
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  执行层：调用数据源（POS/APP/ERP/社媒 API）+ 规则/模型/LLM        │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  响应：{ success, data, execution_time }                        │
└─────────────────────────────────────────────────────────────────┘
```

## 三、能力与 Action 映射

### 原有能力（看板/RFM/信号/四象限/旅程等）

| Action | 说明 |
|--------|------|
| get_dashboard | 私域运营看板 |
| analyze_rfm | RFM 用户分层 |
| detect_signals / get_signals | 6 类信号检测与列表 |
| calculate_store_quadrant | 门店四象限 |
| trigger_journey / get_journeys | 用户旅程触发与列表 |
| segment_users / get_churn_risks | 用户分层与流失风险 |
| process_bad_review | 差评处理与修复旅程 |

### 用户增长侧 18 项（growth_handlers）

| Action | 入参示例 | 输出形态 |
|--------|----------|----------|
| user_portrait | segment_id, time_range | 报告摘要 + 占比与典型特征 |
| funnel_optimize | funnel_stage | 瓶颈说明 + 可执行建议 |
| ab_test_suggest | test_goal | 方案摘要 + 建议采用版本 |
| realtime_metrics | store_ids, metrics[] | 指标键值 + 环比/同比 |
| demand_forecast | store_id, horizon | 预测值 + 库存建议 |
| anomaly_alert | scope | 告警列表 + 建议动作 |
| personalized_recommend | user_id, limit | 推荐列表 + 理由简述 |
| social_content_draft | platform, theme | 文案草稿 + 发布建议 |
| feedback_analysis | source, time_range | 情感分布 + 主题 Top N + 行动建议 |
| store_location_advice | city | 推荐点位 + 预期 ROI |
| inventory_plan | store_ids, category, horizon | 采购与安全库存建议 |
| staff_schedule_advice | store_id, date_range | 排班表摘要 + 培训建议 |
| food_safety_alert | store_id, sensor_ids | 告警项 + 建议处理步骤 |
| privacy_compliance_check | scope, standard | 合规结论 + 风险项与整改建议 |
| crisis_response_plan | scenario_type | 步骤列表 + 话术/模板 |
| product_idea | category, trend_focus | Idea 列表 + 优先级与测试建议 |
| integration_advice | platform, business_goal | 方案摘要 + 预期指标提升 |
| nl_query | query | 意图识别后路由到上述 action，返回 answer + data |

## 四、与数据源/系统的集成

- **会员与 APP**：会员中心 API、行为埋点、订单数据（用于画像、推荐、漏斗）。
- **POS/ERP**：交易、库存、门店主数据（用于实时指标、需求预测、库存与排班）。
- **社媒与客服**：微信/企微/抖音等 API（需合规），用于内容发布与反馈分析。
- **IoT/食品安全**：传感器数据接入，用于 `food_safety_alert`。
- **LLM/规则引擎**：文案生成、意图识别可走 LLM；推荐与风控可走规则或模型。

## 五、API 说明

- **POST** `/api/v1/private-domain/execute`：统一执行任意 action，Body `{"action": "<action>", "params": {}}`，可选 Query `store_id`。
- **GET** `/api/v1/private-domain/actions`：列出全部 action（含 growth_actions）。
- 原有专项接口：`/dashboard/{store_id}`、`/rfm/{store_id}`、`/signals/{store_id}`、`/churn-risks/{store_id}`、`/journeys/{store_id}`、`/journeys/{store_id}/trigger`、`/quadrant/{store_id}`、`/reviews/{store_id}/process` 等保持不变。

以上业务流程与 `packages/agents/private_domain` 及 `apps/api-gateway/src/api/private_domain.py` 中的实现一一对应。

## 六、企业微信应用

私域运营 Agent 作为企业微信应用的规划、消息流与智链OS 整体兼容性见：**[私域运营 Agent 企业微信应用规划及兼容智链OS 整体系统](private_domain_wechat_app_plan.md)**。要点：复用现有 `/wechat/webhook` 与 WeChatService，在 POST 收到文本消息后调用 `nl_query` 并回发回复；store_id 可从 FromUserName 关联 User 表获得。
