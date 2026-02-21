# Prometheus监控部署指南

## 概述

智链OS已集成Prometheus和Grafana监控系统，用于实时监控API Gateway的性能和健康状态。

## 架构

```
┌─────────────────┐
│  API Gateway    │
│  (Port 8000)    │
│  /metrics       │
└────────┬────────┘
         │
         │ HTTP Scrape (10s interval)
         │
┌────────▼────────┐
│  Prometheus     │
│  (Port 9090)    │
│  Time Series DB │
└────────┬────────┘
         │
         │ Query
         │
┌────────▼────────┐
│  Grafana        │
│  (Port 3000)    │
│  Visualization  │
└─────────────────┘
```

## 快速开始

### 1. 启动监控服务

```bash
# 启动Prometheus和Grafana
docker-compose up -d prometheus grafana

# 验证服务状态
docker ps | grep -E "(prometheus|grafana)"
```

### 2. 访问监控界面

- **Prometheus**: http://localhost:9090
  - 查看targets: http://localhost:9090/targets
  - 查询metrics: http://localhost:9090/graph

- **Grafana**: http://localhost:3000
  - 默认用户名: `admin`
  - 默认密码: `admin`

### 3. 配置Grafana

#### 添加Prometheus数据源

1. 登录Grafana (http://localhost:3000)
2. 进入 Configuration → Data Sources
3. 点击 "Add data source"
4. 选择 "Prometheus"
5. 配置:
   - Name: `Prometheus`
   - URL: `http://prometheus:9090`
   - Access: `Server (default)`
6. 点击 "Save & Test"

#### 导入Dashboard

1. 进入 Dashboards → Import
2. 上传 `grafana-dashboard.json` 文件
3. 选择Prometheus数据源
4. 点击 "Import"

## 监控指标

### HTTP请求指标

#### `http_requests_total`
- **类型**: Counter
- **描述**: HTTP请求总数
- **标签**:
  - `method`: HTTP方法 (GET, POST, PUT, DELETE等)
  - `endpoint`: API端点路径
  - `status`: HTTP状态码

**示例查询**:
```promql
# 每秒请求率
rate(http_requests_total[5m])

# 按状态码分组的请求率
sum by (status) (rate(http_requests_total[5m]))

# 错误率 (4xx + 5xx)
sum(rate(http_requests_total{status=~"4..|5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

#### `http_request_duration_seconds`
- **类型**: Histogram
- **描述**: HTTP请求响应时间（秒）
- **标签**:
  - `method`: HTTP方法
  - `endpoint`: API端点路径

**示例查询**:
```promql
# P50响应时间
histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))

# P95响应时间
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# P99响应时间
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# 平均响应时间
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

#### `http_requests_active`
- **类型**: Gauge
- **描述**: 当前活跃的HTTP请求数

**示例查询**:
```promql
# 当前活跃请求数
http_requests_active

# 最大活跃请求数
max_over_time(http_requests_active[5m])
```

## 常用查询

### 性能监控

```promql
# 最慢的10个端点
topk(10, avg by (endpoint, method) (
  rate(http_request_duration_seconds_sum[5m]) /
  rate(http_request_duration_seconds_count[5m])
))

# 请求量最大的10个端点
topk(10, sum by (endpoint) (rate(http_requests_total[5m])))

# 错误率最高的10个端点
topk(10, sum by (endpoint) (
  rate(http_requests_total{status=~"5.."}[5m])
))
```

### 健康监控

```promql
# 5xx错误率
sum(rate(http_requests_total{status=~"5.."}[5m])) /
sum(rate(http_requests_total[5m])) * 100

# 4xx错误率
sum(rate(http_requests_total{status=~"4.."}[5m])) /
sum(rate(http_requests_total[5m])) * 100

# 成功率 (2xx + 3xx)
sum(rate(http_requests_total{status=~"2..|3.."}[5m])) /
sum(rate(http_requests_total[5m])) * 100
```

## 告警规则

创建 `alerts.yml` 文件配置告警规则:

```yaml
groups:
  - name: api_gateway_alerts
    interval: 30s
    rules:
      # 高错误率告警
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) /
          sum(rate(http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "API Gateway错误率过高"
          description: "错误率: {{ $value | humanizePercentage }}"

      # 高响应时间告警
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API Gateway响应时间过长"
          description: "P95响应时间: {{ $value }}s"

      # 高并发告警
      - alert: HighConcurrency
        expr: http_requests_active > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API Gateway并发请求过多"
          description: "活跃请求数: {{ $value }}"
```

## 配置文件

### prometheus.yml

Prometheus配置文件位于项目根目录，包含:
- 全局配置（抓取间隔、评估间隔）
- 抓取目标配置（API Gateway、Prometheus自身）
- 标签配置（cluster、environment）

### docker-compose.yml

Docker Compose配置包含:
- Prometheus服务（端口9090）
- Grafana服务（端口3000）
- 数据卷配置（持久化存储）

## 故障排查

### Prometheus无法抓取metrics

1. 检查API Gateway是否运行:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. 检查Prometheus targets状态:
   ```bash
   curl http://localhost:9090/api/v1/targets
   ```

3. 查看Prometheus日志:
   ```bash
   docker logs zhilian-prometheus-dev
   ```

### Grafana无法连接Prometheus

1. 检查Prometheus是否运行:
   ```bash
   docker ps | grep prometheus
   ```

2. 测试Prometheus连接:
   ```bash
   docker exec zhilian-grafana-dev curl http://prometheus:9090/api/v1/query?query=up
   ```

3. 查看Grafana日志:
   ```bash
   docker logs zhilian-grafana-dev
   ```

## 最佳实践

1. **定期检查监控数据**: 每天查看Dashboard，了解系统运行状况
2. **设置告警**: 配置关键指标的告警规则，及时发现问题
3. **性能优化**: 根据监控数据识别性能瓶颈，优化慢查询
4. **容量规划**: 根据历史数据预测资源需求，提前扩容
5. **数据保留**: 配置合适的数据保留策略，平衡存储和查询性能

## 扩展

### 添加更多监控指标

在 `src/main.py` 中添加自定义指标:

```python
from prometheus_client import Counter, Histogram, Gauge

# 自定义业务指标
ORDER_CREATED = Counter('orders_created_total', 'Total orders created')
ORDER_AMOUNT = Histogram('order_amount_yuan', 'Order amount in yuan')
ACTIVE_USERS = Gauge('active_users', 'Number of active users')

# 在业务代码中使用
ORDER_CREATED.inc()
ORDER_AMOUNT.observe(order.total)
ACTIVE_USERS.set(len(active_users))
```

### 集成Alertmanager

1. 添加Alertmanager到docker-compose.yml
2. 配置alertmanager.yml
3. 在prometheus.yml中配置alerting
4. 配置通知渠道（邮件、Slack、钉钉等）

## 参考资料

- [Prometheus官方文档](https://prometheus.io/docs/)
- [Grafana官方文档](https://grafana.com/docs/)
- [PromQL查询语言](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Prometheus最佳实践](https://prometheus.io/docs/practices/)
