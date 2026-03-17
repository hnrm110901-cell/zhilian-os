#!/usr/bin/env bash
# =============================================================================
# 屯象OS — 生产服务器首次初始化脚本
# 适用于：42.194.229.21（腾讯云 CVM）
# 执行方式：ssh root@42.194.229.21 'bash -s' < scripts/server-setup/bootstrap.sh
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/hnrm110901-cell/zhilian-os.git"
APP_BASE="/opt/zhilian-os"
APP_DIR="$APP_BASE/prod"
STAGING_DIR="$APP_BASE/staging"
NGINX_WEB_ROOT="/var/www/tunxiang"
DEPLOY_KEY_PATH="/root/.ssh/id_ed25519_tunxiang"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. 基础依赖 ─────────────────────────────────────────────────────────────
info "Step 1/9: Installing system dependencies"
apt-get update -qq
BASE_PACKAGES=(
  git curl wget rsync nginx
  docker.io
  ca-certificates gnupg
)

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  BASE_PACKAGES+=(docker-compose-plugin)
fi

apt-get install -y -qq "${BASE_PACKAGES[@]}"

systemctl enable --now docker
info "Docker version: $(docker --version)"

# ── 2. 克隆或更新仓库 ────────────────────────────────────────────────────────
info "Step 2/9: Clone / update repository"
mkdir -p "$APP_BASE"
if [ -d "$APP_DIR/.git" ]; then
  warn "Repo already exists at $APP_DIR — pulling latest"
  git -C "$APP_DIR" fetch origin main
  git -C "$APP_DIR" reset --hard origin/main
else
  git clone "$REPO_URL" "$APP_DIR"
fi
info "Git HEAD: $(git -C $APP_DIR log -1 --oneline)"

# ── 3. 检查 .env.prod 存在 ───────────────────────────────────────────────────
info "Step 3/9: Checking environment files"
if [ ! -f "$APP_DIR/.env.prod" ]; then
  error ".env.prod missing! Create it at $APP_DIR/.env.prod with the required variables.
Required vars:
  API_DATABASE_URL=postgresql+asyncpg://zhilian:<PASS>@postgres:5432/zhilian_os
  POSTGRES_PASSWORD=<PASS>
  REDIS_PASSWORD=<PASS>
  JWT_SECRET_KEY=<32+ char random>
  SECRET_KEY=<32+ char random>"
fi

if [ ! -f "$APP_DIR/apps/api-gateway/.env.production" ]; then
  warn "apps/api-gateway/.env.production missing! Create it for app-specific env vars.
Typically includes:
  ANTHROPIC_API_KEY=...
  PINZHI_API_KEY=...
  PINZHI_API_SECRET=...
  AOQIWEI_APP_ID=...
  AOQIWEI_APP_SECRET=..."
fi
info "Environment files OK"

# ── 4. 创建 Nginx web root ───────────────────────────────────────────────────
info "Step 4/9: Creating nginx web root"
mkdir -p "$NGINX_WEB_ROOT"
chown -R www-data:www-data "$NGINX_WEB_ROOT" 2>/dev/null || true
info "Web root: $NGINX_WEB_ROOT"

# ── 5. 配置 Nginx（如未配置） ────────────────────────────────────────────────
info "Step 5/9: Configuring nginx"
NGINX_CONF="/etc/nginx/conf.d/tunxiang.conf"
if [ ! -f "$NGINX_CONF" ]; then
  cat > "$NGINX_CONF" << 'EOF'
server {
    listen 80;
    server_name zlsjos.cn 42.194.229.21;

    # 前端静态文件
    root /var/www/tunxiang;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF
  nginx -t && systemctl reload nginx
  info "Nginx config written and reloaded"
else
  info "Nginx config already exists, skipping"
fi

# ── 6. 启动基础服务（postgres / redis / qdrant） ─────────────────────────────
info "Step 6/9: Starting infrastructure containers"
cd "$APP_DIR"
docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  up -d postgres redis redis-replica redis-sentinel-1 redis-sentinel-2 redis-sentinel-3 qdrant neo4j
info "Waiting 15s for DB to initialise..."
sleep 15

# ── 7. 启动 API 容器 ─────────────────────────────────────────────────────────
info "Step 7/9: Building & starting API container"
docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  up -d --build api-gateway

info "Waiting for API health..."
HEALTHY=0
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
    info "✓ API healthy after ${i}×3s"
    HEALTHY=1
    break
  fi
  echo "  waiting... ($i/20)"
  sleep 3
done
[ "$HEALTHY" = "1" ] || error "API failed to start. Check: docker logs zhilian-api"

# ── 8. 运行数据库迁移 ─────────────────────────────────────────────────────────
info "Step 8/9: Running Alembic migrations"
docker exec zhilian-api \
  python -m alembic -c /app/alembic.ini upgrade head \
  && info "✓ Migrations applied" \
  || warn "Migration issue — check docker logs zhilian-api"

# ── 9. 启动 Celery ────────────────────────────────────────────────────────────
info "Step 9/9: Starting Celery worker & beat"
docker compose \
  --env-file .env.prod \
  -f docker-compose.prod.yml \
  up -d --build celery-worker celery-beat

# ── 最终状态 ──────────────────────────────────────────────────────────────────
echo ""
info "=== Bootstrap complete ==="
docker ps --filter "name=zhilian" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
info "API health: $(curl -sf http://127.0.0.1:8000/api/v1/health || echo 'FAILED')"
echo ""
warn "Next steps:"
warn "  1. Set GitHub secret TUNXIANGOS = contents of $DEPLOY_KEY_PATH (private key)"
warn "     Repo settings → Secrets and variables → Actions → New repository secret"
warn "  2. Add public key to /root/.ssh/authorized_keys on this server"
warn "  3. Push any commit to main branch → GitHub Actions will deploy automatically"
