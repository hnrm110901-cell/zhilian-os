#!/usr/bin/env python3
"""
更新UserRole枚举类型
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from src.core.database import get_db_session


async def migrate_user_role_enum():
    """更新UserRole枚举类型"""
    print("开始更新UserRole枚举类型...")

    async with get_db_session() as session:
        # Execute each statement separately
        await session.execute(text("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(50)"))
        print("✓ 步骤1: 将role列转换为VARCHAR")

        # Update existing role values to lowercase and map old roles to new ones
        await session.execute(text("UPDATE users SET role = LOWER(role)"))
        await session.execute(text("""
            UPDATE users SET role = CASE
                WHEN role = 'manager' THEN 'store_manager'
                WHEN role = 'staff' THEN 'waiter'
                ELSE role
            END
        """))
        print("✓ 步骤2: 映射旧角色到新角色 (manager→store_manager, staff→waiter)")

        await session.execute(text("DROP TYPE IF EXISTS userrole"))
        print("✓ 步骤3: 删除旧的枚举类型")

        await session.execute(text("""
            CREATE TYPE userrole AS ENUM (
                'admin',
                'store_manager',
                'assistant_manager',
                'floor_manager',
                'customer_manager',
                'team_leader',
                'waiter',
                'head_chef',
                'station_manager',
                'chef',
                'warehouse_manager',
                'finance',
                'procurement'
            )
        """))
        print("✓ 步骤4: 创建新的枚举类型")

        await session.execute(text("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole"))
        print("✓ 步骤5: 将role列转换回枚举类型")

        await session.commit()
        print("\n✓ UserRole枚举类型更新成功")


if __name__ == "__main__":
    asyncio.run(migrate_user_role_enum())
