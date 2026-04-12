# CLAUDE.md — 屯象OS 工作规范

---

## ⚡ Level 0 — 全局宪法（永久底座，每次会话必读）

**项目定位：** 屯象OS 是面向餐饮连锁的 AI 驱动经营决策系统（对外称"屯象经营助手"），核心目标是帮连锁老板每年多赚 30 万+（成本率降低 2 个点）。North Star Metric：**续费率 ≥ 95%**。

**技术栈：** Python/FastAPI + PostgreSQL (Alembic) | React/TypeScript + Vite | LangChain + LangGraph | Claude API (claude-sonnet-4-6 生产 / claude-opus-4-6 架构)

**部署：** 42.194.229.21 / zlsjos.cn (Nginx + Uvicorn) | 企业微信集成 | Docker + K8s

### 核心宪法（5条不可违反）

1. **正确性 > 简洁 > 性能**：有 bug 的快代码不如正确的慢代码
2. **最小化影响**：每次变更只触碰必要的文件，不附带重构
3. **不造轮子**：能用现有 service/model 就不新建文件
4. **安全边界**：所有外部输入必须验证；SQL 用参数化查询，绝不拼接字符串
5. **死代码即技术债**：发现从未被调用的方法立即删除，不留"备用"

### 产品导向规则（5条，v2.0新增）

6. **¥优先**：任何 Service 的输出，如果涉及成本/收入/损耗，必须包含 `¥金额` 字段（单位：元，保留2位小数）
7. **决策型**：推送/建议内容必须包含：建议动作 + 预期¥影响 + 置信度 + 一键操作入口；纯信息不推送
8. **MVP纪律**：不在10个MVP功能之外新增功能，除非客户明确要求且影响续费（10个MVP见 tasks/todo.md）
9. **案例意识**：每个 Sprint 结束时确认本次改动的关键数据（成本率变化/节省¥/决策采纳数）可被 `case_story_generator.py` 采集到
10. **离线优先**：新增的查询类功能必须考虑离线降级方案（无网络时返回缓存数据而非报错）

### 绝不事项（Never-Do List）

- ❌ 永远不要在 SQL text() 里用字符串拼接参数（用 `:param` 绑定）
- ❌ 永远不要在 INTERVAL 字符串里嵌入参数（用 `:n * INTERVAL '1 day'`）
- ❌ 永远不要在 production 代码里留 TODO / FIXME 超过一次 commit
- ❌ 永远不要在没读懂文件的情况下修改它
- ❌ 永远不要一次性加载超过 10 个文件（走 Level 2/3 分级加载）
- ❌ 永远不要跳过测试直接标记任务完成

### 命名规范（极简版）

| 类型 | 规范 | 示例 |
|------|------|------|
| Python 类 | PascalCase | `StoreMemoryService` |
| Python 函数/变量 | snake_case | `compute_peak_patterns` |
| 私有方法 | `_` 前缀 | `_fetch_from_db` |
| 数据库表 | snake_case 复数 | `order_items` |
| Redis Key | `namespace:entity_id` | `store_memory:S001` |
| Agent 包 | `packages/agents/{domain}/` | `packages/agents/schedule/` |

---

## 📋 上下文分级加载协议（Level Loading Protocol）

每个新任务必须走以下 5 个阶段，**禁止跳级**：

```
Phase 1 [必须] 加载全局宪法
  → 默读本文件 Level 0 宪法

Phase 2 [必须] 确认大地图
  → 读取 ARCHITECTURE.md（Level 1 全景图）
  → 确认任务涉及哪个模块/子系统

Phase 3 [按需] 加载模块上下文
  → 读取对应模块的 CLAUDE.md 或 .claude/context/ 文件（Level 2）
  → 路径规则见下方「关键路径速查」

Phase 4 [精确] 只读必要文件（≤8个）
  → 先用 Grep/Glob 定位，再用 Read 读取
  → 如需更多文件：输出「需要额外文件清单」等待确认

Phase 5 [执行前] 输出变更蓝图
  → 当前模块状态摘要（3句话）
  → 拟变更文件清单 + 每个文件的变更意图（1句话）
  → 风险点 + 级联影响评估
  → 等待确认后执行
```

**何时使用子代理（Level 4）：**
- 需要扫描 20+ 文件做架构分析
- 多模块并行研究任务
- 子代理只返回摘要结论，不污染主会话

---

## 🔧 工作流规范

### 计划节点
- 非平凡任务（3步以上/架构决策）：必须先写计划到 `tasks/todo.md`
- 遇到意外：立即停止，重新计划，不强推

### 验证节点
- 标记完成前：问「一个高级工程师会批准这个吗？」
- 异步代码：必须用 `pytest-asyncio` 跑通；同步纯函数：至少手写用例验证
- 数据库变更：必须有对应 Alembic migration

### 错误修复
- 收到错误报告：直接定位 → 修复 → 验证。不要问「能告诉我更多信息吗？」

### 自我提升
- 用户纠正后：立即更新 `tasks/lessons.md`，写清楚「踩坑原因 + 正确做法」

---

## 📁 任务管理

1. **先计划**：写入 `tasks/todo.md`（可勾选格式）
2. **跟踪进度**：每完成一项立即打勾
3. **记录经验**：修正后更新 `tasks/lessons.md`
4. **会话开始**：先读 `tasks/lessons.md` 防止重蹈覆辙

---

## 🗂 关键路径速查

```
ARCHITECTURE.md              ← Level 1 全景图（读这里了解整体）
apps/api-gateway/CONTEXT.md  ← Level 2 API层上下文
packages/agents/CONTEXT.md   ← Level 2 Agent层上下文
tasks/todo.md                ← 当前任务清单
tasks/lessons.md             ← 经验教训（每次开始先读！）
CODEX.md                     ← Codex/Claude 共识协议（开始前必读）
docs/collaboration-workflow.md        ← 多工具分支/部署协作规则
docs/agent-collaboration-standard.md  ← Claude/Codex/CLI 并发协同标准
```

---

## 🎯 四层 Ontology 架构（速览）

```
Perception（感知）→ Ontology（本体）→ Reasoning（推理）→ Action（行动）
  企微/POS/飞书      62个Model       11个Agent        企微推送/一键确认
```

**11个 Agent 领域：** schedule | order | inventory | service | training | performance | decision | reservation | banquet | private_domain | dish_rd

**详见：** `.claude/context/architecture.md`

---

## ⚡ MAX 配额管理策略

### 模型选择规则
- **架构决策 / 复杂推理**：Opus（计划阶段）
- **功能实现 / 迭代修复**：Sonnet（执行阶段）
- 计划用 Opus 想清楚，执行切 Sonnet 省配额

### 上下文管理
- 上下文达到 50% 时执行 `/compact`
- 每完成一个功能模块执行 `/clear` 重置
- 小任务直接执行，不要过度包装工作流

### 日常节奏
| 时段 | 工具 | 任务类型 |
|------|------|---------|
| 早晨 | Claude.ai (Opus) | 架构决策、PRD、Agent 设计 |
| 上午 | Claude Code (Opus) | 复杂功能实现，Plan Mode |
| 下午 | Claude Code (Sonnet) | 迭代修复、测试、文档 |
| 傍晚 | Claude.ai (Sonnet) | 代码审查、明日任务分解 |

---

## 🎨 前端重构规范（v3.0 角色驱动架构）

> 对应规范文档：`屯象OS_前后端重构_产品研发开发规范_V1.0`

### 角色路由约定

| 角色 | 路由前缀 | 设备 | 说明 |
|------|----------|------|------|
| 店长 | `/sm`    | 手机 | 移动优先，底部Tab导航 |
| 厨师长 | `/chef` | 手机 | 食材/损耗/采购视图 |
| 楼面经理 | `/floor` | 平板 | 排队/预订/服务质量 |
| 总部 | `/hq`   | 桌面 | 多店监控/财务/决策 |

**原有 `/` 路由保留**，新角色路由并行运行，迁移完成后再切换默认。

### 设计系统规则

- **Design Token**：所有颜色/间距/圆角 → `src/design-system/tokens/index.ts` CSS 变量
- **品牌色**：`#FF6B2C`（`var(--accent)`）
- **字体栈**：`'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'SF Pro Display'`（禁止 Inter/Roboto）
- **Z组件**：基础 UI 使用 `src/design-system/components/` 内的 Z 前缀组件（ZCard/ZKpi/ZBadge/ZButton/ZInput/ZEmpty/ZSkeleton/ZAvatar）
- **业务组件**：复合业务组件在同目录（HealthRing/UrgencyList/ChartTrend）
- **CSS Modules**：每个组件必须配套 `.module.css`，禁止内联样式（仅动态值除外）
- **图表**：仍使用 `ReactECharts`（大图表）；小卡片趋势用 `ChartTrend`（原生 Canvas）

### BFF 聚合规则

- BFF 端点：`GET /api/v1/bff/{role}/{store_id}`
- 每个角色首屏只发 **1个 BFF 请求**（30s Redis 缓存 + `?refresh=true` 强制刷新）
- 子调用失败 → 降级返回 `null`，前端用 `ZEmpty` 占位，不阻塞整屏

### 前端数据获取规范

```typescript
// ✅ 正确：apiClient + useState（当前项目约定）
const resp = await apiClient.get('/api/v1/bff/sm/...');

// ❌ 禁止：直接 fetch/axios；不要引入 TanStack Query（尚未安装）
```

### 命名规范（前端）

| 类型 | 规范 | 示例 |
|------|------|------|
| React 组件 | PascalCase | `SmHome`, `ZCard` |
| CSS Module 类 | camelCase | `.healthRow`, `.tabBar` |
| BFF 端点角色前缀 | 小写2字母 | `sm`, `chef`, `floor`, `hq` |
| 页面路径 | 角色前缀/页面 | `pages/sm/Home.tsx` |
| Layout 文件 | `{Role}Layout.tsx` | `StoreManagerLayout.tsx` |

---

## 🔒 审计修复期特别约束（2026-03 至 2026-06）

> 基于 v6 代码审计结果，以下约束在修复期间强制执行。

### 异常处理
- 修改 `except Exception` 时，必须替换为具体异常类型（参考 `src/core/exceptions.py` 层级）
- 新代码禁止使用 `except Exception`（最外层兜底除外，且必须加 `exc_info=True`）
- 新增 POS 适配器代码必须附带 ≥3 个测试用例

### 安全
- 禁止在 `config/merchants/` 目录下提交任何文件
- 所有模型调用必须通过 `ModelRouter`（`src/core/model_router.py`），不直接调用 API
- 数据库新表必须包含 `tenant_id` + RLS 策略（使用 `app.current_tenant`，禁止 NULL 绕过）

### 提交前检查
- `git-secrets` 扫描通过
- 涉及的 P1 模块 pytest 通过
- 无新增 broad except（用 ruff S 规则检查）
