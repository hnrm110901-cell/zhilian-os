"""
Database Seed Script
Populates the database with sample data for development and testing
"""
import asyncio
from datetime import datetime, date, time, timedelta
from sqlalchemy import select
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import get_db_session
from src.models import (
    User, Store, Employee, Order, OrderItem, InventoryItem, InventoryTransaction,
    Schedule, Shift, Reservation, KPI, KPIRecord, Supplier, PurchaseOrder
)
from src.models.user import UserRole
from src.models.order import OrderStatus
from src.models.inventory import InventoryStatus, TransactionType
from src.models.reservation import ReservationStatus, ReservationType


async def seed_users():
    """Create sample users"""
    users = [
        User(
            username="admin",
            email="admin@zhilian.com",
            hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVr/1jrPK",  # admin123
            full_name="系统管理员",
            role=UserRole.ADMIN,
            is_active=True,
        ),
        User(
            username="manager",
            email="manager@zhilian.com",
            hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVr/1jrPK",  # manager123
            full_name="门店经理",
            role=UserRole.STORE_MANAGER,
            is_active=True,
            store_id="STORE001",
        ),
        User(
            username="staff",
            email="staff@zhilian.com",
            hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVr/1jrPK",  # staff123
            full_name="服务员",
            role=UserRole.WAITER,
            is_active=True,
            store_id="STORE001",
        ),
    ]
    return users


async def seed_stores():
    """Create sample stores"""
    stores = [
        Store(
            id="STORE001",
            name="智链餐厅-朝阳店",
            address="北京市朝阳区建国路88号",
            phone="010-12345678",
            region="华北",
            is_active=True,
            config={
                "opening_hours": {
                    "monday": "10:00-22:00",
                    "tuesday": "10:00-22:00",
                    "wednesday": "10:00-22:00",
                    "thursday": "10:00-22:00",
                    "friday": "10:00-23:00",
                    "saturday": "09:00-23:00",
                    "sunday": "09:00-22:00",
                },
                "capacity": 200,
                "tables": 40,
            },
            monthly_revenue_target="1000000",  # 100万
            cost_ratio_target="0.35",
        ),
        Store(
            id="STORE002",
            name="智链餐厅-海淀店",
            address="北京市海淀区中关村大街1号",
            phone="010-87654321",
            region="华北",
            is_active=True,
            config={
                "opening_hours": {
                    "monday": "10:00-22:00",
                    "tuesday": "10:00-22:00",
                    "wednesday": "10:00-22:00",
                    "thursday": "10:00-22:00",
                    "friday": "10:00-23:00",
                    "saturday": "09:00-23:00",
                    "sunday": "09:00-22:00",
                },
                "capacity": 180,
                "tables": 35,
            },
            monthly_revenue_target="900000",
            cost_ratio_target="0.35",
        ),
        Store(
            id="STORE003",
            name="智链餐厅-浦东店",
            address="上海市浦东新区陆家嘴环路1000号",
            phone="021-12345678",
            region="华东",
            is_active=True,
            config={
                "opening_hours": {
                    "monday": "10:00-22:00",
                    "tuesday": "10:00-22:00",
                    "wednesday": "10:00-22:00",
                    "thursday": "10:00-22:00",
                    "friday": "10:00-23:00",
                    "saturday": "09:00-23:00",
                    "sunday": "09:00-22:00",
                },
                "capacity": 220,
                "tables": 45,
            },
            monthly_revenue_target="1200000",
            cost_ratio_target="0.35",
        ),
    ]
    return stores


async def seed_employees():
    """Create sample employees"""
    employees = [
        Employee(
            id="EMP001",
            store_id="STORE001",
            name="张三",
            phone="13800138001",
            email="zhangsan@zhilian.com",
            position="waiter",
            skills=["waiter", "cashier"],
            hire_date=date(2024, 1, 1),
            is_active=True,
            performance_score="0.92",
            training_completed=["service_basics", "food_safety"],
        ),
        Employee(
            id="EMP002",
            store_id="STORE001",
            name="李四",
            phone="13800138002",
            email="lisi@zhilian.com",
            position="chef",
            skills=["chef", "kitchen_manager"],
            hire_date=date(2024, 1, 1),
            is_active=True,
            performance_score="0.95",
            training_completed=["cooking_advanced", "food_safety", "kitchen_management"],
        ),
        Employee(
            id="EMP003",
            store_id="STORE001",
            name="王五",
            phone="13800138003",
            email="wangwu@zhilian.com",
            position="waiter",
            skills=["waiter"],
            hire_date=date(2024, 2, 1),
            is_active=True,
            performance_score="0.88",
            training_completed=["service_basics"],
        ),
    ]
    return employees


async def seed_inventory():
    """Create sample inventory items"""
    items = [
        InventoryItem(
            id="INV001",
            store_id="STORE001",
            name="大米",
            category="dry_goods",
            unit="kg",
            current_quantity=150.0,
            min_quantity=50.0,
            max_quantity=300.0,
            unit_cost=500,  # 5元/kg
            status=InventoryStatus.NORMAL,
            supplier_name="粮油批发商",
            supplier_contact="010-88888888",
        ),
        InventoryItem(
            id="INV002",
            store_id="STORE001",
            name="猪肉",
            category="meat",
            unit="kg",
            current_quantity=25.0,
            min_quantity=30.0,
            max_quantity=100.0,
            unit_cost=3500,  # 35元/kg
            status=InventoryStatus.LOW,
            supplier_name="肉类供应商",
            supplier_contact="010-99999999",
        ),
        InventoryItem(
            id="INV003",
            store_id="STORE001",
            name="青菜",
            category="vegetables",
            unit="kg",
            current_quantity=40.0,
            min_quantity=20.0,
            max_quantity=80.0,
            unit_cost=800,  # 8元/kg
            status=InventoryStatus.NORMAL,
            supplier_name="蔬菜批发市场",
            supplier_contact="010-77777777",
        ),
    ]
    return items


async def seed_kpis():
    """Create sample KPI definitions"""
    kpis = [
        KPI(
            id="KPI_REVENUE_001",
            name="总营收",
            category="revenue",
            description="门店月度总营收",
            unit="元",
            target_value=1000000.0,
            warning_threshold=900000.0,
            critical_threshold=800000.0,
            calculation_method="sum",
            is_active="true",
        ),
        KPI(
            id="KPI_COST_001",
            name="成本率",
            category="cost",
            description="成本占营收的比例",
            unit="%",
            target_value=0.35,
            warning_threshold=0.38,
            critical_threshold=0.40,
            calculation_method="ratio",
            is_active="true",
        ),
        KPI(
            id="KPI_CUSTOMER_001",
            name="客户满意度",
            category="customer",
            description="客户满意度评分",
            unit="%",
            target_value=0.90,
            warning_threshold=0.85,
            critical_threshold=0.80,
            calculation_method="average",
            is_active="true",
        ),
    ]
    return kpis


async def seed_suppliers():
    """Create sample suppliers"""
    suppliers = [
        Supplier(
            name="新鲜蔬菜供应商",
            code="SUP001",
            category="food",
            contact_person="王经理",
            phone="010-88888888",
            email="wang@vegetables.com",
            address="北京市大兴区蔬菜批发市场A区101号",
            status="active",
            rating=4.5,
            payment_terms="net30",
            delivery_time=1,
        ),
        Supplier(
            name="优质肉类供应商",
            code="SUP002",
            category="food",
            contact_person="李经理",
            phone="010-99999999",
            email="li@meat.com",
            address="北京市顺义区肉类批发市场B区202号",
            status="active",
            rating=4.8,
            payment_terms="net30",
            delivery_time=2,
        ),
        Supplier(
            name="饮料批发商",
            code="SUP003",
            category="beverage",
            contact_person="张经理",
            phone="010-77777777",
            email="zhang@beverage.com",
            address="北京市朝阳区饮料批发中心C区303号",
            status="active",
            rating=4.3,
            payment_terms="net60",
            delivery_time=3,
        ),
    ]
    return suppliers


async def seed_purchase_orders():
    """Create sample purchase orders"""
    orders = [
        PurchaseOrder(
            order_number="PO-20240218-001",
            supplier_id="SUP001",
            store_id="STORE001",
            status="completed",
            total_amount=50000,  # 500元
            items=[
                {"name": "白菜", "quantity": 50, "unit": "kg", "price": 300},
                {"name": "土豆", "quantity": 30, "unit": "kg", "price": 200},
            ],
            expected_delivery=datetime.now() - timedelta(days=5),
            actual_delivery=datetime.now() - timedelta(days=5),
            created_by="admin",
        ),
        PurchaseOrder(
            order_number="PO-20240218-002",
            supplier_id="SUP002",
            store_id="STORE001",
            status="shipped",
            total_amount=120000,  # 1200元
            items=[
                {"name": "猪肉", "quantity": 20, "unit": "kg", "price": 6000},
            ],
            expected_delivery=datetime.now() + timedelta(days=1),
            created_by="admin",
        ),
        PurchaseOrder(
            order_number="PO-20240218-003",
            supplier_id="SUP003",
            store_id="STORE002",
            status="pending",
            total_amount=80000,  # 800元
            items=[
                {"name": "可乐", "quantity": 100, "unit": "瓶", "price": 500},
                {"name": "雪碧", "quantity": 60, "unit": "瓶", "price": 300},
            ],
            expected_delivery=datetime.now() + timedelta(days=3),
            created_by="manager",
        ),
    ]
    return orders


async def main():
    """Main seed function"""
    print("🌱 Starting database seeding...")

    async with get_db_session() as session:
        try:
            # Seed users
            print("Creating users...")
            users = await seed_users()
            session.add_all(users)
            await session.flush()
            print(f"✓ Created {len(users)} users")

            # Seed stores
            print("Creating stores...")
            stores = await seed_stores()
            session.add_all(stores)
            await session.flush()
            print(f"✓ Created {len(stores)} stores")

            # Seed employees
            print("Creating employees...")
            employees = await seed_employees()
            session.add_all(employees)
            await session.flush()
            print(f"✓ Created {len(employees)} employees")

            # Seed inventory
            print("Creating inventory items...")
            inventory_items = await seed_inventory()
            session.add_all(inventory_items)
            await session.flush()
            print(f"✓ Created {len(inventory_items)} inventory items")

            # Seed KPIs
            print("Creating KPIs...")
            kpis = await seed_kpis()
            session.add_all(kpis)
            await session.flush()
            print(f"✓ Created {len(kpis)} KPIs")

            # Seed suppliers
            print("Creating suppliers...")
            suppliers = await seed_suppliers()
            session.add_all(suppliers)
            await session.flush()
            print(f"✓ Created {len(suppliers)} suppliers")

            # Seed purchase orders
            print("Creating purchase orders...")
            purchase_orders = await seed_purchase_orders()
            session.add_all(purchase_orders)
            await session.flush()
            print(f"✓ Created {len(purchase_orders)} purchase orders")

            # Create sample KPI records
            print("Creating KPI records...")
            today = date.today()
            kpi_records = []
            for kpi in kpis:
                for days_ago in range(30, 0, -1):
                    record_date = today - timedelta(days=days_ago)
                    # Generate sample values
                    if kpi.id == "KPI_REVENUE_001":
                        value = 950000 + (days_ago * 1000)
                    elif kpi.id == "KPI_COST_001":
                        value = 0.36 - (days_ago * 0.0001)
                    else:  # Customer satisfaction
                        value = 0.87 + (days_ago * 0.0005)

                    record = KPIRecord(
                        kpi_id=kpi.id,
                        store_id="STORE001",
                        record_date=record_date,
                        value=value,
                        target_value=kpi.target_value,
                        achievement_rate=value / kpi.target_value if kpi.target_value else 0,
                        status="on_track" if value >= kpi.warning_threshold else "at_risk",
                        trend="stable",
                    )
                    kpi_records.append(record)

            session.add_all(kpi_records)
            await session.flush()
            print(f"✓ Created {len(kpi_records)} KPI records")

            await session.commit()
            print("\n✅ Database seeding completed successfully!")
            print(f"\nSummary:")
            print(f"  - Users: {len(users)}")
            print(f"  - Stores: {len(stores)}")
            print(f"  - Employees: {len(employees)}")
            print(f"  - Inventory Items: {len(inventory_items)}")
            print(f"  - KPIs: {len(kpis)}")
            print(f"  - KPI Records: {len(kpi_records)}")
            print(f"  - Suppliers: {len(suppliers)}")
            print(f"  - Purchase Orders: {len(purchase_orders)}")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error seeding database: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
