#!/usr/bin/env python3
"""
Database migration script for integration tables
创建外部系统集成相关表
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from src.core.database import get_engine


async def migrate():
    """执行数据库迁移"""
    engine = get_engine()

    async with engine.begin() as conn:
        print("开始创建集成相关表...")

        # 创建枚举类型
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE integration_type AS ENUM ('pos', 'supplier', 'member', 'payment', 'delivery', 'erp');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ 创建 integration_type 枚举")

        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE integration_status AS ENUM ('active', 'inactive', 'error', 'testing');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ 创建 integration_status 枚举")

        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE sync_status AS ENUM ('pending', 'syncing', 'success', 'failed', 'partial');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ 创建 sync_status 枚举")

        # 创建 external_systems 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS external_systems (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                type integration_type NOT NULL,
                provider VARCHAR(100),
                version VARCHAR(50),
                status integration_status DEFAULT 'inactive',
                store_id VARCHAR(50),
                api_endpoint VARCHAR(500),
                api_key VARCHAR(500),
                api_secret VARCHAR(500),
                webhook_url VARCHAR(500),
                config JSONB,
                sync_enabled BOOLEAN DEFAULT true,
                sync_interval INTEGER DEFAULT 300,
                last_sync_at TIMESTAMP,
                last_sync_status sync_status,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(50)
            );
        """))
        print("✓ 创建 external_systems 表")

        # 创建 sync_logs 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                system_id UUID NOT NULL,
                sync_type VARCHAR(50) NOT NULL,
                status sync_status NOT NULL,
                records_total INTEGER DEFAULT 0,
                records_success INTEGER DEFAULT 0,
                records_failed INTEGER DEFAULT 0,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                duration_seconds FLOAT,
                error_message TEXT,
                error_details JSONB,
                request_data JSONB,
                response_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        print("✓ 创建 sync_logs 表")

        # 创建 pos_transactions 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                system_id UUID NOT NULL,
                store_id VARCHAR(50) NOT NULL,
                pos_transaction_id VARCHAR(100) NOT NULL UNIQUE,
                pos_order_number VARCHAR(100),
                transaction_type VARCHAR(50),
                subtotal FLOAT DEFAULT 0,
                tax FLOAT DEFAULT 0,
                discount FLOAT DEFAULT 0,
                total FLOAT DEFAULT 0,
                payment_method VARCHAR(50),
                items JSONB,
                customer_info JSONB,
                sync_status sync_status DEFAULT 'pending',
                synced_at TIMESTAMP,
                transaction_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data JSONB
            );
        """))
        print("✓ 创建 pos_transactions 表")

        # 创建 supplier_orders 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS supplier_orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                system_id UUID NOT NULL,
                store_id VARCHAR(50) NOT NULL,
                order_number VARCHAR(100) NOT NULL UNIQUE,
                supplier_id VARCHAR(100),
                supplier_name VARCHAR(200),
                order_type VARCHAR(50),
                status VARCHAR(50),
                subtotal FLOAT DEFAULT 0,
                tax FLOAT DEFAULT 0,
                shipping FLOAT DEFAULT 0,
                total FLOAT DEFAULT 0,
                items JSONB,
                delivery_info JSONB,
                order_date TIMESTAMP NOT NULL,
                expected_delivery TIMESTAMP,
                actual_delivery TIMESTAMP,
                sync_status sync_status DEFAULT 'pending',
                synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data JSONB
            );
        """))
        print("✓ 创建 supplier_orders 表")

        # 创建 member_syncs 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS member_syncs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                system_id UUID NOT NULL,
                member_id VARCHAR(100) NOT NULL,
                external_member_id VARCHAR(100),
                phone VARCHAR(20),
                name VARCHAR(100),
                email VARCHAR(200),
                level VARCHAR(50),
                points INTEGER DEFAULT 0,
                balance FLOAT DEFAULT 0,
                sync_status sync_status DEFAULT 'pending',
                synced_at TIMESTAMP,
                last_activity TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data JSONB,
                UNIQUE(system_id, member_id)
            );
        """))
        print("✓ 创建 member_syncs 表")

        # 创建索引
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_external_systems_type ON external_systems(type);
            CREATE INDEX IF NOT EXISTS idx_external_systems_store ON external_systems(store_id);
            CREATE INDEX IF NOT EXISTS idx_sync_logs_system ON sync_logs(system_id);
            CREATE INDEX IF NOT EXISTS idx_pos_transactions_store ON pos_transactions(store_id);
            CREATE INDEX IF NOT EXISTS idx_pos_transactions_time ON pos_transactions(transaction_time);
            CREATE INDEX IF NOT EXISTS idx_supplier_orders_store ON supplier_orders(store_id);
            CREATE INDEX IF NOT EXISTS idx_supplier_orders_date ON supplier_orders(order_date);
            CREATE INDEX IF NOT EXISTS idx_member_syncs_system ON member_syncs(system_id);
            CREATE INDEX IF NOT EXISTS idx_member_syncs_phone ON member_syncs(phone);
        """))
        print("✓ 创建索引")

        print("\n✅ 数据库迁移完成!")


if __name__ == "__main__":
    asyncio.run(migrate())