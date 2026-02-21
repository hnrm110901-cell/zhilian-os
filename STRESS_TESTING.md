# 压力测试指南

## 概述

智链OS压力测试使用Locust进行，可以模拟大量并发用户访问API Gateway，测试系统在高负载下的性能表现。

## 测试架构

```
┌─────────────────┐
│  Locust Master  │
│  (测试控制器)    │
└────────┬────────┘
         │
         │ 生成虚拟用户
         │
┌────────▼────────┐
│  Virtual Users  │
│  (并发请求)      │
└────────┬────────┘
         │
         │ HTTP请求
         │
┌────────▼────────┐
│  API Gateway    │
│  (被测系统)      │
└────────┬────────┘
         │
         │ 记录指标
         │
┌────────▼────────┐
│  Prometheus     │
│  (性能监控)      │
└─────────────────┘
```

## 快速开始

### 1. 准备环境

```bash
# 安装依赖
pip install -r requirements.txt

# 启动API Gateway
cd apps/api-gateway
uvicorn src.main:app --host 0.0.0.0 --port 8000

# 启动监控服务（可选但推荐）
docker-compose up -d prometheus grafana
```

### 2. 运行压力测试

#### 方式一：使用脚本（推荐）

```bash
# 运行交互式压力测试
./run_stress_test.sh

# 选择测试模式：
# 1) 轻量测试 (10用户, 30秒)
# 2) 中等测试 (50用户, 2分钟)
# 3) 重度测试 (100用户, 5分钟)
# 4) 极限测试 (200用户, 10分钟)
# 5) 自定义测试
```

#### 方式二：直接使用Locust

```bash
# 无头模式（命令行）
cd apps/api-gateway/tests
locust -f locustfile.py \
    --host=http://localhost:8000 \
    --users=50 \
    --spawn-rate=5 \
    --run-time=2m \
    --headless \
    --html=report.html

# Web UI模式（浏览器控制）
locust -f locustfile.py --host=http://localhost:8000
# 然后访问 http://localhost:8089
```

## 测试场景

### APIGatewayUser（常规负载）

模拟正常业务场景的用户行为：

| 任务 | 权重 | 描述 |
|------|------|------|
| health_check | 5 | 健康检查 |
| neural_health_check | 3 | 神经系统健康检查 |
| batch_index_orders | 2 | 批量索引订单（10条） |
| batch_index_dishes | 2 | 批量索引菜品（5条） |
| batch_index_events | 1 | 批量索引事件（8条） |
| semantic_search_orders | 3 | 语义搜索订单 |
| semantic_search_dishes | 2 | 语义搜索菜品 |
| get_metrics | 1 | 获取Prometheus指标 |

**等待时间**: 1-3秒

### HighLoadUser（高负载）

模拟极端负载场景：

| 任务 | 权重 | 描述 |
|------|------|------|
| rapid_health_checks | 10 | 快速健康检查 |
| rapid_batch_operations | 5 | 快速批量操作（50条） |

**等待时间**: 0.5-1.5秒

## 测试配置

### 预设配置

#### 轻量测试
- **用户数**: 10
- **启动速率**: 2用户/秒
- **运行时间**: 30秒
- **适用场景**: 快速验证、开发测试

#### 中等测试
- **用户数**: 50
- **启动速率**: 5用户/秒
- **运行时间**: 2分钟
- **适用场景**: 日常性能测试、回归测试

#### 重度测试
- **用户数**: 100
- **启动速率**: 10用户/秒
- **运行时间**: 5分钟
- **适用场景**: 容量规划、性能优化

#### 极限测试
- **用户数**: 200
- **启动速率**: 20用户/秒
- **运行时间**: 10分钟
- **适用场景**: 压力测试、稳定性测试

### 自定义配置

```bash
locust -f locustfile.py \
    --host=http://localhost:8000 \
    --users=<用户数> \
    --spawn-rate=<启动速率> \
    --run-time=<运行时间> \
    --headless
```

## 测试报告

### 报告文件

测试完成后，结果保存在 `stress_test_results/<timestamp>/` 目录：

```
stress_test_results/
└── 20240219_143000/
    ├── report.html          # HTML可视化报告
    ├── stats_stats.csv      # 请求统计
    ├── stats_failures.csv   # 失败记录
    ├── stats_exceptions.csv # 异常记录
    └── summary.json         # 性能摘要
```

### 关键指标

#### 1. 请求统计
- **Total Requests**: 总请求数
- **Failures**: 失败请求数
- **Failure Rate**: 失败率（应 <1%）
- **RPS**: 每秒请求数

#### 2. 响应时间
- **Average**: 平均响应时间（应 <500ms）
- **Median**: 中位数响应时间
- **P95**: 95分位数（应 <1s）
- **P99**: 99分位数（应 <2s）
- **Max**: 最大响应时间

#### 3. 吞吐量
- **Requests/s**: 每秒处理请求数
- **Content Size**: 平均响应大小

### 性能评级标准

#### 响应时间
- ✓✓ 优秀: <200ms
- ✓ 良好: 200-500ms
- ⚠️ 偏慢: 500-1000ms
- ❌ 过慢: >1000ms

#### 失败率
- ✓ 正常: <1%
- ⚠️ 偏高: 1-5%
- ❌ 过高: >5%

#### 吞吐量
- ✓✓ 优秀: >100 RPS
- ✓ 良好: 50-100 RPS
- ⚠️ 偏低: 20-50 RPS
- ❌ 过低: <20 RPS

## 监控集成

### Prometheus指标

在压力测试期间，可以通过Prometheus监控实时性能：

```bash
# 访问Prometheus
open http://localhost:9090

# 常用查询
# 1. 实时RPS
rate(http_requests_total[1m])

# 2. P95响应时间
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))

# 3. 错误率
sum(rate(http_requests_total{status=~"5.."}[1m])) /
sum(rate(http_requests_total[1m]))

# 4. 活跃请求数
http_requests_active
```

### Grafana Dashboard

```bash
# 访问Grafana
open http://localhost:3000

# 查看实时监控面板
# - HTTP请求总数
# - 活跃请求数
# - 响应时间分布
# - 状态码分布
```

## 性能优化建议

### 1. 识别瓶颈

```bash
# 查看最慢的端点
topk(10, avg by (endpoint) (
  rate(http_request_duration_seconds_sum[5m]) /
  rate(http_request_duration_seconds_count[5m])
))

# 查看错误最多的端点
topk(10, sum by (endpoint) (
  rate(http_requests_total{status=~"5.."}[5m])
))
```

### 2. 常见问题

#### 高响应时间
- **原因**: 数据库查询慢、外部API调用、CPU密集计算
- **解决**: 添加缓存、优化查询、异步处理

#### 高失败率
- **原因**: 资源耗尽、超时、依赖服务不可用
- **解决**: 增加资源、调整超时、添加重试机制

#### 低吞吐量
- **原因**: 单线程瓶颈、I/O阻塞、资源限制
- **解决**: 增加worker数、使用异步I/O、扩容

### 3. 优化检查清单

- [ ] 数据库连接池配置合理
- [ ] 启用HTTP缓存
- [ ] 使用CDN加速静态资源
- [ ] 优化数据库索引
- [ ] 启用gzip压缩
- [ ] 使用异步处理长时间任务
- [ ] 实现请求限流
- [ ] 添加熔断器
- [ ] 优化日志级别（生产环境使用WARNING）

## 最佳实践

### 1. 测试前准备

```bash
# 清理测试数据
# 重启服务
# 预热缓存
curl http://localhost:8000/api/v1/health
```

### 2. 测试执行

- 从小负载开始，逐步增加
- 每次测试至少运行2分钟以达到稳定状态
- 记录系统资源使用情况（CPU、内存、磁盘I/O）
- 同时监控Prometheus指标

### 3. 测试后分析

- 对比不同负载下的性能表现
- 识别性能拐点（系统开始降级的负载点）
- 分析失败请求的原因
- 生成性能基线报告

### 4. 持续测试

- 在CI/CD中集成性能测试
- 每次发布前运行回归测试
- 定期进行容量规划测试
- 建立性能监控告警

## 故障排查

### Locust无法启动

```bash
# 检查Python版本
python3 --version  # 需要 >=3.9

# 重新安装Locust
pip install --upgrade locust

# 检查locustfile语法
python3 -m py_compile apps/api-gateway/tests/locustfile.py
```

### API Gateway连接失败

```bash
# 检查服务状态
curl http://localhost:8000/api/v1/health

# 检查端口占用
lsof -i :8000

# 查看服务日志
# 检查防火墙设置
```

### 测试结果异常

```bash
# 检查系统资源
top
df -h

# 检查网络连接
netstat -an | grep 8000

# 查看Prometheus指标
curl http://localhost:8000/metrics
```

## 示例测试场景

### 场景1：日常负载测试

```bash
# 模拟50个并发用户，持续2分钟
locust -f locustfile.py \
    --host=http://localhost:8000 \
    --users=50 \
    --spawn-rate=5 \
    --run-time=2m \
    --headless \
    --html=daily_test.html
```

### 场景2：峰值负载测试

```bash
# 模拟200个并发用户，持续10分钟
locust -f locustfile.py \
    --host=http://localhost:8000 \
    --users=200 \
    --spawn-rate=20 \
    --run-time=10m \
    --headless \
    --html=peak_test.html
```

### 场景3：持久性测试

```bash
# 模拟100个并发用户，持续1小时
locust -f locustfile.py \
    --host=http://localhost:8000 \
    --users=100 \
    --spawn-rate=10 \
    --run-time=1h \
    --headless \
    --html=endurance_test.html
```

## 参考资料

- [Locust官方文档](https://docs.locust.io/)
- [性能测试最佳实践](https://docs.locust.io/en/stable/writing-a-locustfile.html)
- [Prometheus查询语言](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [API性能优化指南](https://fastapi.tiangolo.com/deployment/concepts/)
