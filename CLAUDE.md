# CLAUDE.md — 智链OS 工作规范

---

## ⚡ Level 0 — 全局宪法（永久底座，每次会话必读）

**项目定位：** 智链OS 是面向餐饮连锁的智能体操作系统，通过 10 个专属 AI Agent 为门店提供自动化运营决策。

### 核心宪法（5条不可违反）

1. **正确性 > 简洁 > 性能**：有 bug 的快代码不如正确的慢代码
2. **最小化影响**：每次变更只触碰必要的文件，不附带重构
3. **不造轮子**：能用现有 service/model 就不新建文件
4. **安全边界**：所有外部输入必须验证；SQL 用参数化查询，绝不拼接字符串
5. **死代码即技术债**：发现从未被调用的方法立即删除，不留"备用"

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
  → 读取对应模块的 CONTEXT.md（Level 2）
  → 路径规则：{module_root}/CONTEXT.md

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
```
