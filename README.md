# 屯象OS (TunXiang OS)

> 连锁餐饮 AI 经营决策系统 — 餐饮人的好伙伴

<p align="center">
  <img src="apps/web/public/logo-icon.svg" alt="屯象OS" width="120" />
</p>
<p align="center">
  <strong>Ω — 终极解决方案 · 象的厚重沉稳</strong>
</p>

## 产品定位

屯象OS 是面向连锁餐饮品牌的 **AI 驱动经营决策 SaaS 平台**。通过 10 大 AI Agent 将门店运营决策（排班、库存、菜单、营销、财务）自动化，帮助连锁老板每年多赚 30 万+（成本率降低 2 个百分点）。

**核心指标**：续费率 ≥ 95%

**首批客户**：尝在一起、最黔线、尚宫厨、徐记海鲜

---

## 系统架构

```
用户端
  管理后台 (React)  ·  店长/厨师长/楼面移动端  ·  总部驾驶舱
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  apps/api-gateway  (FastAPI · Python 3.11)          │
│  100+ API · BFF 聚合 · RBAC · 多租户隔离            │
└──────────┬──────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────┐
│  packages/agents  (LangChain + LangGraph)            │
│  15 个 AI Agent · 向量检索 · 事件驱动 · 联邦学习     │
└──────────┬──────────────────────────────────────────┘
           │
     ┌─────┼─────────────────┐
     ▼     ▼                 ▼
 PostgreSQL  Redis         Qdrant
 (主存储)   (缓存·队列)    (向量检索)
```

**部署形态**：SaaS 多租户（`brand_id` + `store_id` 两级隔离）

---

## 核心能力

### 10 大 AI Agent

| 层级 | Agent | 能力 |
|------|-------|------|
| 增长层 | **经营智能体** BusinessIntel | KPI 异常检测、经营日报、CEO/CFO 驾驶舱 |
| 增长层 | **营销智能体** Marketing | 私域运营、会员 RFM 分层、企微自动触发 |
| 增长层 | **宴会智能体** Banquet | 7 阶段销售漏斗、宴会全生命周期管理 |
| 运营层 | **运营流程体** OpsFlow | 出品链联动、损耗推理、三源对账 |
| 运营层 | **人员智能体** People | 智能排班、员工绩效、人力成本分析 |
| 运营层 | **菜品研发** DishRd | BOM 配方管理、菜品成本分析、新品研发 |
| 底座层 | **合规智能体** Compliance | 质量管理、食品安全、审计追踪 |
| 底座层 | **IT 运维** Ops | 系统健康、适配器监控、Edge 节点管理 |
| 底座层 | **财务智能体** FCT | 利润分析、预算管理、结算风控、财务预测 |
| 底座层 | **供应商智能体** Supplier | 供应链管理、采购协同、库存预警 |

### 4 角色工作台

| 角色 | 路由 | 设备 | 核心场景 |
|------|------|------|----------|
| 店长 | `/sm` | 手机 | 晨间 AI 决策卡、KPI 大盘、一键确认排班 |
| 厨师长 | `/chef` | 手机 | 出品看板、损耗登记、备菜清单、沽清管理 |
| 楼面经理 | `/floor` | 平板 | 排队叫号、翻台监控、预订冲突检测 |
| 总部 | `/hq` | 桌面 | 多店矩阵、跨店对标、品牌级决策下发 |

### 三层导航架构

```
L1  顶部域Tab    经营总览 · 运营中心 · 增长引擎 · 供应链 · 智能体 · 平台治理
L2  可折叠侧栏   220px ↔ 56px · 分组折叠 · RBAC 过滤 · 状态徽标
L3  内容区       面包屑 · KPI 卡片 · AI 建议卡 · 数据钻取
```

### POS 系统适配

| 适配器 | 品牌 | 能力 |
|--------|------|------|
| 品智 Pinzhi | 尝在一起 | 订单同步、日结汇总、菜品明细、Celery 每日 01:30 自动拉取 |
| 天财商龙 | 最黔线 | 订单查询、门店汇总 |
| 奥琦韦 | — | 排班、预订、订单 |
| 客如云 | — | 订单、会员 |
| 易订 | — | 预订管理 |
| 美团 SaaS | — | 排队、外卖 |

---

## 技术栈

### 后端

| 组件 | 技术 |
|------|------|
| 框架 | FastAPI (Python 3.11+, async) |
| AI | LangChain + LangGraph |
| 数据库 | PostgreSQL 15 (asyncpg, 多租户 Schema) |
| 缓存/队列 | Redis 7 (Sentinel HA) + Celery Beat |
| 向量数据库 | Qdrant 1.7 |
| 图数据库 | Neo4j 5.17 |
| 认证 | JWT + RBAC + OAuth (企微/飞书/钉钉) |
| 迁移 | Alembic (多租户 Schema 级迁移) |

### 前端

| 组件 | 技术 |
|------|------|
| 框架 | React 19 + TypeScript 5.9 |
| UI 库 | Ant Design 5 + 自研 Z 组件库 |
| 图表 | ECharts 5 (ReactECharts) + ChartTrend (Canvas) |
| 构建 | Vite 7.3 |
| 样式 | CSS Modules + Design Token 系统 |
| 路由 | React Router 6 (角色路由 /sm /chef /floor /hq) |

### 运维

| 组件 | 技术 |
|------|------|
| 容器 | Docker + Docker Compose (dev/staging/prod) |
| CI/CD | GitHub Actions |
| 监控 | Prometheus + Grafana + Alertmanager |
| 反向代理 | Nginx (SSL/TLS, 通配符证书) |
| 语音 | Shokz 骨传导耳机 WebSocket 集成 |

---

## 项目结构

```
zhilian-os/
├── apps/
│   ├── web/                    # 管理后台 (React + Vite)
│   │   ├── src/layouts/        # MainLayout(三层导航) + 角色 Layout
│   │   ├── src/pages/          # 100+ 页面
│   │   ├── src/pages/sm/       # 店长移动端 (8 页面)
│   │   ├── src/pages/chef/     # 厨师长 (4 页面)
│   │   ├── src/pages/hq/       # 总部驾驶舱 (6 页面)
│   │   ├── src/design-system/  # Design Token + Z 组件库
│   │   └── src/components/     # 全局搜索 · 通知中心 · 推荐卡片
│   └── api-gateway/            # API 网关 (FastAPI)
│       ├── src/api/            # 40+ API 路由模块
│       ├── src/services/       # 100+ Service 文件
│       ├── src/models/         # SQLAlchemy ORM 模型
│       ├── src/core/           # 安全 · 数据库 · Celery · 配置
│       ├── src/middleware/      # CORS · GZip · 认证 · 限流 · 租户
│       └── alembic/            # 数据库迁移 (多租户)
├── packages/
│   ├── agents/                 # 15 个 AI Agent
│   │   ├── schedule/           # 智能排班
│   │   ├── order/              # 订单协同
│   │   ├── inventory/          # 库存预警
│   │   ├── banquet/            # 宴会管理
│   │   ├── business_intel/     # 经营智能
│   │   ├── people_agent/       # 人员管理
│   │   ├── ops_flow/           # 运营流程
│   │   ├── private_domain/     # 私域运营
│   │   ├── dish_rd/            # 菜品研发
│   │   ├── supplier/           # 供应商
│   │   ├── decision/           # 决策支持
│   │   ├── service/            # 服务质量
│   │   ├── training/           # 培训辅导
│   │   ├── reservation/        # 预订管理
│   │   └── performance/        # 绩效分析
│   └── api-adapters/           # POS 适配器
│       ├── pinzhi/             # 品智 (尝在一起)
│       ├── tiancai-shanglong/  # 天财商龙
│       ├── aoqiwei/            # 奥琦韦
│       ├── keruyun/            # 客如云
│       ├── yiding/             # 易订
│       └── meituan-saas/       # 美团 SaaS
├── nginx/                      # Nginx 配置 + SSL
├── scripts/                    # 运维脚本 (部署/备份/监控)
├── docker-compose.yml          # 开发环境
├── docker-compose.staging.yml  # Staging 环境
├── docker-compose.prod.yml     # 生产环境 (Redis HA + Celery)
└── docs/                       # 产品/技术文档
```

---

## 快速开始

### 环境要求

- Node.js ≥ 18 · pnpm ≥ 8
- Python ≥ 3.11
- Docker ≥ 24 · Docker Compose
- PostgreSQL ≥ 15 · Redis ≥ 7

### 安装与启动

```bash
# 1. 克隆
git clone https://github.com/hnrm110901-cell/zhilian-os.git
cd zhilian-os

# 2. 启动基础设施
docker-compose up -d   # PostgreSQL, Redis, Qdrant, Neo4j

# 3. 后端
cd apps/api-gateway
pip install -r requirements.txt
cp .env.example .env   # 编辑环境变量
alembic upgrade head   # 数据库迁移
uvicorn src.main:app --reload --port 8000

# 4. 前端
cd apps/web
pnpm install
pnpm dev               # http://localhost:5173
```

### 关键环境变量

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串 |
| `REDIS_URL` | Redis 连接串 |
| `JWT_SECRET_KEY` | JWT 签名密钥 |
| `OPENAI_API_KEY` | LLM API 密钥 |
| `PINZHI_TOKEN` | 品智 POS Token |

### 生产部署

```bash
# 环境检查
make prod-env-check

# 一键部署 (Docker Compose)
make prod-deploy

# 健康检查
make prod-health

# 数据库迁移
docker compose -f docker-compose.prod.yml exec api-gateway alembic upgrade head
```

详细部署文档：[docs/deployment-guide.md](./docs/deployment-guide.md)

---

## 开发规范

- **提交规范**：Conventional Commits (`feat:` / `fix:` / `docs:`)
- **分支策略**：`main` → 功能分支 → PR → 合并
- **TypeScript**：严格模式，零 TS 错误
- **Python**：snake_case, 参数化 SQL, 禁止字符串拼接
- **CSS**：CSS Modules，禁止内联样式（动态值除外）
- **前端数据获取**：统一使用 `apiClient`，禁止裸 fetch/axios

完整规范：[CLAUDE.md](./CLAUDE.md)

---

## 许可证

MIT License

---

**屯象OS** © 2026 — 让每一家连锁餐厅都有自己的 AI 经营伙伴
