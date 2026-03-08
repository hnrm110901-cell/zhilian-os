# COLLAB.md — Claude × Codex 双AI协作规范

> 智链OS项目 AI 协作握手协议 v1.0（2026-03-08）

---

## 握手宣言

**Claude Code**（Anthropic）负责：架构决策 · 后端 Python · Agent推理层 · 复杂业务逻辑 · Code Review
**Codex**（OpenAI）负责：前端 React/TypeScript · 组件重复模式 · 测试脚手架 · API Client · 类型定义

我们共享同一个 Git 仓库，以 **`tasks/collab-sync.md`** 作为实时通信频道。

---

## 分工边界（Land Map）

```
┌─────────────────────────────┬──────────────────────────────┐
│       Claude Code 领地       │         Codex 领地            │
├─────────────────────────────┼──────────────────────────────┤
│ apps/api-gateway/src/       │ apps/web/src/                │
│   ├─ agents/                │   ├─ pages/                  │
│   ├─ services/              │   ├─ components/             │
│   ├─ models/                │   ├─ design-system/          │
│   ├─ api/                   │   ├─ hooks/                  │
│   └─ core/                  │   └─ stores/                 │
│ packages/agents/            │ apps/web/mobile.html         │
│ packages/api-adapters/      │                              │
│ ARCHITECTURE.md             │ API Client 层（同步接口契约）  │
│ CLAUDE.md 更新              │ CODEX.md 更新                │
│ Alembic migrations          │ CSS Modules / 动画           │
│ 测试：pytest (后端)          │ 测试：vitest (前端)           │
├─────────────────────────────┴──────────────────────────────┤
│              共同维护（任一方修改需同步通知）                  │
│  tasks/collab-sync.md    ← 实时状态频道                     │
│  tasks/todo.md           ← 任务看板                         │
│  tasks/api-contracts.md  ← 接口契约（最重要的握手文件）       │
│  .gitignore / package.json / docker-compose.yml            │
└────────────────────────────────────────────────────────────┘
```

---

## Git 协作规范

### 分支命名

```
claude/{feature}   # Claude 开发的功能分支
codex/{feature}    # Codex 开发的功能分支
collab/{feature}   # 需要双方协作的功能
main               # 稳定主干，只接受经过双方 review 的 PR
```

### Commit 前缀

```
[claude] feat: 新功能
[claude] fix:  修复
[claude] test: 测试
[codex]  feat: 新功能
[codex]  fix:  修复
[codex]  ui:   界面组件
[collab] sync: 接口契约更新（双方都必须读）
```

### PR 规则

- 后端 PR → 通知 Codex 检查接口变更是否影响前端
- 前端 PR → 通知 Claude 确认 API 调用姿势是否正确
- 接口契约变更 → 双方必须 review + approve

---

## 实时协作信号（读 `tasks/collab-sync.md`）

每次开始/完成工作前，更新 `tasks/collab-sync.md`：

```markdown
## [Claude] 当前状态
- 正在做：{描述}
- 已完成：{描述} → 影响前端的接口变更见 tasks/api-contracts.md
- 需要Codex：{具体请求}

## [Codex] 当前状态
- 正在做：{描述}
- 已完成：{描述}
- 需要Claude：{具体请求}
```

---

## 接口契约规范（`tasks/api-contracts.md`）

后端新增/修改接口时，Claude 必须在 `tasks/api-contracts.md` 中同步：
- 端点路径 + HTTP方法
- 请求参数 Schema（TypeScript 类型）
- 响应 Schema（TypeScript 类型）
- 错误码说明
- BFF端点（如有）

Codex 在看到更新后，根据契约生成前端 API Client。

---

## 优势发挥约定

### Claude 发挥优势的场景
- Agent 状态机设计（LangGraph 节点/边/条件）
- 复杂 SQL 查询优化（防注入、防零除、分区裁剪）
- 跨服务事务设计（分布式一致性）
- 架构决策记录（ADR）
- Code Review 安全审查

### Codex 发挥优势的场景
- React 组件快速生成（ZCard/ZKpi/ZTable 模式复用）
- CSS Module 样式实现
- TypeScript 类型推导和泛型
- Vitest 单元测试脚手架
- 重复性 CRUD 页面生成

---

## 冲突解决规则

1. **文件所有权冲突**：按领地边界（Land Map）解决，领地内的文件由对应方最终决定
2. **接口设计分歧**：在 `tasks/collab-sync.md` 中提出，以用户需求为准
3. **代码风格冲突**：遵循 CLAUDE.md 中的命名规范（后端）/ 前端设计系统规范（前端）

---

## 当前握手状态

**握手时间**: 2026-03-08
**Claude 签名**: ✅ 就绪，当前在 Phase 8 后端
**Codex 签名**: ⏳ 等待接入
**下一个协作目标**: Phase 8 Month 2 前端「员工健康」Tab 完善
