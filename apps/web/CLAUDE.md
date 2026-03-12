# Frontend CLAUDE.md — Web 应用开发指令

> 在 `apps/web/` 目录下工作时自动加载。

---

## 快速启动

```bash
cd apps/web
pnpm install    # 安装依赖
pnpm dev        # Vite 开发服务器
pnpm build      # 生产构建
pnpm preview    # 预览生产构建
```

---

## 目录结构约定

```
src/
├── pages/               # 按角色组织的页面
│   ├── sm/              # 店长（/sm 路由，手机优先）
│   ├── chef/            # 厨师长（/chef，手机）
│   ├── floor/           # 楼面经理（/floor，平板）
│   ├── hq/              # 总部（/hq，桌面）
│   └── onboarding/      # 引导流程
├── design-system/
│   ├── components/      # Z前缀基础组件 + 业务复合组件
│   └── tokens/          # Design Token（CSS 变量）
├── components/          # 业务特定组件
├── layouts/             # 角色 Layout（StoreManagerLayout 等）
├── stores/              # 状态管理
├── hooks/               # 自定义 React Hooks
├── services/            # API Client
├── types/               # TypeScript 接口
├── contexts/            # React Context
├── utils/               # 工具函数
├── styles/              # 全局 CSS
└── App.tsx              # 根组件 + 路由
```

---

## 设计系统规则

### Design Token
- 所有颜色/间距/圆角定义在 `src/design-system/tokens/index.ts`
- 使用 CSS 变量：`var(--accent)`, `var(--spacing-md)` 等
- **品牌色**：`#FF6B2C`（`var(--accent)`）
- **字体栈**：`'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'SF Pro Display'`
- **禁止**：Inter、Roboto 等非中文优先字体

### Z 组件库
基础 UI 组件（`src/design-system/components/`）：
- `ZCard` / `ZKpi` / `ZBadge` / `ZButton` / `ZInput`
- `ZEmpty` / `ZSkeleton` / `ZAvatar` / `ZSelect` / `ZTabs`
- `ZModal` / `ZTable`

业务复合组件：
- `HealthRing` — 健康度环形图
- `UrgencyList` — 优先级列表
- `ChartTrend` — 小卡片趋势图（Canvas）
- `AISuggestionCard` — AI 建议卡片
- `DetailDrawer` — 侧面板详情
- `OpsTimeline` — 运营时间轴

### 样式规范
- **CSS Modules**：每个组件配套 `.module.css`
- **禁止内联样式**（仅动态计算值除外）
- **CSS 类名**：camelCase（`.healthRow`, `.tabBar`）
- **图表**：大图表用 `ReactECharts`；小卡片趋势用 `ChartTrend`（原生 Canvas）

---

## 角色路由约定

| 角色 | 路由前缀 | 设备 | Layout |
|------|----------|------|--------|
| 店长 | `/sm` | 手机 | `StoreManagerLayout.tsx` |
| 厨师长 | `/chef` | 手机 | — |
| 楼面经理 | `/floor` | 平板 | — |
| 总部 | `/hq` | 桌面 | `HQLayout.tsx` |

原有 `/` 路由保留并行运行。

---

## 数据获取规范

```typescript
// 正确：使用项目 apiClient
import { apiClient } from '@/services/api';
const resp = await apiClient.get('/api/v1/bff/sm/S001');

// 禁止：
// - 直接 fetch / axios
// - 引入 TanStack Query（未安装）
// - 硬编码 baseURL
```

### BFF 首屏加载
- 每个角色首屏 **1个 BFF 请求**
- 子数据失败显示 `<ZEmpty />` 占位
- `?refresh=true` 强制刷新

---

## 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| React 组件 | PascalCase | `SmHome`, `ZCard` |
| 页面文件 | PascalCase.tsx | `Home.tsx`, `WorkforcePage.tsx` |
| CSS Module 类 | camelCase | `.healthRow`, `.tabBar` |
| Hook | use 前缀 | `useStoreData`, `useBffQuery` |
| 工具函数 | camelCase | `formatYuan`, `parseDate` |
| 类型接口 | PascalCase + I 前缀可选 | `EmployeeHealth`, `BffResponse` |

---

## 前后端一致性

- 修改 TypeScript 类型时，必须检查后端对应的 Pydantic Schema
- 枚举值（如 `risk_level`）必须与后端完全一致（参见 L018）
- 金额字段前端显示时加 `¥` 前缀，保留2位小数
