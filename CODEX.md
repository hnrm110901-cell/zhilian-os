# CODEX.md — 屯象OS 多端协同开发规范（Claude Code ↔ Codex 共识协议）

> **版本**: v2.1 | **生效日期**: 2026-03-15 | **维护人**: 微了一
>
> 本文件是 Claude Code 与 Codex 之间的**绑定协议**。
> 任何 AI 工具在本仓库工作前，必须完整阅读本文件。
> 冲突时以本文件为准，CLAUDE.md 为补充。

---

## ⚠️ 强制约束（开始任何开发前必读）

**开始任何开发前先读完本文件。** 涉及以下目录的改动，必须按第 8 章《防冲突协议》执行：

- `apps/api-gateway/src/api/` — API 路由（Claude Code 所有权）
- `apps/api-gateway/src/core/` — 核心模块（Claude Code 所有权）
- `apps/api-gateway/src/models/` — 数据模型（Claude Code 所有权）
- `apps/api-gateway/src/services/` — 业务服务（Claude Code 所有权）
- `apps/api-gateway/scripts/` — 后端脚本（Claude Code 所有权）
- `apps/web/src/pages/` — 页面组件（Codex 优先，但需遵循模板规范）
- `apps/web/src/layouts/` — 布局组件（Claude Code 所有权，Codex 只读）
- `apps/web/src/App.tsx` — 路由配置（Claude Code 所有权，Codex 只读）

**违反防冲突协议的改动将被拒绝。** 不确定时，在 PR 描述中标注 `[NEED-REVIEW]` 请求 Claude Code 审查。

---

## 0. 协议目的

屯象OS 由多个 AI 工具并行开发：

| 工具 | 角色 | 主战场 |
|------|------|--------|
| **Claude Code** | 架构师 — 核心模块、复杂业务逻辑、系统集成 | `src/core/` `src/agents/` `src/services/` `src/models/` `src/api/` |
| **Codex** | 工程师 — UI 组件、页面补全、代码重构、单元测试 | `src/pages/` `src/components/` `src/design-system/` `tests/` |
| **Claude CLI** | 运维工程师 — 自动化脚本、CI/CD、批量操作 | `.github/` `scripts/` `k8s/` `Makefile` |

**核心原则**：每个工具只修改自己管辖的文件。跨域修改必须通过 PR，不得直接推送。

---

## 1. Git 分支策略（强制执行）

```
main                    ← 生产分支，只接受 develop 的 PR
develop                 ← 集成分支，所有功能分支合并到这里
feat/claude-code-*      ← Claude Code 功能分支
feat/codex-*            ← Codex 功能分支
feat/cli-*              ← CLI 脚本分支
fix/*                   ← bug 修复分支
```

### 规则

1. **禁止直推 main/develop** — 必须通过 PR
2. **每个工具只创建自己前缀的分支** — Codex 只创建 `feat/codex-*` 分支
3. **每次开始工作前** — `git pull origin develop --rebase`
4. **合并前** — 必须通过 CI（TypeScript 检查 + Python 语法 + 测试）
5. **提交格式** — Conventional Commits（见 `.commitlintrc.json`）

```bash
# 正确的提交消息
feat(web): 添加供应商评分详情页          # Codex 前端功能
fix(ui): 修复 ZCard 在暗色主题下的边框   # Codex UI 修复
test(api): 添加订单 API 单元测试         # Codex 测试
refactor(web): 提取公共表格筛选组件      # Codex 重构

# scope 枚举（完整列表见 .commitlintrc.json）
# kernel | api | web | ui | agents | models | services | platform
# integrations | hr | pos | ci | deploy | db | auth | bff | im
# sm | hq | chef | floor
```

---

## 2. 项目概况（Codex 必读）

### 2.1 产品定位

屯象OS 是面向中小连锁餐饮（3～100 门店）的 AI 驱动经营决策系统。定位为**餐饮行业的 Palantir**——不替换 POS，做 POS 之上的智能中间层。

**North Star Metric**: 续费率 ≥ 95%

### 2.2 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | React | 19.2.0 |
| 类型系统 | TypeScript | 5.9.3 |
| 构建工具 | Vite | 7.3.1 |
| UI 库 | Ant Design 5 + Z 设计系统 | 5.13.0 |
| 状态管理 | Zustand | 4.4.7 |
| HTTP 客户端 | Axios（封装为 apiClient） | 1.6.5 |
| 图表 | ECharts 5 + echarts-for-react | 5.4.3 |
| 日期 | dayjs | 1.11.10 |
| CSS 方案 | CSS Modules | — |
| 后端框架 | FastAPI | async |
| ORM | SQLAlchemy 2.0 | async + asyncpg |
| 数据库 | PostgreSQL 15 | UUID 主键 |
| 缓存 | Redis + Sentinel | — |
| 测试 | Vitest（前端）/ pytest（后端） | — |

### 2.3 代码规模（截至 2026-03-15）

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `apps/web/src/pages/` | 178 .tsx | 页面组件 |
| `apps/api-gateway/src/api/` | 235 .py | API 路由 |
| `apps/api-gateway/src/services/` | 299 .py | 业务服务 |
| `apps/api-gateway/src/models/` | 130 .py | 数据模型 |

---

## 3. 前端规范（Codex 核心战场）

### 3.1 目录结构

```
apps/web/src/
├── components/              # 共享业务组件
├── contexts/                # React Context（AuthContext 等）
├── design-system/
│   ├── tokens/index.ts      # CSS 变量 Token 定义
│   └── components/          # Z 前缀基础组件
├── hooks/                   # 自定义 Hook
├── layouts/                 # 布局组件
│   ├── PlatformAdminLayout.tsx  # 管理后台布局
│   ├── StoreManagerLayout.tsx   # 店长移动端布局
│   ├── HQLayout.tsx             # 总部桌面端布局
│   └── MainLayout.tsx           # 通用布局
├── pages/
│   ├── platform/            # 管理后台页面（/platform/*）
│   ├── sm/                  # 店长页面（/sm/*）
│   ├── hq/                  # 总部页面（/hq/*）
│   ├── chef/                # 厨师长页面（/chef/*）
│   ├── floor/               # 楼面经理页面（/floor/*）
│   ├── hr/                  # HR 模块页面
│   └── employee/            # 员工自助页面
├── services/
│   └── api.ts               # API 客户端（唯一 HTTP 出口）
└── utils/
    └── message.ts           # handleApiError 等工具函数
```

### 3.2 API 客户端（铁律 — 违反此条必出 bug）

```typescript
import { apiClient } from '../services/api';       // platform 页面用 '../../services/api'
import { handleApiError } from '../utils/message';  // 同上

// ✅ 正确 — apiClient.get<T>() 直接返回 T（response.data 已解包）
const data = await apiClient.get<MerchantList>('/api/v1/merchants');
// data 就是 MerchantList 类型，不要再 .data

// ✅ 正确 — POST
const result = await apiClient.post<CreateResult>('/api/v1/orders', payload);

// ✅ 正确 — 错误处理
try {
  const data = await apiClient.get<T>('/api/v1/xxx');
  setState(data);
} catch (err) {
  handleApiError(err, '加载失败');
}

// ❌ 致命错误 — 千万不要这样做
const resp = await apiClient.get('/api/v1/xxx');
const data = resp.data;  // ← 这里会 undefined！data 已经是解包后的了

// ❌ 禁止 — 绕过 apiClient
fetch('/api/v1/xxx');          // 不要用
axios.get('/api/v1/xxx');      // 不要用
```

### 3.3 组件体系

#### Z 设计系统组件（优先使用）

```typescript
import {
  ZCard, ZKpi, ZBadge, ZButton, ZInput,
  ZEmpty, ZSkeleton, ZAvatar, ZSelect, ZTable
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
```

#### Ant Design 组件（补充使用）

```typescript
import { Drawer, Modal, Form, Input, Select, Tabs, Table, Tag, Switch } from 'antd';
import { ReloadOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons';
```

#### 使用优先级

1. **Z 组件** — ZCard, ZKpi, ZBadge, ZButton, ZTable, ZEmpty, ZSkeleton（基础 UI 优先用 Z）
2. **Ant Design** — Drawer, Modal, Form, Tabs, DatePicker（复杂交互用 Ant）
3. **自定义** — 仅在 Z + Ant 都不能满足时才自建

### 3.4 设计 Token

```css
/* 品牌色 */
var(--tx-brand-500)    /* #0AAF9A — 主色调 mint */
var(--accent)          /* #FF6B2C — 强调色 */

/* 暗色主题（默认） */
var(--bg)              /* #0B1A20 */
var(--surface)         /* #0D2029 */

/* 文字层级 */
var(--text-primary)    /* rgba(255,255,255, 0.92) */
var(--text-secondary)  /* rgba(255,255,255, 0.65) */
var(--text-tertiary)   /* rgba(255,255,255, 0.38) */

/* 间距 */
var(--sp-1) ~ var(--sp-8)

/* 圆角 */
var(--radius-sm) var(--radius-md) var(--radius-lg)

/* 动画 */
var(--transition-fast)   /* 0.15s */
var(--transition-base)   /* 0.2s */
var(--transition-slow)   /* 0.3s */

/* 语义色 */
var(--tx-success)   var(--tx-warning)   var(--tx-danger)   var(--tx-info)
```

### 3.5 样式规范

```css
/* ✅ 每个页面/组件必须有配套的 .module.css */
/* 文件名: XxxPage.module.css 或 XxxComponent.module.css */

/* ✅ camelCase 类名 */
.pageContainer { }
.statsRow { }
.cardHeader { }

/* ❌ 禁止 kebab-case */
.page-container { }  /* 不要这样 */

/* ❌ 禁止内联样式（动态值除外） */
<div style={{ color: 'red' }}>   /* 不要这样 */
<div style={{ width: `${percent}%` }}>  /* 动态值可以 */
```

### 3.6 页面模板（标准写法）

```typescript
// XxxPage.tsx — Codex 创建新页面时必须遵循此结构
import React, { useState, useEffect, useCallback } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { ZCard, ZButton, ZTable, ZEmpty, ZSkeleton, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './XxxPage.module.css';
import dayjs from 'dayjs';

// ── 类型定义（页面内 inline，不新建 types.ts） ─────────
interface XxxItem {
  id: string;
  name: string;
  status: string;
  created_at: string;
  amount: number;     // 后端返回元（yuan），2位小数
}

// ── 组件 ───────────────────────────────────────────────
const XxxPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<XxxItem[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiClient.get<{ items: XxxItem[]; total: number }>(
        '/api/v1/xxx'
      );
      setData(result.items);
    } catch (err) {
      handleApiError(err, '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <ZSkeleton rows={8} />;

  return (
    <div className={styles.page}>
      {/* 页面内容 */}
    </div>
  );
};

export default XxxPage;
```

### 3.7 路由注册（新增页面时）

```typescript
// apps/web/src/App.tsx — ⚠️ 此文件由 Claude Code 维护
// Codex 不直接修改，在 PR 描述中注明需要的路由变更

// 1. 添加 lazy import（在对应区块）
const XxxPage = lazy(() => import('./pages/platform/XxxPage'));

// 2. 添加 Route（在 /platform 父路由下）
<Route path="xxx" element={<XxxPage />} />

// 3. 导航菜单项（PlatformAdminLayout.tsx — 同样由 Claude Code 维护）
{ key: 'xxx', path: '/platform/xxx', label: 'Xxx管理', icon: <XxxOutlined /> }
```

### 3.8 角色路由映射

| 角色 | 路由前缀 | 设备 | Layout |
|------|----------|------|--------|
| 平台管理员 | `/platform` | 桌面 | `PlatformAdminLayout` |
| 总部 | `/hq` | 桌面 | `HQLayout` |
| 店长 | `/sm` | 手机 | `StoreManagerLayout` |
| 厨师长 | `/chef` | 手机 | `ChefLayout` |
| 楼面经理 | `/floor` | 平板 | `FloorLayout` |

### 3.9 字体规则

```css
font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
/* ❌ 禁止 Inter / Roboto */
```

---

## 4. 后端规范（Claude Code 主导，Codex 只读理解）

> Codex 通常不直接修改后端代码，但需要理解后端接口以正确对接。

### 4.1 API 端点模式

```
GET    /api/v1/{resource}              # 列表（支持 ?page=&size=&status= 筛选）
GET    /api/v1/{resource}/{id}         # 详情
POST   /api/v1/{resource}             # 创建
PUT    /api/v1/{resource}/{id}         # 全量更新
PATCH  /api/v1/{resource}/{id}         # 部分更新
DELETE /api/v1/{resource}/{id}         # 删除
```

### 4.2 认证机制

```typescript
// 前端在 localStorage 存储 token
localStorage.setItem('token', access_token);

// apiClient 自动在请求头注入
// Authorization: Bearer <token>

// 401 响应 → 自动清除 token → 跳转 /login
```

### 4.3 角色枚举（13 个）

| UserRole | 中文 | 典型场景 |
|----------|------|---------|
| `ADMIN` | 系统管理员 | 全部权限 |
| `STORE_MANAGER` | 店长 | 门店管理、排班、库存 |
| `ASSISTANT_MANAGER` | 店长助理 | 辅助店长 |
| `FLOOR_MANAGER` | 楼面经理 | 排队、预订、服务质量 |
| `CUSTOMER_MANAGER` | 客户经理 | 会员、私域 |
| `TEAM_LEADER` | 领班 | 组内管理 |
| `WAITER` | 服务员 | 服务任务 |
| `HEAD_CHEF` | 厨师长 | 食材、损耗、菜品 |
| `STATION_MANAGER` | 档口负责人 | 档口出品 |
| `CHEF` | 厨师 | 出品 |
| `WAREHOUSE_MANAGER` | 库管 | 库存、采购 |
| `FINANCE` | 财务 | 对账、报表 |
| `PROCUREMENT` | 采购 | 供应商、订货 |

### 4.4 金额规范

```
数据库存储：分（fen），整数型
API 返回：元（yuan），保留 2 位小数
前端展示：¥1,234.56

// 目前大部分 API 已在后端转为元返回
// 少数旧接口可能返回分，需确认具体接口
```

### 4.5 后端 API 端点定义模式（Codex 理解即可）

```python
# FastAPI 路由模式
router = APIRouter(prefix="/api/v1/xxx", tags=["xxx"])

@router.get("/")
async def list_items(
    page: int = 1,
    size: int = 20,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    # 返回 { items: [...], total: N, page: N, size: N }
    ...

@router.get("/{item_id}")
async def get_item(item_id: str, db: AsyncSession = Depends(get_db)):
    ...

@router.post("/")
async def create_item(data: CreateRequest, db: AsyncSession = Depends(get_db)):
    ...
```

---

## 5. 多租户与数据隔离

```
brand_id → PostgreSQL schema
每个品牌一个独立 schema，公共数据在 public schema

示例：
  BRD_CZYZ0001 → schema "czq"（尝在一起）
  BRD_ZQX00001 → schema "zqx"（最黔线）
```

**前端注意**：API 请求中 `brand_id` 和 `store_id` 是租户隔离的关键参数，不要遗漏。

---

## 6. 已有能力清单（防止重复开发）

### 6.1 已完成的平台管理页面（/platform/*）

| 页面 | 路由 | 状态 |
|------|------|------|
| 实时控制台 | `/platform` | ✅ |
| 效能分析 | `/platform/analytics` | ✅ |
| 商户管理（列表+详情 7Tab） | `/platform/merchants` | ✅ |
| 门店管理 | `/platform/stores` | ✅ |
| 接入配置 | `/platform/integrations` | ✅ |
| 边缘节点 | `/platform/edge-nodes` | ✅ |
| 开放平台 | `/platform/open-platform` | ✅ |
| 用户管理 | `/platform/users` | ✅ |
| 角色权限 | `/platform/roles` | ✅ |
| Agent 监控 | `/platform/agents` | ✅ |
| 本体图管理 | `/platform/ontology` | ✅ |
| 数据主权 | `/platform/data-sovereignty` | ✅ |
| 系统监控 | `/platform/monitoring` | ✅ |
| 灰度发布 | `/platform/feature-flags` | ✅ |
| 审计日志 | `/platform/audit-log` | ✅ |
| 备份管理 | `/platform/backup` | ✅ |
| 系统设置 | `/platform/settings` | ✅ |

### 6.2 外部集成（18 个功能页面）

**Month 1-3 基础集成**：
电子发票、饿了么、支付对账、抖音团购、食品安全、健康证、供应商B2B、点评监控、银行对账

**Batch 1 数据融合层**：
集成中心、全渠道营收、三角对账

**Batch 2 智能决策层**：
供应商智能、评论行动、合规引擎

**Batch 3 自动化闭环层**：
智能采购、日清日结、指挥中心

### 6.3 角色端页面

| 角色 | 已有页面 |
|------|---------|
| 店长 `/sm` | 首页、库存、排班、损耗、员工、HR快捷 |
| 总部 `/hq` | 仪表盘、商户管理、分析、决策 |
| 厨师长 `/chef` | 首页、食材、损耗、菜品 |
| 楼面 `/floor` | 首页、排队、预订 |

### 6.4 核心基础设施（不要重建）

| 能力 | 文件 | 说明 |
|------|------|------|
| API 客户端 | `services/api.ts` | Axios 封装，自动 token 注入 |
| 认证上下文 | `contexts/AuthContext.tsx` | 登录/登出/用户信息 |
| 信号总线 | `signal_bus_service.py` | 后端事件路由引擎 |
| 成本真相引擎 | `cost_truth_engine.py` | 5 因子成本归因 |
| BFF 聚合层 | `bff.py` | 4 角色首屏数据聚合 |
| 工作流引擎 | `workflow_engine.py` | 6 阶段日常规划 |
| WebSocket Hook | `hooks/useWebSocket.ts` | 实时通知推送 |
| 手势 Hook | `hooks/useSwipe.ts` | 移动端手势支持 |
| 推荐卡片 | `components/RecommendationCard.tsx` | SM/HQ 首页推荐 |
| 通知中心 | `components/NotificationCenter.tsx` | 消息面板 |
| 权限矩阵 | `core/permission_matrix.py` | RBAC 角色-权限映射 |

---

## 7. Codex 的职责与边界

### 7.1 Codex 可以做 ✅

- **UI 优化**：样式微调、响应式适配、暗色主题修复
- **组件提取**：识别重复 UI 模式，提取为 Z 设计系统组件
- **测试补全**：为现有页面/组件编写 Vitest 单元测试
- **页面补全**：根据已有 API 端点创建缺失的前端页面
- **代码重构**：大文件拆分、类型安全增强、无用代码清理
- **可访问性**：aria-label、键盘导航、焦点管理
- **文档**：组件 Storybook、JSDoc 注释

### 7.2 Codex 不可以做 ❌

- ❌ 修改 `src/core/` 下的核心模块（auth, database, config）
- ❌ 修改 Agent 系统（`src/agents/`, `packages/agents/`）
- ❌ 创建新的数据库模型（需要 Alembic 迁移，Claude Code 负责）
- ❌ 修改 CI/CD 配置（`.github/workflows/*` — CLI 负责）
- ❌ 修改 `main.py` 路由注册（Claude Code 负责）
- ❌ 修改 `App.tsx` 路由配置（Claude Code 负责）
- ❌ 修改 `*Layout.tsx` 布局组件（Claude Code 负责）
- ❌ 修改多租户逻辑（高风险，Claude Code 负责）
- ❌ 引入新的 npm 依赖（需要在 PR 中说明理由，经批准后安装）

---

## 8. 防冲突协议

### 8.1 文件所有权矩阵

| 文件 / 目录 | 所有者 | 其他工具权限 |
|-------------|--------|-------------|
| `apps/api-gateway/src/main.py` | Claude Code | 只读 |
| `apps/api-gateway/src/core/*` | Claude Code | 只读 |
| `apps/api-gateway/src/models/*` | Claude Code | 只读 |
| `apps/api-gateway/src/services/*` | Claude Code | 只读 |
| `apps/api-gateway/src/api/*` | Claude Code | 只读 |
| `apps/web/src/App.tsx` | Claude Code | 只读 |
| `apps/web/src/layouts/*` | Claude Code | 只读 |
| `apps/web/src/services/api.ts` | Claude Code | 只读 |
| `apps/web/src/design-system/*` | **Codex** | Claude Code 只读 |
| `apps/web/src/pages/*` | **Codex 优先** | Claude Code 可新建 |
| `apps/web/src/components/*` | **Codex** | Claude Code 只读 |
| `apps/web/src/hooks/*` | **Codex 优先** | Claude Code 可新建 |
| `.github/*` | CLI | 其他只读 |
| `apps/api-gateway/tests/*` | 共同维护 | 先到先得 |
| `apps/web/src/__tests__/*` | 共同维护 | 先到先得 |

### 8.2 新增页面流程（Codex 发起）

```
1. Codex 创建 feat/codex-xxx-page 分支（基于 develop）
2. 新建 XxxPage.tsx + XxxPage.module.css
3. 在 PR 描述中注明：
   - 需要的路由路径（如 /platform/xxx）
   - 需要的导航菜单项
   - 依赖的 API 端点
4. Claude Code review PR 后：
   - 在 App.tsx 注册 lazy import + Route
   - 在对应 Layout 中添加导航菜单项
5. 合并到 develop
```

### 8.3 修改现有页面流程（Codex 发起）

```
1. 确认该页面在自己的管辖范围内（见 8.1）
2. 创建 feat/codex-fix-xxx 分支
3. 修改页面，确保不改变 API 调用契约
4. 本地运行 tsc --noEmit 确认无错误
5. 提交 PR，描述改动原因
```

### 8.4 每日同步（Codex 开始工作前）

```bash
git checkout develop
git pull origin develop --rebase
git checkout feat/codex-my-branch
git rebase develop
```

---

## 9. 质量门禁（PR 合并前必须通过）

| 检查项 | 命令 | 阻止合并 |
|--------|------|----------|
| TypeScript 编译 | `cd apps/web && npx tsc --noEmit` | ✅ 必须通过 |
| ESLint | `cd apps/web && pnpm run lint` | ✅ 必须通过 |
| 前端构建 | `cd apps/web && pnpm run build` | ✅ 必须通过 |
| Python 语法 | `python -m py_compile src/main.py` | ✅ 必须通过 |
| 后端测试 | `cd apps/api-gateway && pytest tests/ -v` | ✅ 必须通过 |
| 前端测试 | `cd apps/web && pnpm run test:coverage` | ⚠️ 建议通过 |

---

## 10. 环境信息

| 项目 | 值 |
|------|-----|
| GitHub 仓库 | `hnrm110901-cell/zhilian-os` |
| 生产服务器 | 42.194.229.21 |
| 域名 | zlsjos.cn |
| 生产端口 | 8000（API）/ 443（前端） |
| Staging 端口 | 8001（API）/ 8081（前端） |
| 生产目录 | `/opt/zhilian-os/prod/` |
| Staging 目录 | `/opt/zhilian-os/staging/` |
| 前端静态目录（prod） | `/var/www/tunxiang/` |
| 前端静态目录（staging） | `/var/www/tunxiang-staging/` |

---

## 11. 沟通协议

### Claude Code → Codex 的信号

当 Claude Code 完成以下操作后，会在 commit message 或 PR 中标注，Codex 据此响应：

| 信号 | 含义 | Codex 动作 |
|------|------|-----------|
| `[NEED-PAGE]` | 后端 API 就绪，需要前端页面 | 创建对应的前端页面 |
| `[NEED-TEST]` | 功能已实现，需要测试覆盖 | 编写单元测试 |
| `[BREAKING-API]` | API 接口有变更 | 检查并更新受影响的前端页面 |
| `[DESIGN-TOKEN]` | 设计 Token 变更 | 检查受影响的样式 |

### Codex → Claude Code 的信号

Codex 在 PR 描述中使用以下标记：

| 标记 | 含义 |
|------|------|
| `[NEED-ROUTE]` | 需要在 App.tsx 注册路由 |
| `[NEED-NAV]` | 需要在 Layout 添加导航菜单项 |
| `[NEED-API]` | 需要后端新增 API 端点 |
| `[NEED-MODEL]` | 需要新增数据库模型 |

---

## 12. 速查 Checklist

### Codex 开始任何任务前

```
□ 读了 CODEX.md（本文件）
□ 在 develop 基础上创建了 feat/codex-* 分支
□ git pull origin develop --rebase 同步了最新代码
□ 确认要修改的文件在自己的管辖范围内（见第 8 章）
```

### Codex 写代码时

```
□ 使用 apiClient（不用 fetch/axios）
□ apiClient.get<T>() 返回值直接就是 T，不再 .data
□ 样式用 CSS Modules + camelCase 类名
□ 组件优先用 Z 设计系统，其次 Ant Design
□ 类型定义写在页面文件内（不新建 types.ts）
□ 金额显示用 ¥ 前缀，保留 2 位小数
□ 字体用 Noto Sans SC，不用 Inter/Roboto
□ 不引入新的 npm 依赖（需审批）
```

### Codex 提交前

```
□ 提交消息遵守 Conventional Commits 格式
□ cd apps/web && npx tsc --noEmit 零错误
□ PR 描述写清楚改了什么、为什么改
□ 标注是否需要 Claude Code 配合（路由/API/模型）
```

---

*本文件由 Claude Code 生成，经微了一确认。Claude Code 与 Codex 共同遵守。有争议时以本文件为准。*
