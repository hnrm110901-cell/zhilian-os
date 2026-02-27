# 业财税资金一体化（FCT）独立部署指南

本文说明如何将 FCT 以**独立服务**形态部署，与智链OS 解耦，通过 HTTP 对接业务系统（智链OS 或第三方 POS/ERP）。

---

## 一、适用场景

- 客户已有业务系统，仅采购业财税资金能力，不部署智链OS。
- 业财税资金与智链OS 分集群部署，通过 `fct.mode=remote` + HTTP 对接。
- 压测或演示时单独跑 FCT，不启动完整智链OS。

---

## 二、运行方式

### 2.1 前提

- 与智链OS 共用同一代码仓（`zhilian-os`），仅换启动入口。
- 已执行过 FCT 表结构迁移（与智链OS 合并部署时相同）：  
  `alembic upgrade head`（在 `apps/api-gateway` 目录下，且 `alembic.ini` 指向同一数据库或独立库均可）。

### 2.2 环境变量

独立服务仍使用 `src.core.config`，需提供以下变量（可在 `apps/api-gateway/.env` 或环境中配置）：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DATABASE_URL` | 是 | PostgreSQL 连接串，建议 `postgresql+asyncpg://user:pass@host:port/dbname` |
| `REDIS_URL` | 是* | 当前 FCT 逻辑未使用 Redis，但配置类要求存在，可填占位如 `redis://localhost:6379/0` |
| `SECRET_KEY` | 是* | 占位即可，如 `fct-standalone-secret` |
| `JWT_SECRET` | 是* | 占位即可，如 `fct-standalone-jwt` |
| `CELERY_BROKER_URL` | 是* | 占位即可，如 `redis://localhost:6379/1` |
| `CELERY_RESULT_BACKEND` | 是* | 占位即可，如 `redis://localhost:6379/2` |
| `FCT_API_KEY` | 否 | 独立服务 API Key；设置后请求需带 `X-API-Key`，不设则不做校验（仅建议内网使用） |

\* 沿用智链OS 的 `Settings`，这些字段必填，独立部署时可使用占位值。

### 2.3 启动命令

在 **智链OS 的 api-gateway 目录** 下执行（保证能解析 `src`）：

```bash
cd apps/api-gateway
uvicorn fct_standalone_main:app --host 0.0.0.0 --port 8001
```

或指定环境与 worker 数：

```bash
uvicorn fct_standalone_main:app --host 0.0.0.0 --port 8001 --workers 1
```

服务启动后：

- 健康检查：`GET http://localhost:8001/health`
- API 文档：`http://localhost:8001/docs`

---

## 三、API 契约（与合并形态一致）

### 3.1 业财事件

- **独立形态推荐路径**：`POST /api/v1/events`  
- **与合并形态一致路径**：`POST /api/v1/fct/events`

请求体（示例）：

```json
{
  "event_type": "store_daily_settlement",
  "event_id": "evt_001",
  "tenant_id": "T001",
  "entity_id": "STORE_001",
  "payload": {
    "store_id": "STORE_001",
    "biz_date": "2025-02-25",
    "total_sales": 50000,
    "total_sales_tax": 2500,
    "payment_breakdown": [{"method": "wechat", "amount": 30000}, {"method": "cash", "amount": 20000}],
    "discounts": 0
  }
}
```

若配置了 `FCT_API_KEY`，请求头需带：`X-API-Key: <FCT_API_KEY>`。

### 3.2 凭证与总账

| 能力 | 方法 | 路径 |
|------|------|------|
| 凭证列表 | GET | `/api/v1/fct/vouchers` |
| 凭证详情 | GET | `/api/v1/fct/vouchers/{id}` |
| 总账余额 | GET | `/api/v1/fct/ledger/balances?tenant_id=xxx` |
| 业财报表（占位） | GET | `/api/v1/fct/reports/{report_type}` |
| 服务状态 | GET | `/api/v1/fct/status` |

同上，若配置了 `FCT_API_KEY`，需在请求头带 `X-API-Key`。

---

## 四、智链OS 对接独立 FCT 服务

当 FCT 独立部署时，智链OS 侧配置：

- `FCT_ENABLED=true`
- `FCT_MODE=remote`
- `FCT_BASE_URL=http://fct-service:8001`（或实际独立服务地址）
- `FCT_EVENT_TARGET=http`
- `FCT_EVENT_HTTP_URL=http://fct-service:8001/api/v1/events`
- （若独立服务启用了 API Key）在智链OS 侧调用 FCT 时请求头需带 `X-API-Key`（需在调用 FCT 的代码或配置中传入，当前合并形态为内网直接调 fct_service，未走 HTTP；若后续改为 HTTP 转发，则需在此处配置 Key）。

当前 Phase 2 实现为：独立服务可单独启动并对外提供上述 API；智链OS 在 `mode=remote` 时**通过 HTTP 调用独立服务**的对接逻辑可在后续迭代中在 `fct_integration` 或适配层中增加（例如根据 `FCT_MODE` 和 `FCT_BASE_URL` 选择调用本地 fct_service 或请求独立服务 `/api/v1/events`）。

---

## 五、Docker 示例（可选）

在 `apps/api-gateway` 目录下可使用与智链OS 同一镜像、仅换启动命令的方式运行独立服务：

```dockerfile
# 与智链OS API Gateway 共用镜像，仅 CMD 不同
CMD ["uvicorn", "fct_standalone_main:app", "--host", "0.0.0.0", "--port", "8001"]
```

或 docker-compose 片段：

```yaml
fct-standalone:
  build: ./apps/api-gateway
  command: uvicorn fct_standalone_main:app --host 0.0.0.0 --port 8001
  environment:
    - DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/fct
    - REDIS_URL=redis://redis:6379/0
    - SECRET_KEY=standalone-secret
    - JWT_SECRET=standalone-jwt
    - CELERY_BROKER_URL=redis://redis:6379/1
    - CELERY_RESULT_BACKEND=redis://redis:6379/2
    - FCT_API_KEY=your-api-key
  ports:
    - "8001:8001"
  depends_on:
    - db
```

---

## 六、代码位置（Phase 2）

| 说明 | 路径 |
|------|------|
| 独立服务入口 | `apps/api-gateway/fct_standalone_main.py` |
| 公开 API（API Key 认证） | `src/api/fct_public.py` |
| API Key 配置项 | `src/core/config.py`（`FCT_API_KEY`） |
| 核心逻辑（与合并形态共用） | `src/services/fct_service.py`、`src/models/fct.py` |

与《[业财税资金一体化技术方案](./chain-restaurant-finance-tax-treasury-technical-solution.md)》中独立形态契约一致，可合并销售或独立交付。
