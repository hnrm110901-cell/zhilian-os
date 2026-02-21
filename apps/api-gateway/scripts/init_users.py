"""
Initialize database with test users
Run this script to create test users for development
"""
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.models.user import User, UserRole
from src.core.security import get_password_hash
from src.core.config import settings


async def init_test_users():
    """Create test users in the database"""

    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=True,
    )

    # Create session
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        # Check if users already exist
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.username == "admin"))
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print("Test users already exist!")
            return

        # Create admin user
        admin = User(
            id=uuid.uuid4(),
            username="admin",
            email="admin@zhilian.com",
            hashed_password=get_password_hash("admin123"),
            full_name="系统管理员",
            role=UserRole.ADMIN,
            is_active=True,
        )

        # Create manager user
        manager = User(
            id=uuid.uuid4(),
            username="manager",
            email="manager@zhilian.com",
            hashed_password=get_password_hash("manager123"),
            full_name="店长",
            role=UserRole.STORE_MANAGER,
            store_id="STORE001",
            is_active=True,
        )

        # Create staff user
        staff = User(
            id=uuid.uuid4(),
            username="staff",
            email="staff@zhilian.com",
            hashed_password=get_password_hash("staff123"),
            full_name="员工",
            role=UserRole.STAFF,
            store_id="STORE001",
            is_active=True,
        )

        session.add_all([admin, manager, staff])
        await session.commit()

        print("✅ Test users created successfully!")
        print("\nLogin credentials:")
        print("  Admin:   admin / admin123")
        print("  Manager: manager / manager123")
        print("  Staff:   staff / staff123")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_test_users())
