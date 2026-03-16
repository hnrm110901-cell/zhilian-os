# AGENTS.md — 屯象OS AI Agent 工作指令

> 本文件对所有 AI 编码工具（Codex / Copilot / Claude Code / Cursor 等）生效。
> 进入本仓库后必须首先读取本文件，再执行任何任务。

---

## 强制前置条件

**开始任何开发前先读 `CODEX.md`**；涉及以下目录的改动，必须按 `CODEX.md` 中第 8 章《防冲突协议》执行：

- `apps/api-gateway/src/api/`
- `apps/api-gateway/src/core/`
- `apps/api-gateway/src/models/`
- `apps/api-gateway/src/services/`
- `apps/api-gateway/scripts/`
- `apps/web/src/pages/`
- `apps/web/src/layouts/`
- `apps/web/src/App.tsx`

违反防冲突协议的 PR 将被自动拒绝。

---

## 角色分工

| 工具 | 角色 | 可写目录 | 只读目录 |
|------|------|---------|---------|
| **Claude Code** | 架构师 | `src/core/` `src/models/` `src/services/` `src/api/` `src/agents/` `App.tsx` `*Layout.tsx` | `src/design-system/` |
| **Codex** | 工程师 | `src/pages/` `src/components/` `src/design-system/` `src/hooks/` `tests/` | `src/core/` `src/models/` `App.tsx` |
| **CLI** | 运维 | `.github/` `scripts/` `k8s/` `Makefile` | `src/` |

---

## 关键约定速查

1. **apiClient.get\<T\>() 直接返回 T** — 不要再访问 `.data`，数据已解包
2. **CSS Modules** — 每个组件配套 `.module.css`，camelCase 类名，禁止内联样式
3. **Z 组件优先** — ZCard/ZKpi/ZBadge/ZButton/ZTable/ZEmpty/ZSkeleton，其次 Ant Design
4. **金额** — 数据库存分(fen)，API 返回元(yuan)，前端显示 ¥X,XXX.XX
5. **字体** — `'Noto Sans SC'` 系列，禁止 Inter/Roboto
6. **Git 分支** — 功能分支 `feat/codex-*`，合并目标 `develop`，禁止直推 main
7. **提交格式** — `feat(scope): 描述` / `fix(scope): 描述`（Conventional Commits）

---

## 新增页面流程

```
1. 基于 develop 创建 feat/codex-xxx 分支
2. 新建 XxxPage.tsx + XxxPage.module.css
3. 提交 PR，描述中标注 [NEED-ROUTE] 和 [NEED-NAV]
4. Claude Code 在 App.tsx 和 Layout 中注册路由后合并
```

---

## 完整规范

详见 [`CODEX.md`](./CODEX.md) — 包含 12 章完整协同协议。
