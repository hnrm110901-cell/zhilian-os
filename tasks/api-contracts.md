# tasks/api-contracts.md — 接口契约（Claude ↔ Codex 握手文件）

> Claude 新增/修改后端接口时在此更新。
> Codex 根据此文件生成前端 API Client，**禁止自行推断接口**。

---

## 最近更新

| 日期 | 变更 | 影响 |
|------|------|------|
| 2026-03-12 | Phase 13 OpsFlowAgent 15个端点 | OpsFlowAgentPage 5个 Tab |
| 2026-03-12 | Agent OKR 看板 4个端点 | AgentOKRPage |
| 2026-03-08 | 整理 Phase 8 workforce 全部接口 | 前端 WorkforcePage 相关 |

---

## OpsFlowAgent（运营流程体）接口

**路由前缀**: `/api/v1/ops-flow`

### POST `/api/v1/ops-flow/chain-events`
创建出品链联动事件，自动触发级联告警
```typescript
// Request
{
  store_id: string;
  event_layer: "order" | "inventory" | "quality";
  event_type: string;   // 事件类型
  event_data: Record<string, any>;
  source_agent: string;
}
// Response
{
  success: boolean;
  chain_event_id: string;
  linkages_triggered: number;
  data: { event: object; linkages: object[] };
}
```

### POST `/api/v1/ops-flow/chain-events/{event_id}/resolve`
```typescript
// Request: { resolution_note?: string }
// Response: { success: boolean; data: object }
```

### GET `/api/v1/ops-flow/chain-events/{event_id}/linkages`
获取联动事件的所有级联响应
```typescript
// Response: { success: boolean; data: object[] }
```

### POST `/api/v1/ops-flow/order-anomaly/detect`
检测订单异常并返回建议动作
```typescript
// Request
{
  store_id: string;
  order_id: string;
  expected_amount: number;
  actual_amount: number;
  order_time: string; // ISO datetime
}
// Response
{
  anomaly_detected: boolean;
  anomaly_type: string | null;
  deviation_pct: number;
  revenue_loss_yuan: number;
  suggested_action: string;
  data: object;
}
```

### GET `/api/v1/ops-flow/order-anomalies`
```typescript
// Query: store_id, start_date?, end_date?, anomaly_type?, limit?
// Response: { success: boolean; data: object[]; count: number }
```

### POST `/api/v1/ops-flow/inventory/check`
单次库存智能检查
```typescript
// Request
{
  store_id: string;
  sku_id: string;
  current_stock: number;
  daily_usage: number;
  reorder_point?: number;
  max_capacity?: number;
}
// Response
{
  risk_level: "safe" | "warning" | "critical";
  days_remaining: number;
  suggested_order_quantity: number;
  inventory_loss_yuan: number;
  data: object;
}
```

### POST `/api/v1/ops-flow/inventory/batch-check`
```typescript
// Request: { items: [{ store_id, sku_id, current_stock, daily_usage, reorder_point?, max_capacity? }] }
// Response: { total: number; critical_count: number; warning_count: number; results: object[] }
```

### GET `/api/v1/ops-flow/inventory-alerts`
```typescript
// Query: store_id, risk_level?, is_resolved?, limit?
// Response: { success: boolean; data: object[]; count: number }
```

### POST `/api/v1/ops-flow/inventory-alerts/{alert_id}/resolve`
```typescript
// Request: { resolution_note?: string }
// Response: { success: boolean; data: object }
```

### POST `/api/v1/ops-flow/quality/inspect`
创建菜品质检记录
```typescript
// Request
{
  store_id: string;
  dish_id: string;
  dish_name: string;
  inspector_id: string;
  appearance_score?: number;   // 0-10
  taste_score?: number;
  temperature_score?: number;
  portion_score?: number;
  overall_score?: number;
  notes?: string;
}
// Response: { success: boolean; quality_status: string; data: object }
```

### GET `/api/v1/ops-flow/quality-summary`
```typescript
// Query: store_id, start_date?, end_date?
// Response: { store_id, total_inspections, pass_count, fail_count, warning_count, avg_score, pass_rate_pct }
```

### GET `/api/v1/ops-flow/quality-records`
```typescript
// Query: store_id, status?, dish_id?, limit?
// Response: { success: boolean; data: object[]; count: number }
```

### GET `/api/v1/ops-flow/stores/{store_id}/optimize`
获取门店运营优化建议（OpsOptimizeAgent）
```typescript
// Response
{
  store_id: string;
  recommendations: Array<{
    category: "order" | "inventory" | "quality";
    priority: "high" | "medium" | "low";
    title: string;
    description: string;
    expected_impact_yuan: number;
    action_items: string[];
  }>;
  total_impact_yuan: number;
  ai_insight: string;
}
```

### POST `/api/v1/ops-flow/decisions/accept`
接受运营优化决策
```typescript
// Request: { store_id, decision_type, decision_data, expected_impact_yuan? }
// Response: { success: boolean; data: object }
```

### GET `/api/v1/ops-flow/decisions`
```typescript
// Query: store_id, decision_type?, limit?
// Response: { success: boolean; data: object[]; count: number }
```

### GET `/api/v1/ops-flow/dashboard`
驾驶舱 BFF（前端首屏单接口）
```typescript
// Query: store_id, days? (default 7)
// Response
{
  store_id: string;
  period_days: number;
  chain_events: { total, resolved, unresolved, by_layer: Record<string, number> };
  order_anomalies: { total, total_revenue_loss_yuan, by_type: Record<string, number> };
  inventory_alerts: { total, critical, warning, safe };
  quality: { total_inspections, pass_count, fail_count, avg_score, pass_rate_pct };
  ai_insight: string;
}
```

---

## Agent OKR 看板接口

**路由前缀**: `/api/v1/agent-okr`

### POST `/api/v1/agent-okr/log`
记录一次 Agent 建议（OKR 追踪起点）
```typescript
// Request
{
  agent_name: "business_intel" | "ops_flow" | "people" | "marketing" | "banquet" | "dish_rd" | "supplier" | "compliance" | "fct" | "private_domain";
  store_id: string;
  recommendation_type: string;
  recommendation_text: string;
  expected_impact_yuan?: number;
  confidence_score?: number;  // 0-1
}
// Response: { success: boolean; log_id: string; data: object }
```

### POST `/api/v1/agent-okr/adopt`
记录用户采纳/拒绝决策
```typescript
// Request
{
  log_id: string;
  status: "adopted" | "rejected" | "auto_executed" | "expired";
  actual_impact_yuan?: number;
  response_latency_seconds?: number;
  notes?: string;
}
// Response: { success: boolean; data: object }
```

### POST `/api/v1/agent-okr/verify`
记录建议效果验证（48h 后回访）
```typescript
// Request
{
  log_id: string;
  actual_impact_yuan: number;
  outcome_notes?: string;
}
// Response: { success: boolean; data: object }
```

### GET `/api/v1/agent-okr/summary`
获取所有 Agent OKR 达成汇总（看板首屏）
```typescript
// Query: brand_id, days? (default 30)
// Response
{
  overall: {
    total_recommendations: number;
    overall_adoption_rate: number | null;
    overall_adoption_rate_pct: number | null;
    total_recommendation_yuan: number;
  };
  agents: Array<{
    agent_name: string;
    total_recommendations: number;
    adopted_count: number;
    rejected_count: number;
    adoption_rate: number | null;
    adoption_rate_pct: number | null;
    adoption_target_pct: number;
    okr_adoption: string;        // "✅ 采纳率达标" / "❌ 采纳率未达标" / "⏳ 数据不足"
    avg_prediction_error_pct: number | null;
    accuracy_target_pct: number | null;
    okr_accuracy: string;
    avg_response_latency_seconds: number | null;
    latency_target_seconds: number | null;
    okr_latency: string;
    total_recommendation_yuan: number;
  }>;
}
```

---

## Workforce（人力管理）接口

### GET `/api/v1/workforce/stores/{store_id}/employee-health`

**用途**: 员工健康度——流失风险 + 班次公平性综合视图

**Query 参数**:
```typescript
{
  year?: number;   // 默认当年
  month?: number;  // 默认当月
  top_n?: number;  // 默认20，最大200
}
```

**响应 Schema**:
```typescript
interface EmployeeHealthResponse {
  store_id: string;
  year: number;
  month: number;
  total: number;
  fairness_index: number;  // 0-100，越高越公平
  fairness_distribution: {
    high_unfairness: number;   // 不公平比例≥50%的人数
    medium_unfairness: number; // 25%-50%
    low_unfairness: number;    // <25%
  };
  items: EmployeeHealthItem[];
}

interface EmployeeHealthItem {
  employee_id: string;
  name: string;
  position: string;
  risk_score_90d: number;       // 0-1，90天内离职风险
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  replacement_cost_yuan: number; // ¥离职替换成本（月薪×50%）
  major_risk_factors: string[];  // 主要风险因子文本列表
  unfavorable_ratio: number;     // 差班占比 0-1
  unfavorable_shifts: number;    // 差班次数
  total_shifts: number;          // 总班次数
}
```

**风险等级映射**:
```
risk_score < 0.3  → 'low'     (绿色)
0.3 - 0.5         → 'medium'  (黄色)
0.5 - 0.7         → 'high'    (橙色)
≥ 0.7             → 'critical'(红色，已触发企微预警)
```

---

### GET `/api/v1/workforce/stores/{store_id}/labor-forecast`

**用途**: 客流预测 → 人力需求建议（明天）

**Query 参数**:
```typescript
{
  date?: string;          // YYYY-MM-DD，默认明天
  weather_score?: number; // 0.5-1.5，天气系数，默认1.0
}
```

**响应 Schema**:
```typescript
interface LaborForecastResponse {
  store_id: string;
  forecast_date: string;
  periods: {
    morning: PeriodForecast;
    lunch: PeriodForecast;
    afternoon: PeriodForecast;
    dinner: PeriodForecast;
  };
  total_recommended_headcount: number;
  estimated_labor_cost_yuan: number;   // ¥预估人工成本
  confidence: number;                  // 0-1 预测置信度
}

interface PeriodForecast {
  predicted_customers: number;
  recommended_headcount: number;
  position_breakdown: {
    kitchen: number;
    floor: number;
    cashier: number;
  };
}
```

---

### GET `/api/v1/workforce/stores/{store_id}/labor-cost`

**用途**: 今日人工成本快照

**Query 参数**:
```typescript
{
  date?: string; // YYYY-MM-DD，默认今天
}
```

**响应 Schema**:
```typescript
interface LaborCostSnapshot {
  store_id: string;
  snapshot_date: string;
  total_labor_cost_yuan: number;
  labor_cost_rate_pct: number;  // 人工成本率 %
  revenue_yuan: number;
  headcount_actual: number;
  overtime_cost_yuan: number;
  vs_yesterday: {
    cost_delta_yuan: number;
    rate_delta_pct: number;
  };
  vs_budget: {
    budget_yuan: number;
    used_pct: number;           // 已用预算百分比
    alert: boolean;             // 超过 alert_threshold 时为 true
  };
}
```

---

### GET `/api/v1/workforce/stores/{store_id}/labor-efficiency`

**用途**: 人效趋势（时间段内）

**Query 参数**:
```typescript
{
  start_date: string;  // YYYY-MM-DD（必填）
  end_date: string;    // YYYY-MM-DD（必填）
}
```

**响应 Schema**:
```typescript
interface LaborEfficiencyResponse {
  store_id: string;
  start_date: string;
  end_date: string;
  avg_revenue_per_labor_hour_yuan: number;  // 人均产值¥
  trend: Array<{
    date: string;
    revenue_per_labor_hour_yuan: number;
    headcount: number;
  }>;
}
```

---

### POST `/api/v1/workforce/stores/{store_id}/staffing-advice/confirm`

**用途**: 店长确认/拒绝人力建议

**请求 Body**:
```typescript
interface StaffingAdviceConfirmRequest {
  advice_date: string;             // YYYY-MM-DD
  meal_period?: string;            // 'morning'|'lunch'|'dinner'|'all_day'，默认all_day
  action: 'confirmed' | 'rejected' | 'modified';
  modified_headcount?: number;     // action=modified 时填写
  rejection_reason?: string;
}
```

**响应**:
```typescript
interface ConfirmResponse {
  success: boolean;
  advice_id: string;
  action: string;
  message: string;               // 用于前端 Toast 提示
  cost_impact_yuan?: number;     // ¥影响（修改时显示）
}
```

---

### GET `/api/v1/workforce/multi-store/labor-ranking`

**用途**: 多店人工成本率排名（总部视图）

**Query 参数**:
```typescript
{
  brand_id?: string;
  month?: string;   // YYYY-MM，默认当月
}
```

**响应 Schema**:
```typescript
interface MultiStoreLaborRankingResponse {
  month: string;
  brand_avg_rate_pct: number;
  stores: Array<{
    store_id: string;
    store_name: string;
    labor_cost_rate_pct: number;
    rank: number;
    vs_brand_avg_pct: number;    // 与品牌均值差值
    status: 'excellent' | 'normal' | 'warning' | 'critical';
  }>;
}
```

---

### GET `/api/v1/workforce/stores/{store_id}/labor-budget`

**用途**: 读取门店月度人工预算

**Query 参数**:
```typescript
{
  month?: string; // YYYY-MM，默认当月
}
```

**响应 Schema**:
```typescript
interface LaborBudget {
  store_id: string;
  month: string;
  target_labor_cost_rate: number;  // 目标成本率 %
  max_labor_cost_yuan: number;     // ¥最大人工成本
  daily_budget_yuan: number | null;
  alert_threshold_pct: number;     // 预警阈值 %
  is_active: boolean;
}
```

---

### PUT `/api/v1/workforce/stores/{store_id}/labor-budget`

**用途**: 更新/创建月度人工预算

**请求 Body**:
```typescript
interface LaborBudgetUpsertRequest {
  month: string;                      // YYYY-MM（必填）
  target_labor_cost_rate: number;     // 0-100（必填）
  max_labor_cost_yuan: number;        // ≥0（必填）
  daily_budget_yuan?: number;
  alert_threshold_pct?: number;       // 默认90
  is_active?: boolean;               // 默认true
}
```

---

### POST `/api/v1/workforce/stores/{store_id}/auto-schedule`

**用途**: 触发 AI 自动排班

**请求 Body**:
```typescript
interface AutoScheduleRequest {
  week_start: string;   // YYYY-MM-DD（周一）
}
```

**响应**:
```typescript
interface AutoScheduleResponse {
  store_id: string;
  week_start: string;
  schedules_created: number;
  estimated_labor_cost_yuan: number;
  within_budget: boolean;
  cost_vs_budget_pct: number;
}
```

---

## BFF 端点

### GET `/api/v1/bff/sm/{store_id}` — 店长首屏聚合

**用途**: 店长工作台首屏一次性加载（30s Redis缓存）

```typescript
interface SmBffResponse {
  store: StoreBasic;
  today_kpis: TodayKpis;
  urgency_list: UrgencyItem[];
  workforce_summary: {
    today_headcount: number;
    labor_cost_rate_pct: number;
    pending_advice_count: number;  // 待确认人力建议数
  };
  // ... 其他字段
}
```

### GET `/api/v1/bff/banquet/{store_id}` — 宴会管理首屏聚合

**用途**: 宴会管理首屏一次性加载（30s Redis缓存，`?refresh=true` 强制刷新）

```typescript
interface BanquetBffResponse {
  store_id: string;
  as_of: string;                   // ISO timestamp
  dashboard: {
    year: number; month: number;
    revenue_yuan: number;          // 本月宴会收入¥
    gross_profit_yuan: number;     // 毛利¥
    order_count: number;
    lead_count: number;
    conversion_rate_pct: number;
    hall_utilization_pct: number;
  } | null;
  stale_lead_count: number;        // 停滞线索总数
  stale_leads: Array<{             // 最多5条提醒
    lead_id: string;
    days_stale: number;
    stage: string;
    suggestion: string;            // 包含¥预算的提醒文本
  }>;
  upcoming_orders: Array<{         // 未来7天宴会
    id: string;
    banquet_date: string;
    banquet_type: string;
    people_count: number;
    order_status: string;
    total_amount_yuan: number;
  }>;
  hall_summary: { active_hall_count: number };
  _from_cache: boolean;
}
```

---

## 待补充接口（Claude 正在开发）

> 以下接口已全部实现，Codex 可直接对接

- ~~`GET /api/v1/workforce/stores/{store_id}/shift-fairness-detail` — 已实现（见下方）~~
- `POST /api/v1/workforce/employees/{employee_id}/preference` — 已存在于 `PUT /api/v1/employees/{employee_id}/preferences`（employees router）

### GET `/api/v1/workforce/stores/{store_id}/shift-fairness-detail`

```typescript
// Query: year?, month?
interface ShiftFairnessDetail {
  store_id: string;
  year: number;
  month: number;
  fairness_index: number;          // 0-100，越高越公平
  total_employees: number;
  distribution: {
    high_unfairness_count: number;   // unfavorable_ratio >= 0.5
    medium_unfairness_count: number; // 0.25 <= ratio < 0.5
    low_unfairness_count: number;    // ratio < 0.25
  };
  employee_stats: Array<{
    employee_id: string;
    total_shifts: number;
    unfavorable_shifts: number;
    unfavorable_ratio: number;      // 0-1，差班占比
  }>;
  consecutive_alerts: string[];    // 连续被分配差班的员工ID列表
}
```

### PATCH `/api/v1/banquet-agent/stores/{store_id}/leads/{lead_id}/stage`

```typescript
// Body:
interface LeadStageUpdateReq {
  stage: LeadStage;
  followup_content: string;
  next_followup_days?: number;    // 1-30，下次跟进天数
}
// Response:
interface LeadStageUpdateResp {
  lead_id: string;
  stage_before: LeadStage;
  new_stage: LeadStage;
  last_followup_at: string;
  next_followup_at: string | null;
}
```

---

## Banquet Agent（宴会管理 Phase 9）接口

> 路由前缀：`/api/v1/banquet-agent`
> Claude 已实现，Codex 据此构建前端

### 驾驶舱

**GET `/api/v1/banquet-agent/stores/{store_id}/dashboard`**
```typescript
// Query: month?: string (YYYY-MM)
interface BanquetDashboard {
  store_id: string;
  year: number;
  month: number;
  revenue_yuan: number;           // ¥本月宴会收入
  gross_profit_yuan: number;      // ¥毛利润
  order_count: number;
  lead_count: number;
  conversion_rate_pct: number;    // 转化率 %
  hall_utilization_pct: number;   // 档期利用率 %
  summary: string;                // AI生成的摘要文本
}
```

### 线索漏斗

**GET `/api/v1/banquet-agent/stores/{store_id}/leads`**
```typescript
// Query: stage?: LeadStage, owner_user_id?: string
type LeadStage = 'new'|'contacted'|'visit_scheduled'|'quoted'|'waiting_decision'|'deposit_pending'|'won'|'lost'
interface LeadListResponse { total: number; items: LeadItem[] }
interface LeadItem {
  id: string; banquet_type: string;
  expected_date: string | null; expected_people_count: number | null;
  expected_budget_yuan: number; current_stage: LeadStage;
  owner_user_id: string | null; last_followup_at: string | null;
}
```

**POST `/api/v1/banquet-agent/stores/{store_id}/leads`** — 创建线索

### 宴会订单

**GET `/api/v1/banquet-agent/stores/{store_id}/orders`**
```typescript
// Query: order_status?, date_from?, date_to?
type OrderStatus = 'draft'|'confirmed'|'preparing'|'in_progress'|'completed'|'settled'|'closed'|'cancelled'
interface OrderItem {
  id: string; banquet_type: string; banquet_date: string;
  people_count: number; table_count: number;
  order_status: OrderStatus; deposit_status: 'unpaid'|'partial'|'paid';
  total_amount_yuan: number; paid_yuan: number; balance_yuan: number;
}
```

**POST `/api/v1/banquet-agent/stores/{store_id}/orders/{order_id}/confirm`** — 确认订单（触发ExecutionAgent生成任务）

**POST `/api/v1/banquet-agent/stores/{store_id}/orders/{order_id}/payment`** — 收款登记

### Agent 接口（Codex 负责配套UI）

**GET `.../agent/followup-scan?dry_run=true`** — 停滞线索扫描（返回提醒文本列表）

**GET `.../agent/quote-recommend?people_count=50&budget_yuan=30000`** — 套餐推荐（含¥毛利）

**GET `.../agent/hall-recommend?target_date=2026-03-15&slot_name=dinner&people_count=50`** — 可用厅房推荐

**POST `.../orders/{id}/review`** — 宴会复盘草稿生成（含¥收入/利润分析）

### 宴会类型枚举
```typescript
type BanquetType = 'wedding'|'birthday'|'business'|'full_moon'|'graduation'|'anniversary'|'other'
type BanquetHallType = 'main_hall'|'vip_room'|'garden'|'outdoor'
```

---

## Dish R&D Agent（菜品研发 Phase 10）接口

> 路由前缀：`/api/v1/dish-rd`

### 菜品主档

**GET `/api/v1/dish-rd/brands/{brand_id}/dishes`**
```typescript
// Query: status?, dish_type?, keyword?, page?, page_size?
interface DishListResponse {
  total: number; page: number; page_size: number;
  items: DishSummary[];
}
interface DishSummary {
  dish_id: string; dish_code: string; dish_name: string;
  dish_type: DishType; status: DishStatus; lifecycle_stage: string;
  positioning_type: string | null;
  target_price_yuan: number | null;
  flavor_tags: string[];
  created_at: string;
}
type DishStatus = 'draft'|'ideation'|'in_dev'|'sampling'|'pilot_pending'|'piloting'|'launch_ready'|'launched'|'optimizing'|'discontinued'|'archived'
type DishType = 'new'|'upgrade'|'seasonal'|'regional'|'banquet'|'delivery'
```

**POST `/api/v1/dish-rd/brands/{brand_id}/dishes`** — 创建菜品

**GET `/api/v1/dish-rd/brands/{brand_id}/dishes/{dish_id}`** — 菜品详情（含成本摘要+试点摘要）

**PATCH `/api/v1/dish-rd/brands/{brand_id}/dishes/{dish_id}`** — 更新菜品

### 配方与 BOM

**POST `.../dishes/{dish_id}/recipe-versions`** — 创建配方版本

**POST `.../recipe-versions/{version_id}/items`** — 批量添加 BOM 行

**GET `.../recipe-versions/{version_id}/items`** — 查询 BOM 明细

### 试点管理

**POST `.../dishes/{dish_id}/pilot-tests`** — 创建试点

**POST `.../pilot-tests/{pilot_id}/decision`** — 记录试点决策（go/revise/stop）

**GET `.../dishes/{dish_id}/pilot-tests`** — 查询试点列表

### 上市管理

**POST `.../dishes/{dish_id}/launch-projects`** — 创建上市项目（自动把菜品状态推进到 launch_ready）

### 反馈 & 复盘

**POST `.../dishes/{dish_id}/feedbacks`** — 录入反馈

**GET `.../dishes/{dish_id}/feedbacks`** — 查询反馈列表

**GET `.../dishes/{dish_id}/retrospective-reports`** — 查询复盘报告

### Agent 接口

**POST `.../dishes/{dish_id}/agent/cost-sim?recipe_version_id=`** — 成本仿真
```typescript
interface CostSimResult {
  total_cost: number;               // ¥总成本
  suggested_price_yuan: number;     // ¥建议售价
  margin_rate: number;              // 毛利率
  margin_amount_yuan: number;       // ¥毛利额
  price_scenarios: Array<{ target_margin_rate: number; suggested_price_yuan: number; margin_amount_yuan: number }>;
  stress_tests: Array<{ price_change_pct: number; stressed_margin_rate: number; margin_delta: number }>;
  item_details: BomItemCost[];
}
```

**GET `.../dishes/{dish_id}/agent/pilot-recommend?top_n=5`** — 试点门店推荐

**POST `.../dishes/{dish_id}/agent/review?period=30d`** — 复盘优化（lifecycle_assessment + optimization_suggestions）

**GET `.../dishes/{dish_id}/agent/launch-readiness`** — 发布就绪检查（checklist + missing_items）

**GET `/api/v1/dish-rd/brands/{brand_id}/agent/risk-scan`** — 风险全扫描（risk_count + high_risks + medium_risks）

**GET `/api/v1/dish-rd/brands/{brand_id}/dashboard`** — 菜品研发驾驶舱
