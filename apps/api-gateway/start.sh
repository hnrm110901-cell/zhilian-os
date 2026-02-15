#!/bin/bash

# 智链OS API Gateway 启动脚本

set -e

echo "🚀 启动智链OS API Gateway..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python版本: $python_version"

# 检查是否在正确的目录
if [ ! -f "src/main.py" ]; then
    echo "❌ 错误: 请在 apps/api-gateway 目录下运行此脚本"
    exit 1
fi

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo "⚠️  警告: .env 文件不存在，使用 .env.example 创建..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ 已创建 .env 文件，请编辑配置后重新运行"
        exit 0
    else
        echo "❌ 错误: .env.example 文件不存在"
        exit 1
    fi
fi

# 检查依赖
echo "📦 检查依赖..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "⚠️  警告: 依赖未安装，正在安装..."
    pip install -r requirements.txt
fi

# 设置环境变量
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 启动服务
echo "🌟 启动服务..."
echo "📍 API文档: http://localhost:8000/docs"
echo "📍 健康检查: http://localhost:8000/api/v1/health"
echo ""

python3 -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
