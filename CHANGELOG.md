# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [2.4.0] — 2026-03-12

### AgentCollaborationOptimizer — 多Agent协同总线（PPT最终模块）

#### Backend (`apps/api-gateway`)

- **`src/models/agent_collab.py`**：3张表（AgentConflict / GlobalOptimizationLog / AgentCollabSnapshot）+ 4 Enum
- **`alembic/versions/z43_agent_collab_tables.py`**：Alembic migration（down_revision=z42）
- **`src/services/agent_collab_optimizer.py`**：核心协同逻辑（冲突检测+仲裁+去重+抑制+排序），40个纯函数单元测试全部通过
- **`src/api/agent_collab.py`**：4个端点（/optimize / /conflicts / /conflicts/{id}/escalate / /dashboard BFF）

#### Frontend (`apps/web`)

- **`src/pages/AgentCollabPage.tsx`**：协同总线驾驶舱（冲突统计KPI + 协同原理说明 + 近期冲突列表）

#### 至此PPT 9-Agent生态系统全部完成

```
增长层: BusinessIntelAgent + MarketingAgent + BanquetAgent
运营层: OpsFlowAgent + PeopleAgent + DishRdAgent
底座层: ComplianceAgent + OpsAgent + FctAgent
基础设施: AgentCollaborationOptimizer (多Agent协同总线)
量化追踪: Agent OKR 看板
```

---

## [2.3.0] — 2026-03-12

### Phase 13 — OpsFlowAgent 三体合并（出品链联动）

#### Backend (`apps/api-gateway`)

- **`src/models/ops_flow_agent.py`**：7张表 + 7 Enum（OpsChainEvent / OpsChainLinkage / OpsOrderAnomaly / OpsInventoryAlert / OpsQualityRecord / OpsFlowDecision / OpsFlowAgentLog）
- **`alembic/versions/z41_ops_flow_agent_tables.py`**：Alembic migration（down_revision=z40）
- **`src/api/ops_flow_agent.py`**：15个端点（chain-events / order-anomaly / inventory / quality / decisions / dashboard BFF）
- **`src/main.py`**：注册 ops_flow_agent + agent_okr 两个新 router

#### Agent Package (`packages/agents/ops_flow`)

- **`src/agent.py`**：5个 Agent 类（ChainAlertAgent / OrderAnomalyAgent / InventoryIntelAgent / QualityInspectionAgent / OpsOptimizeAgent）+ 10个纯函数
- 核心创新：CHAIN_LINKAGE_RULES 实现「1事件 → 3层级联响应」
- **`tests/test_agent.py`**：65个单元测试全部通过（sys.modules 注入模式，无真实 DB）

#### Frontend (`apps/web`)

- **`src/pages/OpsFlowAgentPage.tsx`** + `OpsFlowAgentPage.module.css`：驾驶舱/联动事件/库存预警/菜品质检/优化决策 5Tab

### Agent OKR 看板

#### Backend (`apps/api-gateway`)

- **`src/models/agent_okr.py`**：AgentResponseLog + AgentOKRSnapshot，追踪 Per-Agent OKR 指标（采纳率/预测误差/响应时效）
- **`alembic/versions/z42_agent_okr_tables.py`**：Alembic migration（down_revision=z41）
- **`src/services/agent_okr_service.py`**：OKR_TARGETS 来自 PPT Slide 8，含纯函数检查体系
- **`src/api/agent_okr.py`**：log/adopt/verify/summary 4个端点
- **`tests/test_agent_okr_service.py`**：34个单元测试全部通过

#### Frontend (`apps/web`)

- **`src/pages/AgentOKRPage.tsx`**：OKR达成看板（AdoptionBar进度条+目标线，OKRBadge ✅/❌/⏳，近7/14/30天切换）

### P2 测试基础设施修复

- `src/api/banquet_agent.py`、`supplier_agent.py`、`dish_rd_agent.py`：修复 `get_current_user` 导入路径（`security` → `dependencies`）
- `src/api/agent_okr.py`、`ops_flow_agent.py`、`people_agent.py`、`business_intel.py`：修复 `from src.db import get_db` → `from src.core.database import get_db`
- `tests/test_realtime_notifications.py`：修复 `mock_user` fixture 返回 function 对象 bug
- 测试结果：**88 passed**（修复前 5 个文件收集错误，0 tests run）

---

## [2.1.0] — 2026-03-09

### Banquet Agent — Phase 2

#### Frontend (`apps/web`)

- **SM 线索列表页** (`/sm/banquet-leads`)：阶段 Chip 过滤（全部/初步询价/意向确认/锁台/已签约）、三态列表（加载/空/数据）、推进阶段 ZModal（PATCH）
- **SM 订单列表页** (`/sm/banquet-orders`)：状态 Chip 过滤、订单列表、登记付款 ZModal（仅 confirmed 行，POST）
- **SM 今日宴会页** 快捷操作由 `alert()` 占位替换为 `useNavigate()` 真实路由跳转
- **HQ 宴会页** 重构为 ZTabs 三标签：
  - **仪表盘**（原有内容保留）：月份选择 + 4 KPI + 漏斗 + 订单表
  - **销售管道**：7 阶段手风琴，数据来自 `/api/v1/banquet-lifecycle/{id}/pipeline`
  - **销控日历**：月度 7 列 CSS Grid，吉日金边 / 满负荷红底，数据来自 `/api/v1/banquet-lifecycle/{id}/availability/{year}/{month}`
- 新增路由：`/sm/banquet-leads`、`/sm/banquet-orders`（App.tsx lazy import）

#### Backend (`apps/api-gateway`)

- **`GET .../leads`**：增加 `stage` 过滤参数；响应补全 `banquet_id`、`stage`、`stage_label`（中文）、`contact_name`、`budget_yuan` 字段；`selectinload` 预加载 customer 关联
- **`PATCH .../leads/{id}/stage`**：兼容 `followup_content` / `followup_note` 双字段名
- **`GET .../orders`**：增加 `status` 过滤参数；响应补全 `banquet_id`、`status`、`amount_yuan` 字段
- **`POST .../orders/{id}/payment`**：`payment_type` 默认值 `balance`；正确处理 `deposit_fen` 比较逻辑
- **`GET .../pipeline`**：将服务层返回的 `stages` dict 转换为前端所需数组格式，附加 `stage_label`（中文）、`leads` 字段映射，排除 `cancelled` 阶段
- **`GET .../availability/{year}/{month}`**：每日数据补充 `capacity` 字段；响应顶层增加 `days` 别名
- **仪表盘**：兼容 `?year=&month=`（整数）和 `?month=YYYY-MM`（字符串）两种参数格式；响应补充 `gross_margin_pct`、`conversion_rate`、`room_utilization` 字段

#### Tests (`apps/api-gateway/tests`)

- `test_banquet_agent_phase2.py`：27 个单元测试（leads / lead stage / orders / payment / dashboard 共 5 个 class）
- `test_banquet_lifecycle_api_phase2.py`：13 个单元测试（pipeline / availability calendar 共 2 个 class）
- 全部 mock DB，不依赖真实数据库

---

## [2.0.0] — 2026-02-xx

### 智链OS — 10 大 MVP 功能交付

- Decision Priority Engine（Top3 决策聚合）
- Financial Impact Calculator（财务影响计算）
- Waste Guard Service（浪费 Top5 + ¥ 归因）
- Decision Push Service（4 时间点微信推送）
- Food Cost Service（BOM 成本分析）
- FCT Service（Finance / Tax / Cash flow）
- Edge Node Service（离线收入 / 库存查询）
- Case Story Generator（日/周/月故事）
- Scenario Matcher（7 场景分类器）
- Monthly Report Service（月报 JSON + HTML）

---

[Unreleased]: https://github.com/example/zhilian-os/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/example/zhilian-os/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/example/zhilian-os/releases/tag/v2.0.0
