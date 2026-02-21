# 性能测试文档

## 概述

本目录包含智链OS API Gateway的性能和负载测试工具。

## 测试工具

### 1. Locust负载测试

Locust是一个开源的负载测试工具，使用Python编写测试场景。

**安装**:
```bash
pip install locust
```

**运行测试**:
```bash
# Web UI模式
locust -f tests/performance/locustfile.py --host=http://localhost:8000

# 无头模式（命令行）
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=100 \
  --spawn-rate=10 \
  --run-time=5m \
  --headless

# 生成HTML报告
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=100 \
  --spawn-rate=10 \
  --run-time=5m \
  --headless \
  --html=report.html
```

**访问Web UI**:
- 打开浏览器访问: http://localhost:8089
- 设置用户数和生成速率
- 点击"Start swarming"开始测试

### 2. 性能基准测试

自定义的异步性能基准测试脚本。

**安装依赖**:
```bash
pip install httpx
```

**运行测试**:
```bash
python tests/performance/benchmark.py
```

## 测试场景

### 场景1: 正常负载

模拟正常业务负载。

```bash
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=50 \
  --spawn-rate=5 \
  --run-time=10m \
  --headless
```

**预期结果**:
- 平均响应时间: < 200ms
- P95响应时间: < 500ms
- 错误率: < 1%
- RPS: > 100

### 场景2: 高负载

模拟高峰期负载。

```bash
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=200 \
  --spawn-rate=20 \
  --run-time=10m \
  --headless
```

**预期结果**:
- 平均响应时间: < 500ms
- P95响应时间: < 1000ms
- 错误率: < 5%
- RPS: > 300

### 场景3: 压力测试

测试系统极限。

```bash
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=500 \
  --spawn-rate=50 \
  --run-time=5m \
  --headless
```

**目标**:
- 找出系统瓶颈
- 确定最大承载能力
- 观察系统降级行为

### 场景4: 持久性测试

长时间运行测试。

```bash
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=100 \
  --spawn-rate=10 \
  --run-time=2h \
  --headless
```

**目标**:
- 检测内存泄漏
- 验证系统稳定性
- 监控资源使用趋势

## 性能指标

### 关键指标

1. **响应时间**
   - 平均响应时间 (Average Response Time)
   - 中位数响应时间 (Median Response Time)
   - P95响应时间 (95th Percentile)
   - P99响应时间 (99th Percentile)

2. **吞吐量**
   - RPS (Requests Per Second)
   - 并发用户数 (Concurrent Users)

3. **可靠性**
   - 成功率 (Success Rate)
   - 错误率 (Error Rate)
   - 超时率 (Timeout Rate)

4. **资源使用**
   - CPU使用率
   - 内存使用率
   - 网络带宽
   - 数据库连接数

### 性能目标

| 端点 | 平均响应时间 | P95响应时间 | 目标RPS |
|------|-------------|------------|---------|
| /health | < 10ms | < 20ms | 1000+ |
| /api/v1/tasks | < 100ms | < 200ms | 200+ |
| /api/v1/reconciliation/records | < 150ms | < 300ms | 100+ |
| /metrics | < 50ms | < 100ms | 500+ |

## 监控和分析

### 实时监控

在测试期间监控系统指标:

```bash
# 监控Docker容器资源
docker stats

# 监控API日志
docker-compose logs -f api

# 监控数据库连接
docker-compose exec db psql -U zhilian -d zhilian_os -c "SELECT count(*) FROM pg_stat_activity;"

# 监控Redis
docker-compose exec redis redis-cli info stats
```

### Prometheus指标

访问Prometheus指标端点:
```bash
curl http://localhost:8000/metrics
```

关键指标:
- `http_requests_total`: 总请求数
- `http_request_duration_seconds`: 请求持续时间
- `http_requests_in_progress`: 进行中的请求数

### 性能分析

使用Python profiler分析性能瓶颈:

```python
import cProfile
import pstats

# 运行性能分析
cProfile.run('your_function()', 'profile_stats')

# 查看结果
stats = pstats.Stats('profile_stats')
stats.sort_stats('cumulative')
stats.print_stats(20)
```

## 优化建议

### 1. 数据库优化

- 添加适当的索引
- 使用连接池
- 优化查询语句
- 启用查询缓存

### 2. 缓存优化

- 使用Redis缓存热点数据
- 设置合理的过期时间
- 实现缓存预热
- 使用缓存穿透保护

### 3. 应用优化

- 使用异步I/O
- 优化数据库查询
- 减少不必要的计算
- 使用批量操作

### 4. 基础设施优化

- 增加服务器资源
- 使用负载均衡
- 启用CDN
- 优化网络配置

## 故障排查

### 响应时间过长

1. 检查数据库查询性能
2. 检查是否有慢查询
3. 检查缓存命中率
4. 检查网络延迟

### 错误率过高

1. 查看错误日志
2. 检查数据库连接
3. 检查Redis连接
4. 检查资源限制

### 吞吐量不足

1. 增加并发数
2. 优化代码性能
3. 增加服务器资源
4. 使用负载均衡

## 持续性能测试

### CI/CD集成

在CI/CD流水线中集成性能测试:

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨2点运行

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run performance tests
        run: |
          pip install locust
          locust -f tests/performance/locustfile.py \
            --host=https://api.example.com \
            --users=100 \
            --spawn-rate=10 \
            --run-time=5m \
            --headless \
            --html=report.html
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: performance-report
          path: report.html
```

### 性能回归测试

定期运行性能测试，对比历史数据:

```bash
# 运行测试并保存结果
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=100 \
  --spawn-rate=10 \
  --run-time=5m \
  --headless \
  --csv=results/$(date +%Y%m%d)

# 对比结果
python scripts/compare_performance.py \
  results/20260220_stats.csv \
  results/20260221_stats.csv
```

## 参考资料

- [Locust文档](https://docs.locust.io/)
- [性能测试最佳实践](https://www.nginx.com/blog/performance-testing-best-practices/)
- [FastAPI性能优化](https://fastapi.tiangolo.com/deployment/concepts/)
- [PostgreSQL性能调优](https://wiki.postgresql.org/wiki/Performance_Optimization)
