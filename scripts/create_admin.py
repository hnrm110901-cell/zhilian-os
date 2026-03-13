#!/usr/bin/env python3
"""
scripts/create_admin.py — 初始化超级管理员账户

使用场景：
  - 首次部署时：数据库里没有任何用户，无法通过后台创建
  - 密码重置：admin 密码忘记或被污染

用法（在 apps/api-gateway 目录下执行）：
  python ../../scripts/create_admin.py

可选环境变量覆盖：
  ADMIN_USERNAME  默认 "admin"
  ADMIN_PASSWORD  默认 "TunXiang@2024!"（生产必须改掉）
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# 把 apps/api-gateway/src 加入 sys.path
API_ROOT = Path(__file__).parent.parent / "apps" / "api-gateway" / "src"
sys.path.insert(0, str(API_ROOT))

from core.database import AsyncSessionLocal
from core.security import get_password_hash
from models.user import User, UserRole
from sqlalchemy import select


ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "TunXiang@2024!")


async def create_admin() -> None:
    async with AsyncSessionLocal() as session:
        # 检查是否已存在
        result = await session.execute(
            select(User).where(User.username == ADMIN_USERNAME)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[INFO] 用户 '{ADMIN_USERNAME}' 已存在（id={existing.id}），跳过创建。")
            print(f"[INFO] 当前角色：{existing.role}")
            return

        hashed = get_password_hash(ADMIN_PASSWORD)
        admin = User(
            id=str(uuid.uuid4()),
            username=ADMIN_USERNAME,
            hashed_password=hashed,
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        print(f"[OK] 管理员账户已创建：")
        print(f"     用户名：{ADMIN_USERNAME}")
        print(f"     密码：  {ADMIN_PASSWORD}")
        print(f"     角色：  {admin.role}")
        print(f"     ID：    {admin.id}")
        print()
        print("[!] 生产环境请立即修改密码！")
        print("[!] 企业微信登录配置好后可废弃密码登录。")


if __name__ == "__main__":
    asyncio.run(create_admin())
