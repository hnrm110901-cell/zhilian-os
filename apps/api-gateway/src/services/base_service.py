"""
Service基类
提供统一的租户隔离和数据库访问模式
"""
from typing import Optional
import structlog

from src.core.tenant_context import TenantContext
from src.core.database import get_db_session

logger = structlog.get_logger()


class BaseService:
    """
    Service基类

    所有Service类应继承此基类，自动获得租户隔离能力
    """

    def __init__(self, store_id: Optional[str] = None):
        """
        初始化Service

        Args:
            store_id: 门店ID。如果不提供，将从TenantContext获取
        """
        if store_id:
            self.store_id = store_id
        else:
            # 从租户上下文获取
            self.store_id = TenantContext.get_current_tenant()

        if not self.store_id:
            logger.warning(
                f"{self.__class__.__name__} initialized without store_id. "
                "This may cause issues in multi-tenant environment."
            )

        logger.debug(
            f"{self.__class__.__name__} initialized",
            store_id=self.store_id
        )

    def get_store_id(self) -> Optional[str]:
        """获取当前Service的store_id"""
        return self.store_id

    def require_store_id(self) -> str:
        """
        获取store_id，如果未设置则抛出异常

        Returns:
            str: store_id

        Raises:
            RuntimeError: 如果store_id未设置
        """
        if not self.store_id:
            raise RuntimeError(
                f"{self.__class__.__name__} requires a valid store_id. "
                "Please ensure the service is initialized with a store_id "
                "or the tenant context is properly set."
            )
        return self.store_id

    async def get_session(self, enable_tenant_isolation: bool = True):
        """
        获取数据库Session

        Args:
            enable_tenant_isolation: 是否启用租户隔离

        Returns:
            AsyncSession context manager
        """
        return get_db_session(enable_tenant_isolation=enable_tenant_isolation)
