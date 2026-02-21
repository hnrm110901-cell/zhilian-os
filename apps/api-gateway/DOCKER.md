# Docker 部署指南

## 概述

本项目提供完整的Docker容器化部署方案，包括API服务、数据库、缓存和后台任务处理。

## 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

### 一键启动

```bash
# 克隆项目
git clone <repository-url>
cd zhilian-os/apps/api-gateway

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f api
```

访问服务:
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## 服务架构

### 服务列表

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| db | zhilian-db | 5432 | PostgreSQL数据库 |
| redis | zhilian-redis | 6379 | Redis缓存 |
| qdrant | zhilian-qdrant | 6333 | 向量数据库 |
| api | zhilian-api | 8000 | FastAPI服务 |
| worker | zhilian-worker | - | Celery Worker |
| beat | zhilian-beat | - | Celery Beat |

### 网络拓扑

```
zhilian-network (bridge)
├── db (PostgreSQL)
├── redis (Redis)
├── qdrant (Qdrant)
├── api (FastAPI)
├── worker (Celery Worker)
└── beat (Celery Beat)
```

## 环境配置

### 环境变量

创建`.env`文件配置环境变量:

```bash
# 安全配置
SECRET_KEY=your-production-secret-key-32-chars-minimum
JWT_SECRET=your-production-jwt-secret-32-chars-minimum

# 企业微信配置
WECHAT_CORP_ID=your_corp_id
WECHAT_CORP_SECRET=your_corp_secret
WECHAT_AGENT_ID=1000001
WECHAT_TOKEN=your_token
WECHAT_ENCODING_AES_KEY=your_aes_key

# LLM配置
LLM_PROVIDER=deepseek
LLM_API_KEY=your_api_key
```

### 数据库初始化

首次启动后需要运行数据库迁移:

```bash
# 进入API容器
docker-compose exec api bash

# 运行迁移
python -m alembic upgrade head

# 退出容器
exit
```

## 常用命令

### 服务管理

```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启特定服务
docker-compose restart api

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f beat
```

### 容器操作

```bash
# 进入API容器
docker-compose exec api bash

# 进入数据库容器
docker-compose exec db psql -U zhilian -d zhilian_os

# 进入Redis容器
docker-compose exec redis redis-cli

# 查看容器资源使用
docker stats
```

### 数据管理

```bash
# 备份数据库
docker-compose exec db pg_dump -U zhilian zhilian_os > backup.sql

# 恢复数据库
docker-compose exec -T db psql -U zhilian zhilian_os < backup.sql

# 清理所有数据（危险操作）
docker-compose down -v
```

## 开发环境

### 开发模式启动

```bash
# 使用开发配置
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 挂载代码目录实现热重载
docker-compose up -d --build
```

### 调试

```bash
# 查看API日志
docker-compose logs -f api

# 进入容器调试
docker-compose exec api bash
python -c "from src.main import app; print('OK')"

# 运行测试
docker-compose exec api pytest tests/
```

## 生产部署

### 构建优化

```bash
# 构建生产镜像
docker-compose build --no-cache

# 推送到镜像仓库
docker tag zhilian-api:latest registry.example.com/zhilian-api:v1.0.0
docker push registry.example.com/zhilian-api:v1.0.0
```

### 性能优化

**API服务**:
```yaml
api:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 2G
      reservations:
        cpus: '1'
        memory: 1G
    replicas: 3
```

**Worker服务**:
```yaml
worker:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 2G
    replicas: 2
```

### 健康检查

所有服务都配置了健康检查:

```bash
# 检查服务健康状态
docker-compose ps

# 手动健康检查
curl http://localhost:8000/health
```

## 监控和日志

### 日志管理

```bash
# 查看实时日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f api worker beat

# 导出日志
docker-compose logs > logs/docker-compose.log
```

### 日志轮转

配置日志驱动:

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Prometheus监控

API服务暴露Prometheus指标:

```bash
# 访问指标端点
curl http://localhost:8000/metrics
```

## 故障排查

### 常见问题

**1. 容器无法启动**

```bash
# 查看容器日志
docker-compose logs api

# 检查端口占用
lsof -i :8000

# 重新构建
docker-compose build --no-cache api
```

**2. 数据库连接失败**

```bash
# 检查数据库状态
docker-compose ps db

# 测试数据库连接
docker-compose exec db pg_isready -U zhilian

# 查看数据库日志
docker-compose logs db
```

**3. Redis连接失败**

```bash
# 检查Redis状态
docker-compose exec redis redis-cli ping

# 查看Redis日志
docker-compose logs redis
```

**4. 内存不足**

```bash
# 查看资源使用
docker stats

# 增加Docker内存限制
# Docker Desktop -> Settings -> Resources -> Memory
```

### 清理和重置

```bash
# 停止并删除所有容器
docker-compose down

# 删除所有数据卷（危险）
docker-compose down -v

# 清理未使用的镜像
docker image prune -a

# 完全清理Docker
docker system prune -a --volumes
```

## 安全建议

1. **密钥管理**
   - 使用Docker secrets或环境变量
   - 不要在镜像中硬编码密钥
   - 定期轮换密钥

2. **网络隔离**
   - 使用自定义网络
   - 限制容器间通信
   - 不暴露不必要的端口

3. **镜像安全**
   - 使用官方基础镜像
   - 定期更新镜像
   - 扫描镜像漏洞

4. **资源限制**
   - 设置CPU和内存限制
   - 防止资源耗尽
   - 监控资源使用

## 扩展部署

### Docker Swarm

```bash
# 初始化Swarm
docker swarm init

# 部署Stack
docker stack deploy -c docker-compose.yml zhilian

# 查看服务
docker service ls

# 扩展服务
docker service scale zhilian_api=3
```

### Kubernetes

参考`k8s/`目录下的Kubernetes配置文件。

## 参考资料

- [Docker文档](https://docs.docker.com/)
- [Docker Compose文档](https://docs.docker.com/compose/)
- [FastAPI Docker部署](https://fastapi.tiangolo.com/deployment/docker/)
- [PostgreSQL Docker](https://hub.docker.com/_/postgres)
- [Redis Docker](https://hub.docker.com/_/redis)
