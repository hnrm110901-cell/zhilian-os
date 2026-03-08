# 协作同步看板（Codex × Claude）

更新时间：2026-03-08

## P0（优先执行）
- [x] 前端实时通知系统增强（`apps/web/src/pages/NotificationCenter.tsx`）
  - 自动刷新（默认开启）
  - 前台激活立即刷新
  - 刷新状态可见（最近刷新时间）
- [x] 移动端核心三页骨架落地（`/sm`：首页/班次/任务）
  - 首页已接入 mobile query service（不再直连旧 BFF 结构）
  - 新增 `sm/Shifts.tsx`、`sm/Tasks.tsx`
  - 新增 `mobile.query.service.ts`、`mobile.mutation.service.ts`、`mobile.mock.ts`、`mobile.types.ts`
  - 底部导航切换为 首页/班次/任务/告警，保留原 `business/decisions` 路由兼容
  - 状态机补齐：打卡/下班打卡、任务开始/提交均有状态转移校验与错误提示
  - 任务详情弹窗：补齐任务详情展示 + 证据上传占位 + 提交前证据校验
  - 任务详情接口化：新增 `queryTaskDetail`，提交改为 `submitTask(payload)`（说明/文件名）
  - 证据上传调用化：新增 `uploadTaskEvidence`（FormData）+ mock 回退 + 上传状态展示
  - 后端 `mobile` API 补齐：`home/shifts/tasks` 查询 + check-in/out + start/submit + evidence 上传
  - mobile API 收尾：上传接口返回 `file_url`；补齐 `/mobile` 新端点专项测试（直测路由函数）
  - 前端证据链路收尾：上传后展示可点击 `file_url` 预览链接

## P1
- [x] 核心页面移动端适配补强（`WorkforcePage`、`ActionPlansPage`）
  - 小屏筛选控件改为全宽
  - 表格开启横向滚动
  - 抽屉宽度改为 `92vw`（移动端）
  - 工具栏与操作按钮优化换行
- [x] 前端构建阻塞修复（`MainLayout.tsx` 菜单过滤类型收敛）
  - 修复 `MenuProps['items']` + `flatMap` 联合类型推断冲突
  - 改为显式收集数组并补齐类型断言，恢复 `npm run build` 通过
- [x] 多门店管理页稳定性修复（`MultiStoreManagement.tsx`）
  - 去除 `any`，补齐接口类型（门店列表/区域汇总/绩效排名/对比响应）
  - 对比查询改为选择事件驱动，避免 effect 中级联 setState
  - Select 选项改为 `options` 模式，修复标签渲染与可维护性问题
- [x] 多门店 API 兼容层补齐（`multi_store.py` + `store_service.py`）
  - 新增兼容路径：`/stores`、`/regional-summary`、`/performance-ranking`
  - `POST /compare` 兼容前端 payload（metrics 可选，支持 start/end）
  - 对比结果兼容双结构：保留 `metrics/data`，新增 `stores[].metrics`
  - `avg_order_value` 指标补齐映射，避免前端图表空值
  - 路由稳定性修复：将 `/{store_id}` 动态路由后置，避免吞掉 `/count` 等静态路由
  - 路由回归补强：新增 `/stores`、`/regional-summary`、`/performance-ranking` 静态路由防吞用例
  - 路由自动防吞回归：新增“`/{store_id}` 必须声明在所有静态 GET 路由之后”的顺序校验
- [x] 跨店调货申请/审批最小闭环（API + 页面 + 回归测试）
  - 后端新增：`/inventory/transfer-request`、`/inventory/transfer-requests`、`/inventory/transfer-requests/{decision_id}/approve|reject`
  - 审批执行补齐：来源/目标库存变更 + 双向 `TRANSFER` 流水 + 审批链落库
  - 前端新增：`MultiStoreManagement` 调货申请表单 + 待审批列表 + 批准/驳回动作
  - 新增后端测试：`test_inventory_transfer_workflow_api.py`（创建/列表/批准/驳回）
  - 体验增强：列表按门店/状态筛选、手动刷新、审批意见弹窗（驳回必填）与意见回显
  - 契约收敛：后端调货接口补齐 `response_model`；前端抽离 `inventoryDataService` 调货类型与调用
  - 文档补齐：新增《跨店调货API契约V1》统一字段字典、状态机与请求响应示例
  - HTTP 回归补齐：新增 `TestClient` 路由级用例（创建/列表/批准/驳回）
  - 路由顺序修复：`/inventory/{item_id}` 后置，避免吞掉 `/inventory/transfer-requests`
  - 路由回归增强：单段静态 GET 路由统一断言需声明在 `/inventory/{item_id}` 之前，防后续新增静态路径被动态路由吞掉
  - 输入/状态回归补齐：新增同店调货拦截、非正数量拦截、非 pending 申请禁止批准用例

## P2
- [x] 角色权限管理体验优化（页面入口可见性与无权限提示一致性）
  - 非 admin 侧边栏按角色白名单过滤可见页面
  - `store_manager` 可见并可进入 `L5 行动计划`
  - 无权限跳转携带来源路径与角色信息，403 页面展示上下文
- [x] FCT 会计期间与结账能力补强（public API + service）
  - `StandaloneFCTService`：`period_key` 格式校验（`YYYY-MM`）
  - `close_period/reopen_period`：补齐不存在/重复状态校验
  - 单 open 约束：反结账后目标期间为 open，其余 closed（运行时状态覆盖）
  - 补齐单测：service 与 API 层期间端点
  - 关闭期间保护：禁止新增凭证、凭证过账、红冲过账（返回明确错误）
  - 补齐 API 映射测试：关闭期间错误统一映射为 400
  - 账期持久化落库：新增 `FCTPeriod` 模型，`close/reopen/list` 读写 `fct_periods`
  - 兼容修复：增强 `AsyncMock`/非标准行解析，避免测试环境误判已结账

---

## [Claude] 状态
- branch: `main`
- latest: 以 git 最新提交为准
- focus: 后端服务与调度链路持续完善

## [Codex] 状态
- status: completed
- owner: Codex
- task: 跨店调货申请/审批最小闭环（API + 页面 + 回归测试）
- files:
  - `apps/api-gateway/src/api/inventory.py`
  - `apps/api-gateway/tests/test_inventory_transfer_workflow_api.py`
  - `apps/web/src/pages/MultiStoreManagement.tsx`
  - `tasks/collab-sync.md`
  - `apps/api-gateway/src/api/blindbox.py`
  - `apps/api-gateway/src/api/federated.py`
  - `apps/api-gateway/src/api/mobile.py`
  - `apps/api-gateway/tests/test_mobile_api_v1_routes.py`
  - `apps/api-gateway/tests/test_fct_public_periods_api.py`
  - `apps/api-gateway/tests/test_fct_public_voucher_api.py`
  - `apps/api-gateway/tests/test_fct_service.py`
  - `apps/api-gateway/src/services/fct_service.py`
  - `apps/web/src/pages/sm/Home.tsx`
  - `apps/web/src/pages/sm/Shifts.tsx`
  - `apps/web/src/pages/sm/Shifts.module.css`
  - `apps/web/src/pages/sm/Tasks.tsx`
  - `apps/web/src/pages/sm/Tasks.module.css`
  - `apps/web/src/layouts/StoreManagerLayout.tsx`
  - `apps/web/src/services/mobile.types.ts`
  - `apps/web/src/services/mobile.mutation.service.ts`
  - `apps/web/src/pages/sm/Tasks.tsx`
  - `apps/web/src/pages/sm/Tasks.module.css`
  - `apps/web/src/services/mobile.mock.ts`
  - `apps/web/src/services/mobile.query.service.ts`
  - `apps/web/src/services/mobile.mutation.service.ts`
  - `apps/web/src/App.tsx`
  - `tasks/collab-sync.md`
- verify:
  - `python3 -m py_compile apps/api-gateway/src/api/inventory.py`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_inventory_transfer_routes_http.py`（4 passed）
  - `python3 -m pytest -q apps/api-gateway/tests/test_inventory_transfer_routes_http.py`（5 passed，新增静态路由声明顺序断言）
  - `python3 -m pytest -q tests/test_inventory_transfer_routes_http.py`（5 passed，通用单段静态 GET 防吞断言）
  - `python3 -m pytest -q tests/test_inventory_transfer_routes_http.py`（8 passed，新增输入与审批状态校验回归）
  - `python3 -m pytest -q apps/api-gateway/tests/test_inventory_transfer_workflow_api.py apps/api-gateway/tests/test_multi_store_api_routes.py`（14 passed）
  - 文档校对：`docs/跨店调货API契约V1.md`（已添加接口、状态机、规则、错误语义）
  - `python3 -m pytest -q apps/api-gateway/tests/test_multi_store_api_routes.py`（9 passed，含动态路由顺序防吞断言）
  - `python3 -m py_compile apps/api-gateway/src/api/inventory.py`（通过）
  - `npx eslint apps/web/src/pages/MultiStoreManagement.tsx apps/web/src/services/inventoryData.ts`（通过）
  - `npm run build --workspace @zhilian-os/web`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_inventory_transfer_workflow_api.py`（5 passed）
  - `npx eslint apps/web/src/pages/MultiStoreManagement.tsx`（通过）
  - `npm run build --workspace @zhilian-os/web`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_inventory_transfer_workflow_api.py`（5 passed）
  - `npm run build --workspace @zhilian-os/web`（通过）
  - `python3 -m py_compile apps/api-gateway/src/api/inventory.py`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_inventory_transfer_workflow_api.py`（5 passed）
  - `npm run build --workspace @zhilian-os/web`（失败：`MainLayout.tsx` 既有类型错误，非本次改动引入）
  - `python3 -m py_compile apps/api-gateway/src/api/mobile.py`（通过）
  - `python3 -m py_compile apps/api-gateway/src/api/blindbox.py apps/api-gateway/src/api/federated.py`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_mobile_api_v1_routes.py`（3 passed）
  - `pnpm --filter @zhilian-os/web exec eslint src/services/mobile.types.ts src/services/mobile.mutation.service.ts src/pages/sm/Tasks.tsx`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_fct_service.py -k "ListPeriods or PeriodCloseReopen"`（6 passed）
  - `python3 -m pytest -q apps/api-gateway/tests/test_fct_public_periods_api.py`（3 passed）
  - `python3 -m pytest -q apps/api-gateway/tests/test_fct_service.py -k "CreateManualVoucherPersist or UpdateVoucherStatus or VoucherReverseAndVoid"`（16 passed）
  - `python3 -m pytest -q apps/api-gateway/tests/test_fct_public_voucher_api.py apps/api-gateway/tests/test_fct_public_periods_api.py`（6 passed）
  - `python3 -m pytest -q apps/api-gateway/tests/test_fct_service.py -k "PeriodCloseReopen or CreateManualVoucherPersist or UpdateVoucherStatus or VoucherReverseAndVoid"`（21 passed）
  - `pnpm --filter @zhilian-os/web exec eslint src/pages/MultiStoreManagement.tsx`（通过）
  - `python3 -m py_compile apps/api-gateway/src/api/multi_store.py apps/api-gateway/src/services/store_service.py`（通过）
  - `python3 -m pytest -q apps/api-gateway/tests/test_multi_store_api_routes.py`（8 passed，覆盖 /count /stores /regional-summary /performance-ranking）
- note: 已消除 `src.main` 的 blindbox/federated 缺失模块阻断；mobile 上传接口已返回 `file_url`

## [Codex -> Claude] 分工握手（下一轮）
- Codex 接手（前后端联动优先）：
  - P1 多门店管理深化：跨店调货申请/审批最小闭环（API + 页面 + 回归测试）
  - 多门店页数据契约收敛：清理兼容字段，补充接口文档与前端类型定义
  - 多门店关键路由稳定性：继续补 anti-shadow 回归（新增新增静态路径时自动保护）
- Claude 接手（平台与调度优先）：
  - Celery/调度链路稳定性、07:00 类定时任务巡检与告警
  - 生产配置与运维脚本完善（部署、监控、告警规则）
- 同步机制：
  - 以 `main` 分支 commit message 的 `[Codex]` / `[Claude]` 块为准
  - 每次提交后更新本文件对应状态区块
