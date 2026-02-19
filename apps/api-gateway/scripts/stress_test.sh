#!/bin/bash
# 神经系统压力测试脚本
# Stress Testing Script for Neural System

echo "============================================================"
echo "智链OS神经系统 - 压力测试"
echo "============================================================"
echo ""

API_URL="http://localhost:8000/api/v1/neural"

# 检查ab命令是否可用
if ! command -v ab &> /dev/null; then
    echo "❌ Apache Bench (ab) 未安装"
    echo "安装方法:"
    echo "  macOS: brew install httpd"
    echo "  Ubuntu: sudo apt-get install apache2-utils"
    exit 1
fi

echo "测试配置:"
echo "  并发数: 10, 50, 100"
echo "  请求数: 1000"
echo ""

# 测试1: 健康检查端点
echo "[1] 压力测试: 健康检查端点"
echo "----------------------------------------"
echo "并发10, 请求1000:"
ab -n 1000 -c 10 -q "${API_URL}/health" 2>&1 | grep -E "Requests per second|Time per request|Percentage"

echo ""
echo "并发50, 请求1000:"
ab -n 1000 -c 50 -q "${API_URL}/health" 2>&1 | grep -E "Requests per second|Time per request|Percentage"

echo ""
echo "并发100, 请求1000:"
ab -n 1000 -c 100 -q "${API_URL}/health" 2>&1 | grep -E "Requests per second|Time per request|Percentage"

# 测试2: 系统状态端点
echo ""
echo "[2] 压力测试: 系统状态端点"
echo "----------------------------------------"
echo "并发10, 请求1000:"
ab -n 1000 -c 10 -q "${API_URL}/status" 2>&1 | grep -E "Requests per second|Time per request|Percentage"

echo ""
echo "并发50, 请求1000:"
ab -n 1000 -c 50 -q "${API_URL}/status" 2>&1 | grep -E "Requests per second|Time per request|Percentage"

echo ""
echo "============================================================"
echo "✓ 压力测试完成"
echo "============================================================"
echo ""
echo "性能指标说明:"
echo "  Requests per second: 每秒请求数（越高越好）"
echo "  Time per request: 平均请求时间（越低越好）"
echo "  Percentage: 响应时间百分位数"
