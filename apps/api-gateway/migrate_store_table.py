#!/usr/bin/env python3
"""
更新Store表结构
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from src.core.database import get_db_session


async def migrate_store_table():
    """更新Store表结构"""
    print("开始更新Store表结构...")

    async with get_db_session() as session:
        # 添加新字段
        migrations = [
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS code VARCHAR(20)",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS city VARCHAR(50)",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS district VARCHAR(50)",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS email VARCHAR(100)",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS region VARCHAR(50)",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS area FLOAT",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS seats INTEGER",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS floors INTEGER DEFAULT 1",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS opening_date VARCHAR(20)",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS business_hours JSON",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS daily_customer_target INTEGER",
            "ALTER TABLE stores ADD COLUMN IF NOT EXISTS labor_cost_ratio_target FLOAT",
            # 修改现有字段类型
            "ALTER TABLE stores ALTER COLUMN monthly_revenue_target TYPE FLOAT USING monthly_revenue_target::FLOAT",
            "ALTER TABLE stores ALTER COLUMN cost_ratio_target TYPE FLOAT USING cost_ratio_target::FLOAT",
            # 添加唯一约束
            "ALTER TABLE stores ADD CONSTRAINT stores_code_unique UNIQUE (code)",
        ]

        for i, migration in enumerate(migrations, 1):
            try:
                await session.execute(text(migration))
                print(f"✓ 步骤{i}: {migration[:60]}...")
            except Exception as e:
                # 如果字段已存在或约束已存在,忽略错误
                if "already exists" in str(e) or "duplicate" in str(e).lower():
                    print(f"⊙ 步骤{i}: 已存在,跳过")
                else:
                    print(f"✗ 步骤{i}: 失败 - {str(e)}")

        await session.commit()
        print("\n✓ Store表结构更新成功")


if __name__ == "__main__":
    asyncio.run(migrate_store_table())
