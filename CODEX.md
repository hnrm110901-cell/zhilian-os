# CODEX.md — Codex 开发规范（智链OS）

> 这是专为 Codex 准备的上下文文件，对应 Claude 侧的 CLAUDE.md。
> 每次 Codex 开始新任务时必读。

---

## 项目快照

**智链OS** — 中餐连锁 AI 运营系统
- **后端**：FastAPI (Python) ← Claude Code 负责
- **前端**：React 18 + TypeScript + Vite ← **Codex 负责**
- **协作协议**：`COLLAB.md`
- **实时状态**：`tasks/collab-sync.md`
- **接口契约**：`tasks/api-contracts.md`（从这里读 API，不要自己猜）

---

## Codex 核心规则（5条）

1. **契约优先**：所有 API 调用必须基于 `tasks/api-contracts.md` 中定义的接口，不要自己推断
2. **Z组件优先**：基础 UI 只用 `src/design-system/components/` 中的 Z 前缀组件
3. **品牌色固守**：主色 `#FF6B2C`（`var(--accent)`），字体 `Noto Sans SC`，禁用 Inter/Roboto
4. **CSS Module 强制**：每个组件配套 `.module.css`，禁止内联样式（动态值除外）
5. **apiClient 专用**：`import { apiClient } from '@/utils/apiClient'`，禁止裸 fetch/axios

---

## 角色路由（Codex 的主要战场）

| 角色 | 路由 | 设备 | Layout |
|------|------|------|--------|
| 店长 | `/sm/*` | 手机 | `StoreManagerLayout` |
| 厨师长 | `/chef/*` | 手机 | `ChefLayout` |
| 楼面经理 | `/floor/*` | 平板 | `FloorLayout` |
| 总部 | `/hq/*` | 桌面 | `HQLayout` |

---

## 前端目录结构（Codex 工作范围）

```
apps/web/src/
├── pages/
│   ├── sm/            ← 店长页面（手机优先）
│   ├── chef/          ← 厨师长页面
│   ├── floor/         ← 楼面经理页面
│   └── hq/            ← 总部页面
├── components/        ← 业务组件（HealthRing、UrgencyList 等）
├── design-system/
│   ├── components/    ← Z 前缀基础组件（只读，不改）
│   └── tokens/        ← Design Token（只读，不改）
├── hooks/             ← 自定义 Hook
└── stores/            ← Zustand 状态
```

---

## Z 组件使用速查

```tsx
import { ZCard, ZKpi, ZBadge, ZButton } from '@/design-system/components';
import { ZTable, ZSkeleton, ZEmpty } from '@/design-system/components';
import { ZInput, ZSelect, ZModal, ZTabs } from '@/design-system/components';
import { ZAvatar } from '@/design-system/components';

// 业务组件
import { HealthRing } from '@/components/HealthRing';
import { UrgencyList } from '@/components/UrgencyList';
import { ChartTrend } from '@/components/ChartTrend';
```

---

## 数据获取模式

```typescript
// ✅ 正确
import { apiClient } from '@/utils/apiClient';

const [data, setData] = useState(null);
useEffect(() => {
  apiClient.get('/api/v1/bff/sm/store123').then(r => setData(r.data));
}, []);

// BFF 失败降级
if (!data) return <ZEmpty message="暂无数据" />;
if (loading) return <ZSkeleton rows={4} />;

// ❌ 禁止
fetch('/api/...')        // 裸fetch
axios.get('/api/...')   // 裸axios（引入了也别用）
import { useQuery }     // TanStack Query 未安装
```

---

## 当前优先任务

参见 `tasks/collab-sync.md` 中 Claude 标注的「需要Codex」项目。

Phase 8 当前前端待完善：
- `WorkforcePage.tsx` — 员工健康 Tab（流失风险排名 + 班次公平性）
- 店长端人力建议确认流程（企微推送的一键确认 UI）
- 人工成本趋势图（CEO驾驶舱，hq/ 路由）

---

## 与 Claude 的握手信号

完成一个任务后，在 `tasks/collab-sync.md` 中更新：
```
## [Codex] 当前状态
- 已完成：WorkforcePage 员工健康Tab（2026-03-XX）
  → 依赖接口：GET /api/v1/workforce/{store_id}/employee-health
  → 需要Claude确认：接口返回的 risk_score 字段是否已包含¥离职成本
```
