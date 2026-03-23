# 任务清单

> 格式：- [ ] 待办 / - [x] 完成
> 每次会话开始时更新，完成后在底部添加评论。

---

## 规划未完成任务 — 五大类全部完成（2026-03-12）

### 一：Phase 4 测试补全
- [x] FederatedLearningService：加权聚合 7 测试 + 质量过滤 6 测试 + DataIsolationManager 3 测试（35→passed）
- [x] RecommendationEngine：评分公式详尽验证 8 测试 + 定价策略 6 测试 + 推荐理由 3 测试（34→passed）
- [x] Phase 4 集成测试 `test_phase4_integration.py`：FL E2E/推荐E2E/Agent协同E2E/A/B框架（15 passed）

### 二：Codex 前端任务
- [x] WorkforcePage 员工健康 Tab（已由前期开发完成，含风险排名+公平性图+KPI）
- [x] SM Home 人力建议卡（已实现 confirm/modify/reject 完整流程）
- [x] HQ Home 多店人工成本排名（已实现含品牌均值对比）

### 三：Phase 5 生态扩展
- [x] Open API 平台（service + API + 前端页面已实现）
- [x] 行业垂直解决方案（service + API + IndustrySolutionsPage 已实现）
- [x] 供应链集成（service + API 已实现）
- [x] 国际化（service + API + I18nPage 已实现）

### 四：FCT 长期能力
- [x] 数据模型 `src/models/fct_advanced.py`：8张表（银企直连3+多实体合并3+税务申报2）
- [x] Alembic迁移 `z44_fct_advanced_tables.py`（down_revision=z43）
- [x] 服务 `src/services/fct_advanced_service.py`：银行流水匹配+多实体合并+税务自动提取（全纯函数）
- [x] 40个单元测试全部通过（`tests/test_fct_advanced_service.py`）
- [x] API路由 `/api/v1/fct-advanced`（8个端点 + 驾驶舱 BFF）
- [x] 前端页面 `FctAdvancedPage.tsx`（驾驶舱/银企直连/多实体合并/税务申报 4Tab）

### 五：Tech Debt
- [x] sys.path 污染：创建 `packages/agents/conftest.py` 共享 conftest（自动注入 agent root + core path）
- [x] sync Alembic vs async：已由 `alembic/env.py` L41-43 处理（asyncpg→psycopg2 自动转换）
- [x] Embedding 模型降级监控：`src/services/embedding_monitor_service.py`（相似度/空结果率/延迟P99/健康分/降级检测）
- [x] 29个单元测试全部通过（`tests/test_embedding_monitor_service.py`）

---

## AgentCollaborationOptimizer（多Agent协同总线，2026-03-12）

> PPT战略：基础设施层 AgentCollabOptimizer — 冲突检测·优先级仲裁·全局优化

### 全部完成（2026-03-12）

- [x] 数据模型 `src/models/agent_collab.py`：3张表（AgentConflict/GlobalOptimizationLog/AgentCollabSnapshot）+ 4 Enum
- [x] Alembic迁移 `z43_agent_collab_tables.py`（down_revision=z42）
- [x] 核心服务 `src/services/agent_collab_optimizer.py`：冲突检测/优先级仲裁/字符2-gram去重/低影响抑制/¥×置信度排序
- [x] 40个单元测试全部通过（`tests/test_agent_collab_optimizer.py`）
- [x] API路由 `/api/v1/agent-collab`（4个端点 + 驾驶舱 BFF）`src/api/agent_collab.py`
- [x] 前端页面 `AgentCollabPage.tsx`（KPI总览 + 协同原理 + 近期冲突列表）

**PPT 9-Agent生态系统至此全部完成** ✅

---

## Phase 13 — OpsFlowAgent 三体合并（2026-03-12）

> PPT战略分析：OrderAgent + InventoryAgent + QualityAgent → OpsFlowAgent（出品链联动）
> 核心能力：1个事件 → 3层级联响应（ChainAlert + OrderAnomaly + InventoryAlert + QualityRecord）

### 全部完成（2026-03-12）

- [x] 数据模型（7张表 + 7 Enum）`src/models/ops_flow_agent.py`
- [x] Alembic迁移 `z41_ops_flow_agent_tables.py`（down_revision=z40）
- [x] 5个 Agent：ChainAlertAgent/OrderAnomalyAgent/InventoryIntelAgent/QualityInspectionAgent/OpsOptimizeAgent
- [x] 65个单元测试全部通过（`packages/agents/ops_flow/tests/test_agent.py`）
- [x] API路由 `/api/v1/ops-flow`（15个端点 + 驾驶舱 BFF）`src/api/ops_flow_agent.py`
- [x] 前端页面 `OpsFlowAgentPage.tsx`（驾驶舱/联动事件/库存预警/菜品质检/优化决策5Tab）
- [x] `src/main.py` 注册 ops_flow_agent router

### Agent OKR 看板（2026-03-12）

- [x] OKR数据模型 `src/models/agent_okr.py`（AgentResponseLog + AgentOKRSnapshot）
- [x] Alembic迁移 `z42_agent_okr_tables.py`（down_revision=z41）
- [x] OKR服务 `src/services/agent_okr_service.py`（PPT Slide 8 OKR目标：采纳率/预测误差/响应时效）
- [x] 34个单元测试全部通过（`tests/test_agent_okr_service.py`）
- [x] API路由 `/api/v1/agent-okr`（log/adopt/verify/summary）`src/api/agent_okr.py`
- [x] 前端页面 `AgentOKRPage.tsx`（OKR达成看板，AdoptionBar + OKRBadge）
- [x] `src/main.py` 注册 agent_okr router

### P2 测试修复（2026-03-12）

- [x] `src/api/banquet_agent.py`：修复 `get_current_user` 错误导入路径（security → dependencies）
- [x] `src/api/supplier_agent.py`：同上
- [x] `src/api/dish_rd_agent.py`：同上
- [x] `src/api/agent_okr.py`、`ops_flow_agent.py`、`people_agent.py`、`business_intel.py`：修复 `src.db` → `src.core.database` 导入
- [x] `tests/test_realtime_notifications.py`：修复 `mock_user` fixture 返回 function 而非 user 对象的 bug
- [x] 整体测试结果：88 passed（vs 修复前 0 tests collected）

---

## Phase 11 — 供应商管理 Agent（Supplier Intelligence）

> 北极星：「乐才告诉你买了什么；屯象OS告诉你该从谁买、多少钱、有没有风险。」

### 全部完成（2026-03-11）

- [x] 数据模型（L1-L5，11张表）`src/models/supplier_agent.py`
- [x] Alembic迁移 `z37_supplier_agent_tables.py`
- [x] 5个 Agent：PriceComparisonAgent/SupplierRatingAgent/AutoSourcingAgent/ContractRiskAgent/SupplyChainRiskAgent
- [x] API路由 `/api/v1/supplier-agent`（25个端点 + 驾驶舱）
- [x] 51个单元测试全部通过
- [x] 前端页面 `SupplierAgentPage.tsx`（驾驶舱/档案/合同/预警/寻源5Tab）
- [x] pnpm build ✅ 零 TS 错误

---

## 进行中

### Sprint 1 — CDP地基 + 品智POS打通（90天计划 W1-2）

> CDP宪法：1.任何消费者记录必须经resolve()获取consumer_id 2.consumer_id不可修改只能merge() 3.所有渠道消费行为必须归因到consumer_id

#### S1.1-S1.7: CDP 核心模型+服务+POS改造

- [x] `src/models/consumer_identity.py` — ConsumerIdentity 统一消费者身份（primary_phone业务键，聚合profile，RFM快照，merge支持）
- [x] `src/models/consumer_id_mapping.py` — ConsumerIdMapping 11种外部ID映射（PHONE/WECHAT_OPENID/POS_MEMBER_ID/MEITUAN_UID等）
- [x] `src/services/identity_resolution_service.py` — IdentityResolutionService: resolve()/merge()/backfill_orders()/refresh_profile()/get_stats()
- [x] `src/services/cdp_sync_service.py` — CDPSyncService: sync_store_orders()/sync_all_stores()/get_fill_rate()
- [x] `src/api/cdp.py` — 8个API端点: resolve/consumer/{id}/lookup/merge/backfill/refresh/stats/fill-rate
- [x] Order/Reservation/Queue 三表加 consumer_id 字段（UUID, nullable, indexed）
- [x] Alembic迁移 `z47_cdp_consumer_identity.py`（2表+3字段+索引）
- [x] `models/__init__.py` 注册 ConsumerIdentity + ConsumerIdMapping + IdType
- [x] `main.py` 注册 CDP router
- [x] `alembic/env.py` 注册新模型
- [x] 品智POS celery_tasks INSERT 增加 customer_phone/customer_name（从 vipMobile/vipName 提取）
- [x] adapter_integration_service _convert_pinzhi_order 增加 customer_phone/pos_member_id
- [x] Celery Beat `cdp-sync-consumer-ids`（02:30，紧跟POS拉取后自动回填）
- [x] 19个单元测试全部通过（`tests/test_identity_resolution_service.py`）

#### S1 待完成

- [x] 品智订单全量同步回填 — `cdp_monitor_service.run_full_backfill()` 4步管道 + Celery异步任务
- [x] consumer_id 填充率验证（KPI: ≥80%）— `compute_kpi_summary()` + `classify_fill_rate_health()`

#### S2.1-S2.6: CDP 打通私域 + 企微通道 + RFM 重算

- [x] PrivateDomainMember 加 consumer_id + r_score/f_score/m_score 字段
- [x] `src/services/cdp_rfm_service.py` — CDPRFMService: recalculate_all()/compute_deviation()/backfill_members()
  - 纯函数：score_recency/score_frequency/score_monetary/classify_rfm_level/compute_risk_score
  - R评分：≤7天=5, ≤14天=4, ≤30天=3, ≤60天=2, >60天=1
  - RFM→S1-S5：sum≥13=S1, ≥10=S2, ≥7=S3, ≥4=S4, <4=S5
  - 风险分：R权重60% + F/M各20%
- [x] `src/services/cdp_wechat_channel.py` — CDPWeChatChannel: send_to_consumer()/batch_send_by_rfm()/batch_send_by_tags()/get_channel_stats()
- [x] CDP API 扩展（6个新端点）：rfm/recalculate, rfm/deviation, backfill/members, wechat/batch-send, wechat/tag-send, wechat/channel-stats
- [x] Alembic迁移 `z48_cdp_private_domain_link.py`（consumer_id + r/f/m_score 4字段）
- [x] Celery Beat `cdp-rfm-recalculate`（03:00，02:30 consumer_id 回填后）
- [x] celery_tasks 新增 `cdp_rfm_recalculate` 任务（回填member→重算RFM→偏差校验）
- [x] 49个单元测试全部通过（Sprint 1: 19 + Sprint 2: 30）

#### S2 待完成

- [x] 生产环境执行回填 — `POST /api/v1/cdp/monitor/full-backfill` + Celery `cdp_full_backfill` 异步任务
- [x] RFM 偏差验证（KPI: < 5%）— `compute_kpi_summary()` deviation_kpi 校验
- [x] 前端 CDP 监控面板 — `CDPMonitorPage.tsx`（KPI横幅+填充率表+RFM柱状图+偏差卡+全量回填按钮）
- [x] `src/services/cdp_monitor_service.py` — 纯函数 + Dashboard聚合 + 4步回填管道
- [x] `src/api/cdp_monitor.py` — 4个端点 + Celery异步回填
- [x] `tests/test_cdp_monitor_service.py` — 27个测试全部通过

---

## Phase 7 Month 1 — L5 行动层补全（2026-03-08）

- [x] `celery_app.py` 注册 `nightly-action-dispatch` Beat（04:30，环境变量 L5_DISPATCH_HOUR/MINUTE 可覆盖）
- [x] `wechat_action_fsm.py` 修复 `_upgrade_priority` 方向 bug（P3→P2→P1→P0）
- [x] 新建 `tests/test_action_dispatch_service.py`：13个测试（P1/P2/P3/OK 四路 + 幂等 + 降级 + outcome + stats）
- [x] 新建 `tests/test_wechat_action_fsm.py`：24个测试（生命周期 + 升级 + 超时判断 + webhook验签 + 优先级链）
- [x] 新建 `apps/web/src/pages/ActionPlansPage.tsx`：L5 行动计划管理页面（KPI卡 + 过滤 + 详情Drawer + 结果登记Modal）
- [x] `App.tsx`：新增 `/action-plans` 路由（store_manager 权限）
- [x] `MainLayout.tsx`：新增「L5 行动计划」导航入口

---

## Phase 8 — 人力管理 Agent（Workforce Intelligence）

> 来源：屯象OS_人力管理Agent_产品设计方案.txt + 屯象OS人力管理Agent架构.md（2026-03-08）
> 北极星：「乐才告诉你昨天用了多少人工成本；屯象OS告诉你明天少排1个人能多赚多少钱。」
> 差异化定位：不做第二个乐才（合规管理工具），做连锁餐饮的**人力经营决策系统**

---

### 设计原则（来自产品文档）

1. **经营决策 > 合规管理**：每个输出必须连接到¥影响（Rule 6）
2. **主动推送 > 被动报表**：每日07:00企微推送「今日人力建议」，店长一键确认
3. **需求拉动排班**：客流预测 → 人力需求 → 排班建议（Legion 理念）
4. **可解释性**：每个建议附3条推理链节点（置信度 + 依据 + 预期¥影响）
5. **渐进式自动化**：Phase 1建议+手动执行 → Phase 2建议+一键确认 → Phase 3自动排班

---

### 架构决策

- **不新建 package agent**：直接在 `api-gateway/src/services/` 中扩展，复用现有 DB/Redis/Celery 基础设施
- **与现有 schedule agent 的关系**：`packages/agents/schedule/` 继续负责班次生成逻辑；新服务在其之上添加「经营决策层」（客流预测→人力需求→成本优化）
- **新数据模型**：独立文件 `src/models/workforce.py`（LaborBudget / StaffingPattern / EmployeePreference / TurnoverEvent / ShiftFairnessScore）
- **前端角色分离**：店长工作台（今日建议+确认）/ 运营负责人（跨店对标）/ CEO驾驶舱（人力成本趋势）

---

### Phase 8 Month 1 — MVP 人力建议闭环

> 目标：用数据驱动排班决策，替代店长拍脑袋。可用徐记海鲜1-2家门店验证。
> 验证指标：排班建议采纳率>60% / 人工成本率降低2-3pp / 店长满意度NPS>7

#### Step 1：数据模型 + Alembic Migration

- [x] 新建 `src/models/workforce.py`：6张表（LaborDemandForecast / LaborCostSnapshot / StaffingAdvice / StaffingAdviceConfirmation / StoreLaborBudget / LaborCostRanking）+ 5个 Enum
- [x] 新建 Alembic migration `wf01_workforce_tables.py`（6张表 + 5种 PG Enum，down_revision=z34）
- [x] 在 `src/models/__init__.py` 注册新模型（11个符号）

#### Step 2：客流预测 Service（Agent 1 + 2 核心）

- [x] 新建 `src/services/labor_demand_service.py`：`LaborDemandService`（三档降级：rule_based/statistical/weighted；含 CN 节假日表；`compute_position_requirements` + `get_holiday_weight` 纯函数；离线 db=None 自动降级）

#### Step 3：人工成本监控 Service（Agent 5）

- [x] 新建 `src/services/labor_cost_service.py`：`LaborCostService`（快照计算+持久化 / 成本率趋势 / 跨店排名；`compute_labor_cost_rate` + `compute_variance` + `compute_overtime_cost` 纯函数；4级成本来源降级；`_build_rank_insight` 含¥文案）

#### Step 4：今日人力建议推送（Rippling 主动推送理念）

- [x] 新建 `src/services/workforce_push_service.py`：`WorkforcePushService`
  - 纯函数：`_format_staffing_recommendation(forecast, staffing, cost_summary) → str`：
    - 格式：明日客流预测N人 / 建议排班X人（厨房N/前厅N/收银N）/ 较昨日同比±N / 预计节省¥
    - 附 3条推理链（如：「预计客流+20%，历史周六均值N人，节假日系数×1.2」）
    - 含一键确认按钮文案
  - `push_daily_staffing_advice(store_id, db)`：组装建议 + 调用 WeChatService 推送 → 记录推送日志
  - `push_labor_cost_alert(store_id, db)`：人工成本率超 warning 阈值时触发（Rule 7 合规）

- [x] `src/core/celery_tasks.py`：新增 `push_daily_workforce_advice` 任务（遍历活跃门店）
- [x] `src/core/celery_app.py`：Beat 新增 `daily-workforce-advice`（07:00，L8_WORKFORCE_HOUR/MINUTE 可覆盖，priority=9）

#### Step 5：API 端点

- [x] 新建 `src/api/workforce.py`：Router `/api/v1/workforce`
  - `GET /stores/{store_id}/labor-forecast?date=` → 明日客流预测 + 建议人数
  - `GET /stores/{store_id}/labor-cost?date=` → 人工成本日报（实际/建议/节省¥）
  - `GET /stores/{store_id}/labor-efficiency?start_date=&end_date=` → 人效趋势
  - `POST /stores/{store_id}/staffing-advice/confirm` → 店长确认排班建议（记录采纳行为）
  - `GET /multi-store/labor-ranking?month=` → 跨店人工成本率排名
  - `GET /stores/{store_id}/labor-budget` → 读取月度人工预算
  - `PUT /stores/{store_id}/labor-budget` → 更新月度人工预算（store_manager 权限）
- [x] `src/main.py`：注册 workforce router

#### Step 6：前端页面（店长工作台）

- [x] 新建 `apps/web/src/pages/WorkforcePage.tsx`：人力管理主页面
  - **KPI 卡片行**（4个）：今日建议人数 / 当前实际出勤 / 本月人工成本率% / 本月节省¥
  - **今日人力建议卡片**（核心 UX）：
    - 客流预测数字 + 置信度 Badge
    - 岗位建议表：厨房/前厅/收银各岗位建议人数 + 与昨日对比
    - 3条推理链展示（可折叠）
    - 「确认排班建议」按钮（一键确认，发POST记录采纳）
    - 「修改并确认」按钮（内联编辑人数后确认）
  - **人工成本趋势图**：近30天人工成本率折线 + 目标线 + 周均值柱状图（ReactECharts）
  - **本月与建议对比**：实际出勤人数 vs 建议人数折线对比（高出建议时标红）
- [x] 新建 `apps/web/src/pages/WorkforcePage.module.css`
- [x] `apps/web/src/App.tsx`：新增 `/workforce` 路由（store_manager 权限）
- [x] `apps/web/src/layouts/MainLayout.tsx`：新增「人力管理」导航入口（TeamOutlined，运营管理分组）

#### Step 7：测试

- [x] 新建 `tests/test_labor_demand_service.py`：≥16个测试
  - 纯函数：星期系数×3 / 节假日系数×3 / 天气系数×2
  - forecast_customer_flow：正常/无历史数据/节假日
  - compute_staffing_needs：正常/人效比缺失降级
  - get_labor_efficiency：单店/多日
- [x] 新建 `tests/test_labor_cost_service.py`：≥12个测试
  - 纯函数：cost_rate×3 / classify_status×3 / compute_saving×2
  - get_store_labor_summary：正常/无预算数据
  - get_multi_store_labor_ranking：多店排序
- [x] 新建 `tests/test_workforce_push_service.py`：≥10个测试
  - _format_staffing_recommendation：格式合规（含¥/置信度/推理链）
  - push_daily_staffing_advice：正常/企微失败降级
  - push_labor_cost_alert：超阈值触发/未超阈值不推送
- [x] 新建 `tests/integration/test_workforce_pipeline.py`：≥15个测试
  - 客流预测→人力需求→推送全链路
  - 采纳行为记录闭环
  - 跨店排名结构验证

---

### Phase 8 Month 2 — 双向闭环（员工侧 + 流失预测）

> 核心目标：将员工纳入系统闭环，形成「系统-店长-员工」三方协同

- [x] 员工偏好管理 API（CRUD EmployeePreference）
- [x] 换班申请流（申请→技能检查→店长审批→企微通知）
- [x] `src/services/shift_fairness_service.py`：班次公平性评分
  - 统计每员工月均差班（深夜/早班）分配比例
  - 公平性指数计算（基尼系数思路）
  - 异常员工自动预警（连续3周分配最差班次）
- [x] `src/services/turnover_prediction_service.py`：员工流失风险预测
  - 特征：考勤异常次数 + 班次公平性得分 + 连续工作天数 + 工资波动率
  - 输出：90天内离职风险分（0-1）+ 主要风险因子
  - 高风险（>0.7）触发企微提醒店长介入
  - 离职成本估算（Rule 6：月薪×50% = 替换成本¥）
- [x] 前端：WorkforcePage 新增「员工健康」Tab（流失风险排名 + 班次公平性分布）
- [x] 测试：≥20个

---

### Phase 8 Month 3 — 行业基准 + AI 排班

> 核心目标：用多客户数据积累行业基准，形成数据网络效应壁垒

- [x] `src/services/labor_benchmark_service.py`：行业基准数据库
  - 湖南中式餐饮人效基准（按门店面积/座位数分档）
  - 同类型门店人工成本率基准区间
  - 跨客户数据脱敏聚合（联邦学习模式）
- [x] 客流预测精度迭代：从±15% → ±8%（积累历史数据后加入门店级微事件特征）
- [x] 自动排班 Agent：从「建议+手动确认」→「自动生成+异常提醒」
  - 集成 packages/agents/schedule/ 的班次生成能力
  - 增加人工成本约束：排班方案在 LaborBudget 硬约束内
- [x] `StaffingPattern` 模板库：从历史最优排班中学习，快速应用到相似日期

---

### 新增数据对象与关系（产品文档第七章补充）

```
新增对象
LaborBudget     门店月度人工预算（排班决策的硬约束）
StaffingPattern 历史最优排班模式模板库
EmployeePreference 员工期望班次/不可用时段
TurnoverEvent   离职事件标注（训练留存预测模型）
ShiftFairnessScore 员工月度班次公平性量化分
LaborDemandForecast 客流预测结果（持久化供回测）

新增关系语义
CustomerFlow → LaborDemand   （需求拉动供给，Legion 理念）
TurnoverEvent → PredictionModel  （每次真实离职更新模型权重）
Store → LaborBudget          （预算作为排班的硬约束）
Employee → ShiftFairnessScore （员工级公平性追踪）
```

---



> 来源：屯象OS产品开发计划明细v2（融合Toast建议）2026-03-04
> North Star：续费率≥95% | 客户成本率降低2个点 | 客户ROI≥10x

### P0 — 本周（Week 1）
- [x] Alembic 迁移整理：合并所有 merge heads 为线性链（`alembic history` 确认无分叉）
- [x] 前端裁剪 100→10 MVP页面（其余归档至 apps/web/src/pages/archive/）
- [x] API 端点标注 MVP/非MVP（125个端点中 MVP 端点 < 30个，已建 `src/api/_mvp_tags.py`）
- [x] 新建 `src/services/decision_priority_engine.py`（从各 Agent 建议聚合 Top3，含¥影响分）
- [x] 新建 `src/services/financial_impact_calculator.py`（每条建议附¥预期收益和¥成本）

### P0 — 第2周（Week 2-3）
- [x] 天财商龙适配器：从骨架到可拉取真实订单数据（门店/菜品/订单/库存4个核心API）
- [x] FCT ¥化改造：`fct_service.py` 每个损耗点输出¥金额（`loss_amount_yuan` 字段）
- [x] 新建 `src/services/waste_guard_service.py`：损耗Top5按¥金额排序+归因

### P0 — 第3-4周（Week 3-4）
- [x] 企微决策型推送模板重写：卡片格式含¥+置信度+一键操作按钮
- [x] 推送4时间点调度：08:00晨推 / 12:00异常推 / 17:30战前 / 20:30晚推
- [x] 一键审批回调：企微审批→系统状态更新→48h效果反馈
- [x] 离线查询能力提前启用：`edge_node_service.py` 支持断网查营业额/库存
- [x] 端到端集成测试：POS→FCT→推送→审批全链路，通过率>90%（tests/integration/test_e2e_pos_fct_push_approval.py，6段33个测试）

### P1 — 月2-3
- [x] 决策优先级引擎与现有 Agent 建议系统对接，老板每天收到3个决策
- [x] 新建 `src/services/scenario_matcher.py`：识别经营场景+检索历史相似案例
- [x] 成本率趋势可视化（前端 `ProfitDashboard.tsx`）
- [x] 月度经营报告 PDF（含案例叙事：成本率变化+损耗减少¥+关键决策回顾）
- [x] 新建 `src/services/case_story_generator.py`：自动聚合案例数据（日/周/月维度）

### 10个 MVP 功能清单（唯一允许开发的功能范围）
1. POS数据自动采集（天财商龙）
2. 每日利润快报（含¥金额）
3. 损耗Top5排名（含¥归因）
4. 决策型企微推送（4时间点）
5. 一键审批采购建议
6. BOM配方管理（出纳录入）
7. 成本率趋势图
8. 异常告警推送（阈值可配置）
9. 月度经营报告（PDF）
10. 离线基础查询（断网可用）

---

## Sprint v2.1 — 从"工具"到"主动外脑"

> 来源：屯象OS架构升级深度分析 + 三大设计假设重构方案（2026-03-05）
> 目标：系统主动找老板，老板30秒读懂生意状态
> 原则：在现有代码上叠加能力层，不重写，不扩张 MVP 范围

### ① NarrativeEngine — 经营故事叙述器
> 老板30秒读懂今天生意，系统讲故事，不是让老板查报表

- [x] 新建 `src/services/narrative_engine.py`：纯函数层（`_build_overview` / `_detect_anomalies` / `_build_action` / `compose_brief`）+ `NarrativeEngine.generate_store_brief`（≤200字硬约束）
- [x] 修改 `decision_push_service.py`：`push_evening_recap` 接入 NarrativeEngine，标题升级为「20:30晚推·经营简报」，失败时降级回原有格式
- [x] 新建 `tests/test_narrative_engine.py`：13个测试（纯函数11 + 集成3）

### ② StoreHealthScore — 门店健康指数
> 老板一眼看出5家店哪家有问题，不需要看20张报表

- [x] 新建 `src/services/store_health_service.py`：5维度加权综合指数
  - 营收完成率30% + 翻台率20% + 成本率25% + 客诉率15% + 人效10%
  - 纯函数：`compute_health_score(metrics) → float (0-100)` + `classify_health(score) → excellent/good/warning/critical`
  - `StoreHealthService.get_store_score(store_id, target_date, db)` — 单店当日评分
  - `StoreHealthService.get_multi_store_scores(store_ids, target_date, db)` — 多店排名（供老板看全局）
  - 缺失维度数据时按已有维度比例归一化（不返回0）
- [x] 在 `daily_hub_service.py` 的 `health_score` 字段改为调用 `StoreHealthService`（替代当前简单单值）
- [x] 新建 `src/api/store_health.py`：`GET /api/v1/stores/health?date=` 返回所有门店评分排名
- [x] 前端 `HQDashboardPage.tsx`：新增门店健康度排名卡片（评分 + 状态色标 + 最弱维度标注）
- [x] 新建 `tests/test_store_health_service.py`：≥12个测试（纯函数 + 缺失维度降级 + 多店排名）

### ③ BehaviorScoreEngine — AI建议采纳率跟踪
> 替代个人利润归因，记录"跟着AI走"的行为，向老板证明系统ROI

- [x] 新建 `src/services/behavior_score_engine.py`：追踪AI建议生命周期
  - 纯函数：`compute_adoption_rate(decisions) → float` / `compute_execution_accuracy(decisions) → float`
  - `BehaviorScoreEngine.get_store_report(store_id, start_date, end_date, db)` — 门店维度报告
    - AI建议发出数 / 采纳数 / 采纳率%
    - 已采纳建议中：48h内有效果回馈的数量 / 执行准确率%
    - 累计节省¥（系统价值证明，不归因到个人）
  - `BehaviorScoreEngine.get_system_roi_summary(brand_id, month, db)` — 品牌级ROI汇总（供老板续费决策）
- [x] 在 `monthly_report_service.py` 中接入 `BehaviorScoreEngine.get_store_report`，替代当前手工汇总的采纳率字段
- [x] 在 `src/api/decision_hub.py` 新增端点：`GET /api/v1/decisions/behavior-report?store_id=&start_date=&end_date=`
- [x] 新建 `tests/test_behavior_score_engine.py`：≥10个测试（纯函数 + 各方法 + ROI汇总）

## 已完成

- [x] **测试基础设施修复（2026-03-06）** — 修复12个测试收集错误，0收集错误，3303测试可收集，2910通过
  - `src/ontology/__init__.py`：添加 `get_ontology_repository()` + 重新导出 `NodeLabel/RelType`，懒加载 neo4j 连接
  - `src/services/backup_service.py`：新建 BackupService（pg_dump+gzip）+ backup_service 单例
  - `src/services/data_import_export_service.py`：新建 DataImportExportService CSV导入导出
  - `src/services/supply_chain_service.py`：新建 SupplyChainService CRUD
  - `src/services/federated_learning_service.py`：添加 DataIsolationManager + 2个全局单例
  - 测试修复：patch路径纠正（lazy-import → 源模块）、AsyncContextManager兼容、相对导入修复
  - `tests/conftest.py`：添加全局env vars（CELERY_BROKER_URL等），消除120+个文件的重复设置需求

- [x] **VoiceCommandWhitelist** — `src/core/voice_command_whitelist.py`：语音高危操作白名单（财务/批量删除/权限），3级风险分级（SAFE/CONFIRM/HIGH_RISK），高危操作推送手机端二次确认；25个测试全通过
- [x] **Onboarding Phase 2** — `connect_adapter` 真正触发 `pull_historical_backfill` Celery 任务（low_priority 队列），回灌最近30天历史订单；`complete_onboarding` 通过 AgentMemoryBus 发布 `onboarding_complete` 事件，各 Agent 自动初始化

- [x] 私域 Agent get_journeys 接入真实 DB（_fetch_journeys_from_db + _persist_journey_to_db）
- [x] 用户培训文档（docs/user-training-guide.md）

- [x] 检查所有 agent 完整性与稳定性（预定/排班/订单/私域/服务/库存/培训/绩效/决策/运维）
- [x] 补充 private_domain agent 的 test_agent.py（56个测试）
- [x] 补充 performance_agent 功能测试（38个测试）
- [x] 补充 ops_agent 功能测试（33个测试）
- [x] 将 mock 数据方法替换为真实 DB 服务调用（private_domain / training / schedule）
- [x] 排班 agent 流量预测接入历史订单数据
- [x] 修复 service/decision/reservation/order/inventory/training agent 预存在的测试失败
- [x] 为所有 package agent 测试目录添加 conftest.py（sys.path 修复）
- [x] 新增私域运营 18个增长 action（AARRR 框架）
- [x] 企微 webhook 接入私域 Agent 对话（P0/P1）
- [x] 生成屯象OS功能明细思维导图
- [x] Phase 3 安全加固：SecurityHeadersMiddleware（防 XSS/点击劫持/MIME 嗅探/HSTS）
- [x] Phase 3 安全加固：CORS 配置环境感知（明确 methods/headers，不使用 *）
- [x] Phase 3 安全加固：Nginx SSL/TLS 配置（HTTP→HTTPS 重定向、TLS 1.2+、安全头、OCSP Stapling）
- [x] Phase 3 生产部署：Kubernetes 配置（namespace/configmap/secrets/api/web/postgres/redis/hpa/ingress）
- [x] Phase 3 性能优化：GZip 压缩中间件（minimum_size=1000）
- [x] Phase 3 生产部署：Prometheus 告警规则补充（Redis宕机/DB连接池耗尽/磁盘/Agent错误率）
- [x] P0-1 建立 Alembic 数据库迁移体系（env.py compare_type、URL转换、13个Phase3-8模型注册）
- [x] P0-2 私域Agent SQL bug修复（INTERVAL参数化）并移除 _generate_mock_customers 死代码
- [x] P0-3 菜单排名 MenuRanker 移除 _mock_ranking() 死代码，无DB时返回空列表
- [x] P0-4 门店记忆 StoreMemoryService 移除 _mock_peak_patterns() 死代码，无DB时返回空列表
- [x] P1-1 向量DB 移除 _generate_mock_embedding() 死代码（generate_embedding 已有零向量兜底）
- [x] P1-2 服务质量Agent _generate_mock_feedbacks 重命名为 _fetch_feedbacks_from_db
- [x] P1-3 README Phase 3 路线图状态同步（性能优化/安全加固/生产部署标记完成）
- [x] P2-1 补充服务层核心单元测试（MenuRanker/StoreMemoryService/VectorDbService 共3个测试文件）
- [x] P2 绩效计算引擎：EmployeeMetricRecord 模型 + PerformanceComputeService + API 端点（3个）+ 17个测试

---

## 评论

### 2026-03-07（Phase 1 Week 3-4 — 私域运营自动化）
- `marketing_agent_service.py`：新增 `trigger_batch_churn_recovery`（dry_run优先跳过频控→批量计数；非dry_run通过 FrequencyCapEngine.can_send + record_send 精确控频）+ `get_campaign_roi_summary`（近N天活动按类型汇总ROI）+ `record_campaign_attribution`（幂等归因打点）
- `marketing_agent.py`：新增3个端点：`POST /stores/{id}/batch-churn-recovery`、`GET /stores/{id}/campaigns/roi-summary`、`POST /stores/{id}/campaigns/{id}/track`
- `celery_tasks.py`：新增 `marketing_auto_outreach` 任务（遍历近30天活跃门店批量触达）
- `celery_app.py`：Beat 新增 `marketing-auto-outreach`（10:30，priority=6，可环境变量覆盖）
- `RecommendationsPage.tsx`：从 null stub 完整重建（顾客ID查询 + 门店选择 + 场景感知 + ZTable混合推荐结果 + 算法说明卡片），路由权限从 admin 降为 store_manager
- `RecommendationsPage.module.css`：新建
- `MarketingCampaignPage.tsx`：新增第二行 ROI 汇总 KPI（近30天营收/触达/转化率/综合ROI）+ 「批量挽回触达」+「预估触达」按钮
- `App.tsx`：recommendations 路由权限 admin → store_manager
- `tests/test_marketing_week34.py`：12个测试（批量触达×5 + ROI汇总×5 + 归因打点×2），全部通过

### 2026-03-07（Phase 1 Week 1-2 — Marketing Agent 核心能力）
- `marketing_agent_service.py`：新增 `get_store_segment_summary`（批量RFM，一条SQL聚合全门店顾客→5维客群分布+占比）+ `get_at_risk_customers`（按风险降序，支持 risk_threshold 过滤，返回最近失联天数/消费总额¥/推荐动作）
- `marketing_agent.py`：新增3个端点：`GET /stores/{store_id}/segments`、`GET /stores/{store_id}/customers/at-risk`、`GET /stores/{store_id}/statistics`
- 新建 `tests/test_marketing_agent_service.py`：24个测试（_determine_segment×6 + 向量化×2 + 发券策略×5 + 批量分群×4 + 流失客户列表×7），全部通过
- 重建 `apps/web/src/pages/MarketingCampaignPage.tsx`：Z设计系统，ECharts 客群饼图 + ZTable 流失客户风险条 + ZTable 活动列表 + ZModal 发券策略生成器 + ZModal 新建活动
- 新建 `apps/web/src/pages/MarketingCampaignPage.module.css`
- `apps/web/src/layouts/MainLayout.tsx`：新增「营销智能体」导航入口（RocketOutlined，会员与增长分组），补充路由映射 + 面包屑标题

### 2026-03-02
- P2 绩效计算引擎上线：从订单/损耗事件聚合各岗位核心指标（store_manager/waiter/kitchen）
- 新增 employee_metric_records 表（Alembic b03），幂等 upsert
- API：POST /compute 触发计算，GET /metrics 查询，GET /summary 汇总
- 17个集成测试全部通过

### 2026-02-26
- 所有8个 package agent 测试套件在独立运行时全部通过（共 235 个测试）
- 已知限制：多 agent 同时运行时存在 sys.path 污染问题（各 agent src/agent.py 互相覆盖），需独立运行
- 私域 Agent 增长能力当前返回 mock/demo 数据，待接入真实 DB 后替换

### 2026-03-04
- 完成所有 P0/P1/P2-1 优先级项目开发
- 清理 4 处死代码（_mock_ranking、_mock_peak_patterns、_generate_mock_embedding、_generate_mock_customers）
- 修复私域 Agent SQL INTERVAL 参数化 bug（生产级关键修复）
- 新增 3 个服务层单元测试文件，覆盖核心评分逻辑、异常检测、嵌入降级链路
### 2026-03-04（续）
- 私域 Agent 增长旅程接入真实 DB：新增 `_fetch_journeys_from_db` 和 `_persist_journey_to_db`，`get_journeys` 和 `trigger_journey` 均已替换 mock 数据
- 完成用户培训文档（docs/user-training-guide.md）：覆盖店长/总部/员工三类角色，含备战板操作、食材成本分析、企业微信指令速查等
- Phase 3 所有任务已全部完成

### 2026-03-04（v2.0启动）
- 新建 `financial_impact_calculator.py`：6个静态方法（cost_rate_improvement/purchase_decision/waste_reduction/staffing_optimization/decision_roi/menu_price_impact）
- `food_cost_service.py` 已在上次会话中完成（get_bom_cost_report/get_store_food_cost_variance/get_hq_food_cost_ranking）
- 新建 `decision_priority_engine.py`：DecisionCandidate 数据类 + 4个纯评分函数 + DecisionPriorityEngine.get_top3（inventory/food_cost/reasoning 三源聚合，Top3决策输出）
- 新建 `tests/test_decision_priority_engine.py`：14个测试（纯函数6类 + 集成4个）
- 新建 `waste_guard_service.py`：get_top5_waste（¥排名+归因）/ get_waste_rate_summary（损耗率+环比）/ get_bom_waste_deviation（BOM偏差排名）/ get_full_waste_report
- 新建 `tests/test_waste_guard_service.py`：14个测试（纯函数+各方法+综合报告）

### 2026-03-04（续2）
- 天财商龙适配器扩展完成：新增 fetch_store_info / fetch_dishes / fetch_orders_by_date / fetch_inventory（4个核心 API）+ pull_daily_orders / pull_all_dishes / pull_all_inventory（自动分页）+ to_dish / to_inventory_item / _normalize_store（数据映射）
- 适配器测试扩展：新增 TestToDish(7) + TestToInventoryItem(5) + TestFetchOrdersByDate(2) + TestPullDailyOrders(2) + TestFetchDishes(1) + TestNormalizeStore(2) 共19个测试
- FCT ¥化改造完成：`fct_service.py` 全4个主方法 + dashboard 均已添加 `_yuan` 伴随字段，`_y()` helper 统一转换
  - estimate_monthly_tax：revenue/vat/cit/total_tax 各子字段新增 _yuan
  - forecast_cash_flow：summary + daily_forecast 每项 + outflow_breakdown 每项 + alerts.balance_yuan
  - get_budget_execution：revenue + categories[] + overall 各字段新增 _yuan
  - get_dashboard：cash_flow + tax 新增 _yuan 字段
- 新增 `tests/test_fct_service.py` TestYuanFields 类（4个测试，覆盖全4个方法的¥字段）

### 2026-03-04（续3）
- 新建 `decision_push_service.py`：4时间点决策推送（晨推/午推/战前/晚推），含¥+置信度+一键操作按钮
  - `push_morning_decisions` / `push_noon_anomaly` / `push_prebattle_decisions` / `push_evening_recap`
  - 纯信息不推送（午推仅在 warning/critical 时发，战前推仅在有库存决策时发）
  - 4个格式化纯函数：`_format_card_description` / `_format_anomaly_description` / `_format_prebattle_description` / `_format_evening_description`
- `wechat_service.py` 新增 `send_decision_card()` 方法：textcard 格式+Redis 去重+失败入队
- `celery_app.py` 新增 4 个 Beat 调度条目（08:00/12:00/17:30/20:30，可环境变量覆盖）
- `celery_tasks.py` 新增 5 个 task 函数：`push_morning_decisions` / `push_noon_anomaly` / `push_prebattle_decisions` / `push_evening_recap` / `check_decision_impact`
- `approval.py` 新增 48h 效果反馈调度：审批通过后自动 countdown=48h 触发 `check_decision_impact`
- `edge_node_service.py` 新增离线查询：`query_revenue_offline` / `query_inventory_offline` / `update_revenue_cache` / `update_inventory_cache`
- 新建 `tests/test_decision_push_service.py`：20个测试（纯函数8+push逻辑12）
- 新建 `tests/test_edge_node_offline_query.py`：9个测试（revenue/inventory查询+缓存写入）

### 2026-03-04（续4）
- 新建 `tests/integration/test_e2e_pos_fct_push_approval.py`：P0 全链路集成测试，6个 TestCase 共33个测试
  - TestPosNormalizationChain(6)：meituan/keruyun/generic 归一化 + 签名验证 + 空列表
  - TestFctYuanFields(3)：税务/现金流/预算执行率 _yuan 字段存在性验证
  - TestDecisionPushPipeline(6)：晨推/午推/战前推/晚推条件逻辑 + 全链路无决策不发送
  - TestApprovalCallbackChain(4)：审批状态更新 + 48h 反馈调度逻辑
  - TestOfflineQueryChain(4)：离线降级全链路：写入→读取数据一致性
  - TestPushFormatCompliance(5)：Rule 7 合规验证（动作/¥/置信度/512字符/4字按钮）
- 新建 `src/services/case_story_generator.py`：P1 服务
  - 纯函数：`_compute_cost_metrics` / `_summarize_decisions` / `_narrative_sentence`
  - `CaseStoryGenerator.generate_daily_story` / `generate_weekly_story` / `generate_monthly_story` / `get_metrics_summary`
  - Rule 6 兼容：所有输出包含 _yuan 伴随字段
- 新建 `tests/test_case_story_generator.py`：13个测试（纯函数9+DB mock 4）
- 新建 `src/services/scenario_matcher.py`：P1 服务
  - 纯函数：`classify_scenario`（7种场景）/ `score_case_similarity`（0-1评分）/ `get_scenario_label`
  - `ScenarioMatcher.identify_current_scenario` / `find_similar_cases` / `get_recommended_actions`
  - 场景优先级：high_cost > high_waste > holiday_peak > revenue_down > weekend > new_dish > weekday_normal
- 新建 `tests/test_scenario_matcher.py`：20个测试（纯函数11+DB mock 9）
- 新建 `src/api/_mvp_tags.py`：MVP 端点注册表，28个 MVP 端点，按10个MVP功能组织，含 `is_mvp_endpoint()` / `get_all_mvp_paths()` 工具函数
- 前端页面归档：85个非MVP页面移至 `apps/web/src/pages/archive/`，原位置改为 React null stubs；14个MVP页面保留（含 Login/404/FCT/Dashboard）

### 2026-03-04（续5）
- 完成全部 P1 功能交付：
- 新建 `src/api/decision_hub.py`：4个端点（Top3查询/手动触发推送/待审批列表/场景识别），对接 DecisionPriorityEngine + DecisionPushService + ScenarioMatcher
- 新建 `src/services/monthly_report_service.py`：纯函数（build_executive_summary / build_weekly_trend_chart / render_html_report）+ MonthlyReportService.generate / generate_html（HTML报告供浏览器打印PDF，无外部依赖）
- 新建 `src/api/monthly_report.py`：GET /reports/monthly/{store_id}（JSON）+ /html 变体（HTMLResponse），默认返回上月数据
- 新建 `apps/web/src/pages/ProfitDashboard.tsx`：双Tab ECharts仪表盘（跨店成本率排名柱状图+折线叠加 / 单店周趋势双轴折线+柱状图），含打印PDF按钮、KPI统计卡、Alert横幅
- `src/main.py` 注册 decision_hub + monthly_report 两个新 router
- 新建 `tests/test_monthly_report_service.py`：16个测试（纯函数13 + 服务集成3）
- 新建 `tests/test_decision_hub.py`：14个测试（top3×4 / trigger-push×4 / pending×3 / scenario×3）
- Alembic P0任务：已确认单HEAD `aa01_merge_all_heads`，无需额外操作

### 2026-03-04（续6）
- 修复 MVP 功能缺口：
- `apps/web/src/App.tsx`：新增 `ProfitDashboard`（路径 `/profit-dashboard`，admin）和 `AlertThresholdsPage`（路径 `/alert-thresholds`，store_manager）两条路由，并对应添加 lazy import
- 新建 `apps/web/src/pages/AlertThresholdsPage.tsx`：MVP #8 告警阈值配置页面
  - `GET /api/v1/kpis` 加载所有 KPI 列表
  - `PATCH /api/v1/kpis/{kpi_id}/thresholds` 更新警告/超标阈值（inline 编辑，Save/Cancel 按钮）
  - 按类别过滤（食材成本/损耗管理/营业收入/决策执行）
  - 客户端校验：warning < critical 阈值
  - 阈值显示：Tag颜色（warning=橙，critical=红），未设置显示「未设置」

### 2026-03-04（续7）
- `apps/web/src/layouts/MainLayout.tsx`：补充两条缺失的导航入口
  - 「告警阈值配置」加入「业务管理」分组（store_manager 可见）
  - 「成本率分析」加入「智能分析」分组（admin 可见）
  - 同步更新路由→分组映射表和面包屑标题映射表

### 2026-03-04（续8）
- `apps/web/src/pages/DailyHubPage.tsx`：新增「今日 AI 决策推荐」区块
  - 调用 `GET /api/v1/decisions/top3?store_id=X` 加载 Top3 决策
  - 3列卡片（每个决策一列）：rank badge + source/difficulty tag + title + action + 净收益¥ + 决策窗口 + 置信度 Progress bar + 「去审批」按钮
  - 加载失败静默降级（不阻断主页面）
  - 首次加载和 store 切换自动刷新，支持手动刷新

### 2026-03-04（续9）
- 新建 `src/services/kpi_alert_service.py`：食材成本率 KPI 阈值告警服务
  - 纯函数：`classify_alert`（ok/warning/critical）/ `build_alert_message`（Rule 7 合规：含¥+动作建议）
  - `_get_food_cost_thresholds`：读 KPI 表用户配置，无配置回落环境变量默认值（32%/35%）
  - `_get_active_store_ids`：从 orders 表查近30天有交易的门店
  - `check_store`：单店检查（FoodCostService + 阈值对比），返回含 actual_cost_yuan 的结构
  - `run_all_stores`：多店遍历，单店失败静默跳过
  - `run_and_notify`：完整流程（检查→发送企微告警）
- `src/core/celery_tasks.py`：新增 `check_food_cost_kpi_alert` 任务
- `src/core/celery_app.py`：Beat 新增 `check-food-cost-kpi-alert`（09:30，priority=8，可环境变量覆盖）
- 新建 `tests/test_kpi_alert_service.py`：20个测试（classify_alert×6 / build_message×6 / check_store×4 / run_all_stores×2 / run_and_notify×2）

### 2026-03-04（续10）
- 新建 `src/api/waste_guard.py`：MVP #3 损耗Top5前端接入所需 API
  - `GET /api/v1/waste/report?store_id=&start_date=&end_date=` — 综合损耗报告（调用 get_full_waste_report）
  - `GET /api/v1/waste/top5` — 单独 Top5 损耗食材
  - `GET /api/v1/waste/summary` — 损耗率汇总（含环比）
- `src/main.py`：注册 waste_guard router（v2.0 MVP #3 损耗Top5排名）
- 重建 `apps/web/src/pages/WasteReasoningPage.tsx`：MVP #3 完整前端页面
  - 4个 KPI 卡片：总损耗¥ / 损耗率（带状态badge） / 较上期变化¥ / Top5食材种数
  - Top5 损耗食材表格：排名badge + 食材名称 + 损耗¥ + 数量 + 占比Progress + 归因Tag + 建议行动
  - BOM 偏差排名表格（偏差成本¥ / 超用数量 / 平均偏差率）
  - 日期范围选择器（默认近7天） + 门店选择 + 手动刷新
  - 加载失败显示 Alert 错误信息

### 2026-03-04（续11）
- `apps/web/src/pages/FctPage.tsx`：Rule 6 合规修复——所有金额展示改用 `_yuan` 伴随字段
  - DashboardTab：`net_7d_yuan` / `total_tax_yuan`（降级兜底：旧字段 ÷100）
  - TaxTab：`total_tax_yuan` / `output_vat_yuan` / `input_vat_yuan` / `net_vat_yuan` / `surcharge_yuan` / `taxable_income_yuan` / `cit_amount_yuan` / `pos_total_yuan` / `avg_order_yuan`
  - CashFlowTab：dataIndex 改为 `inflow_yuan` / `outflow_yuan` / `cumulative_balance_yuan`
  - BudgetTab：dataIndex 改为 `actual_yuan` / `budget_yuan`
  - 所有改动均保留降级兜底（`?? 旧字段/100`），不破坏旧版后端兼容性

### 2026-03-05（merge conflict 批量修复）
- 发现并修复 `git pull --no-rebase` 遗留的全量 merge conflict：
  - `waste_guard_service.py`：保留 HEAD v2.0（Top5+BOM分析），弃 d1df728 旧实时告警版
  - `models/__init__.py`：合并两版本——保留 Phase 3-8 models，新增 MealPeriod + EmployeeMetricRecord
  - `feishu_message_service.py`：同时保留 `import json` 和 `import os`
  - `menu_ranker.py`：保留 HEAD 的 logger.warning/info 日志调用
  - `private_domain/src/agent.py`：保留 HEAD（使用 `_fetch_journeys_from_db` + `_persist_journey_to_db`），修复 `next_action_at` 缺失 bug
  - `private_domain/tests/test_agent.py`：保留 HEAD，移除 d1df728 多余注释
  - `test_store_memory_service.py`：保留 HEAD 中文测试套件（含 os.environ.setdefault 环境设置）
  - 47 个 TSX 归档页面（`apps/web/src/pages/*.tsx`）：保留 HEAD null stubs（`() => null`），弃 d1df728 旧完整实现
- commit c401756 推送至 main

### 2026-03-05（代码质量修复）
- **前端 TabPane 废弃 API 修复**（Ant Design 5.x 兼容）：4个文件迁移到 `items` 数组 API
  - `FctPage.tsx`（MVP #2）：4个 TabPane → items 数组
  - `WasteEventPage.tsx`（损耗事件）：3个 TabPane → items 数组
  - `NotificationCenter.tsx`：2个 TabPane → items 数组
  - `BOMManagementPage.tsx`（MVP #6）：移除未使用的 `const { TabPane } = Tabs;`
- **MVP 页面 store_id 初始值修复**：改用 `localStorage.getItem('store_id') || 'STORE001'` 避免首次渲染查错门店数据
  - `DailyHubPage.tsx`、`WasteReasoningPage.tsx`、`BOMManagementPage.tsx`
- **`waste-reasoning` 路由权限修复**：从 `admin` 改为 `store_manager`（MVP #3 损耗Top5排名需店长可见）
- **`GET /api/v1/approvals` 端点增强**（MVP #5 一键审批）：
  - 新增 `status`/`decision_type`/`start_date`/`end_date` 查询参数支持多状态过滤
  - 不传 status 默认返回全部（而非仅 pending），与前端"全部"筛选对齐
- **BOMManagementPage 成本分析按钮**（MVP #6）：接入 `/api/v1/bom/{bom_id}/cost-report`
  - 新增「成本分析」按钮（¥图标）在每条 BOM 操作列
  - 弹出 Modal：标准总成本¥ / 菜品售价¥ / 食材成本率%（红/橙/绿色标）
  - 食材明细表：按成本贡献降序 + Progress 占比可视化

### 2026-03-05（字段命名修复 — ProfitDashboard NaN bug）
- **`food_cost_service.py` 字段名统一**（Breaking bug fix）：
  - `get_store_food_cost_variance`：`actual_pct` → `actual_cost_pct`（与 monthly_report / kpi_alert_service 一致）
  - `get_hq_food_cost_ranking` summary：`total_stores`→`store_count`，`avg_actual_food_cost_pct`→`avg_actual_cost_pct`，`over_budget_stores`→`over_budget_count`（与 ProfitDashboard.tsx 接口匹配）
- **级联修复**（读取旧字段名的 5 个位置）：
  - `food_cost_service.py`：avg 计算改用 `actual_cost_pct`
  - `daily_hub_service.py`：`fc["actual_pct"]` → `fc["actual_cost_pct"]`（×3 行）
  - `decision_priority_engine.py`：`variance.get("actual_pct")` → `variance.get("actual_cost_pct")`
- **测试同步更新**：`test_food_cost_service.py`、`test_decision_priority_engine.py`、`test_daily_hub_food_cost.py` 中 mock 数据字段名统一更新

### 2026-03-05（ProfitDashboard 第3个Tab — 食材成本明细钻取）
- `apps/web/src/pages/ProfitDashboard.tsx`：新增「单店食材明细」Tab
  - 新增 `VarianceDetail` / `VarianceIngredient` 接口，新增 `varianceData` / `varianceLoading` 状态
  - `loadVariance(storeId)` 调用 `GET /api/v1/hq/food-cost-variance`
  - 4个 KPI 卡片：实际成本¥ / 实际成本率%（颜色分级）/ 理论成本率% / 差异%（±图标）
  - Top10 食材用料明细表：排名badge + 食材名称 + 用料成本¥ + 占实际成本%（Progress条）
  - 门店切换与排名 Tab 联动；首次进入提示用户先选门店

### 2026-03-05（DailyHubPage 食材成本率展示）
- `apps/web/src/pages/DailyHubPage.tsx`：「昨日复盘」卡片补充食材成本率区块
  - 后端 `review.food_cost` 已有数据（`actual_pct`/`theoretical_pct`/`variance_pct`/`variance_status`/`top_ingredients`），但前端未展示
  - 新增：实际成本率%（绿/橙/红分级）+ 状态 Tag + 理论值 + 差异%
  - warning/critical 时展示 Top2 问题食材名称 + 用料成本¥

### 2026-03-05（MVP #9 月度经营报告前端页面）
- 新建 `apps/web/src/pages/MonthlyReportPage.tsx`：MVP #9 月度经营报告完整前端
  - 门店选择器 + 月份选择器（DatePicker picker="month"，默认上月）
  - 6个 KPI 卡片：月度营业额¥ / 食材成本率%（颜色分级）/ 损耗金额¥ / 决策采纳率% / 决策节省¥ / 审批决策
  - 经营叙事文字区块（绿色背景）
  - ECharts 双轴折线图：周成本率趋势 + 营业额柱状图，含33%警戒线
  - Top3 节省决策表格（rank badge + 动作 + 预期节省¥ + 实际结果）
  - 「打印 / 导出 PDF」按钮 → 新标签打开 `/api/v1/reports/monthly/{store_id}/html` HTML报告
- `apps/web/src/App.tsx`：新增 `monthly-report` 路由（admin）+ lazy import
- `apps/web/src/layouts/MainLayout.tsx`：
  - ROUTE_TO_GROUP 新增 `/monthly-report` → `admin-analytics`
  - 面包屑映射新增 `/monthly-report` → `月度经营报告`
  - 「智能分析」菜单组新增「月度经营报告」入口

### 2026-03-05（NarrativeEngine 经营故事叙述器）
- 新建 `src/services/narrative_engine.py`：架构升级 v2.1，将结构化数据转为 ≤200字 自然语言简报

### 2026-03-05（StoreHealthScore 门店健康指数）
- 新建 `src/services/store_health_service.py`：5维度加权综合指数（0-100分）
  - 纯函数全部实现：compute_health_score / classify_health / _score_* × 5
  - StoreHealthService.get_store_score（单店）/ get_multi_store_scores（多店排名）
  - 缺失维度按已有维度比例归一化（不返回0）
  - 成本率维度复用 FoodCostService（Rule 3），不重复 SQL
- 新建 `src/api/store_health.py`：GET /api/v1/stores/health（所有活跃门店评分排名+汇总）
- `src/main.py` 注册 store_health router
- `apps/web/src/pages/HQDashboardPage.tsx`：新增「门店健康度排名」卡片
  - 评分 Progress 条（颜色分级）+ 状态 Tag + 最弱维度标注 + 营收¥
  - 汇总 Tag：危险/需关注/良好/优秀门店数
- 新建 `tests/test_store_health_service.py`：28个测试（纯函数17 + 集成5）

### 2026-03-05（会员档案管理 + 生日提醒闭环）
- FrequencyCapEngine wiring into execute_journey_step（lazy-init Redis client，pass freq_cap_engine=）
- MainLayout.tsx: 新增 /dynamic-pricing 导航入口（admin-crm 分组，DollarOutlined）
- EventScheduler P0 gap 补全：birthday_reminder_service.py + birthday_greeting/anniversary_greeting BUILTIN_JOURNEYS + trigger_birthday_reminders Celery task（10:00 daily）+ Alembic d01 migration + 13个测试
- 会员档案管理 API: GET /members/{store_id}/list（分页+搜索+多维过滤）+ PATCH /members/{store_id}/{customer_id}（更新 birth_date/wechat_openid/channel_source）
- MemberSystemPage.tsx: 从 null stub 重建为完整会员档案表格（RFM tag、生命周期 tag、内联生日编辑、旅程触发）
- test_member_profile_api.py: 13个测试（GET×7 + PATCH×6）

---

## Phase P1 — 数据融合引擎 + 知识库生成（2026-03-23）

> 战略：屯象OS 定位餐饮行业 Palantir，面向复杂集团/多品牌/品质中大型餐饮
> 两阶段目标：
>   Phase 1 — 历史数据智能融合 → 知识库自动生成 → 接入即出经营体检报告
>   Phase 2 — 影子模式验证 → 灰度切换 → SaaS 渐进替换（零停机）

### Phase 1.1 — 数据融合引擎（Data Fusion Engine）— 全部完成 ✅（2026-03-23）

- [x] 数据模型 `models/fusion_task.py`：5张表 + 5 Enum
- [x] Alembic 迁移 `z69_data_fusion_engine.py`（down_revision=z68_mission_journey）
- [x] 实体解析服务 `services/entity_resolver.py`：跨系统实体识别与合并
- [x] 数据融合引擎 `services/data_fusion_engine.py`：多源采集编排 + 断点续传
- [x] 历史回填服务 `services/historical_backfill.py`：三通道批量回填（API/CSV/DB镜像）
- [x] 时间线组装器 `services/timeline_assembler.py`：跨系统事件时间轴对齐
- [x] 知识库生成管道 `services/knowledge_generator.py`：6维经营体检报告
- [x] API路由 `api/data_fusion.py`：8个端点 + 总部BFF
- [x] 注册路由到 main.py
- [x] 60个单元测试全部通过（`tests/test_data_fusion.py`）

### Phase 1.2 — 经营体检报告 + 前端向导 — 全部完成 ✅（2026-03-23）

- [x] 体检报告生成器集成在 `knowledge_generator.py`：营收/成本/菜品/会员/人效/供应商6维
- [x] 前端迁移向导页面 `pages/hq/DataFusionWizard.tsx`：4步向导 + 10个SaaS系统选择
- [ ] 种子客户试跑验证（待尝在一起品智POS数据接入后执行）

### Phase 2.1 — 影子模式 + 灰度切换 — 全部完成 ✅（2026-03-23）

- [x] 数据模型 `models/shadow_mode.py`：5张表（ShadowSession/Record/ConsistencyReport/CutoverState/Event）+ 5 Enum
- [x] Alembic 迁移 `z70_shadow_mode_cutover.py`（down_revision=z69）
- [x] 影子模式引擎 `services/shadow_mode_engine.py`：影子记账 + 一致性比对 + 灰度切换控制器
- [x] API路由 `api/shadow_mode.py`：10个端点 + 总部BFF
- [x] 注册路由到 main.py
- [x] 30个单元测试全部通过（`tests/test_shadow_mode.py`）

### Phase 2.2 — 功能平权 — 全部完成 ✅（2026-03-23）

- [x] 轻量POS收银 `services/pos_terminal_service.py`：开单/加菜/折扣/结账/作废
- [x] 采购工作台 `services/purchase_workbench_service.py`：创建PO/提交/供应商确认/收货/对账
- [x] 移动盘点 `services/mobile_stocktake_service.py`：创建盘点/逐条计数/批量/差异报告/审批
- [x] API路由 `api/pos_terminal.py` + `api/purchase_workbench.py` + `api/mobile_stocktake.py`
- [x] 注册路由到 main.py
- [x] 前端路由注册 App.tsx + 导航菜单 HQLayout.tsx
- [x] 影子模式驾驶舱 `pages/hq/ShadowModeDashboard.tsx`

### Phase 2.2 前端页面 — 全部完成 ✅（2026-03-23）

- [x] 40个单元测试全部通过（`tests/test_pos_purchase_stocktake.py`）
- [x] POS收银界面 `pages/sm/PosTerminal.tsx`（开单/加菜/折扣/结账/作废，移动端）
- [x] 采购工作台 `pages/sm/PurchaseWorkbench.tsx`（创建PO/提交/确认/收货/对账，移动端）
- [x] 移动盘点 `pages/sm/MobileStocktake.tsx`（全盘/分类盘/抽盘/差异/审批，移动端）
- [x] 注册路由 App.tsx + 导航菜单 StoreManagerLayout.tsx

### 待做（下一阶段）

- [ ] 种子客户试跑（尝在一起品智POS数据接入后执行）
- [ ] Phase 2.3：实体解析器接入Neo4j本体图（OntologyAdapter集成）
- [ ] Phase 2.3：POS收银数据实时同步到影子模式引擎
