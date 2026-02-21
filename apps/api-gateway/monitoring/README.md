# 监控和告警系统

## 概述

智链OS使用Prometheus + Grafana + AlertManager构建完整的监控和告警系统。

## 架构

```
┌─────────────┐
│   Grafana   │ ← 可视化仪表板
└──────┬──────┘
       │
┌──────▼──────┐
│ Prometheus  │ ← 指标收集和存储
└──────┬──────┘
       │
       ├─────→ API服务 (/metrics)
       ├─────→ PostgreSQL Exporter
       ├─────→ Redis Exporter
       ├─────→ Node Exporter
       └─────→ Celery Exporter
       
┌─────────────┐
│AlertManager │ ← 告警管理和通知
└─────────────┘
```

## 快速开始

### 启动监控服务

```bash
# 创建网络（如果还没有）
docker network create zhilian-network

# 启动应用服务
cd apps/api-gateway
docker-compose up -d

# 启动监控服务
cd monitoring
docker-compose -f docker-compose.monitoring.yml up -d
```

### 访问服务

- **Grafana**: http://localhost:3000
  - 用户名: admin
  - 密码: admin

- **Prometheus**: http://localhost:9090

- **AlertManager**: http://localhost:9093

## 监控指标

### API服务指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| http_requests_total | Counter | 总请求数 |
| http_request_duration_seconds | Histogram | 请求持续时间 |
| http_requests_in_progress | Gauge | 进行中的请求数 |
| process_cpu_seconds_total | Counter | CPU使用时间 |
| process_resident_memory_bytes | Gauge | 内存使用量 |

### 数据库指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| pg_stat_activity_count | Gauge | 活动连接数 |
| pg_stat_database_tup_fetched | Counter | 读取的行数 |
| pg_stat_database_tup_inserted | Counter | 插入的行数 |
| pg_stat_database_conflicts | Counter | 冲突数 |

### Redis指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| redis_connected_clients | Gauge | 连接的客户端数 |
| redis_memory_used_bytes | Gauge | 使用的内存 |
| redis_commands_processed_total | Counter | 处理的命令总数 |
| redis_keyspace_hits_total | Counter | 键空间命中数 |

### 系统指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| node_cpu_seconds_total | Counter | CPU使用时间 |
| node_memory_MemAvailable_bytes | Gauge | 可用内存 |
| node_disk_io_time_seconds_total | Counter | 磁盘IO时间 |
| node_network_receive_bytes_total | Counter | 网络接收字节数 |

## 告警规则

### 严重告警 (Critical)

1. **APIServiceDown** - API服务不可用
   - 条件: 服务下线超过1分钟
   - 处理: 立即检查服务状态，重启服务

### 警告告警 (Warning)

1. **HighErrorRate** - 错误率过高
   - 条件: 5分钟内错误率超过5%
   - 处理: 检查错误日志，分析原因

2. **HighResponseTime** - 响应时间过长
   - 条件: P95响应时间超过1秒
   - 处理: 检查数据库查询，优化性能

3. **HighCPUUsage** - CPU使用率过高
   - 条件: CPU使用率超过80%持续10分钟
   - 处理: 检查资源使用，考虑扩容

4. **HighMemoryUsage** - 内存使用过高
   - 条件: 内存使用超过2GB持续10分钟
   - 处理: 检查内存泄漏，重启服务

5. **HighDatabaseConnections** - 数据库连接数过高
   - 条件: 连接数超过80持续5分钟
   - 处理: 检查连接池配置，优化查询

6. **SlowQueries** - 数据库慢查询
   - 条件: 平均查询时间超过1秒
   - 处理: 分析慢查询日志，添加索引

7. **HighRedisMemory** - Redis内存使用过高
   - 条件: 内存使用超过80%
   - 处理: 清理过期键，增加内存

8. **HighTaskFailureRate** - Celery任务失败率过高
   - 条件: 任务失败率超过10%
   - 处理: 检查任务日志，修复错误

9. **CeleryQueueBacklog** - Celery队列积压
   - 条件: 队列长度超过1000持续10分钟
   - 处理: 增加Worker数量，优化任务

## Grafana仪表板

### API监控概览

显示API服务的关键指标：
- 请求速率 (RPS)
- 响应时间 (P50, P95, P99)
- 错误率
- 并发请求数
- CPU和内存使用

### 数据库监控

显示数据库性能指标：
- 连接数
- 查询速率
- 慢查询
- 缓存命中率
- 磁盘使用

### Redis监控

显示Redis性能指标：
- 内存使用
- 命令速率
- 键空间统计
- 连接数
- 命中率

### 系统监控

显示系统资源使用：
- CPU使用率
- 内存使用率
- 磁盘IO
- 网络流量

## 告警通知

### 配置企业微信通知

在API服务中实现告警webhook接收器：

```python
@router.post("/api/v1/alerts/webhook")
async def receive_alert(alert: dict):
    # 解析告警信息
    alertname = alert.get("alertname")
    severity = alert.get("severity")
    description = alert.get("description")
    
    # 发送企业微信通知
    await wechat_service.send_alert(
        title=f"[{severity}] {alertname}",
        content=description
    )
```

### 配置邮件通知

在AlertManager配置中添加邮件接收器：

```yaml
receivers:
  - name: 'email'
    email_configs:
      - to: 'ops@example.com'
        from: 'alertmanager@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alertmanager@example.com'
        auth_password: 'password'
```

## 查询示例

### Prometheus查询

```promql
# 过去5分钟的平均RPS
rate(http_requests_total[5m])

# P95响应时间
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# 错误率
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# 数据库连接数
pg_stat_activity_count

# Redis内存使用率
redis_memory_used_bytes / redis_memory_max_bytes
```

### Grafana查询

在Grafana中创建面板时使用相同的PromQL查询。

## 性能优化

### Prometheus优化

1. **调整抓取间隔**
   ```yaml
   global:
     scrape_interval: 30s  # 降低频率减少负载
   ```

2. **设置数据保留期**
   ```bash
   --storage.tsdb.retention.time=30d
   ```

3. **启用远程存储**
   ```yaml
   remote_write:
     - url: "http://remote-storage:9201/write"
   ```

### Grafana优化

1. **使用变量**
   - 创建环境、服务等变量
   - 减少仪表板数量

2. **优化查询**
   - 使用合适的时间范围
   - 避免过于复杂的查询

3. **启用缓存**
   ```ini
   [caching]
   enabled = true
   ```

## 故障排查

### Prometheus无法抓取指标

1. 检查目标服务是否运行
2. 检查网络连接
3. 检查/metrics端点是否可访问
4. 查看Prometheus日志

### Grafana无法显示数据

1. 检查数据源配置
2. 检查Prometheus是否有数据
3. 检查查询语句是否正确
4. 查看Grafana日志

### 告警未触发

1. 检查告警规则配置
2. 检查AlertManager配置
3. 检查通知接收器
4. 查看AlertManager日志

## 最佳实践

1. **合理设置告警阈值**
   - 避免告警疲劳
   - 根据实际情况调整

2. **使用标签分类**
   - 按服务、环境分类
   - 便于过滤和聚合

3. **定期审查告警**
   - 删除无用告警
   - 优化告警规则

4. **监控监控系统**
   - 监控Prometheus自身
   - 确保监控系统可用

5. **文档化告警处理**
   - 记录处理步骤
   - 建立运维手册

## 参考资料

- [Prometheus文档](https://prometheus.io/docs/)
- [Grafana文档](https://grafana.com/docs/)
- [AlertManager文档](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [PromQL查询语言](https://prometheus.io/docs/prometheus/latest/querying/basics/)
