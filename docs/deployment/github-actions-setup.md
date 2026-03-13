# GitHub Actions 自动部署配置指南

## 概述

屯象OS 的 CI/CD 流水线：
```
代码推送到 main → GitHub Actions 自动触发
  → TypeScript 检查 + 前端构建
  → SSH 到服务器 pull 代码
  → 停止旧 supervisor 进程
  → Docker Compose 重启 API
  → 前端 rsync 到 nginx 目录
  → 健康检查验证
```

## 一次性设置步骤

### 1. 在服务器生成 Deploy SSH 密钥

在服务器（root 账户）上执行：

```bash
# 生成专用 deploy key（不加密码）
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy -C "github-actions-deploy" -N ""

# 查看公钥（添加到服务器 authorized_keys）
cat /root/.ssh/github_deploy.pub >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# 查看私钥（复制到 GitHub Secrets）
cat /root/.ssh/github_deploy
```

### 2. 将私钥添加到 GitHub Secrets

1. 打开 GitHub 仓库 → Settings → Secrets and variables → Actions
2. 点击 "New repository secret"
3. Name: `SERVER_SSH_KEY`
4. Value: 粘贴上一步 `cat /root/.ssh/github_deploy` 的完整内容（包括 `-----BEGIN ...-----` 行）
5. 点击 "Add secret"

### 3. 验证配置

推送任意代码到 main 分支，然后在 GitHub → Actions 查看部署日志。

## 工作流文件

`.github/workflows/deploy.yml` — 部署工作流

### 触发条件
- `git push origin main` 时自动触发
- 串行执行（同时只有一个部署，不会并发冲突）

### 部署内容
1. **后端**：SSH 进服务器 → git pull → Docker Compose restart zhilian-api
2. **前端**：rsync 编译后的 `dist/` → `/var/www/html/zhilian-os/` → nginx reload

## 服务器结构

```
/opt/zhilian-os/          ← 主代码目录（Docker 模式）
├── .env.prod             ← 生产环境变量（不进 git）
├── docker-compose.prod.yml
└── apps/
    ├── api-gateway/      ← FastAPI 后端
    └── web/              ← React 前端

/var/www/html/zhilian-os/ ← 前端静态文件（由 GitHub Actions rsync）
/usr/local/bin/zhilian-os-sync.sh ← 备用定时同步（每日 02:00）
```

## 手动部署（不走 GitHub Actions）

```bash
# 在服务器上执行：
bash /usr/local/bin/zhilian-os-sync.sh

# 或者完整重部署：
cd /opt/zhilian-os
git pull origin main
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --no-deps --build zhilian-api
```

## 紧急修复（首次迁移）

如果服务器还在跑旧版 supervisor/gunicorn，执行：

```bash
# 在服务器上执行（一键修复）：
bash /opt/zhilian-os/scripts/server-setup/emergency-fix.sh
# OR
curl -sL https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/scripts/server-setup/emergency-fix.sh | bash
```

## 当前状态

| 组件 | 期望状态 | 检查命令 |
|------|----------|---------|
| Docker API | 运行中 | `docker ps --filter name=zhilian-api` |
| Nginx | 运行中 | `systemctl status nginx` |
| API 健康 | 200 OK | `curl http://127.0.0.1:8000/api/v1/health` |
| 前端 | 正常访问 | `curl https://zlsjos.cn/` |
| Supervisor | 已停止旧进程 | `supervisorctl status tunxiang-os` |
