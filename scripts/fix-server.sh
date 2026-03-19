#!/bin/bash
# ═══════════════════════════════════════════════════
# 屯象OS 服务器修复脚本
# 用法: ssh root@42.194.229.21 后逐步执行
# ═══════════════════════════════════════════════════
set -e

# ═══ 第一步：诊断当前状态 ═══════════════════════════
echo "=== 检查 Docker 容器状态 ==="
docker ps -a --filter "name=zhilian" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== 检查 API 容器日志（最近 30 行）==="
docker logs zhilian-api --tail 30 2>&1 || echo "容器不存在"

echo ""
echo "=== 检查 Nginx 配置中 /api/ 代理 ==="
grep -A3 "location /api" /etc/nginx/sites-enabled/* /etc/nginx/conf.d/* 2>/dev/null || echo "未找到 /api/ 代理配置"

echo ""
echo "=== 检查端口占用 ==="
ss -tlnp | grep -E '8000|5432|6379'

# ═══ 第二步：拉取最新代码 ═══════════════════════════
echo ""
echo "=== 拉取最新代码 ==="
cd /opt/zhilian-os/prod
git fetch origin main
git reset --hard origin/main
echo "当前 HEAD: $(git log -1 --oneline)"

# ═══ 第三步：启动基础服务 ═══════════════════════════
echo ""
echo "=== 启动 PostgreSQL + Redis + Qdrant ==="
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d postgres redis qdrant

echo "等待 PostgreSQL..."
for i in $(seq 1 15); do
  docker exec zhilian-postgres pg_isready -U zhilian >/dev/null 2>&1 && echo "✓ PostgreSQL 就绪" && break
  echo "  等待中... ($i/15)"
  sleep 2
done

echo "等待 Redis..."
for i in $(seq 1 10); do
  docker exec zhilian-redis-master redis-cli ping 2>/dev/null | grep -q PONG && echo "✓ Redis 就绪" && break
  echo "  等待中... ($i/10)"
  sleep 2
done

# ═══ 第四步：启动 API 容器 ═══════════════════════════
echo ""
echo "=== 构建并启动 API 容器 ==="
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build api-gateway

echo "等待 API 健康检查..."
HEALTHY=0
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
    echo "✓ API 健康！(${i}×3s)"
    HEALTHY=1
    break
  fi
  echo "  等待中... ($i/20)"
  sleep 3
done

if [ "$HEALTHY" = "0" ]; then
  echo "✗ API 启动失败，查看日志："
  docker logs zhilian-api --tail 80
  exit 1
fi

# ═══ 第五步：数据库迁移 + 种子数据 ═══════════════════
echo ""
echo "=== 执行数据库迁移 ==="
docker exec zhilian-api python -m alembic -c /app/alembic.ini upgrade head \
  && echo "✓ 迁移完成" \
  || echo "⚠ 迁移有警告"

echo ""
echo "=== 初始化种子数据（管理员 + 三家商户）==="
docker exec zhilian-api python scripts/seed_admin.py

# ═══ 第六步：启动 Celery =══════════════════════════
echo ""
echo "=== 启动 Celery Worker + Beat ==="
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d celery-worker celery-beat

# ═══ 第七步：确认 Nginx /api/ 代理 ═══════════════════
echo ""
echo "=== 检查 Nginx /api/ 代理 ==="
if ! grep -rq "proxy_pass.*8000" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null; then
  echo "⚠ Nginx 缺少 /api/ 代理！请手动添加以下内容到 zlsjos.cn 的 server block："
  echo ""
  echo '    location /api/ {'
  echo '        proxy_pass         http://127.0.0.1:8000;'
  echo '        proxy_set_header   Host $host;'
  echo '        proxy_set_header   X-Real-IP $remote_addr;'
  echo '        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;'
  echo '        proxy_set_header   X-Forwarded-Proto $scheme;'
  echo '        proxy_set_header   X-Tenant-ID platform_admin;'
  echo '        proxy_read_timeout 300s;'
  echo '    }'
  echo ""
  echo "添加后执行: nginx -t && nginx -s reload"
else
  echo "✓ Nginx /api/ 代理已配置"
  nginx -t && nginx -s reload && echo "✓ Nginx 重载成功"
fi

# ═══ 第八步：验证登录 ═══════════════════════════════
echo ""
echo "========== 最终验证 =========="

echo "--- 管理员登录 ---"
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -m json.tool 2>/dev/null | head -10

echo "--- 尝在一起·店长登录 ---"
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"czyz_manager","password":"czyz123"}' | python3 -m json.tool 2>/dev/null | head -10

echo "--- 最黔线·店长登录 ---"
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zqx_manager","password":"zqx12345"}' | python3 -m json.tool 2>/dev/null | head -10

echo ""
echo "--- HTTPS 域名验证 ---"
curl -sk -o /dev/null -w "zlsjos.cn/api/v1/health => %{http_code}\n" https://zlsjos.cn/api/v1/health

echo ""
docker ps --filter "name=zhilian" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "══════════════════════════════════════"
echo "  账号汇总："
echo "  企业后台: https://zlsjos.cn/login"
echo "    admin / admin123"
echo "  尝在一起: https://changzaiyiqi.zlsjos.cn/login"
echo "    czyz_manager / czyz123"
echo "  最黔线:   https://zuiqianxian.zlsjos.cn/login"
echo "    zqx_manager / zqx12345"
echo "══════════════════════════════════════"
