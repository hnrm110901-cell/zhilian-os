# 协作同步看板（Codex × Claude）

更新时间：2026-03-08

## P0（优先执行）
- [ ] 前端实时通知系统增强（`apps/web/src/pages/NotificationCenter.tsx`）
  - 自动刷新（默认开启）
  - 前台激活立即刷新
  - 刷新状态可见（最近刷新时间）

## P1
- [ ] 核心页面移动端适配补强（先从 `WorkforcePage`、`ActionPlansPage` 开始）

## P2
- [ ] 角色权限管理体验优化（页面入口可见性与无权限提示一致性）

---

## [Claude] 状态
- branch: `main`
- latest: 以 git 最新提交为准
- focus: 后端服务与调度链路持续完善

## [Codex] 状态
- status: completed
- owner: Codex
- task: P0 前端实时通知系统增强
- files:
  - `apps/web/src/pages/NotificationCenter.tsx`
  - `tasks/collab-sync.md`
  - `CODEX.md`
- verify:
  - `pnpm --filter @zhilian-os/web exec eslint src/pages/NotificationCenter.tsx`（通过，0 errors，保留历史 no-explicit-any warnings）
- note: 已完成自动刷新（30秒）、前台激活刷新、手动刷新、最近刷新时间展示；下一步可进入 P1 移动端适配
