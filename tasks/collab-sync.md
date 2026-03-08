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

## P1
- [x] 核心页面移动端适配补强（`WorkforcePage`、`ActionPlansPage`）
  - 小屏筛选控件改为全宽
  - 表格开启横向滚动
  - 抽屉宽度改为 `92vw`（移动端）
  - 工具栏与操作按钮优化换行

## P2
- [x] 角色权限管理体验优化（页面入口可见性与无权限提示一致性）
  - 非 admin 侧边栏按角色白名单过滤可见页面
  - `store_manager` 可见并可进入 `L5 行动计划`
  - 无权限跳转携带来源路径与角色信息，403 页面展示上下文

---

## [Claude] 状态
- branch: `main`
- latest: 以 git 最新提交为准
- focus: 后端服务与调度链路持续完善

## [Codex] 状态
- status: completed
- owner: Codex
- task: 移动端首页/班次/任务 V1 骨架接入
- files:
  - `apps/web/src/pages/sm/Home.tsx`
  - `apps/web/src/pages/sm/Shifts.tsx`
  - `apps/web/src/pages/sm/Shifts.module.css`
  - `apps/web/src/pages/sm/Tasks.tsx`
  - `apps/web/src/pages/sm/Tasks.module.css`
  - `apps/web/src/layouts/StoreManagerLayout.tsx`
  - `apps/web/src/services/mobile.types.ts`
  - `apps/web/src/services/mobile.mock.ts`
  - `apps/web/src/services/mobile.query.service.ts`
  - `apps/web/src/services/mobile.mutation.service.ts`
  - `apps/web/src/App.tsx`
  - `tasks/collab-sync.md`
- verify:
  - `pnpm --filter @zhilian-os/web exec eslint src/pages/sm/Home.tsx src/pages/sm/Shifts.tsx src/pages/sm/Tasks.tsx src/layouts/StoreManagerLayout.tsx src/services/mobile.types.ts src/services/mobile.mock.ts src/services/mobile.query.service.ts src/services/mobile.mutation.service.ts`（通过）
- note: 三页已同源 DTO 化；下一步补充状态机转移校验和任务详情抽屉
