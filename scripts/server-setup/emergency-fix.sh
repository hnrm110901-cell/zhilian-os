#!/bin/bash
# ================================================================
# 屯象OS — 服务器紧急修复脚本 v1.0
# 解决问题：旧 supervisor/gunicorn 占用端口 8000，导致
#           Docker 容器无法启动，API 返回 404
#
# 在服务器上运行（复制粘贴到终端）：
#   curl -sL https://raw.githubusercontent.com/hnrm110901-cell/zhilian-os/main/scripts/server-setup/emergency-fix.sh | bash
#   OR
#   bash emergency-fix.sh
# ================================================================

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step() { echo -e "\n${GREEN}══ Step $1: $2 ══${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       屯象OS — 服务器紧急修复 (Supervisor → Docker)       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: 停止占用端口的旧进程 ────────────────────────────────
step 1 "停止 supervisor 管理的旧进程"

# 停止 tunxiang-os supervisor 进程
supervisorctl stop tunxiang-os 2>/dev/null && warn "已停止 tunxiang-os" || warn "tunxiang-os 未运行"

# 禁用 autostart（下次重启后不再自动拉起）
for CONF_FILE in \
    /etc/supervisor/conf.d/tunxiang-os.conf \
    /etc/supervisor/conf.d/zhilian-os.conf \
    /etc/supervisord.d/tunxiang-os.ini; do
  if [ -f "$CONF_FILE" ]; then
    sed -i 's/^autostart=true/autostart=false/g' "$CONF_FILE"
    log "禁用 autostart: $CONF_FILE"
  fi
done

supervisorctl reread 2>/dev/null || true
supervisorctl update 2>/dev/null || true

# 强制杀掉所有还在跑的 gunicorn/uvicorn 进程
PIDS=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  warn "强制终止占用端口 8000 的进程: $PIDS"
  kill -9 $PIDS 2>/dev/null || true
  sleep 2
fi

# 验证端口已释放
if lsof -ti:8000 > /dev/null 2>&1; then
  err "端口 8000 仍被占用，请手动检查: lsof -ti:8000"
fi
log "端口 8000 已释放"

# ── Step 2: 确保 /opt/zhilian-os 存在并是最新代码 ───────────────
step 2 "更新代码仓库"

if [ ! -d "/opt/zhilian-os/.git" ]; then
  warn "初次克隆到 /opt/zhilian-os..."
  git clone https://github.com/hnrm110901-cell/zhilian-os.git /opt/zhilian-os
else
  cd /opt/zhilian-os
  git fetch origin main
  git reset --hard origin/main
  log "代码已更新: $(git log -1 --oneline)"
fi

# ── Step 3: 检查 .env.prod ──────────────────────────────────────
step 3 "验证环境配置"

if [ ! -f "/opt/zhilian-os/.env.prod" ]; then
  warn "⚠ /opt/zhilian-os/.env.prod 不存在！"
  warn "  正在从 /var/www/zhilian-os/.env 复制（如果存在）..."

  if [ -f "/var/www/zhilian-os/apps/api-gateway/.env" ]; then
    cp "/var/www/zhilian-os/apps/api-gateway/.env" /opt/zhilian-os/.env.prod
    log "已复制旧 .env 到 .env.prod（请检查变量名是否匹配）"
  elif [ -f "/var/www/zhilian-os/.env" ]; then
    cp "/var/www/zhilian-os/.env" /opt/zhilian-os/.env.prod
    log "已复制旧 .env 到 .env.prod"
  else
    err ".env.prod 不存在，且找不到旧版 .env！请手动创建 /opt/zhilian-os/.env.prod"
  fi
fi
log ".env.prod ✓"

# ── Step 4: 启动 Docker API 容器 ─────────────────────────────────
step 4 "启动 Docker API 容器"

cd /opt/zhilian-os

# 先把正在运行的旧容器干净地停掉
docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  stop zhilian-api 2>/dev/null || true

docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  up -d --no-deps zhilian-api

log "zhilian-api 容器已启动"

# ── Step 5: 等待 API 健康 ────────────────────────────────────────
step 5 "等待 API 就绪"

READY=0
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
    log "API 已就绪！(等待了 $((i*3))s)"
    READY=1
    break
  fi
  printf "  等待中... %d/30\r" $i
  sleep 3
done

if [ "$READY" = "0" ]; then
  warn "API 30 次健康检查未通过，查看日志:"
  docker logs --tail=30 zhilian-api
fi

# ── Step 6: 更新同步脚本 ────────────────────────────────────────
step 6 "更新 cron 同步脚本"

cat > /usr/local/bin/zhilian-os-sync.sh << 'SYNC'
#!/bin/bash
# 屯象OS 自动同步脚本 v2.0 — Docker 模式
LOG=/var/log/zhilian-os-sync.log
APP_DIR=/opt/zhilian-os

echo "======== $(date '+%Y-%m-%d %H:%M:%S') ========" >> $LOG
cd $APP_DIR && git fetch origin main >> $LOG 2>&1
git reset --hard origin/main >> $LOG 2>&1
echo "Git: $(git log -1 --oneline)" >> $LOG

# 停止旧 supervisor 进程（以防自动重启）
supervisorctl stop tunxiang-os >> $LOG 2>&1 || true

# 重启 Docker API
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --no-deps zhilian-api >> $LOG 2>&1

echo "同步完成" >> $LOG
SYNC

chmod +x /usr/local/bin/zhilian-os-sync.sh

# 更新 cron job
(crontab -l 2>/dev/null | grep -v "zhilian-os-sync\|tunxiang\|zhilian"; \
 echo "0 2 * * * /usr/local/bin/zhilian-os-sync.sh") | crontab -

log "同步脚本已更新（每日 02:00）"

# ── 最终状态汇报 ────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    最终状态汇报                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Docker 容器:"
docker ps --filter "name=zhilian" --format "  {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  (无运行中的容器)"
echo ""
echo "端口 8000:"
lsof -i:8000 2>/dev/null | head -5 || ss -tlnp | grep 8000 || echo "  (端口未监听)"
echo ""
echo "API 健康检查:"
curl -sf http://127.0.0.1:8000/api/v1/health 2>/dev/null | python3 -m json.tool || \
  echo "  ⚠ API 未就绪（可能正在启动，请稍后重试）"
echo ""
echo "Nginx 测试:"
nginx -t 2>&1 | tail -2
echo ""
log "修复完成！"
echo ""
echo "常用命令:"
echo "  查看 API 日志:  docker logs -f zhilian-api"
echo "  手动同步:       bash /usr/local/bin/zhilian-os-sync.sh"
echo "  查看同步日志:   tail -f /var/log/zhilian-os-sync.log"
