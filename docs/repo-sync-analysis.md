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

**tunxiang-os Agent 核心组件**（已实现）：
- **base.py**（3.8KB）：`SkillAgent` 抽象基类 + `AgentResult` 数据类（含 confidence/constraints_passed/execution_ms）
- **master.py**（4.7KB）：`MasterAgent` 编排器（register/dispatch/route_intent/multi_agent_execute）
- **constraints.py**（5.2KB）：3 项约束检查（利润率≥15% / 食材24h过期 / 服务≤30分钟）
- **memory_bus.py**（3.3KB）：Agent 间共享记忆总线（Finding + TTL 1h）
- **decision_push.py**（4.4KB）：4 时段推送（08:00 晨会 / 12:00 损耗 / 17:30 备战 / 20:30 日结）
- **9 个 Skill Agent**：每个 6~15KB，代码量充实

**关键差异**：
- zhilian-os 有 30 个 Agent（15 内置 + 15 独立包），覆盖面广但冗余
- tunxiang-os 精简为 9 个 Skill Agent + 1 个 Master Agent，架构更清晰
- tunxiang-os 新增约束检查器（Constraint Checker）和记忆总线（Memory Bus），zhilian-os 缺少这些基础设施

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

**更正**：tunxiang-os 的 `shared/adapters/` 实际已实现完整的适配器注册体系：
- **Base 基类**（5.1KB）：含 httpx 异步客户端、tenacity 重试、认证抽象
- **Registry 注册中心**（7KB）：动态加载，按类型分 POS/预订/外卖/供应链/会员/财务 6 类
- **品智 POS**（26.4KB）：MD5 签名认证，菜单/订单/财务全接口
- **奥琦玮**（22.6KB + CRM 13.8KB）：API Key 认证，含 CRM 集成
- **美团 SaaS**（17.6KB + 预订 2KB）：外卖 + 等位
- 天财商龙、客如云、一订、饿了么、抖音、微生活、诺诺：已注册但实现程度不一

**结论**：tunxiang-os 适配器体系比初步分析更完善，品智/奥琦玮/美团已有较完整实现。

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

## 9. tunxiang-os 各微服务 API 明细

### tx-trade（端口 8001）— 交易引擎
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/orders` | 创建订单 |
| POST | `/orders/{id}/items` | 加菜 |
| PATCH | `/orders/{id}/items/{item_id}` | 改数量 |
| DELETE | `/orders/{id}/items/{item_id}` | 退菜 |
| POST | `/orders/{id}/discount` | 打折 |
| POST | `/orders/{id}/settle` | 结算 |
| POST | `/orders/{id}/cancel` | 取消 |
| GET | `/orders/{id}` | 查询订单 |
| POST | `/orders/{id}/payments` | 支付 |
| POST | `/orders/{id}/refund` | 退款 |
| POST | `/orders/{id}/print/receipt` | 打印小票 |
| POST | `/orders/{id}/print/kitchen` | 厨房打印 |

### tx-supply（端口 8003）— 供应链
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/inventory` | 库存列表 |
| POST | `/inventory/{id}/adjust` | 库存调整 |
| GET | `/inventory/alerts` | 库存预警 |
| GET/POST | `/procurement/plans` | 采购计划 |
| POST | `/procurement/plans/{id}/approve` | 审批采购 |
| GET | `/suppliers` | 供应商列表 |
| GET | `/suppliers/{id}/rating` | 供应商评分 |
| GET | `/suppliers/price-comparison` | 比价 |
| GET | `/waste/top5` | Top5 损耗 |
| GET | `/waste/rate` | 损耗率趋势 |
| GET | `/demand/forecast` | 需求预测（7天+） |

### tx-member（端口 8004）— 会员
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/customers` | 客户 CRUD |
| GET | `/customers/{id}` | Golden ID 360° 画像 |
| GET | `/customers/{id}/orders` | 消费历史 |
| GET | `/rfm/segments` | RFM 分层（S1-S5） |
| GET | `/rfm/at-risk` | 流失风险客户 |
| GET/POST | `/campaigns` | 营销活动 |
| POST | `/campaigns/{id}/trigger` | 触发活动 |
| GET | `/journeys` | 客户旅程 |
| POST | `/customers/merge` | Golden ID 合并 |

### tx-org（端口 8006）— 组织
| 方法 | 路径 | 说明 |
|------|------|------|
| CRUD | `/employees` | 员工管理 |
| GET | `/employees/{id}/performance` | 绩效（含提成） |
| GET | `/labor-cost` | 人力成本分析 |
| POST | `/attendance/clock-in` | 打卡 |
| GET | `/training/plans` | 培训计划 |
| GET | `/turnover-risk` | 离职风险预测 |
| GET | `/schedule` | 排班 |

### tx-analytics（端口 8007）— 分析
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stores/health` | 门店健康度（5 维评分） |
| GET | `/stores/{id}/brief` | 叙事引擎概要 |
| GET | `/kpi/alerts` | KPI 预警 |
| GET | `/kpi/trend` | KPI 趋势（30天） |
| GET | `/reports/daily` | 日报 |
| GET | `/reports/weekly` | 周报 |
| GET | `/decisions/top3` | AI Top3 建议 |
| GET | `/scenario` | 场景识别 |
| GET | `/cross-store/insights` | 跨店洞察 |
| GET | `/bff/hq/{brand_id}` | 总部 BFF（30s 缓存） |
| GET | `/bff/sm/{store_id}` | 店长 BFF |

### tx-agent（端口 8008）— Agent OS
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agents` | 已注册 Agent 列表 |
| POST | `/dispatch` | 按 agent_id + action 调度 |

### 门店健康度评分权重（tx-analytics）
| 维度 | 权重 | 目标值 |
|------|------|--------|
| 营收完成率 | 30% | 日目标 100% |
| 翻台率 | 20% | 2.0 次/小时 |
| 成本率 | 25% | 预算偏差 ≤ 2% |
| 投诉率 | 15% | 越低越好 |
| 人效 | 10% | ≥ ¥500/人·小时 |

---

## 10. 测试覆盖对比

| 维度 | zhilian-os | tunxiang-os |
|------|-----------|-------------|
| 总测试数 | 分散在各 packages | **173 tests passing** |
| tx-agent 测试 | — | 76 tests |
| tx-analytics 测试 | — | 40 tests |
| tx-trade 测试 | — | 26 tests |
| tx-supply 测试 | — | 21 tests |
| 集成测试 | — | 10 tests |
| 测试框架 | pytest + pytest-asyncio | pytest + pytest-asyncio（asyncio_mode=auto） |

---

*本报告基于 2026-03-22 两仓库 main 分支状态生成，含 tunxiang-os 服务层源码级分析。*
