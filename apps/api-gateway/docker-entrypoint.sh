#!/bin/bash
set -e

echo "=== 屯象OS API Gateway 启动 ==="

echo "[1/4] 等待 PostgreSQL 就绪..."
for i in $(seq 1 30); do
  python3 -c "
import sys
sys.path.insert(0, '/app')
from src.core.config import settings
url = settings.DATABASE_URL.replace('+asyncpg', '').replace('postgresql+psycopg2', 'postgresql')
import psycopg2
try:
    conn = psycopg2.connect(url, connect_timeout=3)
    conn.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" && echo "[1/4] ✓ PostgreSQL 就绪" && break
  echo "  等待 PostgreSQL... ($i/30)"
  sleep 2
done

echo "[2/4] 初始化数据库表结构..."
python3 -c "
import asyncio, sys
sys.path.insert(0, '/app')

async def run():
    from src.core.database import init_db
    await init_db(retries=10, delay=3.0)

asyncio.run(run())
" && echo "[2/4] ✓ 数据库初始化完成" || echo "[2/4] ⚠ 数据库初始化失败（将在 startup_event 重试）"

echo "[3/4] 执行 Alembic 数据库迁移..."
python3 -m alembic -c /app/alembic.ini upgrade head \
  && echo "[3/4] ✓ 数据库迁移完成" \
  || echo "[3/4] ⚠ 数据库迁移跳过（可能已是最新）"

echo "[4/4] 确保种子数据存在（管理员 + 演示商户）..."
python3 /app/scripts/seed_admin.py \
  && echo "[4/4] ✓ 种子数据就绪" \
  || echo "[4/4] ⚠ 种子数据初始化跳过（可能已存在）"

echo "=== 启动服务... ==="
exec "$@"
