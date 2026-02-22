# 智链OS腾讯云部署指南
# Zhilian OS Tencent Cloud Deployment Guide

**服务器**: 42.194.229.21
**域名**: www.zlsjos.cn
**部署日期**: 2026-02-22

---

## 一、部署前准备

### 1.1 服务器要求

**最低配置**:
- CPU: 2核
- 内存: 4GB
- 硬盘: 40GB
- 操作系统: Ubuntu 20.04 LTS 或更高版本

**推荐配置**:
- CPU: 4核
- 内存: 8GB
- 硬盘: 100GB SSD
- 操作系统: Ubuntu 22.04 LTS

### 1.2 域名配置

在域名DNS管理中添加A记录：
```
类型: A
主机记录: www
记录值: 42.194.229.21
TTL: 600
```

### 1.3 SSH访问

确保可以通过SSH连接到服务器：
```bash
ssh root@42.194.229.21
```

---

## 二、快速部署（推荐）

### 2.1 下载部署脚本

```bash
# 连接到服务器
ssh root@42.194.229.21

# 下载部署脚本
wget https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/deploy.sh

# 或者使用curl
curl -O https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/deploy.sh

# 赋予执行权限
chmod +x deploy.sh
```

### 2.2 运行部署脚本

```bash
# 以root用户运行
sudo bash deploy.sh
```

部署脚本会自动完成以下操作：
1. ✅ 更新系统软件包
2. ✅ 安装基础依赖（Git、Python、Nginx等）
3. ✅ 安装PostgreSQL数据库
4. ✅ 安装Redis缓存
5. ✅ 创建应用用户
6. ✅ 创建数据库和用户
7. ✅ 克隆代码仓库
8. ✅ 创建Python虚拟环境
9. ✅ 安装Python依赖
10. ✅ 配置环境变量
11. ✅ 运行数据库迁移
12. ✅ 配置Supervisor（进程管理）
13. ✅ 配置Nginx（反向代理）
14. ✅ 配置防火墙
15. ✅ 启动服务

**预计时间**: 10-15分钟

---

## 三、手动部署（详细步骤）

如果自动部署脚本失败，可以按照以下步骤手动部署。

### 3.1 更新系统

```bash
apt-get update
apt-get upgrade -y
```

### 3.2 安装基础依赖

```bash
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
```

### 3.3 安装PostgreSQL

```bash
# 安装PostgreSQL
apt-get install -y postgresql postgresql-contrib

# 启动服务
systemctl start postgresql
systemctl enable postgresql

# 创建数据库和用户
sudo -u postgres psql <<EOF
CREATE DATABASE zhilian_os;
CREATE USER zhilian WITH PASSWORD 'zhilian_password_2026';
GRANT ALL PRIVILEGES ON DATABASE zhilian_os TO zhilian;
\q
EOF
```

### 3.4 安装Redis

```bash
# 安装Redis
apt-get install -y redis-server

# 启动服务
systemctl start redis-server
systemctl enable redis-server
```

### 3.5 创建应用用户

```bash
useradd -m -s /bin/bash zhilian
```

### 3.6 克隆代码仓库

```bash
# 切换到应用用户
su - zhilian

# 克隆代码
git clone https://github.com/hnrm110901-cell/zhilian-os.git /opt/zhilian-os

# 进入项目目录
cd /opt/zhilian-os/apps/api-gateway
```

### 3.7 创建Python虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

### 3.8 配置环境变量

```bash
# 创建.env文件
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
```

### 3.9 运行数据库迁移

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行迁移
alembic upgrade head
```

### 3.10 配置Supervisor

```bash
# 退出应用用户，切换回root
exit

# 创建Supervisor配置
cat > /etc/supervisor/conf.d/zhilian-os.conf <<EOF
[program:zhilian-os]
command=/opt/zhilian-os/apps/api-gateway/venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
directory=/opt/zhilian-os/apps/api-gateway
user=zhilian
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/zhilian-os/app.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/opt/zhilian-os/apps/api-gateway/venv/bin"
EOF

# 创建日志目录
mkdir -p /var/log/zhilian-os
chown zhilian:zhilian /var/log/zhilian-os

# 重新加载Supervisor配置
supervisorctl reread
supervisorctl update
supervisorctl start zhilian-os
```

### 3.11 配置Nginx

```bash
# 创建Nginx配置
cat > /etc/nginx/sites-available/zhilian-os <<EOF
server {
    listen 80;
    server_name www.zlsjos.cn;

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
```

### 3.12 配置防火墙

```bash
# 允许SSH、HTTP、HTTPS
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp

# 启用防火墙
ufw --force enable
```

---

## 四、SSL证书配置（HTTPS）

### 4.1 安装Certbot

```bash
apt-get install -y certbot python3-certbot-nginx
```

### 4.2 申请SSL证书

```bash
# 自动配置Nginx并申请证书
certbot --nginx -d www.zlsjos.cn

# 按照提示输入邮箱和同意条款
```

### 4.3 自动续期

```bash
# 测试自动续期
certbot renew --dry-run

# Certbot会自动添加cron任务，每天检查证书是否需要续期
```

---

## 五、验证部署

### 5.1 检查服务状态

```bash
# 检查应用状态
supervisorctl status zhilian-os

# 检查Nginx状态
systemctl status nginx

# 检查PostgreSQL状态
systemctl status postgresql

# 检查Redis状态
systemctl status redis-server
```

### 5.2 访问API文档

在浏览器中访问：
- API文档: http://www.zlsjos.cn/docs
- ReDoc文档: http://www.zlsjos.cn/redoc
- 健康检查: http://www.zlsjos.cn/api/v1/health

### 5.3 测试API

```bash
# 健康检查
curl http://www.zlsjos.cn/api/v1/health

# 预期响应
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-02-22T14:00:00Z"
}
```

---

## 六、常用运维命令

### 6.1 应用管理

```bash
# 查看应用状态
supervisorctl status zhilian-os

# 启动应用
supervisorctl start zhilian-os

# 停止应用
supervisorctl stop zhilian-os

# 重启应用
supervisorctl restart zhilian-os

# 查看应用日志
tail -f /var/log/zhilian-os/app.log
```

### 6.2 Nginx管理

```bash
# 测试配置
nginx -t

# 重启Nginx
systemctl restart nginx

# 查看访问日志
tail -f /var/log/nginx/zhilian-os-access.log

# 查看错误日志
tail -f /var/log/nginx/zhilian-os-error.log
```

### 6.3 数据库管理

```bash
# 连接数据库
sudo -u postgres psql zhilian_os

# 备份数据库
pg_dump -U zhilian zhilian_os > backup_$(date +%Y%m%d).sql

# 恢复数据库
psql -U zhilian zhilian_os < backup_20260222.sql
```

### 6.4 代码更新

```bash
# 切换到应用用户
su - zhilian

# 进入项目目录
cd /opt/zhilian-os

# 拉取最新代码
git pull

# 激活虚拟环境
cd apps/api-gateway
source venv/bin/activate

# 安装新依赖（如果有）
pip install -r requirements.txt

# 运行数据库迁移（如果有）
alembic upgrade head

# 退出应用用户
exit

# 重启应用
supervisorctl restart zhilian-os
```

---

## 七、监控与日志

### 7.1 应用日志

```bash
# 实时查看应用日志
tail -f /var/log/zhilian-os/app.log

# 查看最近100行日志
tail -n 100 /var/log/zhilian-os/app.log

# 搜索错误日志
grep "ERROR" /var/log/zhilian-os/app.log
```

### 7.2 Nginx日志

```bash
# 实时查看访问日志
tail -f /var/log/nginx/zhilian-os-access.log

# 实时查看错误日志
tail -f /var/log/nginx/zhilian-os-error.log

# 统计访问量
cat /var/log/nginx/zhilian-os-access.log | wc -l
```

### 7.3 系统监控

```bash
# 查看CPU和内存使用
htop

# 查看磁盘使用
df -h

# 查看网络连接
netstat -tulpn | grep LISTEN
```

---

## 八、故障排查

### 8.1 应用无法启动

**问题**: supervisorctl status显示FATAL

**排查步骤**:
1. 查看应用日志
   ```bash
   tail -f /var/log/zhilian-os/app.log
   ```

2. 检查Python虚拟环境
   ```bash
   su - zhilian
   cd /opt/zhilian-os/apps/api-gateway
   source venv/bin/activate
   python -c "import src.main"
   ```

3. 检查环境变量
   ```bash
   cat .env
   ```

4. 检查数据库连接
   ```bash
   psql -U zhilian -d zhilian_os -h localhost
   ```

### 8.2 502 Bad Gateway

**问题**: Nginx返回502错误

**排查步骤**:
1. 检查应用是否运行
   ```bash
   supervisorctl status zhilian-os
   ```

2. 检查端口是否监听
   ```bash
   netstat -tulpn | grep 8000
   ```

3. 检查Nginx配置
   ```bash
   nginx -t
   ```

4. 查看Nginx错误日志
   ```bash
   tail -f /var/log/nginx/zhilian-os-error.log
   ```

### 8.3 数据库连接失败

**问题**: 应用无法连接数据库

**排查步骤**:
1. 检查PostgreSQL是否运行
   ```bash
   systemctl status postgresql
   ```

2. 检查数据库用户和密码
   ```bash
   sudo -u postgres psql
   \du  # 列出所有用户
   \l   # 列出所有数据库
   ```

3. 检查环境变量中的DATABASE_URL
   ```bash
   cat /opt/zhilian-os/apps/api-gateway/.env | grep DATABASE_URL
   ```

---

## 九、安全加固

### 9.1 修改默认密码

```bash
# 修改数据库密码
sudo -u postgres psql <<EOF
ALTER USER zhilian WITH PASSWORD 'your_strong_password_here';
\q
EOF

# 更新.env文件中的密码
vim /opt/zhilian-os/apps/api-gateway/.env
```

### 9.2 配置SSH密钥登录

```bash
# 在本地生成SSH密钥（如果还没有）
ssh-keygen -t rsa -b 4096

# 将公钥复制到服务器
ssh-copy-id root@42.194.229.21

# 禁用密码登录
vim /etc/ssh/sshd_config
# 修改: PasswordAuthentication no

# 重启SSH服务
systemctl restart sshd
```

### 9.3 配置Fail2ban

```bash
# 安装Fail2ban
apt-get install -y fail2ban

# 启动服务
systemctl start fail2ban
systemctl enable fail2ban
```

---

## 十、性能优化

### 10.1 调整Worker数量

根据CPU核心数调整Uvicorn worker数量：
```bash
# 编辑Supervisor配置
vim /etc/supervisor/conf.d/zhilian-os.conf

# 修改workers参数
# workers = CPU核心数 * 2 + 1
# 例如4核CPU: --workers 9

# 重启应用
supervisorctl restart zhilian-os
```

### 10.2 配置Nginx缓存

```bash
# 编辑Nginx配置
vim /etc/nginx/sites-available/zhilian-os

# 添加缓存配置
# proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m;
# proxy_cache api_cache;
# proxy_cache_valid 200 10m;

# 重启Nginx
systemctl restart nginx
```

### 10.3 配置PostgreSQL连接池

在应用中配置连接池参数（已在代码中实现）。

---

## 十一、备份策略

### 11.1 数据库备份

```bash
# 创建备份脚本
cat > /opt/backup_db.sh <<EOF
#!/bin/bash
BACKUP_DIR="/opt/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
mkdir -p \$BACKUP_DIR
pg_dump -U zhilian zhilian_os > \$BACKUP_DIR/zhilian_os_\$DATE.sql
# 保留最近7天的备份
find \$BACKUP_DIR -name "*.sql" -mtime +7 -delete
EOF

chmod +x /opt/backup_db.sh

# 添加到crontab（每天凌晨2点备份）
crontab -e
# 添加: 0 2 * * * /opt/backup_db.sh
```

### 11.2 代码备份

代码已托管在GitHub，无需额外备份。

---

## 十二、总结

### 12.1 部署清单

- [x] 系统更新
- [x] 安装依赖
- [x] 安装PostgreSQL
- [x] 安装Redis
- [x] 克隆代码
- [x] 配置环境
- [x] 数据库迁移
- [x] 配置Supervisor
- [x] 配置Nginx
- [x] 配置防火墙
- [x] SSL证书（可选）

### 12.2 访问地址

- **API文档**: http://www.zlsjos.cn/docs
- **ReDoc文档**: http://www.zlsjos.cn/redoc
- **健康检查**: http://www.zlsjos.cn/api/v1/health

### 12.3 技术支持

如遇到问题，请联系：
- Email: support@zhilian-os.com
- GitHub Issues: https://github.com/hnrm110901-cell/zhilian-os/issues

---

**部署文档版本**: v1.0
**最后更新**: 2026-02-22
