# Backend CLAUDE.md — API Gateway 开发指令

> 在 `apps/api-gateway/` 目录下工作时自动加载。

---

## 快速启动

```bash
# 本地开发
cd apps/api-gateway && uvicorn src.main:app --reload --port 8000

# 运行测试
cd apps/api-gateway && pytest tests/ -v -q

# 数据库迁移
alembic upgrade head                    # 执行迁移
alembic revision --autogenerate -m "描述" # 生成迁移
alembic check                           # 检查漂移
```

---

## 目录结构约定

```
src/
├── main.py              # FastAPI app 入口，中间件注册
├── core/
│   ├── config.py        # pydantic_settings 配置（环境变量）
│   ├── celery_app.py    # Celery + Beat 定时任务
│   └── celery_tasks.py  # 异步任务定义
├── api/                 # 路由层（薄，只做参数校验和调用 Service）
├── services/            # 业务逻辑层（核心代码在这里）
├── models/              # SQLAlchemy ORM 模型
├── schemas/             # Pydantic 请求/响应 Schema
├── repositories/        # 数据访问层（复杂查询封装）
├── middleware/          # CORS/Security/Auth/RateLimit
├── utils/               # 工具函数
├── ontology/            # 语义知识图谱
├── agents/              # 本地 Agent 实现
└── interfaces/          # 类型提示和协议
```

---

## 编码规则

### SQL 安全（最高优先级）
- **参数化查询**：`text("SELECT ... WHERE id = :id")` + `{"id": value}`
- **INTERVAL**：`:n * INTERVAL '1 day'`，不在字符串内嵌入参数
- **JSON 构造**：`json.dumps()`，不用 f-string
- **表名动态**：正则白名单 `^[a-z][a-z0-9_]*$` 校验后拼入

### 金额处理
- DB 存分（fen）：`Column(BigInteger)`
- API 返回元（yuan）：`amount_fen / 100`，保留2位小数
- 字段命名显式标注单位

### 除法保护
```python
# 正确
rate = cost / revenue if revenue > 0 else 0.0

# 错误（dict.get 默认值不防零）
rate = cost / data.get("revenue", 1)  # key存在但值为0时仍会除零
```

### 异步代码
- 所有 DB 操作用 `async session`
- Agent 调用用 `await`
- 测试用 `pytest-asyncio`

### 模型注册
- 新增 Model 必须在 `src/models/__init__.py` 中 import（Alembic 依赖）
- 外键统一使用 `UUID` 类型（不用 VARCHAR）
- 多租户表必须包含 `brand_id` + `store_id`

### Service 层
- 无数据时返回空结构（`[]`、`{"total": 0}`），不抛异常
- `except Exception` 必须有 `logger.warning()` 记录
- 分页接口 `total` 必须是 `SELECT COUNT(*)` 真实总量

### 测试
- pydantic_settings 校验：测试文件顶部先设 `os.environ` 再 import
- Agent 测试独立运行：`cd packages/agents/X && pytest`
- 方法重命名后 grep 所有调用点同步更新

---

## 环境变量

必须配置（无默认值，缺失即崩溃）：
- `DATABASE_URL` — PostgreSQL 连接串
- `REDIS_URL` — Redis 连接串
- `ANTHROPIC_API_KEY` — Claude API Key

可选配置：
- `L5_DISPATCH_HOUR` / `L5_DISPATCH_MINUTE` — 行动派发时间（默认 04:30）
- `WORKFORCE_PUSH_HOUR` — 人力推送时间（默认 07:00）
- `BFF_CACHE_TTL` — BFF 缓存秒数（默认 30）
