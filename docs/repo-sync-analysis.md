# 两仓库架构对比分析报告

> **对比对象**：`hnrm110901-cell/zhilian-os`（V2.x 单体架构）vs `hnrm110901-cell/tunxiang-os`（V3.0 微服务架构）
> **生成日期**：2026-03-22

---

## 1. 基本信息对比

| 维度 | zhilian-os（本仓库） | tunxiang-os（新仓库） |
|------|---------------------|----------------------|
| 仓库大小 | ~14,178 KB | ~400 KB |
| 默认分支 | main | main |
| 主语言 | Python | Python |
| 版本 | V2.x（隐含） | V3.0.0（显式声明） |
| 创建时间 | 2026-02-14 | 2026-03-22 |
| 定位 | 餐饮连锁运营 AI Agent 系统 | AI-Native 零售数字化解决方案 |

---

## 2. 顶层目录结构对比

### zhilian-os（当前）
```
zhilian-os/
├── apps/
│   ├── api-gateway/          ← 单体 FastAPI 后端（全部业务）
│   └── web/                  ← 单体 React 前端（全部角色）
├── packages/
│   ├── agents/               ← 15 个领域 Agent 包（LangChain）
│   └── api-adapters/         ← 11 个 POS 适配器
├── alembic/                  ← 数据库迁移（根级）
├── config/
├── docs/
├── k8s/
├── nginx/
├── scripts/
├── tasks/
├── docker-compose.yml        ← PostgreSQL + Redis + Neo4j + Qdrant + Prometheus + Grafana
└── pyproject.toml
```

### tunxiang-os（新）
```
tunxiang-os/
├── apps/
│   ├── web-pos/              ← POS 收银前端
│   ├── web-admin/            ← 管理后台前端
│   ├── web-kds/              ← 厨显前端
│   ├── web-crew/             ← 员工管理前端
│   ├── android-shell/        ← Android 原生壳（Kotlin）
│   ├── ios-shell/            ← iOS 原生壳（Swift）
│   └── miniapp-customer/     ← 微信小程序（C端顾客）
├── services/
│   ├── gateway/              ← API 网关（路由转发）
│   ├── tx-agent/             ← Agent 服务（Master + 9 Skill Agents）
│   ├── tx-trade/             ← 交易服务（收银/结算/退款）
│   ├── tx-menu/              ← 菜品服务（菜单管理/排行）
│   ├── tx-member/            ← 会员服务
│   ├── tx-supply/            ← 供应链服务（库存/采购/损耗）
│   ├── tx-finance/           ← 财务服务
│   ├── tx-org/               ← 组织架构服务
│   └── tx-analytics/         ← 分析服务（BI/叙事引擎）
├── edge/
│   ├── coreml-bridge/        ← Core ML 推理桥（Swift）
│   ├── mac-station/          ← Mac mini 边缘站
│   └── sync-engine/          ← 云端同步引擎
├── shared/
│   └── adapters/             ← POS 适配器（奥琦玮等）
├── infra/
│   ├── docker/               ← Docker + RLS 初始化 SQL
│   ├── nginx/
│   └── tailscale/            ← VPN 组网
├── scripts/
├── docs/
├── docker-compose.yml        ← PostgreSQL 16 + Redis 7 + 微服务容器
└── pyproject.toml
```

---

## 3. 架构范式对比

### 3.1 后端架构

| 维度 | zhilian-os | tunxiang-os |
|------|-----------|-------------|
| **架构风格** | 单体（Monolith） | 微服务（Microservices） |
| **后端入口** | 1 个 FastAPI 应用（`apps/api-gateway`） | 1 个 Gateway + 8 个独立微服务 |
| **模型层** | 163 个模型文件，集中在 `src/models/` | 各服务独立 models |
| **服务层** | 337 个 service 文件，集中在 `src/services/` | 按领域拆分到各 `tx-*` 服务 |
| **API 路由** | 254 个路由文件，集中在 `src/api/` | 各服务独立路由 |
| **数据库** | 单库（PostgreSQL 15） | 单库 + RLS 行级安全（PostgreSQL 16） |
| **Agent 系统** | 15 个 Agent（主应用内）+ 15 个独立包 | Master Agent + 9 Skill Agents（独立服务） |
| **端口** | 8000（唯一） | 8000(GW) + 8001(trade) + 8002(menu) + 8008(agent) + ... |

### 3.2 前端架构

| 维度 | zhilian-os | tunxiang-os |
|------|-----------|-------------|
| **应用数量** | 1 个 SPA（`apps/web`） | 7 个应用（4 Web + 2 Native + 1 小程序） |
| **角色路由** | 同一 SPA 内路由前缀（`/sm`, `/chef`, `/hq`） | 独立应用（web-pos, web-admin, web-kds, web-crew） |
| **构建工具** | Vite 7.3 | Vite（pnpm workspace） |
| **UI 库** | Ant Design 5 + Z 组件设计系统 | Z 前缀设计系统（web-pos 内置） |
| **移动端** | 响应式 Web | Android Shell（Kotlin）+ iOS Shell（Swift） |
| **C 端** | 无 | 微信小程序（miniapp-customer） |

### 3.3 基础设施

| 维度 | zhilian-os | tunxiang-os |
|------|-----------|-------------|
| **向量数据库** | Qdrant（384 维嵌入） | 无（Agent 服务内置？） |
| **图数据库** | Neo4j 5.17 | 无 |
| **监控** | Prometheus + Grafana | 无（待补充） |
| **边缘计算** | Raspberry Pi 5 | Mac mini M4 + Core ML |
| **VPN** | 无 | Tailscale 组网 |
| **容器编排** | Docker Compose + Kubernetes | Docker Compose（dev/prod） |
| **数据安全** | 中间件层租户隔离 | PostgreSQL RLS 行级安全 |

---

## 4. Agent 系统对比

### zhilian-os：15 + 15 Agent 体系
```
apps/api-gateway/src/agents/（15 个内置 Agent）
├── llm_agent.py          (526 LOC) — LLM 编排核心
├── performance_agent.py  (1303 LOC) — KPI 分析
├── ops_agent.py          (445 LOC) — 运营流程
├── inventory_agent.py    (357 LOC) — 库存管理
├── order_agent.py        (310 LOC) — 订单处理
├── kpi_agent.py          (293 LOC) — KPI 监控
├── decision_agent.py     (298 LOC) — 决策支持
├── schedule_agent.py     (300 LOC) — 排班优化
├── compliance_agent.py   (220 LOC) — 合规检查
├── quality_agent.py      (199 LOC) — 质量检查
├── fct_agent.py          (123 LOC) — 财务合并
├── reservation_agent.py  — 预订
├── training_agent.py     — 培训
├── service_agent.py      — 服务质量
├── hr_agent.py           — 人力资源
└── ontology_adapter.py   (233 LOC) — Neo4j 图交互

packages/agents/（15 个独立 Agent 包，LangChain + LangGraph）
├── banquet/     ├── business_intel/ ├── decision/
├── dish_rd/     ├── inventory/      ├── ops_flow/
├── order/       ├── people_agent/   ├── performance/
├── private_domain/ ├── reservation/ ├── schedule/
├── service/     ├── supplier/       └── training/
```

### tunxiang-os：Master + 9 Skill Agent 体系
```
services/tx-agent/src/skills/（9 个技能 Agent）
├── discount_guard/     — 折扣风控
├── finance_audit/      — 财务审计
├── inventory_alert/    — 库存预警
├── member_insight/     — 会员洞察
├── private_ops/        — 私域运营
├── serve_dispatch/     — 服务调度
├── smart_menu/         — 智能菜单
├── smart_service/      — 智慧服务
└── store_inspect/      — 门店巡检
```

**关键差异**：
- zhilian-os 有 30 个 Agent（15 内置 + 15 独立包），覆盖面广但冗余
- tunxiang-os 精简为 9 个 Skill Agent + 1 个 Master Agent，聚焦核心场景

---

## 5. POS 适配器对比

| 适配器 | zhilian-os | tunxiang-os |
|--------|-----------|-------------|
| 奥琦玮（徐记海鲜） | ✅ | ✅（含 CRM 扩展） |
| 品智 POS（尝在一起） | ✅ | ❌ |
| 天财商龙 | ✅ | ❌ |
| 美团 SaaS | ✅ | ❌ |
| 一订（预订） | ✅ | ❌ |
| 客如云 | ✅ | ❌ |
| 抖音 | ✅ | ❌ |
| 饿了么 | ✅ | ❌ |
| 诺诺发票 | ✅ | ❌ |
| 微生活 | ✅ | ❌ |
| Base 基类 | ✅ | ✅ |

**结论**：tunxiang-os 目前仅实现了奥琦玮适配器，其余 9 个需要从 zhilian-os 迁移。

---

## 6. 微服务拆分映射（zhilian-os → tunxiang-os）

| tunxiang-os 微服务 | 对应 zhilian-os 模块 | 合并了多少文件 |
|-------------------|---------------------|---------------|
| `tx-trade` | `services/order_*.py` + `services/payment_*.py` + `services/settlement_*.py` | ~20 个 service |
| `tx-menu` | `services/menu_*.py` + `services/dish_*.py` + `services/bom_*.py` | ~15 个 service |
| `tx-member` | `services/private_domain_*.py` + `services/customer_*.py` + `services/rfm_*.py` | ~20 个 service |
| `tx-supply` | `services/inventory_*.py` + `services/procurement_*.py` + `services/waste_*.py` | ~12 个 service |
| `tx-finance` | `services/fct_*.py` + `services/budget_*.py` + `services/cost_*.py` | ~15 个 service |
| `tx-org` | `services/employee_*.py` + `services/schedule_*.py` + `services/attendance_*.py` | ~20 个 service |
| `tx-analytics` | `services/analytics_*.py` + `services/report_*.py` + `services/kpi_*.py` | ~34 个 service |
| `tx-agent` | `agents/*.py` + `packages/agents/*/` | 30 个 Agent → 9 Skill |

---

## 7. 关键技术差异总结

| 特性 | zhilian-os（当前） | tunxiang-os（目标） | 迁移难度 |
|------|-------------------|-------------------|---------|
| 单体 → 微服务 | 单体 | 微服务 | ★★★★★ |
| 数据库隔离 | 中间件层 | PostgreSQL RLS | ★★★ |
| Agent 精简 | 30 个 | 10 个（1+9） | ★★★ |
| 前端拆分 | 1 个 SPA | 7 个应用 | ★★★★ |
| 边缘计算 | RPi 5 | Mac mini M4 + Core ML | ★★★ |
| 移动端 | 响应式 Web | Native Shell + WebView | ★★ |
| C 端入口 | 无 | 微信小程序 | ★★ |
| 网络层 | 公网直连 | Tailscale VPN | ★★ |
| 向量/图数据库 | Qdrant + Neo4j | 未引入 | 待决策 |
| 监控 | Prometheus + Grafana | 未配置 | ★★ |
| POS 适配器 | 11 个 | 1 个 | ★★★（迁移） |
| 测试覆盖 | 分散 | 173 tests passing | — |

---

## 8. 迁移建议（优先级排序）

### P0 — 必须先做
1. **POS 适配器迁移**：将品智 POS 适配器迁移到 tunxiang-os（尝在一起客户依赖）
2. **核心 Service 逻辑迁移**：将 zhilian-os 中经过验证的业务逻辑（特别是成本真相引擎、需求预测、损耗追踪）迁移到对应的 tx-* 微服务

### P1 — 本月内
3. **Agent 能力对齐**：确保 9 个 Skill Agent 覆盖原 15+15 Agent 的核心能力
4. **数据模型迁移**：将 163 个模型精简合并后迁移到各微服务
5. **BFF 层实现**：tunxiang-os 的 gateway 需要实现 BFF 聚合（角色首屏 1 请求）

### P2 — 下个 Sprint
6. **监控体系补齐**：Prometheus + Grafana 迁移到 tunxiang-os
7. **向量检索决策**：tunxiang-os 是否需要 Qdrant？RAG 能力如何保留？
8. **图数据库决策**：Neo4j 本体图是否迁入 tunxiang-os？

---

*本报告基于 2026-03-22 两仓库 main 分支状态生成。*
