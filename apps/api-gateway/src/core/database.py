"""
Database Configuration and Connection
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
import structlog

from src.core.config import settings

logger = structlog.get_logger()

# Import Base for models
from src.models.base import Base

# Create async engine with environment-specific configuration
# Architecture Review Fix: Clear separation of test vs production pool config
if settings.APP_ENV == "test":
    # Test environment: Use NullPool to avoid connection issues
    # NullPool creates a new connection for each request and closes it immediately
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.APP_DEBUG,
        poolclass=NullPool,
        # Connection arguments for better reliability
        connect_args={
            "server_settings": {"application_name": "zhilian_os_api_test"},
            "timeout": 10,
        } if "postgresql" in settings.DATABASE_URL else {},
    )
else:
    # Production/Development: Use QueuePool with optimized settings
    # QueuePool maintains a pool of connections for reuse
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.APP_DEBUG,
        # Connection pool settings for production load
        pool_size=20,  # Base pool size
        max_overflow=40,  # Allow up to 60 total connections (20 + 40)
        pool_timeout=30,  # Wait up to 30 seconds for a connection
        pool_recycle=3600,  # Recycle connections after 1 hour to avoid stale connections
        pool_pre_ping=True,  # Verify connections before using them
        # Connection arguments for better reliability
        connect_args={
            "server_settings": {"application_name": "zhilian_os_api"},
            "timeout": 10,  # Connection timeout
            "command_timeout": 60,  # Query timeout
        } if "postgresql" in settings.DATABASE_URL else {},
    )

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_session():
    """
    Async context manager for database sessions

    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            await session.close()


async def get_db():
    """
    Dependency for FastAPI endpoints

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database - create all tables"""
    from src.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")


async def get_pool_status():
    """
    Get database connection pool status for monitoring

    Returns:
        dict: Pool statistics including size, checked out connections, etc.
    """
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "checked_in": pool.checkedin(),
        "total_connections": pool.size() + pool.overflow(),
    }


async def health_check():
    """
    Check database health and connectivity

    Returns:
        dict: Health status with connection test result
    """
    try:
        async with get_db_session() as session:
            # Simple query to test connection
            result = await session.execute("SELECT 1")
            result.scalar()

        pool_status = await get_pool_status()

        return {
            "status": "healthy",
            "database": "connected",
            "pool": pool_status,
        }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }

