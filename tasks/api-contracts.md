# tasks/api-contracts.md — 接口契约（Claude ↔ Codex 握手文件）

> Claude 新增/修改后端接口时在此更新。
> Codex 根据此文件生成前端 API Client，**禁止自行推断接口**。

---

## 最近更新

| 日期 | 变更 | 影响 |
|------|------|------|
| 2026-03-08 | 整理 Phase 8 workforce 全部接口 | 前端 WorkforcePage 相关 |

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

---

## 待补充接口（Claude 正在开发）

> 以下接口尚未实现，Codex 先用 mock 数据占位，等Claude更新此文件

- `GET /api/v1/workforce/stores/{store_id}/shift-fairness-detail` — 班次公平性详细分布图数据
- `POST /api/v1/workforce/employees/{employee_id}/preference` — 员工班次偏好更新

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
