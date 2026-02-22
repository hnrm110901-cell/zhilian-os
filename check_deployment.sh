#!/bin/bash
# 智链OS腾讯云服务器部署状态检查脚本
# 使用方法: bash check_deployment.sh

echo "=========================================="
echo "智链OS 腾讯云部署状态检查"
echo "服务器: 42.194.229.21"
echo "域名: www.zlsjos.cn"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 检查函数
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
    fi
}

echo "1. 检查服务器连接..."
ping -c 1 42.194.229.21 > /dev/null 2>&1
check_status "服务器可达"

echo ""
echo "2. 检查域名解析..."
nslookup www.zlsjos.cn > /dev/null 2>&1
check_status "域名解析正常"

echo ""
echo "3. 检查HTTP服务..."
curl -s -o /dev/null -w "%{http_code}" http://www.zlsjos.cn > /tmp/http_status.txt 2>&1
HTTP_STATUS=$(cat /tmp/http_status.txt)
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "302" ]; then
    echo -e "${GREEN}✓${NC} HTTP服务正常 (状态码: $HTTP_STATUS)"
else
    echo -e "${YELLOW}⚠${NC} HTTP服务状态: $HTTP_STATUS (可能尚未部署)"
fi

echo ""
echo "4. 检查API健康状态..."
HEALTH_CHECK=$(curl -s http://www.zlsjos.cn/api/v1/health 2>&1)
if echo "$HEALTH_CHECK" | grep -q "healthy"; then
    echo -e "${GREEN}✓${NC} API健康检查通过"
    echo "   响应: $HEALTH_CHECK"
else
    echo -e "${YELLOW}⚠${NC} API尚未部署或无法访问"
fi

echo ""
echo "5. 检查API文档..."
curl -s -o /dev/null -w "%{http_code}" http://www.zlsjos.cn/docs > /tmp/docs_status.txt 2>&1
DOCS_STATUS=$(cat /tmp/docs_status.txt)
if [ "$DOCS_STATUS" = "200" ]; then
    echo -e "${GREEN}✓${NC} API文档可访问"
else
    echo -e "${YELLOW}⚠${NC} API文档状态: $DOCS_STATUS"
fi

echo ""
echo "=========================================="
echo "部署状态总结"
echo "=========================================="

# 判断部署状态
if [ "$HTTP_STATUS" = "200" ] && echo "$HEALTH_CHECK" | grep -q "healthy"; then
    echo -e "${GREEN}✓ 智链OS已成功部署并运行${NC}"
    echo ""
    echo "访问地址:"
    echo "  - API文档: http://www.zlsjos.cn/docs"
    echo "  - ReDoc文档: http://www.zlsjos.cn/redoc"
    echo "  - 健康检查: http://www.zlsjos.cn/api/v1/health"
else
    echo -e "${YELLOW}⚠ 智链OS尚未部署或服务未启动${NC}"
    echo ""
    echo "请按照以下步骤部署:"
    echo ""
    echo "1. SSH连接到服务器:"
    echo "   ssh root@42.194.229.21"
    echo ""
    echo "2. 下载部署脚本:"
    echo "   wget https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/deploy.sh"
    echo ""
    echo "3. 运行部署脚本:"
    echo "   chmod +x deploy.sh"
    echo "   sudo bash deploy.sh"
    echo ""
    echo "4. 等待10-15分钟完成部署"
    echo ""
    echo "5. 再次运行此检查脚本验证部署"
fi

echo ""
echo "=========================================="

# 清理临时文件
rm -f /tmp/http_status.txt /tmp/docs_status.txt
