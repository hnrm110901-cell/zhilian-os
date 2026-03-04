# ARCHITECTURE.md — 智链OS 全景图（Level 1）

> 每次新任务启动必读。理解整体架构后再定位具体模块。

---

## 系统定位

**智链OS** = 餐饮连锁智能体操作系统
- 通过 10 个专属 AI Agent，将门店运营决策（排班/库存/菜单/服务/培训）自动化
- 核心接入：企业微信 / 飞书 Webhook → 自然语言指令 → Agent 执行 → 结果回传
- 部署形态：SaaS 多租户（brand_id + store_id 两级隔离）

---

## 模块依赖图

```
外部渠道
  企业微信 Webhook
  飞书 Webhook
  POS 系统 / 美团外卖
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  apps/api-gateway  (FastAPI, Python 3.11+)          │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ API Routes   │  │ Middleware   │                 │
│  │ /api/v1/...  │  │ CORS/GZip/   │                 │
│  │              │  │ Security/    │                 │
│  │              │  │ Auth/Rate    │                 │
│  └──────┬───────┘  └──────────────┘                 │
│         │                                           │
│  ┌──────▼──────────────────────────────────────┐   │
│  │  Services 层 (100+ service files)            │   │
│  │  核心：agent_service / intent_router         │   │
│  │        store_memory_service / menu_ranker    │   │
│  │        vector_db_service / rag_service       │   │
│  │        analytics / forecast / notification  │   │
│  └──────┬──────────────────────────────────────┘   │
└─────────┼───────────────────────────────────────────┘
          │  调用（HTTP内部 或 直接 import）
          ▼
┌─────────────────────────────────────────────────────┐
│  packages/agents  (LangChain + LangGraph)           │
│                                                     │
│  schedule │ order │ inventory │ private_domain      │
│  service  │ training │ decision │ ops               │
│  performance │ reservation                          │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────────┐
          ▼            ▼                ▼
    PostgreSQL       Redis           Qdrant
    (主存储)      (缓存+会话)      (向量检索)
    asyncpg        Sentinel HA      384维嵌入
```

---

## 核心领域模型

| 实体 | 说明 | 关键字段 |
|------|------|---------|
| `Store` | 门店（多租户基本单元）| `store_id`, `brand_id` |
| `Order` / `OrderItem` | 订单及明细 | `store_id`, `waiter_id`, `final_amount`(分) |
| `Employee` | 员工 | `store_id`, `role` |
| `Dish` | 菜品 | `store_id`, `is_available`, `cost`, `price` |
| `InventoryItem` | 库存 | `store_id`, `current_stock`, `min_stock` |
| `StoreMemory` | 门店运营记忆快照 | `peak_patterns`, `anomaly_patterns` |
| `DailyWorkflow` | 每日决策工作流 | `phases`, `status` |

**金额单位约定：** 数据库存分（fen），展示/计算时 `/100` 转元

---

## 技术栈快照

| 层次 | 技术 | 版本/说明 |
|------|------|---------|
| Web 框架 | FastAPI | async first |
| ORM | SQLAlchemy 2.0 | async session + asyncpg |
| 数据库迁移 | Alembic | sync psycopg2（迁移专用）|
| Agent 框架 | LangChain + LangGraph | 状态机式 Agent |
| LLM | Claude API（Anthropic）| 可配置 |
| 向量DB | Qdrant | 本地 + 云端 |
| 嵌入模型 | sentence-transformers | 384维，本地优先 |
| 缓存 | Redis + Sentinel | TTL 策略按业务定 |
| 任务队列 | Celery | 定时刷新/异步任务 |
| 监控 | Prometheus + Grafana | 告警规则在 monitoring/ |
| 容器编排 | Kubernetes | k8s/ 目录全套配置 |
| 反向代理 | Nginx | SSL/TLS 终止 |

---

## 关键文件路径

```bash
# 入口
apps/api-gateway/src/main.py              # FastAPI app，中间件注册
apps/api-gateway/src/core/config.py       # 全部配置（Settings）

# Agent 分发
apps/api-gateway/src/services/agent_service.py   # Agent 调度入口
apps/api-gateway/src/services/intent_router.py   # 自然语言意图路由

# 核心业务服务
apps/api-gateway/src/services/store_memory_service.py
apps/api-gateway/src/services/menu_ranker.py
apps/api-gateway/src/services/vector_db_service_enhanced.py
apps/api-gateway/src/services/demand_forecaster.py

# 数据模型
apps/api-gateway/src/models/__init__.py   # 所有 model 注册（Alembic 依赖）
apps/api-gateway/alembic/env.py           # 迁移环境配置

# Agent 包（每个 agent 结构相同）
packages/agents/{domain}/src/agent.py    # Agent 实现
packages/agents/{domain}/tests/          # Agent 测试

# 基础设施
nginx/conf.d/default.conf                 # Nginx SSL + 安全头
k8s/                                      # K8s 全套配置
monitoring/                               # Prometheus + Grafana
```

---

## 构建 / 测试 / 部署（一行命令）

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全量测试
pytest packages/*/tests -v --cov=packages

# 运行特定 Agent 测试
pytest packages/agents/schedule/tests -v

# 运行 API Gateway 测试
cd apps/api-gateway && pytest tests/ -v

# 启动本地开发服务
make run           # uvicorn + reload，端口 8000

# 数据库迁移
make migrate-gen msg="描述变更"    # 生成迁移文件
make migrate-up                    # 执行迁移
make migrate-status                # 查看当前版本

# Docker
make up            # docker-compose 启动所有服务
make down          # 停止
make logs          # 查看日志
```

---

## 已知约束与痛点

| 痛点 | 说明 | 影响范围 |
|------|------|---------|
| sys.path 污染 | 多 Agent 测试并行运行时互相覆盖 `src/agent.py` | packages/agents/* 测试需独立运行 |
| 同步 Alembic | 迁移用 psycopg2（同步），运行时用 asyncpg | alembic/env.py URL 转换逻辑不能删 |
| 金额单位 | DB 存分，API 返回元，转换分散在各 service | 改动金额字段时必须确认单位 |
| 嵌入降级 | 无本地模型+无 API Key 时返回零向量，语义无意义 | RAG 检索质量会下降，需监控 |
| 用户培训文档 | Phase 3 已完成（docs/user-training-guide.md） | — |
