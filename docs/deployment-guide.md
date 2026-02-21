# 生产环境部署指南

## 概述

本文档提供智链OS系统的生产环境部署指南，包括环境配置、Docker部署、服务器配置等内容。

## 系统要求

### 硬件要求
- CPU: 4核心或以上
- 内存: 8GB或以上
- 磁盘: 50GB或以上SSD

### 软件要求
- Node.js: 18.x或以上
- Python: 3.9或以上
- Docker: 20.x或以上
- Docker Compose: 2.x或以上
- Nginx: 1.20或以上

## 部署架构

```
┌─────────────────────────────────────────────┐
│              Load Balancer (Nginx)          │
└─────────────────┬───────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼────────┐  ┌──────▼────────┐
│  Web Frontend  │  │  API Gateway  │
│   (React App)  │  │   (FastAPI)   │
└────────────────┘  └───────┬───────┘
                            │
                    ┌───────┴────────┐
                    │                │
            ┌───────▼──────┐  ┌─────▼──────┐
            │   Agents     │  │  Database  │
            │   (Python)   │  │ (Optional) │
            └──────────────┘  └────────────┘
```

## 快速部署

### 1. 使用Docker Compose (推荐)

```bash
# 克隆项目
git clone <repository-url>
cd zhilian-os

# 配置环境变量
cp .env.example .env.production
# 编辑 .env.production 填入生产环境配置

# 构建并启动服务
docker-compose -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f
```

### 2. 手动部署

#### 2.1 前端部署

```bash
# 进入前端目录
cd apps/web

# 安装依赖
pnpm install

# 构建生产版本
pnpm build

# 部署到Nginx
sudo cp -r dist/* /var/www/zhilian-os/
```

#### 2.2 后端部署

```bash
# 进入后端目录
cd apps/api-gateway

# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动服务 (使用gunicorn)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.main:app --bind 0.0.0.0:8000
```

## 环境配置

### 前端环境变量

创建 `apps/web/.env.production`:

```env
# API配置
VITE_API_BASE_URL=https://api.yourdomain.com

# 企业微信配置
VITE_WECHAT_CORP_ID=your_corp_id
VITE_WECHAT_APP_ID=your_app_id

# 飞书配置
VITE_FEISHU_APP_ID=your_app_id
```

### 后端环境变量

创建 `apps/api-gateway/.env.production`:

```env
# 应用配置
APP_ENV=production
DEBUG=False
SECRET_KEY=your_secret_key_here

# 数据库配置 (可选)
DATABASE_URL=postgresql://user:password@localhost:5432/zhilian_os

# Redis配置 (可选)
REDIS_URL=redis://localhost:6379/0

# 企业微信配置
WECHAT_CORP_ID=your_corp_id
WECHAT_APP_SECRET=your_app_secret
WECHAT_AGENT_ID=your_agent_id

# 飞书配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret

# CORS配置
CORS_ORIGINS=https://yourdomain.com

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=/var/log/zhilian-os/app.log
```

## Nginx配置

创建 `/etc/nginx/sites-available/zhilian-os`:

```nginx
# 前端服务
server {
    listen 80;
    server_name yourdomain.com;

    # 重定向到HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    # SSL证书配置
    ssl_certificate /etc/ssl/certs/yourdomain.com.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.com.key;

    # SSL安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # 前端静态文件
    root /var/www/zhilian-os;
    index index.html;

    # Gzip压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # 前端路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API代理
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

启用配置:

```bash
sudo ln -s /etc/nginx/sites-available/zhilian-os /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 进程管理

### 使用Systemd管理后端服务

创建 `/etc/systemd/system/zhilian-api.service`:

```ini
[Unit]
Description=Zhilian OS API Gateway
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/zhilian-os/apps/api-gateway
Environment="PATH=/opt/zhilian-os/apps/api-gateway/venv/bin"
ExecStart=/opt/zhilian-os/apps/api-gateway/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.main:app --bind 0.0.0.0:8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务:

```bash
sudo systemctl daemon-reload
sudo systemctl enable zhilian-api
sudo systemctl start zhilian-api
sudo systemctl status zhilian-api
```

## 监控和日志

### 日志配置

```bash
# 创建日志目录
sudo mkdir -p /var/log/zhilian-os
sudo chown www-data:www-data /var/log/zhilian-os

# 配置日志轮转
sudo tee /etc/logrotate.d/zhilian-os <<EOF
/var/log/zhilian-os/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload zhilian-api > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 健康检查

```bash
# API健康检查
curl https://api.yourdomain.com/api/v1/health

# 前端检查
curl https://yourdomain.com
```

## 安全配置

### 1. 防火墙配置

```bash
# 允许HTTP和HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 允许SSH (如果需要)
sudo ufw allow 22/tcp

# 启用防火墙
sudo ufw enable
```

### 2. SSL证书 (Let's Encrypt)

```bash
# 安装certbot
sudo apt-get install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d yourdomain.com

# 自动续期
sudo certbot renew --dry-run
```

### 3. 安全头配置

在Nginx配置中添加:

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
```

## 备份策略

### 数据库备份

```bash
# 创建备份脚本
sudo tee /opt/zhilian-os/backup.sh <<EOF
#!/bin/bash
BACKUP_DIR="/var/backups/zhilian-os"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p \$BACKUP_DIR

# 备份数据库 (如果使用)
# pg_dump zhilian_os > \$BACKUP_DIR/db_\$DATE.sql

# 备份配置文件
tar -czf \$BACKUP_DIR/config_\$DATE.tar.gz /opt/zhilian-os/.env.production

# 删除30天前的备份
find \$BACKUP_DIR -name "*.sql" -mtime +30 -delete
find \$BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
EOF

chmod +x /opt/zhilian-os/backup.sh

# 添加到crontab (每天凌晨2点执行)
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/zhilian-os/backup.sh") | crontab -
```

## 性能优化

### 1. 前端优化

- 启用Gzip压缩
- 配置浏览器缓存
- 使用CDN加速静态资源
- 代码分割和懒加载

### 2. 后端优化

- 使用多进程/多线程
- 配置连接池
- 启用缓存 (Redis)
- 数据库索引优化

### 3. 系统优化

```bash
# 增加文件描述符限制
sudo tee -a /etc/security/limits.conf <<EOF
* soft nofile 65535
* hard nofile 65535
EOF

# 优化TCP参数
sudo tee -a /etc/sysctl.conf <<EOF
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_tw_reuse = 1
EOF

sudo sysctl -p
```

## 故障排查

### 常见问题

1. **前端无法访问**
   - 检查Nginx配置: `sudo nginx -t`
   - 查看Nginx日志: `sudo tail -f /var/log/nginx/error.log`
   - 检查防火墙: `sudo ufw status`

2. **API无法访问**
   - 检查服务状态: `sudo systemctl status zhilian-api`
   - 查看应用日志: `sudo tail -f /var/log/zhilian-os/app.log`
   - 检查端口占用: `sudo netstat -tlnp | grep 8000`

3. **性能问题**
   - 查看系统资源: `htop`
   - 检查磁盘空间: `df -h`
   - 分析慢查询日志

## 更新部署

### 零停机更新

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 构建新版本
pnpm build

# 3. 备份当前版本
sudo cp -r /var/www/zhilian-os /var/www/zhilian-os.backup

# 4. 部署新版本
sudo cp -r apps/web/dist/* /var/www/zhilian-os/

# 5. 重启后端服务
sudo systemctl restart zhilian-api

# 6. 验证部署
curl https://yourdomain.com/api/v1/health
```

## 监控告警

### 推荐监控工具

- **Prometheus + Grafana**: 系统监控和可视化
- **ELK Stack**: 日志收集和分析
- **Sentry**: 错误追踪
- **UptimeRobot**: 服务可用性监控

## 支持和维护

### 联系方式

- 技术支持: support@zhilian-os.com
- 文档: https://docs.zhilian-os.com
- GitHub: https://github.com/zhilian-os

### 维护计划

- 每周安全更新检查
- 每月性能优化评估
- 每季度系统升级

---

**文档版本**: v1.0
**最后更新**: 2024-02-15
**智链OS开发团队** © 2026
