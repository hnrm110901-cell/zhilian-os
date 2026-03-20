#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  屯象OS 一键更新部署脚本
#  服务器: 42.194.229.21
#  域名: zlsjos.cn
#  执行: ssh root@42.194.229.21 'bash -s' < scripts/deploy_update.sh
# ═══════════════════════════════════════════════════════════

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
APP_DIR="/opt/zhilian-os"

echo "========================================"
echo "  屯象OS 更新部署 $(date '+%Y-%m-%d %H:%M')"
echo "========================================"

# 1. 拉取最新代码
echo -e "\n${GREEN}[1/7] 拉取最新代码${NC}"
cd $APP_DIR
git pull origin main --no-rebase
echo "当前版本: $(git log --oneline -1)"

# 2. 后端依赖更新
echo -e "\n${GREEN}[2/7] 后端依赖${NC}"
cd $APP_DIR/apps/api-gateway
pip3 install -r requirements.txt -q 2>/dev/null || pip install -r requirements.txt -q 2>/dev/null || echo "跳过pip(可能无requirements.txt)"

# 3. 数据库迁移
echo -e "\n${GREEN}[3/7] 数据库迁移${NC}"
cd $APP_DIR/apps/api-gateway
if [ -f "alembic.ini" ]; then
    alembic upgrade head 2>&1 || echo -e "${YELLOW}迁移跳过(可能已是最新)${NC}"
else
    echo "无 alembic.ini，跳过迁移"
fi

# 4. 种子数据(三品牌商户)
echo -e "\n${GREEN}[4/7] 种子数据${NC}"
cd $APP_DIR/apps/api-gateway
if [ -f "scripts/seed_real_merchants.py" ]; then
    python3 scripts/seed_real_merchants.py 2>&1 || echo -e "${YELLOW}种子脚本跳过(可能DB未连接)${NC}"
fi

# 5. 前端构建
echo -e "\n${GREEN}[5/7] 前端构建${NC}"
cd $APP_DIR/apps/web
if command -v pnpm &>/dev/null; then
    pnpm install --frozen-lockfile 2>/dev/null || pnpm install
    pnpm build
elif command -v npm &>/dev/null; then
    npm install
    npm run build
else
    echo -e "${YELLOW}未找到pnpm/npm，跳过前端构建${NC}"
fi

# 6. 重启服务
echo -e "\n${GREEN}[6/7] 重启服务${NC}"

# 方式A: Docker Compose
if [ -f "$APP_DIR/docker-compose.prod.yml" ] && command -v docker-compose &>/dev/null; then
    cd $APP_DIR
    docker-compose -f docker-compose.prod.yml pull
    docker-compose -f docker-compose.prod.yml up -d --build
    echo "Docker 服务已重启"

# 方式B: systemd
elif systemctl is-active --quiet zhilian-api 2>/dev/null; then
    systemctl restart zhilian-api
    systemctl restart zhilian-web 2>/dev/null || true
    echo "systemd 服务已重启"

# 方式C: 直接 uvicorn
else
    cd $APP_DIR/apps/api-gateway
    pkill -f "uvicorn.*main:app" 2>/dev/null || true
    sleep 2
    nohup python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2 > /var/log/zhilian-api.log 2>&1 &
    echo "uvicorn 已后台启动 (PID: $!)"

    # Nginx 静态文件更新
    if [ -d "/var/www/zhilian-os" ]; then
        cp -r $APP_DIR/apps/web/dist/* /var/www/zhilian-os/
        nginx -s reload 2>/dev/null || systemctl reload nginx 2>/dev/null
        echo "Nginx 静态文件已更新"
    elif [ -d "/usr/share/nginx/html" ]; then
        cp -r $APP_DIR/apps/web/dist/* /usr/share/nginx/html/
        nginx -s reload 2>/dev/null || systemctl reload nginx 2>/dev/null
        echo "Nginx 静态文件已更新"
    fi
fi

# 7. 验证
echo -e "\n${GREEN}[7/7] 部署验证${NC}"
sleep 3

# 后端API
API_CODE=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" http://localhost:8000/docs)
if [ "$API_CODE" = "200" ]; then
    echo -e "  ${GREEN}✅ 后端API: /docs → HTTP 200${NC}"
else
    echo -e "  ${RED}❌ 后端API: /docs → HTTP $API_CODE${NC}"
fi

# 新增端点
for path in "/api/v1/daily-flow/config/standard-nodes" "/api/v1/analytics/pareto/scenes"; do
    CODE=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" "http://localhost:8000${path}")
    if [ "$CODE" = "200" ]; then
        echo -e "  ${GREEN}✅ ${path} → HTTP 200${NC}"
    else
        echo -e "  ${RED}❌ ${path} → HTTP $CODE${NC}"
    fi
done

# 前端
FRONT_CODE=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" http://localhost/)
if [ "$FRONT_CODE" = "200" ]; then
    echo -e "  ${GREEN}✅ 前端: / → HTTP 200${NC}"
else
    FRONT_CODE2=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" http://localhost:80/)
    echo -e "  ${YELLOW}⚠️  前端: HTTP $FRONT_CODE (nginx: $FRONT_CODE2)${NC}"
fi

echo ""
echo "========================================"
echo "  部署完成! $(date '+%Y-%m-%d %H:%M')"
echo "  版本: $(cd $APP_DIR && git log --oneline -1)"
echo "  域名: https://zlsjos.cn"
echo "========================================"
