#!/bin/bash
# 智链OS腾讯云服务器部署脚本
# 服务器: 42.194.229.21
# 域名: www.zlsjos.cn

set -e  # 遇到错误立即退出

echo "=========================================="
echo "智链OS 腾讯云部署脚本"
echo "服务器: 42.194.229.21"
echo "域名: www.zlsjos.cn"
echo "=========================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 配置变量
SERVER_IP="42.194.229.21"
DOMAIN="www.zlsjos.cn"
APP_DIR="/opt/zhilian-os"
APP_USER="zhilian"
PYTHON_VERSION="3.9"

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用root用户运行此脚本${NC}"
    echo "使用命令: sudo bash deploy.sh"
    exit 1
fi

echo -e "${GREEN}Step 1: 更新系统软件包${NC}"
apt-get update
apt-get upgrade -y

echo -e "${GREEN}Step 2: 安装基础依赖${NC}"
apt-get install -y \
    git \
    curl \
    wget \
    vim \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    python3-pip \
    python3-venv \
    nginx \
    supervisor

echo -e "${GREEN}Step 3: 安装PostgreSQL${NC}"
apt-get install -y postgresql postgresql-contrib
systemctl start postgresql
systemctl enable postgresql

echo -e "${GREEN}Step 4: 安装Redis${NC}"
apt-get install -y redis-server
systemctl start redis-server
systemctl enable redis-server

echo -e "${GREEN}Step 5: 创建应用用户${NC}"
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash $APP_USER
    echo -e "${YELLOW}已创建用户: $APP_USER${NC}"
fi

echo -e "${GREEN}Step 6: 创建PostgreSQL数据库${NC}"
sudo -u postgres psql <<EOF
CREATE DATABASE zhilian_os;
CREATE USER zhilian WITH PASSWORD 'zhilian_password_2026';
GRANT ALL PRIVILEGES ON DATABASE zhilian_os TO zhilian;
\q
EOF

echo -e "${GREEN}Step 7: 克隆代码仓库${NC}"
if [ -d "$APP_DIR" ]; then
    echo -e "${YELLOW}目录已存在，拉取最新代码${NC}"
    cd $APP_DIR
    sudo -u $APP_USER git pull
else
    sudo -u $APP_USER git clone https://github.com/hnrm110901-cell/zhilian-os.git $APP_DIR
fi

cd $APP_DIR/apps/api-gateway

echo -e "${GREEN}Step 8: 创建Python虚拟环境${NC}"
sudo -u $APP_USER python3 -m venv venv
source venv/bin/activate

echo -e "${GREEN}Step 9: 安装Python依赖${NC}"
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}Step 10: 配置环境变量${NC}"
cat > .env <<EOF
# 应用配置
APP_ENV=production
APP_DEBUG=False
APP_HOST=0.0.0.0
APP_PORT=8000

# 数据库配置
DATABASE_URL=postgresql://zhilian:zhilian_password_2026@localhost:5432/zhilian_os

# Redis配置
REDIS_URL=redis://localhost:6379/0

# JWT配置
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS配置
CORS_ORIGINS=["https://www.zlsjos.cn", "https://zlsjos.cn", "http://localhost:3000"]

# 日志配置
LOG_LEVEL=INFO
EOF

chown $APP_USER:$APP_USER .env

echo -e "${GREEN}Step 11: 运行数据库迁移${NC}"
alembic upgrade head

echo -e "${GREEN}Step 12: 配置Supervisor${NC}"
cat > /etc/supervisor/conf.d/zhilian-os.conf <<EOF
[program:zhilian-os]
command=$APP_DIR/apps/api-gateway/venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
directory=$APP_DIR/apps/api-gateway
user=$APP_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/zhilian-os/app.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="$APP_DIR/apps/api-gateway/venv/bin"
EOF

# 创建日志目录
mkdir -p /var/log/zhilian-os
chown $APP_USER:$APP_USER /var/log/zhilian-os

# 重新加载Supervisor配置
supervisorctl reread
supervisorctl update
supervisorctl start zhilian-os

echo -e "${GREEN}Step 13: 配置Nginx${NC}"
cat > /etc/nginx/sites-available/zhilian-os <<EOF
# HTTP重定向到HTTPS
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$server_name\$request_uri;
}

# HTTPS配置
server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    # SSL证书配置（需要先申请证书）
    # ssl_certificate /etc/nginx/ssl/zlsjos.cn.crt;
    # ssl_certificate_key /etc/nginx/ssl/zlsjos.cn.key;

    # 临时使用HTTP（证书申请后启用HTTPS）
    listen 80;

    # SSL配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # 日志
    access_log /var/log/nginx/zhilian-os-access.log;
    error_log /var/log/nginx/zhilian-os-error.log;

    # 客户端最大上传大小
    client_max_body_size 100M;

    # 反向代理到FastAPI应用
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 静态文件（如果有）
    location /static/ {
        alias $APP_DIR/apps/api-gateway/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # API文档
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8000/redoc;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

# 启用站点
ln -sf /etc/nginx/sites-available/zhilian-os /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试Nginx配置
nginx -t

# 重启Nginx
systemctl restart nginx
systemctl enable nginx

echo -e "${GREEN}Step 14: 配置防火墙${NC}"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo -e "${GREEN}Step 15: 检查服务状态${NC}"
echo "----------------------------------------"
echo "PostgreSQL状态:"
systemctl status postgresql --no-pager | head -3
echo "----------------------------------------"
echo "Redis状态:"
systemctl status redis-server --no-pager | head -3
echo "----------------------------------------"
echo "智链OS应用状态:"
supervisorctl status zhilian-os
echo "----------------------------------------"
echo "Nginx状态:"
systemctl status nginx --no-pager | head -3
echo "----------------------------------------"

echo ""
echo -e "${GREEN}=========================================="
echo "部署完成！"
echo "==========================================${NC}"
echo ""
echo -e "${YELLOW}访问地址:${NC}"
echo "  - API文档: http://$DOMAIN/docs"
echo "  - ReDoc文档: http://$DOMAIN/redoc"
echo "  - 健康检查: http://$DOMAIN/api/v1/health"
echo ""
echo -e "${YELLOW}下一步操作:${NC}"
echo "  1. 申请SSL证书（Let's Encrypt）"
echo "     certbot --nginx -d $DOMAIN"
echo ""
echo "  2. 查看应用日志"
echo "     tail -f /var/log/zhilian-os/app.log"
echo ""
echo "  3. 重启应用"
echo "     supervisorctl restart zhilian-os"
echo ""
echo "  4. 查看Nginx日志"
echo "     tail -f /var/log/nginx/zhilian-os-access.log"
echo ""
echo -e "${GREEN}部署成功！🎉${NC}"
