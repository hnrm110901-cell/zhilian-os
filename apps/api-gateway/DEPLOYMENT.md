# 部署指南

## 系统要求

- Python 3.9+
- PostgreSQL 13+
- Redis 6+
- Node.js 16+ (用于前端)

## 环境配置

### 1. 数据库设置

```bash
# 创建PostgreSQL数据库
createdb zhilian_os

# 创建数据库用户
createuser -P zhilian  # 设置密码: zhilian
```

### 2. Redis设置

```bash
# 启动Redis服务
redis-server

# 或使用Docker
docker run -d -p 6379:6379 redis:6-alpine
```

### 3. 环境变量配置

复制环境变量模板并配置:

```bash
cp .env.example .env
```

关键环境变量:

```bash
# 数据库配置
DATABASE_URL=postgresql+asyncpg://zhilian:zhilian@localhost:5432/zhilian_os

# Redis配置
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 企业微信配置
WECHAT_CORP_ID=your_corp_id
WECHAT_AGENT_ID=your_agent_id
WECHAT_SECRET=your_secret
WECHAT_TOKEN=your_token
WECHAT_ENCODING_AES_KEY=your_aes_key

# JWT配置
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## 安装依赖

```bash
cd apps/api-gateway
pip install -r requirements.txt
```

## 数据库迁移

```bash
# 运行所有迁移
python3 -m alembic upgrade head

# 查看当前版本
python3 -m alembic current

# 查看迁移历史
python3 -m alembic history
```

## 启动服务

### 方式一: 开发模式

```bash
# 1. 启动API服务
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 2. 启动Celery Worker (新终端)
celery -A src.core.celery_app worker --loglevel=info --concurrency=4

# 3. 启动Celery Beat (新终端)
./scripts/start_celery_beat.sh
```

### 方式二: 生产模式

```bash
# 1. 启动API服务 (使用Gunicorn)
gunicorn src.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log

# 2. 启动Celery Worker
celery -A src.core.celery_app worker \
    --loglevel=info \
    --concurrency=8 \
    --max-tasks-per-child=1000 \
    --logfile=logs/celery_worker.log

# 3. 启动Celery Beat
./scripts/start_celery_beat.sh
```

## 定时任务说明

系统配置了以下定时任务:

### 1. 日报生成 (每日凌晨1点)

- 任务: `generate_and_send_daily_report`
- 功能: 为所有门店生成前一天的营业日报
- 发送: 通过企业微信发送给门店管理员

### 2. POS对账 (每日凌晨2点)

- 任务: `perform_daily_reconciliation`
- 功能: 对比POS系统和实际订单数据
- 告警: 差异超过阈值时发送企业微信通知

## 监控和日志

### Prometheus指标

访问 `http://localhost:8000/metrics` 查看系统指标:

- HTTP请求统计
- 响应时间
- 错误率
- Celery任务统计

### 日志文件

```bash
logs/
├── access.log          # API访问日志
├── error.log           # API错误日志
├── celery_worker.log   # Celery Worker日志
└── celery_beat.log     # Celery Beat日志
```

### 查看日志

```bash
# 实时查看API日志
tail -f logs/access.log

# 实时查看Celery日志
tail -f logs/celery_worker.log

# 查看错误日志
tail -f logs/error.log
```

## 健康检查

```bash
# API健康检查
curl http://localhost:8000/health

# 数据库连接检查
curl http://localhost:8000/health/db

# Redis连接检查
curl http://localhost:8000/health/redis
```

## 常见问题

### 1. 数据库连接失败

检查PostgreSQL服务是否运行:
```bash
pg_isready
```

检查数据库配置:
```bash
psql -U zhilian -d zhilian_os -c "SELECT 1"
```

### 2. Redis连接失败

检查Redis服务:
```bash
redis-cli ping
```

### 3. Celery任务不执行

检查Celery Worker状态:
```bash
celery -A src.core.celery_app inspect active
```

检查Celery Beat状态:
```bash
celery -A src.core.celery_app inspect scheduled
```

### 4. 企业微信消息发送失败

检查企业微信配置:
- WECHAT_CORP_ID
- WECHAT_AGENT_ID
- WECHAT_SECRET

测试企业微信连接:
```bash
curl -X POST http://localhost:8000/api/v1/test/wechat
```

## 性能优化

### 1. 数据库连接池

在 `.env` 中配置:
```bash
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
```

### 2. Redis连接池

```bash
REDIS_POOL_SIZE=50
REDIS_MAX_CONNECTIONS=100
```

### 3. Celery并发

根据CPU核心数调整:
```bash
# Worker并发数 = CPU核心数 * 2
celery -A src.core.celery_app worker --concurrency=8
```

## 备份和恢复

### 数据库备份

```bash
# 备份数据库
pg_dump -U zhilian zhilian_os > backup_$(date +%Y%m%d).sql

# 恢复数据库
psql -U zhilian zhilian_os < backup_20260221.sql
```

### Redis备份

```bash
# Redis会自动保存到dump.rdb
# 手动触发保存
redis-cli BGSAVE
```

## 安全建议

1. **更改默认密码**: 修改数据库和Redis密码
2. **使用HTTPS**: 在生产环境使用SSL证书
3. **限制访问**: 配置防火墙规则
4. **定期更新**: 保持依赖包最新
5. **备份数据**: 定期备份数据库和配置文件

## 扩展部署

### 使用Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://zhilian:zhilian@db:5432/zhilian_os
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

  worker:
    build: .
    command: celery -A src.core.celery_app worker --loglevel=info
    depends_on:
      - db
      - redis

  beat:
    build: .
    command: celery -A src.core.celery_app beat --loglevel=info
    depends_on:
      - db
      - redis

  db:
    image: postgres:13
    environment:
      - POSTGRES_USER=zhilian
      - POSTGRES_PASSWORD=zhilian
      - POSTGRES_DB=zhilian_os
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:6-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

## 支持

如有问题，请查看:
- API文档: http://localhost:8000/docs
- 项目README: /apps/api-gateway/README.md
- 测试文档: /apps/api-gateway/tests/README.md
