# Celery任务队列集成指南

## 概述

智链OS的Neural System现已集成Celery分布式任务队列，替代原有的内存事件队列。这带来了以下优势：

- **持久化**: 事件存储在Redis中，服务重启不丢失
- **可靠性**: 自动重试机制，确保事件处理成功
- **可扩展性**: 支持水平扩展，多个worker并行处理
- **优先级**: 支持高/中/低优先级队列
- **监控**: 完整的任务状态跟踪和监控

## 架构变更

### 之前（内存队列）
```python
# 内存事件队列
self.event_queue: List[NeuralEventSchema] = []

# 同步处理
await vector_db_service.index_event(event)
await self._process_event(event)
```

### 现在（Celery任务队列）
```python
# 提交到Celery异步任务队列
task = process_neural_event.apply_async(
    kwargs={
        "event_id": event_id,
        "event_type": event_type,
        "event_source": event_source,
        "store_id": store_id,
        "data": data,
        "priority": priority,
    },
    priority=priority,
)
```

## 队列配置

### 三个优先级队列

1. **high_priority**: 实时事件处理
   - 订单创建/更新
   - 支付完成
   - 库存告警
   - 优先级: 10

2. **default**: 普通事件处理
   - 向量数据库索引
   - 菜品更新
   - 员工排班
   - 优先级: 5

3. **low_priority**: 批量处理和ML训练
   - 联邦学习模型训练
   - 批量数据索引
   - 数据分析任务
   - 优先级: 1

## 安装依赖

```bash
cd apps/api-gateway
pip install celery redis kombu
```

或使用requirements.txt:
```bash
pip install -r requirements.txt
```

## 配置

### 环境变量 (.env)

```bash
# Celery配置
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### Redis数据库分配

- DB 0: 应用缓存和会话
- DB 1: Celery broker（任务队列）
- DB 2: Celery result backend（任务结果）

## 启动服务

### 1. 启动Redis

```bash
redis-server
```

### 2. 启动Celery Worker

```bash
cd apps/api-gateway
python start_celery_worker.py
```

或使用celery命令:
```bash
celery -A src.core.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=high_priority,default,low_priority
```

### 3. 启动API服务

```bash
python src/main.py
```

## 可用的Celery任务

### 1. process_neural_event
处理神经系统事件（核心任务）

```python
from src.core.celery_tasks import process_neural_event

task = process_neural_event.apply_async(
    kwargs={
        "event_id": "uuid",
        "event_type": "order.created",
        "event_source": "pos_system",
        "store_id": "store_123",
        "data": {...},
        "priority": 10,
    }
)
```

### 2. index_to_vector_db
索引数据到向量数据库

```python
from src.core.celery_tasks import index_to_vector_db

task = index_to_vector_db.apply_async(
    kwargs={
        "collection_name": "orders",
        "data": order_data,
    }
)
```

### 3. train_federated_model
训练联邦学习模型

```python
from src.core.celery_tasks import train_federated_model

task = train_federated_model.apply_async(
    kwargs={
        "store_id": "store_123",
        "model_type": "demand_forecast",
    }
)
```

### 4. batch_index_orders
批量索引订单

```python
from src.core.celery_tasks import batch_index_orders

task = batch_index_orders.apply_async(
    kwargs={
        "orders": [order1, order2, order3],
    }
)
```

## 任务监控

### 使用Flower（Celery监控工具）

安装Flower:
```bash
pip install flower
```

启动Flower:
```bash
celery -A src.core.celery_app flower --port=5555
```

访问: http://localhost:5555

### 查看任务状态

```python
from src.core.celery_app import celery_app

# 获取任务结果
result = celery_app.AsyncResult(task_id)
print(result.state)  # PENDING, STARTED, SUCCESS, FAILURE
print(result.result)  # 任务返回值
```

### 查看队列状态

```bash
celery -A src.core.celery_app inspect active
celery -A src.core.celery_app inspect stats
celery -A src.core.celery_app inspect registered
```

## 重试机制

所有任务都配置了自动重试:

- **最大重试次数**: 3次
- **重试延迟**: 60秒（指数退避）
- **最大退避时间**: 600秒（10分钟）
- **抖动**: 启用（避免重试风暴）

```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
async def my_task(self, ...):
    try:
        # 任务逻辑
        pass
    except Exception as e:
        # 自动重试
        raise self.retry(exc=e)
```

## 性能优化

### 1. Worker并发数

根据CPU核心数调整:
```bash
celery worker --concurrency=8  # 8个并发worker
```

### 2. 预取倍数

控制每个worker预取的任务数:
```python
worker_prefetch_multiplier=4  # 每个worker预取4个任务
```

### 3. 任务超时

设置合理的超时时间:
```bash
celery worker --time-limit=300 --soft-time-limit=240
```

### 4. Worker重启

定期重启worker避免内存泄漏:
```python
worker_max_tasks_per_child=1000  # 每1000个任务后重启
```

## 故障排查

### 问题1: 任务不执行

**检查项**:
1. Redis是否运行: `redis-cli ping`
2. Celery worker是否启动: `ps aux | grep celery`
3. 队列是否正确: `celery -A src.core.celery_app inspect active_queues`

### 问题2: 任务失败

**查看日志**:
```bash
# Worker日志
tail -f celery.log

# 任务详情
celery -A src.core.celery_app inspect query_task <task_id>
```

### 问题3: 任务堆积

**解决方案**:
1. 增加worker数量
2. 提高并发数
3. 优化任务逻辑
4. 使用批量处理

### 问题4: Redis连接失败

**检查配置**:
```python
# 测试Redis连接
import redis
r = redis.from_url("redis://localhost:6379/1")
r.ping()
```

## 生产环境部署

### 使用Supervisor管理Celery

创建 `/etc/supervisor/conf.d/celery.conf`:

```ini
[program:celery_worker]
command=/path/to/venv/bin/celery -A src.core.celery_app worker --loglevel=info --concurrency=8
directory=/path/to/zhilian-os/apps/api-gateway
user=zhilian
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/worker.log
```

启动:
```bash
supervisorctl reread
supervisorctl update
supervisorctl start celery_worker
```

### 使用systemd管理Celery

创建 `/etc/systemd/system/celery.service`:

```ini
[Unit]
Description=Celery Worker for Zhilian OS
After=network.target redis.service

[Service]
Type=forking
User=zhilian
Group=zhilian
WorkingDirectory=/path/to/zhilian-os/apps/api-gateway
ExecStart=/path/to/venv/bin/celery -A src.core.celery_app worker --loglevel=info --concurrency=8 --detach
Restart=always

[Install]
WantedBy=multi-user.target
```

启动:
```bash
systemctl daemon-reload
systemctl enable celery
systemctl start celery
```

## 相关文档

- [Neural System实现指南](../NEURAL_SYSTEM_IMPLEMENTATION.md)
- [Redis配置指南](./redis-configuration.md)
- [监控和日志](./monitoring-and-logging.md)
