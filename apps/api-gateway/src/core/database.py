"""
Database Configuration and Connection
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
import structlog
import os

from src.core.config import settings
from src.core.tenant_context import TenantContext
from src.core.tenant_filter import enable_tenant_filter

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
        # Connection pool settings for production load（支持环境变量覆盖）
        pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "40")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
        pool_pre_ping=True,
        connect_args={
            "server_settings": {"application_name": "zhilian_os_api"},
            "timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
            "command_timeout": int(os.getenv("DB_COMMAND_TIMEOUT", "60")),
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
async def get_db_session(enable_tenant_isolation: bool = True):
    """
    Async context manager for database sessions with tenant isolation

    Args:
        enable_tenant_isolation: 是否启用租户隔离（默认True）

    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
    """
    async with AsyncSessionLocal() as session:
        try:
            # 启用租户过滤器
            if enable_tenant_isolation:
                tenant_id = TenantContext.get_current_tenant()
                if tenant_id:
                    enable_tenant_filter(session)
                    logger.debug("Tenant isolation enabled", tenant_id=tenant_id)
                else:
                    logger.warning(
                        "Tenant isolation requested but no tenant context set. "
                        "Session will not be filtered."
                    )

            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            await session.close()


async def get_db(enable_tenant_isolation: bool = True):
    """
    Dependency for FastAPI endpoints with tenant isolation

    Args:
        enable_tenant_isolation: 是否启用租户隔离（默认True）

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            # 启用租户过滤器
            if enable_tenant_isolation:
                tenant_id = TenantContext.get_current_tenant()
                if tenant_id:
                    enable_tenant_filter(session)
                    logger.debug("Tenant isolation enabled for endpoint", tenant_id=tenant_id)

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

