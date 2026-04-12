#!/bin/bash
# 安装并配置git-secrets防止凭证泄露
set -e

echo "=== 屯象OS git-secrets 配置 ==="

# 检查git-secrets是否安装
if ! command -v git-secrets &> /dev/null; then
    echo "请先安装git-secrets: brew install git-secrets"
    exit 1
fi

# 初始化
git secrets --install -f
git secrets --register-aws

# 添加自定义规则
git secrets --add --literal 'PINZHI_API_TOKEN='
git secrets --add --literal 'AOQIWEI_APP_KEY='
git secrets --add --literal 'AOQIWEI_APP_SECRET='
git secrets --add --literal 'APP_SECRET='
git secrets --add '[a-f0-9]{32}'

# 添加允许列表（.env.example中的占位符）
git secrets --add --allowed 'your_.*_here'
git secrets --add --allowed 'REPLACE_WITH_ACTUAL_VALUE'
git secrets --add --allowed 'test[-_]'

echo "git-secrets配置完成。每次commit前将自动扫描。"
echo "手动扫描: git secrets --scan"
