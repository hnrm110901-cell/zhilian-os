"""
Database Configuration and Connection
支持多租户 Schema 隔离: 根据 TenantContext.brand_id 动态切换 search_path
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy import text
from contextlib import asynccontextmanager
from typing import Optional
import asyncio
import structlog
import os

from src.core.config import settings
from src.core.tenant_context import TenantContext
from src.core.tenant_filter import enable_tenant_filter

logger = structlog.get_logger()

# ---- 多租户 Schema 映射（静态 + 运行时从 DB 加载） ----
# tenant_id（Nginx X-Tenant-ID） → schema_name
# brand_id → schema_name
_TENANT_SCHEMA_MAP: dict[str, str] = {
    # tenant_id → schema
    "brand_czq": "czq",
    "brand_zqx": "zqx",
    "brand_sgc": "sgc",
    # brand_id → schema
    "BRD_CZYZ0001": "czq",
    "BRD_ZQX00001": "zqx",
    "BRD_SGC00001": "sgc",
}


def resolve_schema(brand_or_tenant_id: str) -> Optional[str]:
    """将 brand_id 或 tenant_id 解析为 PostgreSQL schema 名"""
    return _TENANT_SCHEMA_MAP.get(brand_or_tenant_id)


async def reload_schema_map_from_db():
    """从 tenant_schema_map 表热加载映射（服务启动或定时刷新时调用）"""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT schema_name, brand_id, tenant_id FROM public.tenant_schema_map WHERE is_active = TRUE"
            ))
            rows = result.fetchall()
            for row in rows:
                _TENANT_SCHEMA_MAP[row[1]] = row[0]  # brand_id → schema
                if row[2]:
                    _TENANT_SCHEMA_MAP[row[2]] = row[0]  # tenant_id → schema
            logger.info("Schema map reloaded from DB", count=len(rows))
    except Exception as e:
        logger.warning("Failed to reload schema map from DB (table may not exist yet)", error=str(e))


async def _set_search_path(session: AsyncSession, schema_name: str):
    """动态设置当前会话的 search_path"""
    await session.execute(text(f"SET search_path TO {schema_name}, public"))
    logger.debug("search_path set", schema=schema_name)

# Import Base for models
from src.models.base import Base


def _get_async_database_url(raw_url: str) -> str:
    """Normalize DATABASE_URL to an async SQLAlchemy URL."""
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


ASYNC_DATABASE_URL = _get_async_database_url(settings.DATABASE_URL)
IS_POSTGRES = ASYNC_DATABASE_URL.startswith("postgresql")

# Create async engine with environment-specific configuration
# Architecture Review Fix: Clear separation of test vs production pool config
if settings.APP_ENV == "test":
    # Test environment: Use NullPool to avoid connection issues
    # NullPool creates a new connection for each request and closes it immediately
    engine = create_async_engine(
        ASYNC_DATABASE_URL,
        echo=settings.APP_DEBUG,
        poolclass=NullPool,
        # Connection arguments for better reliability
        connect_args={
            "server_settings": {"application_name": "zhilian_os_api_test"},
            "timeout": 10,
        } if IS_POSTGRES else {},
    )
else:
    # Production/Development: Use QueuePool with optimized settings
    # QueuePool maintains a pool of connections for reuse
    engine = create_async_engine(
        ASYNC_DATABASE_URL,
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
        } if IS_POSTGRES else {},
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
            # Schema 级隔离: 根据 brand_id 切换 search_path
            brand_id = TenantContext.get_current_brand()
            if brand_id:
                schema = resolve_schema(brand_id)
                if schema:
                    await _set_search_path(session, schema)

            # 启用租户过滤器（ORM 级 store_id 行过滤）
            if enable_tenant_isolation:
                tenant_id = TenantContext.get_current_tenant()
                if tenant_id:
                    enable_tenant_filter(session)
                    logger.debug("Tenant isolation enabled", tenant_id=tenant_id)

            yield session
            await session.commit()
        except asyncio.TimeoutError as e:
            await session.rollback()
            logger.error("Database operation timed out", error=str(e))
            raise
        except OperationalError as e:
            await session.rollback()
            logger.error("Database connection error", error=str(e))
            raise
        except IntegrityError as e:
            await session.rollback()
            logger.error("Database integrity constraint violated", error=str(e))
            raise
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
            # Schema 级隔离: 根据 brand_id 切换 search_path
            brand_id = TenantContext.get_current_brand()
            if brand_id:
                schema = resolve_schema(brand_id)
                if schema:
                    await _set_search_path(session, schema)

            # 启用租户过滤器（ORM 级 store_id 行过滤）
            if enable_tenant_isolation:
                tenant_id = TenantContext.get_current_tenant()
                if tenant_id:
                    enable_tenant_filter(session)
                    logger.debug("Tenant isolation enabled for endpoint", tenant_id=tenant_id)

            yield session
        finally:
            await session.close()


async def init_db(retries: int = 5, delay: float = 3.0):
    """Initialize database - create all tables（带重试，兼容 DB 启动慢的场景）"""
    import asyncio
    from src.models import Base

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                # checkfirst=True: 跳过已存在的表和 ENUM 类型，幂等安全
                await conn.run_sync(Base.metadata.create_all, checkfirst=True)
            logger.info("Database initialized successfully", attempt=attempt)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Database init attempt failed, retrying",
                attempt=attempt,
                max_retries=retries,
                error=str(exc),
            )
            if attempt < retries:
                await asyncio.sleep(delay)

    raise RuntimeError(f"Database init failed after {retries} attempts: {last_exc}")


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
    except asyncio.TimeoutError as e:
        logger.error("Database health check timed out", error=str(e))
        return {
            "status": "unhealthy",
            "database": "timeout",
            "error": "连接超时",
        }
    except OperationalError as e:
        logger.error("Database health check: connection failed", error=str(e))
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }
