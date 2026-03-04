# 任务清单

> 格式：- [ ] 待办 / - [x] 完成
> 每次会话开始时更新，完成后在底部添加评论。

---

## 进行中


---

## 待办（v2.0 战略重置，按优先级排序）

> 来源：智链OS产品开发计划明细v2（融合Toast建议）2026-03-04
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

## 已完成

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
- [x] 生成智链OS功能明细思维导图
<<<<<<< HEAD
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
=======
- [x] P2 绩效计算引擎：EmployeeMetricRecord 模型 + PerformanceComputeService + API 端点（3个）+ 17个测试
>>>>>>> d1df728dec60bb243c50ae42ff68074712ddafd9

---

## 评论

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