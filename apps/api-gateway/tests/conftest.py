"""
测试配置和fixtures
"""
import os

# ── 测试环境变量（必须在所有 src.* 导入前设置）────────────────────────────────
for _k, _v in {
    "APP_ENV":               "test",
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import sys
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Pre-load core modules BEFORE any test file is collected.
# Many test files use sys.modules.setdefault("src.core.config", MagicMock(...))
# to avoid importing Settings when env vars are missing.  By eagerly importing
# the real modules here (env vars are already set above), setdefault() becomes
# a no-op and no test file can pollute the global module cache.
# ---------------------------------------------------------------------------
import src.core.config   # noqa: F401
import src.core.database  # noqa: F401
import src.core.security  # noqa: F401
import src.services.agent_service  # noqa: F401 — preload to prevent mock injection
import src.services.redis_cache_service  # noqa: F401 — preload to prevent mock injection
import src.services.wechat_work_message_service  # noqa: F401
import src.services.wechat_alert_service  # noqa: F401
import src.services.waste_guard_service  # noqa: F401
import src.services.waste_reasoning_service  # noqa: F401

from src.models import Base

# ---------------------------------------------------------------------------
# Snapshot sys.modules after all conftest imports so we can detect and undo
# pollution from test files that do sys.modules["x"] = MagicMock() at module
# level.  We use pytest_collect_file to restore between file collections.
# ---------------------------------------------------------------------------
_SYS_MODULES_SNAPSHOT = dict(sys.modules)


def _restore_sys_modules():
    """Undo sys.modules pollution from test files."""
    import types as _types
    # Restore any snapshot modules that were overwritten with mocks
    for key, orig in _SYS_MODULES_SNAPSHOT.items():
        if sys.modules.get(key) is not orig:
            sys.modules[key] = orig
    # Remove mock modules that were added after conftest loaded
    added = set(sys.modules) - set(_SYS_MODULES_SNAPSHOT)
    for key in added:
        mod = sys.modules.get(key)
        if mod is None:
            continue
        if hasattr(mod, '_mock_name'):
            del sys.modules[key]
        elif isinstance(mod, _types.ModuleType) and not hasattr(mod, '__file__'):
            del sys.modules[key]


def pytest_collect_file(parent, file_path):
    """Restore sys.modules before each test file is collected."""
    _restore_sys_modules()


# ---------------------------------------------------------------------------
# Also restore core modules before each test function runs.
# This catches pollution that occurs during collection of one file and
# affects tests in later files (e.g. celery_tasks decorated with FakeCelery).
# We only restore modules from the snapshot, NOT remove test-specific mocks,
# to avoid breaking tests that rely on their own module-level setdefault stubs.
# ---------------------------------------------------------------------------
_CORE_MODULES_TO_PROTECT = [
    k for k in _SYS_MODULES_SNAPSHOT
    if k.startswith("src.core.") or k.startswith("src.models")
    or k.startswith("src.services.") or k == "structlog"
]


_SECURITY_SETTINGS_ORIG = src.core.security.settings


def pytest_runtest_setup(item):
    """Restore core modules before each test to prevent cross-file pollution."""
    for key in _CORE_MODULES_TO_PROTECT:
        orig = _SYS_MODULES_SNAPSHOT.get(key)
        if orig is not None and sys.modules.get(key) is not orig:
            sys.modules[key] = orig
    # Restore security.settings if it was replaced by a test file at module level
    if src.core.security.settings is not _SECURITY_SETTINGS_ORIG:
        src.core.security.settings = _SECURITY_SETTINGS_ORIG


# 测试数据库URL - 优先使用PostgreSQL，回退到SQLite
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/zhilian_test"
)

# 如果PostgreSQL不可用，使用SQLite
USE_SQLITE_FALLBACK = os.getenv("USE_SQLITE_FALLBACK", "true").lower() == "true"


@pytest.fixture(scope="function")
def event_loop() -> Generator:
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture
def benchmark():
    """轻量 benchmark 兼容夹具（在未安装 pytest-benchmark 时提供）。"""
    def _run(func, *args, **kwargs):
        return func(*args, **kwargs)
    return _run


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
