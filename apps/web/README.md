# 智链OS管理后台

智链OS的Web管理后台，提供可视化界面管理和调用所有智能体。

## 技术栈

- React 19 + TypeScript
- Ant Design 5
- React Router 6
- Axios
- Vite 7

## 功能特性

- 控制台仪表板
- 7个智能体管理界面
  - 智能排班Agent
  - 订单协同Agent
  - 库存预警Agent
  - 服务质量Agent
  - 培训辅导Agent
  - 决策支持Agent
  - 预定宴会Agent
- 实时API调用
- 响应式布局

## 快速开始

### 安装依赖

```bash
# 从项目根目录
pnpm install

# 或从web目录
cd apps/web
pnpm install
```

### 配置环境变量

创建 `.env` 文件:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

### 启动开发服务器

```bash
# 从项目根目录
pnpm --filter @zhilian-os/web dev

# 或从web目录
cd apps/web
pnpm dev
```

访问 http://localhost:3000

## 项目结构

```
src/
├── components/      # 可复用组件
├── layouts/         # 布局组件
│   └── MainLayout.tsx
├── pages/           # 页面组件
│   ├── Dashboard.tsx
│   ├── SchedulePage.tsx
│   ├── OrderPage.tsx
│   ├── InventoryPage.tsx
│   ├── ServicePage.tsx
│   ├── TrainingPage.tsx
│   ├── DecisionPage.tsx
│   └── ReservationPage.tsx
├── services/        # API服务
│   ├── api.ts
│   └── config.ts
├── stores/          # 状态管理
├── types/           # TypeScript类型
│   └── api.ts
├── utils/           # 工具函数
├── App.tsx          # 应用入口
└── main.tsx         # React入口
```

## API调用示例

```typescript
import { apiClient } from './services/api';

// 调用排班Agent
const response = await apiClient.callAgent('schedule', {
  action: 'run',
  store_id: 'store_001',
  date: '2024-02-20',
  employees: [...]
});

// 健康检查
const health = await apiClient.healthCheck();
```

## 开发指南

### 添加新页面

1. 在 `src/pages/` 创建新页面组件
2. 在 `src/App.tsx` 添加路由
3. 在 `src/layouts/MainLayout.tsx` 添加菜单项

### 调用Agent

使用 `apiClient.callAgent(agentType, inputData)` 方法:

```typescript
const response = await apiClient.callAgent('schedule', {
  action: 'run',
  store_id: 'store_001',
  date: '2024-02-20',
  employees: []
});
```

## 构建

```bash
pnpm build
```

构建产物在 `dist/` 目录。

## 预览

```bash
pnpm preview
```

## 许可证

MIT
