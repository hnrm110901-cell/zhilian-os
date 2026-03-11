# 智链OS 四层架构说明

> 按需加载：当任务涉及跨层交互或架构决策时读取此文件。

---

## 四层 Ontology 架构

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Perception（感知层）                        │
│  企业微信/飞书 Webhook → 自然语言 → intent_router     │
│  POS 数据同步 → api-adapters（客如云/美团/宜鼎）       │
│  定时任务 → Celery Beat（04:30行动派发/07:00人力推送） │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Ontology（本体层）                          │
│  11个核心对象类型（见下方实体清单）                      │
│  SQLAlchemy Model + Pydantic Schema                  │
│  金额单位：DB存分(fen)，API返回元(yuan)               │
│  多租户：brand_id + store_id 两级隔离                 │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3: Reasoning（推理层）                         │
│  11个 Domain Agent（LangChain + LangGraph）          │
│  packages/agents/{domain}/src/agent.py               │
│  Agent 无状态：接收数据 → 推理 → 返回结果              │
│  Services 层编排：agent_service.py 调度分发            │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 4: Action（行动层）                            │
│  L5 行动派发：action_dispatch_service.py              │
│  企微推送：wechat_action_fsm.py（P0-P3优先级）        │
│  一键确认：StaffingAdviceConfirmation 等闭环           │
│  案例采集：case_story_generator.py                    │
└─────────────────────────────────────────────────────┘
```

---

## 11个 Domain Agent

| # | Agent | 包路径 | 职责 | 核心输出 |
|---|-------|--------|------|---------|
| 1 | Schedule | `packages/agents/schedule/` | 需求驱动排班 | 班次表 + ¥人力成本预估 |
| 2 | Order | `packages/agents/order/` | 订单流转 | 订单状态 + ¥金额 |
| 3 | Inventory | `packages/agents/inventory/` | 库存预警 + 采购建议 | 补货清单 + ¥采购金额 |
| 4 | Service | `packages/agents/service/` | 服务质量分析 | 改进建议 + 满意度评分 |
| 5 | Training | `packages/agents/training/` | 员工培训 | 技能评估 + 培训计划 |
| 6 | Performance | `packages/agents/performance/` | KPI跟踪 | 指标对标 + ¥差距分析 |
| 7 | Decision | `packages/agents/decision/` | 跨店决策 | 经营建议 + ¥ROI预测 |
| 8 | Reservation | `packages/agents/reservation/` | 预订管理 | 排期 + 预估¥营收 |
| 9 | Banquet | `packages/agents/banquet/` | 宴会全流程 | BEO + ¥报价 + 应收管理 |
| 10 | Private Domain | `packages/agents/private_domain/` | 会员营销 | CRM策略 + ¥转化预测 |
| 11 | Dish R&D | `packages/agents/dish_rd/` | 菜单创新 | 成本分析 + ¥毛利预测 |

---

## 服务层关键路径

```
intent_router.py          → 自然语言意图分类 → 分发到对应 Agent
agent_service.py          → Agent 调度入口，管理 Agent 生命周期
store_memory_service.py   → 门店运营记忆（峰值模式/异常模式/季节性）
vector_db_service_enhanced.py → RAG 语义检索（Qdrant 384维）
demand_forecaster.py      → 客流/营收预测（三档降级）
menu_ranker.py            → 菜品排名 + 毛利优化
labor_demand_service.py   → 人力需求预测（客流→岗位需求）
labor_cost_service.py     → 人工成本监控 + 跨店排名
workforce_push_service.py → 每日人力建议推送（企微）
action_dispatch_service.py → L5 行动计划派发（Celery Beat）
```

---

## BFF 聚合模式

```
GET /api/v1/bff/{role}/{store_id}

角色: sm(店长) / chef(厨师长) / floor(楼面) / hq(总部)
缓存: Redis 30s TTL
强刷: ?refresh=true
降级: 子调用失败返回 null，前端 ZEmpty 占位
```

---

## 技术栈速查

| 层次 | 技术 | 关键配置 |
|------|------|---------|
| Web 框架 | FastAPI | async first, CORS/GZip/Security 中间件 |
| ORM | SQLAlchemy 2.0 | async session + asyncpg |
| 迁移 | Alembic | sync psycopg2（迁移专用，env.py URL转换） |
| Agent | LangChain + LangGraph | 状态机式，无状态设计 |
| LLM | Claude API (Anthropic) | claude-sonnet-4-6(生产) / claude-opus-4-6(架构) |
| 向量DB | Qdrant | 384维嵌入，本地优先 |
| 缓存 | Redis + Sentinel HA | TTL 按业务定 |
| 任务队列 | Celery + Beat | 定时刷新/异步推送 |
| 容器 | Docker + K8s | k8s/ 全套配置 |
| 监控 | Prometheus + Grafana | monitoring/ 目录 |
| 反代 | Nginx | SSL/TLS 终止，安全头 |

---

## 外部集成（API Adapters）

| 系统 | 包路径 | 数据 |
|------|--------|------|
| 客如云 | `packages/api-adapters/keruyun/` | POS订单/菜品/库存 |
| 美团SaaS | `packages/api-adapters/meituan-saas/` | 外卖订单 |
| 宜鼎 | `packages/api-adapters/yiding/` | 宴会预订 |
| 品质 | `packages/api-adapters/pinzhi/` | 质检数据 |
| 天财商龙 | `packages/api-adapters/tiancai-shanglong/` | HR/考勤 |
| 奥琦玮 | `packages/api-adapters/aoqiwei/` | 会员/营销 |
