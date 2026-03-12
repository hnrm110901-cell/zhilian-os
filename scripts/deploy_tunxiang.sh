#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 屯象OS 全量部署脚本 (裸机版)
# 服务器: 42.194.229.21 (腾讯云 Lighthouse)
# 用法: sudo bash deploy_tunxiang.sh
# ═══════════════════════════════════════════════════════════════

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

APP_DIR="/opt/zhilian-os"
APP_USER="zhilian"
REPO_URL="https://github.com/hnrm110901-cell/zhilian-os.git"
FRONTEND_DIST="/var/www/tunxiang"

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] $1${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] $1${NC}"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] $1${NC}"; }

echo ""
echo "═══════════════════════════════════════════════"
echo "   屯象OS · 全量部署   $(date '+%Y-%m-%d %H:%M')"
echo "═══════════════════════════════════════════════"
echo ""

# ── 0. 权限检查 ───────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    err "请使用 root 或 sudo 运行: sudo bash deploy_tunxiang.sh"
    exit 1
fi

# ── 1. 检查 & 安装 Node.js ───────────────────────────────────
log "Step 1/8: 检查 Node.js..."
if ! command -v node &>/dev/null || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]]; then
    warn "Node.js 未安装或版本 < 18，正在安装 Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
    log "Node.js $(node -v) 安装完成"
else
    log "Node.js $(node -v) ✓"
fi

# 确保 npm 可用
if ! command -v npm &>/dev/null; then
    err "npm 未找到，请检查 Node.js 安装"
    exit 1
fi

# ── 2. 拉取最新代码 ──────────────────────────────────────────
log "Step 2/8: 拉取最新代码..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    # 保存当前 .env 文件
    cp -f apps/api-gateway/.env apps/api-gateway/.env.bak 2>/dev/null || true

    git fetch origin main
    git reset --hard origin/main
    log "代码更新到 $(git log --oneline -1)"
else
    warn "首次部署，克隆仓库..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
    log "仓库克隆完成"
fi

# 确保应用用户存在
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    warn "创建用户: $APP_USER"
fi

# ── 3. 构建前端 ──────────────────────────────────────────────
log "Step 3/8: 构建前端 (npm install + build)..."
cd "$APP_DIR/apps/web"

# 前端环境变量
cat > .env.production <<'ENVEOF'
VITE_API_BASE_URL=
VITE_APP_TITLE=屯象OS
ENVEOF

npm install --legacy-peer-deps 2>&1 | tail -3
npm run build 2>&1 | tail -5

if [ ! -f "dist/index.html" ]; then
    err "前端构建失败! dist/index.html 不存在"
    exit 1
fi
log "前端构建完成 ✓ ($(du -sh dist | cut -f1))"

# 部署前端静态文件
mkdir -p "$FRONTEND_DIST"
rm -rf "${FRONTEND_DIST:?}"/*
cp -r dist/* "$FRONTEND_DIST/"
chown -R www-data:www-data "$FRONTEND_DIST"
log "前端文件部署到 $FRONTEND_DIST ✓"

# ── 4. 更新后端依赖 ──────────────────────────────────────────
log "Step 4/8: 更新后端依赖..."
cd "$APP_DIR/apps/api-gateway"

# 恢复 .env
if [ -f .env.bak ]; then
    cp -f .env.bak .env
    log "已恢复 .env 配置"
fi

# 确保 .env 存在
if [ ! -f .env ]; then
    warn "未找到 .env，创建默认配置..."
    JWT_KEY=$(openssl rand -hex 32)
    cat > .env <<ENVEOF
APP_ENV=production
APP_DEBUG=False
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_URL=postgresql://zhilian:zhilian_password_2026@localhost:5432/zhilian_os
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=${JWT_KEY}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=["https://www.zlsjos.cn","https://zlsjos.cn","http://42.194.229.21"]
LOG_LEVEL=INFO
SECRET_KEY=$(openssl rand -hex 32)
ALERT_DEDUPE_BACKEND=memory
ALERT_DEDUPE_ENABLED=true
ALERT_DEDUPE_TTL_SECONDS=300
ENVEOF
    chown "$APP_USER:$APP_USER" .env
    log "已创建默认 .env"
fi

# Python 虚拟环境
if [ ! -d venv ]; then
    python3 -m venv venv
    warn "创建 Python 虚拟环境"
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q 2>&1 | tail -3
log "后端依赖更新完成 ✓"

# ── 5. 数据库迁移 ────────────────────────────────────────────
log "Step 5/8: 数据库迁移..."
cd "$APP_DIR/apps/api-gateway"
source venv/bin/activate

# 检查 PostgreSQL 是否可连接
if command -v pg_isready &>/dev/null && pg_isready -q; then
    if [ -f alembic.ini ]; then
        PYTHONPATH="$APP_DIR/apps/api-gateway:$APP_DIR/packages" \
            alembic upgrade head 2>&1 | tail -5 || warn "迁移跳过（可能已是最新）"
        log "数据库迁移完成 ✓"
    fi
else
    warn "PostgreSQL 未运行或无法连接，跳过迁移"
fi

# ── 6. 配置 Nginx (前后端分离) ───────────────────────────────
log "Step 6/8: 配置 Nginx..."

# 检测 SSL 证书位置
SSL_CERT=""
SSL_KEY=""
for cert_dir in /etc/nginx/ssl /etc/letsencrypt/live/www.zlsjos.cn /etc/letsencrypt/live/zlsjos.cn; do
    if [ -f "$cert_dir/fullchain.pem" ] && [ -f "$cert_dir/privkey.pem" ]; then
        SSL_CERT="$cert_dir/fullchain.pem"
        SSL_KEY="$cert_dir/privkey.pem"
        break
    fi
done

if [ -z "$SSL_CERT" ]; then
    # 检查其他常见证书格式
    for cert_dir in /etc/nginx/ssl /etc/ssl; do
        if ls "$cert_dir"/*.crt &>/dev/null && ls "$cert_dir"/*.key &>/dev/null; then
            SSL_CERT=$(ls "$cert_dir"/*.crt | head -1)
            SSL_KEY=$(ls "$cert_dir"/*.key | head -1)
            break
        fi
        if ls "$cert_dir"/*.pem &>/dev/null; then
            SSL_CERT=$(ls "$cert_dir"/*fullchain*.pem 2>/dev/null || ls "$cert_dir"/*cert*.pem 2>/dev/null | head -1)
            SSL_KEY=$(ls "$cert_dir"/*privkey*.pem 2>/dev/null || ls "$cert_dir"/*key*.pem 2>/dev/null | head -1)
            [ -n "$SSL_CERT" ] && [ -n "$SSL_KEY" ] && break
        fi
    done
fi

# 写入 Nginx 配置
cat > /etc/nginx/sites-available/tunxiang-os <<NGINXEOF
# ═══ 屯象OS Nginx 配置 ═══

# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name _;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# HTTPS 主服务
server {
NGINXEOF

if [ -n "$SSL_CERT" ] && [ -n "$SSL_KEY" ]; then
    cat >> /etc/nginx/sites-available/tunxiang-os <<NGINXEOF
    listen 443 ssl http2;
    server_name _;

    ssl_certificate     ${SSL_CERT};
    ssl_certificate_key ${SSL_KEY};
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
NGINXEOF
    log "SSL 证书: $SSL_CERT ✓"
else
    warn "未找到 SSL 证书，使用 HTTP 模式"
    # 修改 HTTP 块不重定向
    cat > /etc/nginx/sites-available/tunxiang-os <<'NGINXEOF'
server {
    listen 80;
    server_name _;
NGINXEOF
fi

cat >> /etc/nginx/sites-available/tunxiang-os <<NGINXEOF

    server_tokens off;
    client_max_body_size 100M;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # ── 前端 SPA ──
    root ${FRONTEND_DIST};
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # 静态资源长缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ── API 反向代理 ──
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_connect_timeout 10s;
    }

    # ── API 文档 ──
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    location /redoc {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
    }

    # ── WebSocket ──
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 3600s;
    }

    # ── Nginx 健康检查 ──
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    # 错误页
    error_page 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
        internal;
    }
}
NGINXEOF

# 启用站点
ln -sf /etc/nginx/sites-available/tunxiang-os /etc/nginx/sites-enabled/tunxiang-os
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-enabled/zhilian-os 2>/dev/null

# 测试 Nginx 配置
if nginx -t 2>&1; then
    log "Nginx 配置验证通过 ✓"
else
    err "Nginx 配置有误，请检查!"
    nginx -t
    exit 1
fi

# ── 7. 配置 Supervisor (后端) ────────────────────────────────
log "Step 7/8: 配置 Supervisor..."

mkdir -p /var/log/zhilian-os
chown "$APP_USER:$APP_USER" /var/log/zhilian-os

cat > /etc/supervisor/conf.d/tunxiang-os.conf <<SUPEOF
[program:tunxiang-os]
command=${APP_DIR}/apps/api-gateway/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.main:app --bind 0.0.0.0:8000 --access-logfile - --error-logfile -
directory=${APP_DIR}/apps/api-gateway
user=${APP_USER}
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/zhilian-os/app.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="${APP_DIR}/apps/api-gateway/venv/bin",PYTHONPATH="${APP_DIR}/apps/api-gateway:${APP_DIR}/packages"
SUPEOF

# 移除旧配置
rm -f /etc/supervisor/conf.d/zhilian-os.conf 2>/dev/null

log "Supervisor 配置更新 ✓"

# ── 8. 重启所有服务 ──────────────────────────────────────────
log "Step 8/8: 重启服务..."

# 重启后端
supervisorctl reread
supervisorctl update
supervisorctl restart tunxiang-os 2>/dev/null || supervisorctl start tunxiang-os
sleep 3

# 重启 Nginx
systemctl reload nginx

# ── 验证 ─────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
log "部署完成! 开始验证..."
echo "═══════════════════════════════════════════════"
echo ""

# 检查后端
sleep 2
if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    log "后端 API: ✓ 健康"
    curl -s http://127.0.0.1:8000/api/v1/health | python3 -m json.tool 2>/dev/null || true
else
    warn "后端 API 可能还在启动中，请等待 10 秒后重试:"
    echo "  curl http://127.0.0.1:8000/api/v1/health"
fi

# 检查前端
if [ -f "$FRONTEND_DIST/index.html" ]; then
    if grep -q "屯象OS" "$FRONTEND_DIST/index.html"; then
        log "前端品牌: ✓ 屯象OS"
    else
        warn "前端 index.html 未包含屯象OS标识"
    fi
fi

# 检查 Nginx
if systemctl is-active nginx >/dev/null 2>&1; then
    log "Nginx: ✓ 运行中"
else
    err "Nginx 未运行!"
fi

# 检查 Supervisor
if supervisorctl status tunxiang-os | grep -q RUNNING; then
    log "后端进程: ✓ RUNNING"
else
    warn "后端进程状态:"
    supervisorctl status tunxiang-os
fi

echo ""
echo "═══════════════════════════════════════════════"
echo -e "${GREEN}  屯象OS 部署完成!${NC}"
echo "═══════════════════════════════════════════════"
echo ""
echo "  访问地址:"
echo "    https://www.zlsjos.cn/"
echo "    http://42.194.229.21/"
echo ""
echo "  API 文档:"
echo "    https://www.zlsjos.cn/docs"
echo ""
echo "  管理命令:"
echo "    supervisorctl status tunxiang-os   # 查看状态"
echo "    supervisorctl restart tunxiang-os  # 重启后端"
echo "    tail -f /var/log/zhilian-os/app.log  # 查看日志"
echo "    nginx -t && systemctl reload nginx   # 重载Nginx"
echo ""
echo -e "${GREEN}  屯象OS — 餐饮人的好伙伴 🐘${NC}"
echo ""
