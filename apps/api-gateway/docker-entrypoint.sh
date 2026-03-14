#!/bin/bash
set -e

echo "=== 屯象OS API Gateway 启动 ==="

echo "[1/2] 初始化数据库表结构..."
python3 -c "
import asyncio, sys
sys.path.insert(0, '/app')

async def run():
    from src.core.database import init_db
    await init_db(retries=10, delay=3.0)

asyncio.run(run())
" && echo "[1/2] ✓ 数据库初始化完成" || echo "[1/2] ⚠ 数据库初始化失败（继续启动，将在 startup_event 重试）"

echo "[2/2] 启动服务..."
exec "$@"
