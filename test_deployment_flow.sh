#!/bin/bash
# 智链OS部署流程完整测试脚本

echo "=========================================="
echo "智链OS GitHub到腾讯云部署流程测试"
echo "测试时间: $(date)"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 测试计数
PASS=0
FAIL=0

# 测试函数
test_item() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        ((PASS++))
    else
        echo -e "${RED}✗${NC} $1"
        ((FAIL++))
    fi
}

echo "第一部分: GitHub仓库测试"
echo "----------------------------------------"

echo -n "1. 测试GitHub仓库访问..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://github.com/hnrm110901-cell/zhilian-os)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e " ${GREEN}✓${NC} (HTTP $HTTP_CODE)"
    ((PASS++))
else
    echo -e " ${RED}✗${NC} (HTTP $HTTP_CODE)"
    ((FAIL++))
fi

echo -n "2. 测试部署脚本下载..."
curl -s -o /tmp/test_deploy.sh https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/apps/api-gateway/deploy.sh
test_item "部署脚本下载"

echo -n "3. 测试检查脚本下载..."
curl -s -o /tmp/test_check.sh https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/apps/api-gateway/check_deployment.sh
test_item "检查脚本下载"

echo -n "4. 测试部署文档下载..."
curl -s -o /tmp/test_guide.md https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/apps/api-gateway/DEPLOYMENT_GUIDE.md
test_item "部署文档下载"

echo ""
echo "第二部分: 脚本验证测试"
echo "----------------------------------------"

echo -n "5. 验证部署脚本语法..."
bash -n /tmp/test_deploy.sh 2>/dev/null
test_item "部署脚本语法"

echo -n "6. 验证检查脚本语法..."
bash -n /tmp/test_check.sh 2>/dev/null
test_item "检查脚本语法"

echo -n "7. 检查部署脚本配置..."
if grep -q "42.194.229.21" /tmp/test_deploy.sh && grep -q "www.zlsjos.cn" /tmp/test_deploy.sh; then
    echo -e " ${GREEN}✓${NC}"
    ((PASS++))
else
    echo -e " ${RED}✗${NC}"
    ((FAIL++))
fi

echo ""
echo "第三部分: 服务器状态测试"
echo "----------------------------------------"

echo -n "8. 测试服务器连接..."
ping -c 1 42.194.229.21 > /dev/null 2>&1
test_item "服务器可达"

echo -n "9. 测试域名解析..."
nslookup www.zlsjos.cn > /dev/null 2>&1
test_item "域名解析"

echo -n "10. 测试HTTP服务..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://www.zlsjos.cn)
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "302" ]; then
    echo -e " ${GREEN}✓${NC} (HTTP $HTTP_STATUS)"
    ((PASS++))
else
    echo -e " ${YELLOW}⚠${NC} (HTTP $HTTP_STATUS)"
fi

echo -n "11. 测试API健康检查..."
HEALTH=$(curl -s http://www.zlsjos.cn/api/v1/health 2>&1)
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e " ${GREEN}✓${NC}"
    ((PASS++))
else
    echo -e " ${YELLOW}⚠${NC} (API未部署)"
fi

echo ""
echo "=========================================="
echo "测试结果总结"
echo "=========================================="
echo -e "通过: ${GREEN}$PASS${NC}"
echo -e "失败: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ 所有测试通过！部署流程准备就绪。${NC}"
    echo ""
    echo "下一步操作:"
    echo "1. SSH连接到服务器: ssh root@42.194.229.21"
    echo "2. 下载部署脚本:"
    echo "   wget https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/apps/api-gateway/deploy.sh"
    echo "3. 运行部署: chmod +x deploy.sh && sudo bash deploy.sh"
else
    echo -e "${RED}✗ 部分测试失败，请检查问题后重试。${NC}"
fi

echo ""
echo "=========================================="

# 清理临时文件
rm -f /tmp/test_deploy.sh /tmp/test_check.sh /tmp/test_guide.md
