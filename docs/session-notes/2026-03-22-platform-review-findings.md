# 平台架构审查发现 — 2026-03-22

## 一、品牌色一致性审计

### 现状概述

设计系统定义了 `#0AAF9A`（薄荷绿）为品牌主色（`--accent`），但代码中存在 **三种冲突色系**：

| 色系 | 色值 | 出现位置 | 数量 |
|------|------|----------|------|
| 薄荷绿（正确） | `#0AAF9A` | design-system tokens, theme.ts, chartTheme | 正确定义 |
| 橙色（旧品牌色） | `#FF6B2C` | CSS fallback `var(--accent, #FF6B2C)`, inline styles | 130+ CSS 文件, 85+ TSX 文件 |
| Ant Design 蓝 | `#1677ff` / `#1890ff` | OpsAdminLayout, 页面 inline styles | 35+ 处 |

### 严重问题

#### P0：OpsAdminLayout 使用 Ant Design 蓝色
- 文件：`layouts/OpsAdminLayout.module.css`
- 问题：8处硬编码 `#1677ff`，与品牌色完全不符
- 修复：替换为 `var(--accent)`

#### P0：HQLayout 硬编码旧品牌色
- 文件：`layouts/HQLayout.module.css`
- 问题：6处硬编码 `#FF6B2C`
- 修复：替换为 `var(--accent)`

#### P1：130+ CSS 文件使用 `var(--accent, #FF6B2C)` fallback
- 运行时 `--accent` 被注入为 `#0AAF9A`，fallback 不触发
- 但 IDE 预览和 CSS 变量加载失败时会显示橙色
- 修复：批量替换 fallback 为 `#0AAF9A`

#### P1：85+ TSX 文件 inline style 硬编码颜色
- 常见模式：`style={{ color: '#FF6B2C' }}` 或 `style={{ color: '#1890ff' }}`
- 修复：改为 `style={{ color: 'var(--accent)' }}`

### 语义色混乱（P2）
- Success: `#1A7A52` vs `#27AE60` vs `#34D399`（混用）
- Warning: `#C8923A` vs `#faad14` vs `#F2994A`（混用）
- Danger: `#C53030` vs `#EB5757` vs `#F87171`（混用）
- 建议：统一使用 design-system tokens 中的语义变量

### 修复优先级

1. **立即修复**：OpsAdminLayout `#1677ff` → `var(--accent)` (8处)
2. **立即修复**：HQLayout `#FF6B2C` → `var(--accent)` (6处)
3. **批量替换**：所有 CSS fallback `#FF6B2C` → `#0AAF9A` (130文件)
4. **逐步替换**：inline style 中硬编码颜色 → CSS变量 (85文件)
5. **规范制定**：添加 ESLint 规则禁止 inline style 中硬编码十六进制颜色

---

## 二、Stub 页面盘点

### 统计概览

| 类别 | 数量 |
|------|------|
| 1行redirect文件（纯导出） | 5 |
| archive/ 已归档stub | 84 |
| 活跃页面含 TODO/待开发标记 | 185 |

### 纯 Stub 文件（1行，仅re-export）

| 文件 | 内容 |
|------|------|
| `DataVisualizationScreen.tsx` | 1行 |
| `EnterpriseIntegrationPage.tsx` | 1行 |
| `KnowledgeRulePage.tsx` | 1行 |
| `MonitoringPage.tsx` | 1行 |
| `UserManagementPage.tsx` | 1行 |

### archive/ 目录（84个已归档stub）

所有文件均为4行 redirect 到活跃页面或空壳。这些可以安全删除（确认路由不再引用后）。

### 含 TODO 但有实际内容的页面（按角色分）

#### 店长 (sm/) — 15个页面有 TODO
大部分页面功能完整，TODO 主要标记"对接真实API"或"优化交互"。这些不算真正 stub。

#### 总部 (hq/) — 6个页面有 TODO
- `HRImport.tsx`, `HRKnowledge.tsx`, `HRTalentPipeline.tsx` — HR子模块
- `Decisions.tsx`, `Stores.tsx`, `Banquet.tsx` — 核心决策页面

#### 厨师长 (chef/) — 1个
- `Soldout.tsx` — 沽清管理

#### 平台运维 (platform/) — 20个页面有 TODO
大量运维/配置类页面，功能框架在但缺少后端API对接。

#### HR (hr/) — 10个页面有 TODO
人力资源子系统，多数有UI框架但用mock数据。

#### 运维 (ops/) — 12个页面有 TODO
数据管道、模型监控、Agent训练等运维工具类页面。

### 建议

1. **删除 archive/ 目录**：84个归档stub已无价值，确认路由清理后删除
2. **补全高优先级 stub**：hq/Decisions、hq/Stores 属于核心路径，优先对接API
3. **保留运维/平台 TODO**：这些页面非用户面向，可延后处理

---

## 三、Z 组件迁移状态

### 可用 Z 组件清单

| Z 组件 | 替代的 Ant Design 组件 |
|--------|----------------------|
| ZCard | Card |
| ZButton | Button |
| ZBadge | Badge |
| ZInput | Input |
| ZSelect | Select |
| ZEmpty | Empty |
| ZSkeleton | Skeleton |
| ZAvatar | Avatar |
| ZTabs | Tabs |
| ZTable | Table |
| ZModal | Modal |
| ZDrawer | Drawer |
| ZAlert | Alert |
| ZTag | Tag |
| ZTimeline | Timeline |

另有业务组件：HealthRing, UrgencyList, ChartTrend, DetailDrawer, AISuggestionCard, DecisionCard 等。

### 迁移统计

| 指标 | 数据 |
|------|------|
| 总页面文件数 | 429 |
| 已完全使用 Z 组件 | 103 (24%) |
| 仍用原生 Ant Design | 189 (44%) |
| 混合使用 | 12 (3%) |
| **迁移率** | **24%** |

### 角色首页迁移状态

| 首页 | Z组件 | 原生Ant Design | 状态 |
|------|-------|----------------|------|
| Chef Home | 全部Z组件 | 无 | ✅ 完成 |
| Floor Home | 全部Z组件 | 无 | ✅ 完成 |
| HQ Home | Z组件为主 | 仅 message | ✅ 基本完成 |
| SM Home | Z组件为主 | Form/Input/Modal/Select | ⚠️ 部分完成 |

### 原生 Ant Design 高频使用（有 Z 等价物）

| 组件 | 仍在使用的文件数 | 迁移优先级 |
|------|----------------|-----------|
| Card | 55 | 高 |
| Tag | 53 | 高 |
| Button | 45 | 高 |
| Select | 44 | 高 |
| Table | 43 | 高 |
| Input | 40 | 高 |
| Modal | 26 | 中 |
| Alert | 25 | 中 |
| Tabs | 24 | 中 |
| 合计 | **355 处** | |

### 缺失的 Z 组件（无等价物）

| Ant Design 组件 | 使用文件数 | 建议 |
|-----------------|-----------|------|
| Form | 36 | **优先创建 ZForm**（最大阻塞项） |
| Statistic | 30 | 扩展 ZKpi 或创建 ZStatistic |
| Spin | 19 | 创建 ZSpin |
| Progress | 14 | 创建 ZProgress |
| DatePicker | 14 | 创建 ZDatePicker |
| InputNumber | 16 | 扩展 ZInput |
| Descriptions | 11 | 创建 ZDescriptions |
| Row/Col | 35 | 用 CSS Grid/Flexbox 替代 |

### Z 组件功能差距

- **ZTable**：缺分页、排序、筛选
- **ZSelect**：缺多选、异步搜索
- **ZInput**：缺密码切换、长度限制、校验状态
- **ZForm**：完全缺失（36个文件阻塞）

### 迁移建议

**Phase 1（快速收益，1-2天）**：
- Card → ZCard（55文件，1:1替换）
- Tag → ZTag（53文件）
- Badge → ZBadge（4文件）

**Phase 2（中等工作量，3-5天）**：
- Button → ZButton（45文件，需检查变体映射）
- Alert → ZAlert（25文件）
- Tabs → ZTabs（24文件）

**Phase 3（需扩展Z组件，1-2周）**：
- 创建 ZForm（解除36文件阻塞）
- 扩展 ZTable 支持分页/排序
- 扩展 ZSelect 支持多选
- Input → ZInput + 扩展（40文件）

---

## 四、综合改进建议（按优先级）

### 立即可做（Quick Wins）

1. 修复 OpsAdminLayout 品牌色（8处 `#1677ff` → `var(--accent)`）
2. 修复 HQLayout 品牌色（6处硬编码）
3. 删除 `archive/` 目录下84个废弃stub

### 短期（1-2周）

4. 批量替换 CSS fallback `#FF6B2C` → `#0AAF9A`
5. Card/Tag/Badge 迁移到 Z 组件（112文件）
6. 补全 hq/Decisions 和 hq/Stores 页面

### 中期（2-4周）

7. 创建 ZForm 组件
8. Button/Alert/Tabs 迁移到 Z 组件（94文件）
9. inline style 硬编码颜色清理（85文件）
10. 扩展 ZTable/ZSelect/ZInput 功能

### 长期（4-8周）

11. 完成所有页面 Z 组件迁移（目标 80%+）
12. 语义色标准化（667处）
13. 添加 ESLint 规则防止品牌色漂移
14. 清理所有 TODO 标记或转为 issue 跟踪
