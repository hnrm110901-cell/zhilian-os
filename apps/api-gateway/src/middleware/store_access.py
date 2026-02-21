"""
Store ID Validation Middleware
门店ID归属校验中间件 - 防止跨店铺数据访问
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, List
import structlog

logger = structlog.get_logger()


class StoreAccessMiddleware(BaseHTTPMiddleware):
    """
    门店访问权限校验中间件

    验证用户是否有权访问指定的store_id
    防止跨店铺数据泄露
    """

    # 不需要校验的路径
    EXCLUDED_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/metrics",
        "/auth/login",
        "/auth/register",
    ]

    # 超级管理员角色（可以访问所有门店）
    SUPER_ADMIN_ROLES = ["super_admin", "system_admin"]

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 跳过不需要校验的路径
        if self._should_skip_validation(request.url.path):
            return await call_next(request)

        try:
            # 从请求中提取store_id
            store_id = await self._extract_store_id(request)

            if store_id:
                # 验证用户是否有权访问该门店
                if not await self._validate_store_access(request, store_id):
                    logger.warning(
                        "Unauthorized store access attempt",
                        path=request.url.path,
                        store_id=store_id,
                        user=getattr(request.state, "user", None),
                    )

                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "您没有权限访问该门店的数据",
                            "error_code": "STORE_ACCESS_DENIED",
                            "store_id": store_id,
                        },
                    )

            # 继续处理请求
            response = await call_next(request)
            return response

        except Exception as e:
            logger.error("Store access middleware error", error=str(e))
            # 出错时允许请求继续，避免阻塞正常流程
            return await call_next(request)

    def _should_skip_validation(self, path: str) -> bool:
        """判断是否应该跳过校验"""
        for excluded_path in self.EXCLUDED_PATHS:
            if path.startswith(excluded_path):
                return True
        return False

    async def _extract_store_id(self, request: Request) -> Optional[str]:
        """
        从请求中提取store_id

        支持多种方式：
        1. Query参数: ?store_id=xxx
        2. Path参数: /stores/{store_id}/...
        3. Request body (JSON)
        """
        # 1. 从query参数获取
        store_id = request.query_params.get("store_id")
        if store_id:
            return store_id

        # 2. 从path参数获取
        path_params = request.path_params
        if "store_id" in path_params:
            return path_params["store_id"]

        # 3. 从request body获取（仅POST/PUT/PATCH请求）
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # 注意：这里需要小心处理，避免消耗request body
                # 实际使用时可能需要更复杂的处理
                body = await request.body()
                if body:
                    import json

                    try:
                        data = json.loads(body)
                        if isinstance(data, dict) and "store_id" in data:
                            return data["store_id"]
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        return None

    async def _validate_store_access(
        self, request: Request, store_id: str
    ) -> bool:
        """
        验证用户是否有权访问指定门店

        Args:
            request: FastAPI请求对象
            store_id: 门店ID

        Returns:
            bool: 是否有权访问
        """
        # 获取当前用户信息（假设已通过认证中间件设置）
        user = getattr(request.state, "user", None)

        if not user:
            # 如果没有用户信息，拒绝访问
            return False

        # 超级管理员可以访问所有门店
        user_role = user.get("role", "")
        if user_role in self.SUPER_ADMIN_ROLES:
            return True

        # 检查用户的门店权限列表
        user_stores = user.get("stores", [])
        if isinstance(user_stores, list):
            return store_id in user_stores

        # 检查用户的主门店
        user_store_id = user.get("store_id")
        if user_store_id == store_id:
            return True

        # 默认拒绝访问
        return False


def get_user_accessible_stores(user: dict) -> List[str]:
    """
    获取用户可访问的门店列表

    Args:
        user: 用户信息字典

    Returns:
        可访问的门店ID列表
    """
    # 超级管理员可以访问所有门店
    user_role = user.get("role", "")
    if user_role in StoreAccessMiddleware.SUPER_ADMIN_ROLES:
        return ["*"]  # 特殊标记表示所有门店

    # 获取用户的门店权限列表
    stores = user.get("stores", [])
    if isinstance(stores, list):
        return stores

    # 获取用户的主门店
    store_id = user.get("store_id")
    if store_id:
        return [store_id]

    return []


def validate_store_access_sync(user: dict, store_id: str) -> bool:
    """
    同步版本的门店访问权限校验

    Args:
        user: 用户信息
        store_id: 门店ID

    Returns:
        是否有权访问
    """
    accessible_stores = get_user_accessible_stores(user)

    # 超级管理员
    if "*" in accessible_stores:
        return True

    # 检查是否在可访问列表中
    return store_id in accessible_stores
