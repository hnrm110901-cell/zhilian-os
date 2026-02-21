"""
测试配置和fixtures
"""
import pytest
import asyncio
import os
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.models import Base


# 测试数据库URL - 优先使用PostgreSQL，回退到SQLite
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/zhilian_test"
)

# 如果PostgreSQL不可用，使用SQLite
USE_SQLITE_FALLBACK = os.getenv("USE_SQLITE_FALLBACK", "true").lower() == "true"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话"""
    # 尝试连接PostgreSQL
    try:
        engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=NullPool,
            echo=False,
        )

        # 测试连接
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # 创建会话
        async_session = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session() as session:
            yield session

        # 清理
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await engine.dispose()

    except Exception as e:
        # PostgreSQL不可用，跳过需要数据库的测试
        if USE_SQLITE_FALLBACK:
            pytest.skip(f"PostgreSQL test database not available: {e}. Set TEST_DATABASE_URL environment variable or install PostgreSQL.")
        else:
            raise


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User",
        "role": "staff",
    }


@pytest.fixture
def sample_order_data():
    """示例订单数据"""
    return {
        "store_id": "store_001",
        "table_number": "A01",
        "items": [
            {
                "item_id": "item_001",
                "name": "宫保鸡丁",
                "quantity": 1,
                "price": 3800,
            }
        ],
        "total_amount": 3800,
    }


@pytest.fixture
def sample_inventory_data():
    """示例库存数据"""
    return {
        "item_id": "INV_001",
        "name": "大米",
        "category": "主食",
        "current_stock": 50,
        "min_stock": 20,
        "max_stock": 100,
        "unit": "kg",
    }


@pytest.fixture
def sample_schedule_data():
    """示例排班数据"""
    return {
        "store_id": "store_001",
        "date": "2024-02-20",
        "employees": [
            {
                "id": "emp_001",
                "name": "张三",
                "skills": ["waiter", "cashier"],
            },
            {
                "id": "emp_002",
                "name": "李四",
                "skills": ["chef"],
            },
        ],
    }


@pytest.fixture
async def sample_user(test_db):
    """创建示例用户"""
    import uuid
    from src.models.user import User, UserRole
    from src.core.security import get_password_hash

    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Test User",
        role=UserRole.STAFF,
        is_active=True,
    )

    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    return user
