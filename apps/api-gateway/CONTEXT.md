# CONTEXT.md — API Gateway（Level 2）

> 仅在任务涉及 `apps/api-gateway/` 时读取。
> 读完这里再去定位具体文件（Level 3）。

---

## 模块职责

`apps/api-gateway` 是系统唯一的对外服务端口：
1. 接收来自企业微信/飞书/前端的 HTTP 请求
2. 路由到对应 Agent 或 Service 处理
3. 管理所有持久化（PostgreSQL/Redis/Qdrant）的读写
4. 返回结构化 JSON 响应

---

## 目录结构

```
apps/api-gateway/src/
├── main.py              # FastAPI app 入口，中间件注册顺序（关键！）
├── core/
│   ├── config.py        # Settings（Pydantic）所有环境变量
│   ├── database.py      # async engine + session 工厂
│   └── security.py      # JWT 签发/验证
├── api/                 # 路由层（thin controller，不含业务逻辑）
│   ├── __init__.py      # 所有 router 注册
│   ├── menu.py          # GET /menu/recommendations
│   ├── store_memory.py  # GET/POST /stores/{id}/memory
│   └── ...（60+ 路由文件）
├── services/            # 业务逻辑层（100+ 文件，见分类）
├── models/              # SQLAlchemy ORM 模型（70+ 文件）
│   └── __init__.py      # 所有 model 必须在此注册（Alembic 依赖）
└── middleware/
    ├── security_headers.py  # X-Frame-Options / CSP / HSTS
    └── auth.py              # JWT 校验中间件
```

---

## 中间件注册顺序（main.py，外→内）

```
SecurityHeadersMiddleware   ← 最外层，所有响应加安全头
GZipMiddleware              ← 压缩（minimum_size=1000）
CORSMiddleware              ← 跨域（精确配置，非 *）
```
**注意：** JWT 校验**不是**全局 Middleware，而是通过 FastAPI `Depends(get_current_user)` 在路由层注入。
Starlette 中间件是反向执行的（最后注册的最先执行），当前注册顺序已正确。

---

## Services 层分类速查

| 类别 | 关键文件 | 说明 |
|------|---------|------|
| **Agent 调度** | `agent_service.py`, `intent_router.py` | 将用户指令路由到对应 Agent |
| **门店记忆** | `store_memory_service.py` | 计算高峰时段/员工基线/菜品健康度，Redis缓存72h |
| **菜单排名** | `menu_ranker.py` | 5因子评分（趋势/毛利/库存/时段/低退单），Redis缓存5min |
| **向量检索** | `vector_db_service_enhanced.py`, `rag_service.py` | Qdrant 语义检索，嵌入3级降级 |
| **需求预测** | `demand_forecaster.py`, `prophet_forecast_service.py` | 营业额/客流预测 |
| **通知** | `notification_service.py`, `multi_channel_notification.py` | 企微/飞书/SMS |
| **财务** | `finance_service.py`, `fct_service.py` | 财务流水/发票/税务 |
| **集成** | `pos_service.py`, `meituan_queue_service.py` | POS/美团外卖集成 |
| **知识库** | `ontology_knowledge_service.py`, `knowledge_rule_service.py` | 规则引擎/本体库 |
| **安全** | `auth_service.py`, `data_encryption_service.py` | 认证/加密 |

---

## 常见开发模式

### 新增 API 端点
```
1. models/new_model.py       ← 定义 ORM 模型
2. models/__init__.py        ← 注册（必须！否则 Alembic 检测不到）
3. services/new_service.py   ← 业务逻辑
4. api/new_router.py         ← 路由（薄层，调用 service）
5. api/__init__.py           ← 注册 router
6. alembic: make migrate-gen msg="add new_model"
7. tests/test_new_service.py ← 单元测试
```

### 异步数据库查询模式
```python
# ✅ 正确：参数化查询
stmt = select(Order).where(Order.store_id == store_id)
result = await self._db.execute(stmt)

# ✅ 正确：text() 参数化
await db.execute(text("SELECT * FROM t WHERE id = :id"), {"id": val})

# ❌ 错误：SQL 字符串拼接
await db.execute(text(f"SELECT * FROM t WHERE id = '{val}'"))

# ❌ 错误：INTERVAL 字符串嵌参
text("WHERE t >= NOW() - INTERVAL ':n days'")  # :n 不会被绑定！
# ✅ 正确：
text("WHERE t >= NOW() - (:n * INTERVAL '1 day')")
```

---

## 测试结构

```
tests/
├── conftest.py                     # DB fixture（PostgreSQL → SQLite fallback）
├── test_{service_name}.py          # 服务层单元测试（mock DB/Redis）
└── integration/
    └── test_{feature}_api.py       # API 端点集成测试（TestClient）
```

**运行：**
```bash
cd apps/api-gateway
pytest tests/ -v                    # 全部
pytest tests/test_menu_ranker_service.py -v   # 单文件
```

---

## 关键约束

- `models/__init__.py` 中未注册的 model，Alembic autogenerate 不会检测到 → 加新 model 必须同时更新此文件
- Agent 调用链：`API Route → agent_service.py → packages/agents/{domain}/src/agent.py`
- Redis Key 命名：`{namespace}:{store_id}`，例如 `store_memory:S001`, `menu_rank:S001`
- 所有金额在 DB 中以**分（fen）**存储，API 响应时由 service 层 `/100` 转元
