#!/bin/bash
# 压力测试运行脚本
# Stress Testing Runner Script

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "智链OS - 压力测试"
echo "=========================================="
echo ""

# 检查API Gateway是否运行
echo "检查API Gateway状态..."
if ! curl -s http://localhost:8000/api/v1/health > /dev/null; then
    echo -e "${RED}错误: API Gateway未运行${NC}"
    echo "请先启动API Gateway: cd apps/api-gateway && uvicorn src.main:app --reload"
    exit 1
fi
echo -e "${GREEN}✓ API Gateway运行正常${NC}"
echo ""

# 检查Prometheus是否运行
echo "检查Prometheus状态..."
if ! curl -s http://localhost:9090/-/healthy > /dev/null; then
    echo -e "${YELLOW}警告: Prometheus未运行${NC}"
    echo "建议启动Prometheus以监控性能: docker-compose up -d prometheus"
else
    echo -e "${GREEN}✓ Prometheus运行正常${NC}"
fi
echo ""

# 选择测试模式
echo "选择测试模式:"
echo "1) 轻量测试 (10用户, 30秒)"
echo "2) 中等测试 (50用户, 2分钟)"
echo "3) 重度测试 (100用户, 5分钟)"
echo "4) 极限测试 (200用户, 10分钟)"
echo "5) 自定义测试"
echo ""
read -p "请选择 [1-5]: " choice

case $choice in
    1)
        USERS=10
        SPAWN_RATE=2
        RUN_TIME="30s"
        TEST_NAME="轻量测试"
        ;;
    2)
        USERS=50
        SPAWN_RATE=5
        RUN_TIME="2m"
        TEST_NAME="中等测试"
        ;;
    3)
        USERS=100
        SPAWN_RATE=10
        RUN_TIME="5m"
        TEST_NAME="重度测试"
        ;;
    4)
        USERS=200
        SPAWN_RATE=20
        RUN_TIME="10m"
        TEST_NAME="极限测试"
        ;;
    5)
        read -p "用户数: " USERS
        read -p "启动速率 (用户/秒): " SPAWN_RATE
        read -p "运行时间 (如: 1m, 30s): " RUN_TIME
        TEST_NAME="自定义测试"
        ;;
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "测试配置: $TEST_NAME"
echo "=========================================="
echo "用户数: $USERS"
echo "启动速率: $SPAWN_RATE 用户/秒"
echo "运行时间: $RUN_TIME"
echo "目标主机: http://localhost:8000"
echo ""
read -p "按Enter开始测试..."

# 创建结果目录
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_DIR="stress_test_results/${TIMESTAMP}"
mkdir -p "$RESULT_DIR"

echo ""
echo "开始压力测试..."
echo "结果将保存到: $RESULT_DIR"
echo ""

# 运行Locust
cd apps/api-gateway/tests

# 无头模式运行
locust \
    -f locustfile.py \
    --host=http://localhost:8000 \
    --users=$USERS \
    --spawn-rate=$SPAWN_RATE \
    --run-time=$RUN_TIME \
    --headless \
    --html="../../../${RESULT_DIR}/report.html" \
    --csv="../../../${RESULT_DIR}/stats" \
    --loglevel=INFO

cd ../../..

echo ""
echo "=========================================="
echo "压力测试完成"
echo "=========================================="
echo ""
echo "测试报告:"
echo "  HTML报告: ${RESULT_DIR}/report.html"
echo "  CSV统计: ${RESULT_DIR}/stats_*.csv"
echo ""

# 显示简要统计
if [ -f "${RESULT_DIR}/stats_stats.csv" ]; then
    echo "请求统计摘要:"
    echo "----------------------------------------"
    head -n 1 "${RESULT_DIR}/stats_stats.csv"
    tail -n +2 "${RESULT_DIR}/stats_stats.csv" | head -n 10
    echo ""
fi

# 检查Prometheus metrics
echo "Prometheus指标:"
echo "  查看实时指标: http://localhost:9090"
echo "  查看Grafana: http://localhost:3000"
echo ""

# 生成性能报告
echo "生成性能分析报告..."
python3 << 'EOF'
import csv
import json
from datetime import datetime

result_dir = "$RESULT_DIR"
stats_file = f"{result_dir}/stats_stats.csv"

try:
    with open(stats_file, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 找到Aggregated行
    aggregated = [r for r in rows if r['Name'] == 'Aggregated'][0]

    report = {
        "test_name": "$TEST_NAME",
        "timestamp": "$TIMESTAMP",
        "configuration": {
            "users": $USERS,
            "spawn_rate": $SPAWN_RATE,
            "run_time": "$RUN_TIME"
        },
        "results": {
            "total_requests": int(aggregated['Request Count']),
            "total_failures": int(aggregated['Failure Count']),
            "failure_rate": float(aggregated['Failure Count']) / float(aggregated['Request Count']) * 100 if float(aggregated['Request Count']) > 0 else 0,
            "avg_response_time_ms": float(aggregated['Average Response Time']),
            "min_response_time_ms": float(aggregated['Min Response Time']),
            "max_response_time_ms": float(aggregated['Max Response Time']),
            "median_response_time_ms": float(aggregated['Median Response Time']),
            "requests_per_second": float(aggregated['Requests/s']),
            "avg_content_size_bytes": float(aggregated['Average Content Size'])
        }
    }

    # 保存JSON报告
    with open(f"{result_dir}/summary.json", 'w') as f:
        json.dump(report, f, indent=2)

    print("\n性能摘要:")
    print(f"  总请求数: {report['results']['total_requests']}")
    print(f"  失败数: {report['results']['total_failures']}")
    print(f"  失败率: {report['results']['failure_rate']:.2f}%")
    print(f"  平均响应时间: {report['results']['avg_response_time_ms']:.2f}ms")
    print(f"  中位数响应时间: {report['results']['median_response_time_ms']:.2f}ms")
    print(f"  最大响应时间: {report['results']['max_response_time_ms']:.2f}ms")
    print(f"  RPS: {report['results']['requests_per_second']:.2f}")

    # 性能评级
    avg_time = report['results']['avg_response_time_ms']
    failure_rate = report['results']['failure_rate']

    print("\n性能评级:")
    if failure_rate > 5:
        print("  ❌ 失败率过高 (>5%)")
    elif failure_rate > 1:
        print("  ⚠️  失败率偏高 (>1%)")
    else:
        print("  ✓ 失败率正常 (<1%)")

    if avg_time > 1000:
        print("  ❌ 响应时间过慢 (>1s)")
    elif avg_time > 500:
        print("  ⚠️  响应时间偏慢 (>500ms)")
    elif avg_time > 200:
        print("  ✓ 响应时间良好 (<500ms)")
    else:
        print("  ✓✓ 响应时间优秀 (<200ms)")

except Exception as e:
    print(f"生成报告失败: {e}")
EOF

echo ""
echo "测试完成！"
