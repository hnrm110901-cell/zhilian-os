#!/bin/bash
# ================================================================
# 屯象OS — 服务器同步脚本更新工具
# 在服务器上运行此脚本，将同步方式从旧版 supervisor/gunicorn
# 切换为 Docker Compose（/opt/zhilian-os）
#
# 用法（在服务器 root 账户下执行）：
#   bash update-sync-script.sh
# ================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "================================================================"
echo " 屯象OS — 服务器同步脚本迁移 (supervisor → Docker)"
echo "================================================================"
echo ""

# ── Step 1: 停止旧 supervisor 进程 ────────────────────────────────
log "Step 1: 停止旧 supervisor 进程 (tunxiang-os)"
supervisorctl stop tunxiang-os 2>/dev/null && warn "已停止 tunxiang-os" || warn "tunxiang-os 未运行或不存在"

# 禁用自动启动（防止重启）
SUPERVISOR_CONF=""
for f in /etc/supervisor/conf.d/tunxiang-os.conf \
          /etc/supervisor/conf.d/zhilian-os.conf \
          /etc/supervisor.d/tunxiang-os.ini; do
  [ -f "$f" ] && SUPERVISOR_CONF="$f" && break
done

if [ -n "$SUPERVISOR_CONF" ]; then
  sed -i 's/^autostart=true/autostart=false/' "$SUPERVISOR_CONF"
  supervisorctl reread 2>/dev/null || true
  supervisorctl update 2>/dev/null || true
  log "已禁用 supervisor 自动启动: $SUPERVISOR_CONF"
else
  warn "未找到 supervisor 配置文件，跳过"
fi

# 强制释放端口 8000（如果 gunicorn 还占用）
PIDS=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  warn "端口 8000 被占用（PID: $PIDS），强制终止"
  kill -9 $PIDS 2>/dev/null || true
  sleep 2
fi

# ── Step 2: 确保 /opt/zhilian-os 目录存在并已克隆代码 ───────────
log "Step 2: 准备 /opt/zhilian-os 目录"

if [ ! -d "/opt/zhilian-os/.git" ]; then
  warn "/opt/zhilian-os 不是 git 仓库，正在克隆..."
  rm -rf /opt/zhilian-os
  git clone https://github.com/hnrm110901-cell/zhilian-os.git /opt/zhilian-os
  log "克隆完成"
else
  log "/opt/zhilian-os 已存在，拉取最新代码"
  cd /opt/zhilian-os
  git fetch origin main
  git reset --hard origin/main
  log "代码已更新: $(git log -1 --oneline)"
fi

# ── Step 3: 检查 .env.prod ──────────────────────────────────────
log "Step 3: 检查生产环境配置"
if [ ! -f "/opt/zhilian-os/.env.prod" ]; then
  err ".env.prod 不存在！请先创建 /opt/zhilian-os/.env.prod（参见文档）"
fi
log ".env.prod 存在 ✓"

# ── Step 4: 更新同步脚本 ────────────────────────────────────────
log "Step 4: 更新 /usr/local/bin/zhilian-os-sync.sh"

cat > /usr/local/bin/zhilian-os-sync.sh << 'SYNC_SCRIPT'
#!/bin/bash
# 屯象OS 自动同步脚本 v2.0
# 从 GitHub 拉取最新代码并用 Docker Compose 重启服务
# Cron: 0 2 * * * /usr/local/bin/zhilian-os-sync.sh

set -e
LOG=/var/log/zhilian-os-sync.log
APP_DIR=/opt/zhilian-os

echo "================================================" >> $LOG
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始同步" >> $LOG

# 1. 拉取代码
cd $APP_DIR
git fetch origin main >> $LOG 2>&1
git reset --hard origin/main >> $LOG 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Git: $(git log -1 --oneline)" >> $LOG

# 2. 停止旧 supervisor 进程（防止抢占端口）
supervisorctl stop tunxiang-os >> $LOG 2>&1 || true

# 3. 启动 Docker 服务
docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  up -d --no-deps --build zhilian-api zhilian-web >> $LOG 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 同步完成" >> $LOG
echo "================================================" >> $LOG
SYNC_SCRIPT

chmod +x /usr/local/bin/zhilian-os-sync.sh
log "同步脚本已更新 ✓"

# ── Step 5: 更新 cron job ───────────────────────────────────────
log "Step 5: 更新 cron job"
# 删除旧的 cron 条目，添加新的
(crontab -l 2>/dev/null | grep -v "zhilian-os-sync"; echo "0 2 * * * /usr/local/bin/zhilian-os-sync.sh") | crontab -
log "Cron 已更新: 每日 02:00 自动同步"

# ── Step 6: 配置 nginx 前端路径 ─────────────────────────────────
log "Step 6: 确保 nginx 前端目录存在"
mkdir -p /var/www/html/zhilian-os
log "前端目录 /var/www/html/zhilian-os ✓"

# ── Step 7: 启动 Docker 服务 ────────────────────────────────────
log "Step 7: 启动 Docker Compose 服务"
cd /opt/zhilian-os
docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  up -d --no-deps zhilian-api

# 等待 API 启动
log "等待 API 启动..."
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
    log "API 已就绪 (${i}*3s)"
    break
  fi
  echo "  等待中... $i/20"
  sleep 3
done

# ── 最终状态 ────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " 迁移完成！最终状态："
echo "================================================================"
docker ps --filter "name=zhilian" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "API 健康检查:"
curl -sf http://127.0.0.1:8000/api/v1/health | python3 -m json.tool 2>/dev/null || echo "（API 尚未完全启动，请稍后检查）"
echo ""
log "同步脚本已迁移至 Docker 模式"
log "下次推送到 GitHub main 分支后，自动部署将通过 GitHub Actions 触发"
echo ""
echo "手动触发同步："
echo "  bash /usr/local/bin/zhilian-os-sync.sh"
echo ""
echo "查看同步日志："
echo "  tail -f /var/log/zhilian-os-sync.log"
