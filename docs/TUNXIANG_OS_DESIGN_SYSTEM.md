# 屯象OS · 品牌前后端总设计规范 v1.0

> **品牌升级**: 智链OS → 屯象OS (TUN XIANG OS)
> **生效日期**: 2026-03-12
> **适用范围**: 全端（Web/Mobile/API/文档/对外物料）
> **设计哲学**: 东方的魂，西方的骨 — 易经·屯卦的生长意象 × Bauhaus/Rams/Swiss/Tufte 的精确体系

---

## 目录

1. [品牌基因](#1-品牌基因)
2. [设计Token体系](#2-设计token体系)
3. [色彩系统](#3-色彩系统)
4. [字体系统](#4-字体系统)
5. [间距与栅格](#5-间距与栅格)
6. [圆角与阴影](#6-圆角与阴影)
7. [图标与插画](#7-图标与插画)
8. [Z组件库升级](#8-z组件库升级)
9. [页面布局体系](#9-页面布局体系)
10. [角色路由与导航](#10-角色路由与导航)
11. [数据可视化规范](#11-数据可视化规范)
12. [动效与交互](#12-动效与交互)
13. [语气与文案](#13-语气与文案)
14. [深色/浅色主题](#14-深色浅色主题)
15. [后端命名对齐](#15-后端命名对齐)
16. [迁移计划](#16-迁移计划)

---

## 1. 品牌基因

### 1.1 品牌定位

| 维度 | 内容 |
|------|------|
| **中文名** | 屯象 |
| **英文名** | TUN XIANG |
| **产品名** | 屯象OS · AI-Native Restaurant OS |
| **一句话** | 餐饮人的好伙伴 |
| **情感标语** | 每一天，都有我在 |
| **价值标语** | 让好生意，更好做 |
| **产品标语** | 人只做判断，我来负责其余 |
| **终极检验** | 用户会说："你真好" |

### 1.2 品牌四柱（伴·懂·活·真）

```
伴 Companion — 陪伴同行。不是工具，是伙伴。开业第一天到第十年。
懂 Understand — 懂餐饮，懂你的生意，懂你的难处。不是通用系统，是行业专家。
活 Vitality  — 年轻有活力。像清晨的薄荷，让你每天都有新的能量和希望。
真 Genuine   — 说真话，做真事。你真好，是你对我们说的。
```

### 1.3 六大品牌感受

| 感受 | 关键词 | 设计体现 |
|------|--------|----------|
| 🤝 陪伴同行 | Companion | 晨间问候、好消息优先推送、生日祝福 |
| 🌅 充满希望 | Hope | 首屏第一件事是"今天的3个机会"，不是报错 |
| 🛡️ 安心托付 | Trust | 数据跑着你放心，异常来了我先知道 |
| ⚡ 年轻活力 | Energy | 快、懂、轻、好用，不是老系统升级版 |
| 👨‍🍳 以人为本 | Human | 所有功能出发点：让厨师/店长/老板日子更好过 |
| 💛 真实真诚 | Genuine | 说人话、不炫技、有问题直接说 |

### 1.4 Logo体系

**Logo Mark v3 — 极简芽象**（三个形状，一个意思）：

```
○  圆  = 太阳 · 希望 · 新的开始
|  茎  = 生长 · 向上 · 陪你前行
─  根  = 大地 · 踏实 · 烟火人间
```

**Logo文件清单**：

| 文件 | 用途 | 尺寸 |
|------|------|------|
| `logo-mark-v3.svg` | App图标/Favicon | 80×100 |
| `logo-horizontal.svg` | 导航栏横排 | 520×120 |
| `logo-mark.svg` | 屯卦六爻全版 | 100×100 |
| `logo-mark-v2.svg` | 带象牙弧线版 | 100×100 |
| `logo-print.svg` | 印刷用（CMYK安全） | — |

**Logo安全区**：Logo周围留出自身高度的 25% 作为净空区。

**Logo背景规则**：

| 背景 | CSS | 用途 |
|------|-----|------|
| 浅色底 | `var(--surface)` + border | 日常界面 |
| 深色底 | `#1A2F35` | 深色模式 |
| 品牌渐变 | `linear-gradient(135deg, #073D38, #0AAF9A)` | 登录页/营销 |
| 暖色底 | `linear-gradient(135deg, #3D1800, #7A3200)` | 温度场景 |

---

## 2. 设计Token体系

### 2.1 Token命名规范

所有Token采用 `--tx-{category}-{variant}` 命名前缀（`tx` = TunXiang），避免与Ant Design内置变量冲突。

```
前缀: --tx-
分类: color / space / type / radius / shadow / z / motion
```

### 2.2 Token文件结构

```
src/design-system/
├── tokens/
│   ├── index.ts          ← 统一导出 + injectTokens()
│   ├── colors.ts         ← 色彩Token
│   ├── typography.ts     ← 字体Token
│   ├── spacing.ts        ← 间距Token
│   └── elevation.ts      ← 阴影/圆角/z-index
├── components/           ← Z组件库
│   ├── ZCard/
│   ├── ZKpi/
│   ├── ZBadge/
│   ├── ZButton/
│   ├── ZInput/
│   ├── ZEmpty/
│   ├── ZSkeleton/
│   ├── ZAvatar/
│   ├── ZTabs/
│   ├── ZTable/
│   ├── ZModal/
│   ├── ZSelect/
│   ├── ZTag/            ← 新增
│   ├── ZAlert/          ← 新增
│   ├── ZTimeline/       ← 新增
│   ├── ZDrawer/         ← 新增
│   ├── HealthRing/
│   ├── UrgencyList/
│   ├── ChartTrend/
│   ├── DetailDrawer/
│   ├── AISuggestionCard/
│   ├── OpsTimeline/
│   ├── DecisionCard/    ← 新增（每日1决策英雄卡）
│   └── index.ts
└── themes/
    ├── light.ts          ← 浅色主题Ant Design覆盖
    └── dark.ts           ← 深色主题Ant Design覆盖
```

---

## 3. 色彩系统

### 3.1 品牌主色阶（Mint薄荷）

| Token | 色值 | 用途 |
|-------|------|------|
| `--tx-mint-50` | `#EDFCF9` | 卡片浅底 |
| `--tx-mint-100` | `#CBFAF2` | 选中态底色 |
| `--tx-mint-200` | `#9CF4E5` | Hover底色 |
| `--tx-mint-300` | `#5FE8D4` | 进度条/环形 |
| `--tx-mint-400` | `#2DD4BC` | 辅助高亮 |
| `--tx-mint-500` | **`#0AAF9A`** | **主色（Primary）** |
| `--tx-mint-600` | `#088F7A` | Hover态 |
| `--tx-mint-700` | `#066E5D` | 按下态/Dark模式主色 |
| `--tx-mint-800` | `#054E42` | 深色背景文字 |
| `--tx-mint-900` | `#032E27` | 极深底色 |

### 3.2 暖色辅助（Warm温度色）

| Token | 色值 | 用途 | 情感 |
|-------|------|------|------|
| `--tx-warm-sun` | `#FFC244` | 希望金 | 太阳·向阳·好消息 |
| `--tx-warm-fire` | `#FF7A3D` | 晨炉暖橙 | 餐饮温度·行动呼唤 |
| `--tx-warm-blush` | `#FF9B6A` | 柔和点缀 | 温馨提示 |
| `--tx-warm-amber` | `#C8923A` | 琥珀金 | Logo象牙弧·高级感 |

### 3.3 中性色阶（Neutral偏冷）

| Token | 色值 | 用途 |
|-------|------|------|
| `--tx-n-0` | `#FFFFFF` | 纯白 |
| `--tx-n-50` | `#F7FAFA` | 页面底色（浅色模式） |
| `--tx-n-100` | `#EEF3F3` | 卡片底色/分割线 |
| `--tx-n-200` | `#D8E4E4` | 边框/分割 |
| `--tx-n-300` | `#B8CCCC` | 禁用态 |
| `--tx-n-400` | `#8AABAB` | Placeholder |
| `--tx-n-500` | `#628A8A` | 次要文字 |
| `--tx-n-600` | `#4A6B6B` | 辅助文字 |
| `--tx-n-700` | `#344E4E` | 正文 |
| `--tx-n-800` | `#1E3232` | 标题 |
| `--tx-n-900` | `#0D1E1E` | 最深文字 |

### 3.4 语义色

| Token | 色值 | 用途 |
|-------|------|------|
| `--tx-success` | `#1A7A52` | 成功/达标/完成 |
| `--tx-warning` | `#C8923A` | 预警/待处理 |
| `--tx-danger` | `#C53030` | 危险/超标/紧急 |
| `--tx-info` | `#0AAF9A` | 提示/信息 |

### 3.5 深色模式专用

| Token | 色值 | 用途 |
|-------|------|------|
| `--tx-dark-bg` | `#0B1A20` | 页面底色 |
| `--tx-dark-raised` | `#0D2029` | 卡片底色 |
| `--tx-dark-sidebar` | `#08131A` | 侧边栏 |
| `--tx-dark-topbar` | `#08141A` | 顶栏 |
| `--tx-dark-t1` | `rgba(255,255,255,0.92)` | 主文字 |
| `--tx-dark-t2` | `rgba(255,255,255,0.50)` | 次文字 |
| `--tx-dark-t3` | `rgba(255,255,255,0.25)` | 弱文字 |
| `--tx-dark-t4` | `rgba(255,255,255,0.08)` | 极弱/分割 |
| `--tx-dark-border` | `rgba(255,255,255,0.06)` | 边框 |

### 3.6 迁移映射（旧 → 新）

| 旧Token (智链) | 新Token (屯象) | 说明 |
|----------------|----------------|------|
| `--accent: #FF6B2C` | `--tx-mint-500: #0AAF9A` | 品牌主色 |
| `--bg: #0B1A20` | `--tx-dark-bg: #0B1A20` | 深色底（保留） |
| `--surface: #FFFFFF` | `--tx-n-0: #FFFFFF` | 浅色底 |
| `--text-primary: #1D1D1F` | `--tx-n-900: #0D1E1E` | 主文字 |
| `--success: #34C759` | `--tx-success: #1A7A52` | 成功色（更沉稳） |
| `--warning: #FF9F0A` | `--tx-warning: #C8923A` | 预警色（琥珀金） |
| `--error: #FF3B30` | `--tx-danger: #C53030` | 危险色 |

---

## 4. 字体系统

### 4.1 字体栈

| 用途 | Token | 字体栈 |
|------|-------|--------|
| **品牌字** | `--tx-f-serif` | `'Noto Serif SC', 'STSong', Georgia, serif` |
| **界面字** | `--tx-f-sans` | `'Noto Sans SC', 'PingFang SC', sans-serif` |
| **数据字** | `--tx-f-ui` | `'Inter', 'Helvetica Neue', system-ui, sans-serif` |
| **代码字** | `--tx-f-mono` | `'JetBrains Mono', 'Fira Code', monospace` |

### 4.2 字号阶梯（Perfect Fourth × 1.333）

| Token | 尺寸 | 用途 |
|-------|------|------|
| `--tx-t-2xs` | `10px` | 标签/时间戳/版本号 |
| `--tx-t-xs` | `12px` | 辅助文字/描述 |
| `--tx-t-sm` | `14px` | **UI基准**：正文/按钮/输入框 |
| `--tx-t-md` | `18px` | 卡片标题/重要提示 |
| `--tx-t-lg` | `24px` | 页面小标题 |
| `--tx-t-xl` | `32px` | 页面大标题/H1 |
| `--tx-t-2xl` | `42px` | Hero文字 |
| `--tx-t-3xl` | `56px` | 品牌名展示 |

### 4.3 行高

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-lh-tight` | `1.2` | 标题/数字 |
| `--tx-lh-snug` | `1.4` | 副标题/卡片 |
| `--tx-lh-base` | `1.6` | 正文 |
| `--tx-lh-relaxed` | `1.75` | 长文/引用 |
| `--tx-lh-loose` | `2.0` | 宽松/空间感 |

### 4.4 字间距

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-ls-tight` | `-0.02em` | 大标题 |
| `--tx-ls-normal` | `0em` | 正文 |
| `--tx-ls-wide` | `0.04em` | 按钮/标签 |
| `--tx-ls-wider` | `0.08em` | Tag/Badge |
| `--tx-ls-widest` | `0.16em` | Uppercase英文标签 |

### 4.5 字体使用规则

| 场景 | 字体 | 字号 | 字重 |
|------|------|------|------|
| 品牌名"屯象" | Noto Serif SC | 42-72px | 900 |
| 页面大标题 | Noto Serif SC | 32px | 700 |
| Section标题 | Noto Serif SC | 24px | 700 |
| 卡片标题 | Noto Sans SC | 18px | 600 |
| 正文 | Noto Sans SC | 14px | 400 |
| KPI数字 | Inter | 24-48px | 700 |
| 百分比/趋势 | Inter | 12-14px | 600 |
| 时间戳 | Inter | 10px | 400 |
| 代码/技术 | JetBrains Mono | 12px | 400 |

---

## 5. 间距与栅格

### 5.1 间距阶梯（8pt基准）

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-sp-1` | `4px` | 紧凑间隙（icon与text） |
| `--tx-sp-2` | `8px` | 元素内间距 |
| `--tx-sp-3` | `12px` | 小卡片内边距 |
| `--tx-sp-4` | `16px` | 标准内边距 |
| `--tx-sp-5` | `24px` | 卡片内边距/组间距 |
| `--tx-sp-6` | `32px` | 区块间距 |
| `--tx-sp-7` | `40px` | 大区块 |
| `--tx-sp-8` | `48px` | 页面侧边距 |
| `--tx-sp-9` | `64px` | Section间距 |
| `--tx-sp-10` | `80px` | 大Section |
| `--tx-sp-11` | `96px` | 页面顶部 |
| `--tx-sp-12` | `128px` | 底部留白 |

**铁律**：所有间距必须是4的倍数，禁止出现17px、22px、26px等随意值。

### 5.2 栅格系统

| 设备 | 列数 | 列宽 | 间距 | 外边距 |
|------|------|------|------|--------|
| Desktop (≥1280px) | 12 | Auto | 24px | 48px |
| Tablet (768-1279px) | 8 | Auto | 16px | 32px |
| Mobile (≤767px) | 4 | Auto | 12px | 16px |

### 5.3 常用布局尺寸

| 元素 | 尺寸 | 说明 |
|------|------|------|
| 顶栏高度 | `52px` | 固定 |
| 图标导航栏宽度 | `56px` | 收起态 |
| 侧边栏宽度 | `220px` | 展开态 |
| AI面板宽度 | `272-340px` | 右侧 |
| 底部TabBar | `56px + safe-area` | 移动端 |
| 页面最大宽度 | `1080px` | 文档页 |
| 抽屉宽度 | `400px` | 详情面板 |

---

## 6. 圆角与阴影

### 6.1 圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-r-2xs` | `3px` | 内联代码/小标签 |
| `--tx-r-xs` | `4px` | Tag/Badge |
| `--tx-r-sm` | `6px` | 输入框/小按钮 |
| `--tx-r-md` | `8px` | 按钮/Select |
| `--tx-r-lg` | `12px` | 卡片/面板 |
| `--tx-r-xl` | `16px` | 大卡片/模态 |
| `--tx-r-2xl` | `24px` | Hero区块 |
| `--tx-r-full` | `9999px` | 圆形/胶囊 |

### 6.2 阴影（Elevation层级）

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-sh-0` | `none` | 平面/深色模式 |
| `--tx-sh-1` | `0 1px 2px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04)` | 静态卡片 |
| `--tx-sh-2` | `0 2px 8px rgba(0,0,0,0.07), 0 1px 4px rgba(0,0,0,0.04)` | Hover卡片 |
| `--tx-sh-3` | `0 4px 16px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04)` | 弹出层/Drawer |
| `--tx-sh-4` | `0 8px 32px rgba(0,0,0,0.10), 0 4px 12px rgba(0,0,0,0.05)` | Modal/全局搜索 |

### 6.3 Z-index层级

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-z-base` | `0` | 普通内容 |
| `--tx-z-raised` | `10` | 卡片/Sticky |
| `--tx-z-overlay` | `100` | Drawer/下拉 |
| `--tx-z-modal` | `200` | Modal/对话框 |
| `--tx-z-toast` | `300` | 通知/Toast |

---

## 7. 图标与插画

### 7.1 图标风格

- **主图标库**: Ant Design Icons（已安装）
- **补充图标**: Emoji用于感受型场景（如首页问候、Agent状态）
- **自定义图标**: 仅用于Logo相关

### 7.2 图标尺寸

| 场景 | 尺寸 | Token |
|------|------|-------|
| 导航栏 | 20px | — |
| 卡片标题 | 16px | — |
| 行内 | 14px | — |
| 状态点 | 6-8px | 圆形 |

### 7.3 状态点颜色

| 颜色 | 含义 |
|------|------|
| `--tx-danger` 红 | 紧急/超标/异常 |
| `--tx-warm-sun` 金 | 待处理/关注/行动中 |
| `--tx-success` 绿 | 正常/完成/达标 |
| `--tx-mint-500` 薄荷 | 主要操作/AI推荐 |
| `--tx-n-400` 灰 | 禁用/历史/未来 |

---

## 8. Z组件库升级

### 8.1 现有组件（需换肤）

| 组件 | 状态 | 升级内容 |
|------|------|----------|
| `ZCard` | ✅ 已有 | 换色：accent→mint，radius→12px |
| `ZKpi` | ✅ 已有 | 数字字体→Inter，趋势色→语义色 |
| `ZBadge` | ✅ 已有 | Tag色阶对齐屯象色板 |
| `ZButton` | ✅ 已有 | Primary→mint-500，radius→8px |
| `ZInput` | ✅ 已有 | Focus border→mint-500 |
| `ZEmpty` | ✅ 已有 | 插画风格→简洁薄荷线条 |
| `ZSkeleton` | ✅ 已有 | 骨架色→n-100/n-200 |
| `ZAvatar` | ✅ 已有 | 边框→mint-200 |
| `ZTabs` | ✅ 已有 | 激活下划线→mint-500 |
| `ZTable` | ✅ 已有 | Hover行→mint-50 |
| `ZModal` | ✅ 已有 | Shadow→sh-4，radius→xl |
| `ZSelect` | ✅ 已有 | 同ZInput风格 |

### 8.2 新增组件

| 组件 | 用途 | 设计要点 |
|------|------|----------|
| `ZTag` | 状态/分类标签 | 5色变体：mint/warn/danger/ok/neutral |
| `ZAlert` | 告警卡片 | 左边3px色条 + 图标 + 动作按钮 |
| `ZTimeline` | 营业时间线 | 状态机：done(绿)/now(amber)/pending(灰) |
| `ZDrawer` | 右侧详情面板 | 400px宽，slideIn动画，sh-3 |
| `DecisionCard` | 每日1决策英雄卡 | 2px彩边框，severity色阶，¥节省金额高亮 |
| `AIMessageCard` | AI建议卡 | mint左边框 + 渐变底 + 置信度指示 |
| `QuoteBlock` | 引用/提示块 | 3px mint左边框 + n-50底 |

### 8.3 ZTag色彩变体

```css
/* .tag-mint */    bg: mint-50,  color: mint-700,  border: mint-200
/* .tag-warn */    bg: #FFF3E0,  color: #8B5E00,   border: #FFE0B2
/* .tag-danger */  bg: #FFF0F0,  color: #A82020,   border: #FFCDD2
/* .tag-ok */      bg: #EDFAF3,  color: #1A6040,   border: #C8E6C9
/* .tag-neutral */ bg: n-100,    color: n-600,      border: n-200
```

---

## 9. 页面布局体系

### 9.1 桌面端布局（Desktop Admin）

```
┌──────────────────────────────────────────────────────────┐
│ TOPBAR (52px)   Logo · KPI Strip · Search · Notif · User │
├────────┬─────────────────────────────────┬───────────────┤
│ RAIL   │ MAIN CONTENT                    │ AI PANEL      │
│ 56px   │ flex: 1                         │ 272-340px     │
│        │                                 │ (可收起)       │
│ 图标   │ ┌─ OrgBar (36px) ─────────────┐ │               │
│ 导航   │ │ 🌐 全国 › 华东 › 上海(14家)  │ │ 🤖 屯象智脑   │
│        │ ├─ SubNav (44px) ──────────────┤ │               │
│        │ │ Tab1 | Tab2 | Tab3 | Tab4    │ │ AI洞察       │
│        │ ├─ Toolbar ────────────────────┤ │ 建议卡片      │
│        │ │ Filter · Search · Actions    │ │ 聊天对话      │
│        │ ├─ Content Body (scroll) ──────┤ │               │
│        │ │                              │ │               │
│        │ │ [Cards / Tables / Charts]    │ │               │
│        │ │                              │ │               │
│        │ └──────────────────────────────┘ │               │
└────────┴─────────────────────────────────┴───────────────┘
```

### 9.2 移动端布局（Mobile 店长）

```
┌──────────────────────┐
│ Status Bar (safe)    │
├──────────────────────┤
│ Header (48px)        │
│ Logo · Notif · Avatar│
├──────────────────────┤
│ SCROLL CONTENT       │
│ (flex: 1)            │
│                      │
│ 晨间问候             │
│ 每日1决策英雄卡      │
│ KPI 2×2网格          │
│ 快捷操作 4宫格       │
│ 排班/任务/预警       │
│                      │
├──────────────────────┤
│ Bottom Tab (56px)    │
│ 首页 班次 任务 预警 经营│
└──────────────────────┘
```

### 9.3 六大桌面模块布局

| 模块 | 布局特点 | 关键组件 |
|------|----------|----------|
| **01 经营总览** | 3列：时间线 + 门店健康网格 + AI面板 | KPI strip, 异常/机会双面板, 营收图表 |
| **02 门店运营** | 表格 + 右侧Drawer | 损耗表(sparkline), 排班甘特, 巡检清单 |
| **03 供应链** | AI推荐Banner + 库存表 | 采购建议, 供应商评分, 库存预警 |
| **04 会员增长** | KPI条 + 多图表 | RFM矩阵, 增长漏斗, 活动管理表 |
| **05 智能体中心** | 3面板：Agent列表 + 工作流 + 对话 | 工作流步骤, Agent状态, 聊天界面 |
| **06 平台治理** | 3列：角色树 + 权限矩阵 + 审计 | 权限开关, 实时审计流 |

---

## 10. 角色路由与导航

### 10.1 路由前缀

| 角色 | 路由 | 设备 | Layout |
|------|------|------|--------|
| 桌面管理端 | `/` | Desktop | `MainLayout` |
| 店长 | `/sm` | 手机 | `StoreManagerLayout` |
| 厨师长 | `/chef` | 手机/平板 | `ChefLayout` |
| 楼面经理 | `/floor` | 平板 | `FloorLayout` |
| 总部 | `/hq` | 桌面 | `HQLayout` |

### 10.2 店长首页（/sm）核心流

```
打开App
  ↓
晨间问候（"张店长，早上好 ☀️"）
  ↓
每日1决策英雄卡（severity色边框 + ¥节省 + 一键操作）
  ↓
  ├── 有预警 → 红色AlertBanner → 点击跳转预警详情
  ├── 有建议 → 金色AdviceBanner → 点击查看排班建议
  └── 无异常 → 绿色OkBanner（"今天一切顺利"）
  ↓
KPI 2×2 网格（营收/客流/成本率/损耗率）
  ↓
快捷操作 4宫格（日报/盘点/采购/排班）
  ↓
排班/历史/趋势
```

### 10.3 导航图标映射

| 模块 | 图标 | 说明 |
|------|------|------|
| 经营总览 | 📊 | 仪表盘/KPI |
| 门店运营 | 📱 | 日常运营 |
| 供应链 | 📦 | 食材/库存 |
| 会员增长 | 👥 | CRM |
| 智能体 | 🤖 | AI Agent |
| 平台治理 | 🛡️ | 管理/RBAC |

---

## 11. 数据可视化规范

### 11.1 Tufte原则（必须遵守）

| 原则 | 规则 | 示例 |
|------|------|------|
| **数据墨水比** | ≥85%的视觉元素承载数据 | 去掉背景网格/3D效果 |
| **消灭图表垃圾** | 不使用装饰性渐变/阴影 | 纯色填充 |
| **Sparkline** | KPI旁嵌入80×20px迷你趋势 | 替代完整图表 |
| **标注数据** | 重要数据点直接标注数字 | 不依赖Tooltip |

### 11.2 图表配色

| 数据类型 | 颜色 | 说明 |
|----------|------|------|
| 主系列 | `--tx-mint-500` | 营收/正向 |
| 对比系列 | `--tx-n-300` | 上期/基准 |
| 超标/负面 | `--tx-danger` | 损耗/超支 |
| 预警 | `--tx-warm-sun` | 接近阈值 |
| 达标/正面 | `--tx-success` | 节省/增长 |

### 11.3 KPI展示规范

```
标签    → 10px, uppercase, n-500, Inter
数值    → 24px, bold, n-900, Inter (¥金额必须2位小数)
趋势    → 12px, bold + Sparkline
    ↑ 正向 → success绿
    ↓ 负向 → danger红
    → 持平 → n-400灰
```

---

## 12. 动效与交互

### 12.1 动效Token

| Token | 值 | 用途 |
|-------|-----|------|
| `--tx-motion-fast` | `100ms ease-in` | 按钮按下 |
| `--tx-motion-normal` | `200ms ease-out` | 卡片Hover/切换 |
| `--tx-motion-slow` | `400ms ease` | 页面进入/Drawer |
| `--tx-motion-spring` | `300ms cubic-bezier(0.34,1.56,0.64,1)` | 弹性效果 |

### 12.2 交互规范

| 交互 | 动效 | 说明 |
|------|------|------|
| 卡片Hover | `translateY(-2px)` + `sh-2` | 微提升 |
| 按钮按下 | `scale(0.98)` + `brightness(0.95)` | 按压反馈 |
| Drawer进入 | `translateX(100% → 0)` | 右滑入 |
| Modal弹出 | `scale(0.95 → 1)` + `opacity(0 → 1)` | 缩放淡入 |
| 页面切换 | `opacity(0 → 1)` + `translateY(8px → 0)` | 淡入上移 |
| 脉冲指示 | `opacity 30%→100%`, 2s循环 | AI处理中/实时 |
| 骨架屏 | `background-position` 扫过 | 加载中 |

### 12.3 手势支持（移动端）

| 手势 | 动作 | 范围 |
|------|------|------|
| 左右滑 | 底部Tab切换 | StoreManagerLayout |
| 下拉 | 刷新数据 | 所有列表页 |
| 长按 | 批量选择 | 表格/列表 |

---

## 13. 语气与文案

### 13.1 四字文案原则

| 原则 | 中文 | 示例 |
|------|------|------|
| **直接** | 说要干嘛，不绕弯 | "7号店食材不够，建议16:00前补货" |
| **温暖** | 有好消息要说，有进步要鼓励 | "好消息！3号店利润涨了18%，干得好" |
| **踏实** | 数字是数字，建议是建议 | "预计节省 ¥1,800（置信度75%）" |
| **尊重** | 建议而不代替 | "建议调整克重，您来决定" |

### 13.2 文案对照表

| 场景 | ❌ 不要这样说 | ✅ 要这样说 |
|------|-------------|------------|
| 成本超标 | "智能算法检测到异常数据" | "今天成本率34.2%，超了2.2个点，主要是鲈鱼用多了" |
| 库存预警 | "库存预测模型低于安全阈值" | "鲈鱼只够用到明天中午，建议现在补15kg" |
| 好消息 | "系统运行正常" | "好消息！本月损耗率降到2.8%，比上月省了¥4,200" |
| AI建议 | "优化方案已生成" | "酸菜鱼鱼片改到350g，预计每月省¥12,800" |
| 空状态 | "暂无数据" | "还没有今天的数据，营业开始后会自动更新" |
| 错误 | "Error 500" | "数据加载失败了，正在重试…" |

### 13.3 问候语规则

| 时段 | 问候 |
|------|------|
| 6:00-11:00 | "{name}，早上好 ☀️" |
| 11:00-14:00 | "{name}，午市加油 🔥" |
| 14:00-17:00 | "{name}，下午好 ☕" |
| 17:00-21:00 | "{name}，晚市顺利 🌙" |
| 21:00-6:00 | "{name}，辛苦了，早点休息 🌙" |

### 13.4 金额展示规则

- 数据库：分(fen)
- API输出：元(yuan)，保留2位小数
- 界面展示：`¥{金额}` 格式，千位用逗号分隔
- 示例：`¥12,800.00` / `¥-428.50`
- 节省金额：绿色 + ↓ 箭头
- 超支金额：红色 + ↑ 箭头

---

## 14. 深色/浅色主题

### 14.1 主题切换机制

```typescript
// data-theme attribute on <html>
document.documentElement.setAttribute('data-theme', 'dark' | 'light');
```

### 14.2 浅色主题映射

| 语义Token | 浅色值 |
|-----------|--------|
| `--tx-bg` | `--tx-n-50` (#F7FAFA) |
| `--tx-surface` | `--tx-n-0` (#FFFFFF) |
| `--tx-text-primary` | `--tx-n-900` (#0D1E1E) |
| `--tx-text-secondary` | `--tx-n-600` (#4A6B6B) |
| `--tx-text-tertiary` | `--tx-n-400` (#8AABAB) |
| `--tx-border` | `--tx-n-200` (#D8E4E4) |
| `--tx-accent` | `--tx-mint-500` (#0AAF9A) |

### 14.3 深色主题映射

| 语义Token | 深色值 |
|-----------|--------|
| `--tx-bg` | `--tx-dark-bg` (#0B1A20) |
| `--tx-surface` | `--tx-dark-raised` (#0D2029) |
| `--tx-text-primary` | `--tx-dark-t1` (rgba 0.92) |
| `--tx-text-secondary` | `--tx-dark-t2` (rgba 0.50) |
| `--tx-text-tertiary` | `--tx-dark-t3` (rgba 0.25) |
| `--tx-border` | `--tx-dark-border` (rgba 0.06) |
| `--tx-accent` | `--tx-mint-500` (#0AAF9A，双模式通用) |

### 14.4 深色模式设计原则

- 深色不是简单反转 — `#0B1A20`带绿调，与薄荷品牌色协调
- 卡片用`--tx-dark-raised`而非纯黑，有层次感
- 文字分4级透明度（0.92/0.50/0.25/0.08），而非灰色
- 图表在深色模式下颜色略提亮（+10%亮度）

### 14.5 Ant Design主题覆盖

```typescript
// light theme override
const txLightTheme: ThemeConfig = {
  token: {
    colorPrimary: '#0AAF9A',      // mint-500
    colorSuccess: '#1A7A52',       // tx-success
    colorWarning: '#C8923A',       // tx-warning
    colorError: '#C53030',         // tx-danger
    colorInfo: '#0AAF9A',          // mint-500
    colorBgContainer: '#FFFFFF',
    colorBgLayout: '#F7FAFA',
    colorText: '#0D1E1E',
    colorTextSecondary: '#4A6B6B',
    colorBorder: '#D8E4E4',
    borderRadius: 8,
    fontFamily: "'Noto Sans SC', 'PingFang SC', sans-serif",
  },
};

// dark theme override
const txDarkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#0AAF9A',
    colorBgContainer: '#0D2029',
    colorBgLayout: '#0B1A20',
    colorText: 'rgba(255,255,255,0.92)',
    colorTextSecondary: 'rgba(255,255,255,0.50)',
    colorBorder: 'rgba(255,255,255,0.06)',
    borderRadius: 8,
    fontFamily: "'Noto Sans SC', 'PingFang SC', sans-serif",
  },
};
```

---

## 15. 后端命名对齐

### 15.1 品牌升级不影响后端

后端代码（Python/API路由/数据库表名）**不做重命名**，原因：
- 表名、字段名是内部实现，用户不可见
- 大规模重命名带来的迁移风险远大于收益
- API前缀 `/api/v1/` 保持不变

### 15.2 需要变更的位置

| 位置 | 旧值 | 新值 |
|------|------|------|
| `src/main.py` title | `智链OS API` | `屯象OS API` |
| `src/main.py` description | `智链经营助手` | `屯象 · 餐饮人的好伙伴` |
| Swagger UI 标题 | `智链OS` | `屯象OS` |
| API响应 header | `X-Powered-By: ZhilianOS` | `X-Powered-By: TunxiangOS` |
| 前端 `<title>` | `智链OS` | `屯象OS` |
| 前端 Logo组件 | 旧Logo | 屯象Logo SVG |
| PWA manifest | `name: 智链OS` | `name: 屯象OS` |

### 15.3 AI文案模板

```python
# 旧（智链风格 — 冷/技术）
"智能算法已检测到异常数据，建议执行优化方案。"

# 新（屯象风格 — 温暖/直接）
"今天成本率偏高了一点，主要是鲈鱼用多了。建议调到350g/份，预计每月省¥12,800。"
```

所有 `generate_one_sentence_insight()` / `generate_actionable_decision()` 的文案模板需按 §13 语气规范更新。

---

## 16. 迁移计划

### Phase 1：Token基础（1天）

- [ ] 创建 `src/design-system/tokens/colors.ts` — 全量屯象色彩Token
- [ ] 创建 `src/design-system/tokens/typography.ts` — 字体Token
- [ ] 创建 `src/design-system/tokens/spacing.ts` — 间距Token
- [ ] 创建 `src/design-system/tokens/elevation.ts` — 阴影/圆角/z-index
- [ ] 更新 `src/design-system/tokens/index.ts` — 统一导出 + `injectTokens()`
- [ ] 更新 `src/styles/variables.css` — CSS变量对齐屯象Token
- [ ] 更新 `src/config/theme.ts` — Ant Design主题覆盖
- [ ] 引入字体文件（Google Fonts CDN: Noto Serif SC + Inter + JetBrains Mono）

### Phase 2：Z组件换肤（2天）

- [ ] ZCard — 圆角/边框/阴影对齐
- [ ] ZKpi — 数字字体→Inter，趋势色→语义色
- [ ] ZBadge/ZTag — 5色变体
- [ ] ZButton — Primary→mint，Ghost→n边框
- [ ] ZInput/ZSelect — Focus→mint
- [ ] ZTable — Hover→mint-50
- [ ] ZModal — sh-4，r-xl
- [ ] ZSkeleton — n-100/n-200
- [ ] 新增 ZTag, ZAlert, ZTimeline, ZDrawer
- [ ] 新增 DecisionCard, AIMessageCard, QuoteBlock

### Phase 3：Layout & 导航（1天）

- [ ] MainLayout — Logo替换，侧边栏色彩，顶栏KPI strip
- [ ] StoreManagerLayout — 底部Tab色彩，Header品牌
- [ ] HQLayout / ChefLayout / FloorLayout — Logo + 色彩
- [ ] 全局 `<title>` → 屯象OS
- [ ] Favicon → logo-mark-v3.svg

### Phase 4：角色首页重做（2天）

- [ ] `/sm` 店长首页 — 晨间问候 + 决策英雄卡 + KPI 2×2 + 快捷操作
- [ ] `/hq` 总部首页 — 多店健康网格 + 异常/机会双面板
- [ ] `/chef` 厨师长首页 — 损耗排名 + 采购建议 + BOM偏差
- [ ] `/floor` 楼面首页 — 排队/预订 + 服务质量

### Phase 5：后端品牌对齐（0.5天）

- [ ] `src/main.py` — 标题/描述更新
- [ ] AI文案模板 — 温暖语气重写
- [ ] Swagger文档 — 品牌标识

### Phase 6：深色主题（1天）

- [ ] CSS变量 dark模式完整映射
- [ ] Ant Design dark算法 + 屯象色覆盖
- [ ] 图表深色适配
- [ ] Z组件深色态测试

---

## 附录A：设计哲学参考

### 五大西方设计流派在屯象的应用

| 流派 | 核心教义 | 在屯象的体现 |
|------|----------|-------------|
| **Bauhaus** | 形式追随功能 | Logo仅3个几何形（圆+矩形+矩形），颜色承载信息不是装饰 |
| **Dieter Rams** | 好设计尽可能少 | 每个屏幕只保留必要元素，去掉不去掉也不会被想起的东西 |
| **Swiss Style** | 网格是隐形建筑 | 所有间距8的倍数，数学计算而非感觉 |
| **Edward Tufte** | 数据墨水比最大化 | 去掉图表网格线/3D效果/装饰渐变，Sparkline替代完整图表 |
| **Apple HIG** | 清晰·顺从·纵深 | 文字可读/UI不抢数据/视觉层级+真实动效 |

### 东方意象

| 意象 | 来源 | 在屯象的体现 |
|------|------|-------------|
| **屯** | 易经·屯卦（始生之卦） | 从混沌到有序 = 散乱数据→汇聚洞察 |
| **象** | 取象比类（模式识别） | AI的本质 = 从数据中取象 |
| **芽** | 甲骨文（种子破土） | Logo = 芽 = 生长·希望·新开始 |
| **伴** | 以人为本 | 品牌核心 = 陪伴而不是替代 |

---

## 附录B：文件变更清单

### 前端文件（需新建/修改）

```
# 新建
src/design-system/tokens/colors.ts
src/design-system/tokens/typography.ts
src/design-system/tokens/spacing.ts
src/design-system/tokens/elevation.ts
src/design-system/themes/light.ts
src/design-system/themes/dark.ts
src/design-system/components/ZTag/
src/design-system/components/ZAlert/
src/design-system/components/ZTimeline/
src/design-system/components/ZDrawer/
src/design-system/components/DecisionCard/
src/design-system/components/AIMessageCard/
src/design-system/components/QuoteBlock/
public/logo-mark-v3.svg
public/logo-horizontal.svg

# 修改
src/design-system/tokens/index.ts      — 统一导出
src/design-system/components/ZCard/    — 换肤
src/design-system/components/ZKpi/     — 换肤
src/design-system/components/ZBadge/   — 换肤
src/design-system/components/ZButton/  — 换肤
src/design-system/components/ZInput/   — 换肤
src/design-system/components/ZTable/   — 换肤
src/design-system/components/ZModal/   — 换肤
src/styles/variables.css               — Token对齐
src/styles/global.css                  — 字体栈
src/config/theme.ts                    — Ant Design覆盖
src/layouts/MainLayout.tsx             — Logo/色彩
src/layouts/StoreManagerLayout.tsx     — Logo/色彩
src/layouts/HQLayout.tsx               — Logo/色彩
src/pages/sm/Home.tsx                  — 首页重做
src/pages/sm/Home.module.css           — 样式重做
index.html                             — <title>、Font引入
```

### 后端文件（需修改）

```
src/main.py                            — title/description
src/services/cost_truth_engine.py      — 文案模板
src/services/unified_brain.py          — 文案模板
```

---

> **维护说明**: 本文档由设计团队和开发团队共同维护。任何Token变更须同步更新本文档。
> **版本控制**: 路径 `docs/TUNXIANG_OS_DESIGN_SYSTEM.md`，随代码一起版本管理。
