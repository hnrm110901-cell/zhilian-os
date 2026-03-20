#!/bin/bash
# ============================================================
# 屯象OS 生产部署脚本
#
# 用法:
#   ./scripts/deploy.sh              # 本地构建部署（当前方式）
#   ./scripts/deploy.sh --pull       # 从GHCR拉取镜像部署（推荐）
#   ./scripts/deploy.sh --workers 2  # 指定worker数量
#
# ============================================================
set -euo pipefail

PROD_DIR="/opt/zhilian-os/prod"
WORKERS="${WORKERS:-2}"
MODE="build"  # build 或 pull
API_CONTAINER="zhilian-api"

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --pull)    MODE="pull"; shift ;;
    --build)   MODE="build"; shift ;;
    --workers) WORKERS="$2"; shift 2 ;;
    *)         echo "未知参数: $1"; exit 1 ;;
  esac
done

echo "========================================="
echo "  屯象OS 生产部署"
echo "  模式: $MODE | Workers: $WORKERS"
echo "========================================="

cd "$PROD_DIR"

# ── 1. 拉取代码 ──────────────────────────────────────
echo "[1/6] 拉取最新代码..."
git fetch origin main
git reset --hard origin/main
echo "  HEAD: $(git log -1 --oneline)"

# ── 2. 构建或拉取镜像 ────────────────────────────────
if [ "$MODE" = "pull" ]; then
  echo "[2/6] 从GHCR拉取镜像..."
  REPO="ghcr.io/hnrm110901-cell/zhilian-os/api-gateway"
  docker pull "${REPO}:main"
  export API_IMAGE="${REPO}:main"
else
  echo "[2/6] 本地构建镜像（利用缓存）..."
  docker compose -f docker-compose.prod.yml build api-gateway
fi

# ── 3. 停止旧容器 ────────────────────────────────────
echo "[3/6] 停止旧API容器..."
docker rm -f "$API_CONTAINER" 2>/dev/null || true

# ── 4. 启动新容器 ────────────────────────────────────
echo "[4/6] 启动API容器 (${WORKERS} workers)..."
docker compose -f docker-compose.prod.yml run -d \
  --name "$API_CONTAINER" \
  --service-ports \
  api-gateway \
  bash docker-entrypoint.sh \
  /root/.local/bin/gunicorn -w "$WORKERS" -k uvicorn.workers.UvicornWorker \
  src.main:app --bind 0.0.0.0:8000 --access-logfile - --error-logfile - --timeout 120

# ── 5. 等待健康检查 ──────────────────────────────────
echo "[5/6] 等待API就绪..."
HEALTHY=0
for i in $(seq 1 30); do
  RESP=$(curl -sf http://127.0.0.1:8000/api/v1/ready 2>/dev/null || echo '{}')
  if echo "$RESP" | grep -q '"ready"'; then
    echo "  ✓ API就绪 (${i}x3s)"
    HEALTHY=1
    break
  fi
  echo "  等待... ($i/30)"
  sleep 3
done

if [ "$HEALTHY" = "0" ]; then
  echo "  ✗ API启动失败"
  docker logs "$API_CONTAINER" --tail 30
  exit 1
fi

# ── 6. 清理 + 重启Celery ─────────────────────────────
echo "[6/6] 清理旧镜像 + 重启Celery..."
docker image prune -f
docker compose -f docker-compose.prod.yml up -d --no-deps celery-worker celery-beat 2>/dev/null || true

echo ""
echo "========================================="
echo "  ✓ 部署完成!"
echo "========================================="
docker ps --filter "name=zhilian" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
