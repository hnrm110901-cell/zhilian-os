"""
Store ID Validation Middleware
门店ID归属校验中间件 - 防止跨店铺/跨品牌数据访问
支持 X-Tenant-ID Header（Nginx 注入）+ JWT brand_id 双层隔离
"""

from typing import List, Optional

import structlog
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from src.core.tenant_context import TenantContext
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


def _decode_user_from_request(request: Request) -> Optional[dict]:
    """从 Authorization header 解码 JWT，提取用户信息"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from src.core.security import decode_access_token

        payload = decode_access_token(token)
        return {
            "sub": payload.get("sub"),
            "username": payload.get("username"),
            "role": payload.get("role", ""),
            "store_id": payload.get("store_id", ""),
            "brand_id": payload.get("brand_id", ""),
            "stores": payload.get("stores", []),
        }
    except Exception:
        return None


class StoreAccessMiddleware(BaseHTTPMiddleware):
    """
    门店访问权限校验中间件（双层隔离：store_id + brand_id）

    验证用户是否有权访问指定的 store_id，同时检查 brand_id 跨品牌访问。
    防止跨店铺、跨品牌数据泄露。

    支持 Nginx 注入的 X-Tenant-ID Header 自动设置品牌上下文。
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
        "/api/v1/auth",
        # 边缘节点注册/心跳/Bootstrap — 使用独立 edge bootstrap token 认证，不走门店访问控制
        "/api/v1/hardware/edge-node/register",
        "/api/v1/hardware/edge-node/heartbeat",
        "/api/v1/hardware/admin/bootstrap-token",
    ]

    # 超级管理员角色（可以访问所有门店/品牌）
    SUPER_ADMIN_ROLES = ["super_admin", "system_admin", "admin"]

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 跳过不需要校验的路径
        if self._should_skip_validation(request.url.path):
            return await call_next(request)

        try:
            # 从 JWT 解码用户信息并注入 request.state
            user = getattr(request.state, "user", None)
            if user is None:
                user = _decode_user_from_request(request)
                if user:
                    request.state.user = user

            # 从 Nginx X-Tenant-ID Header 设置品牌上下文（最高优先级）
            x_tenant_id = request.headers.get("x-tenant-id", "")
            if x_tenant_id and x_tenant_id != "platform_admin":
                # x_tenant_id 格式: brand_czq / brand_zqx / brand_sgc
                TenantContext.set_current_brand(x_tenant_id)
                logger.debug("Brand context set from X-Tenant-ID", tenant_id=x_tenant_id)

            # 从请求中提取 store_id
            store_id = await self._extract_store_id(request)

            # 如果没有提取到 store_id，尝试从用户信息获取
            if not store_id:
                if user:
                    store_id = user.get("store_id")

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

                # 设置门店租户上下文
                TenantContext.set_current_tenant(store_id)
                logger.debug("Tenant context set in middleware", store_id=store_id)

            # 从 JWT 提取 brand_id 并设置品牌上下文
            user = getattr(request.state, "user", None)
            if user:
                brand_id = user.get("brand_id")
                user_role = user.get("role", "")

                if brand_id and user_role not in self.SUPER_ADMIN_ROLES:
                    # 检查跨品牌访问
                    request_brand_id = await self._extract_brand_id(request, user)
                    if request_brand_id and request_brand_id != brand_id:
                        logger.warning(
                            "Cross-brand access attempt",
                            path=request.url.path,
                            user_brand_id=brand_id,
                            request_brand_id=request_brand_id,
                        )
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={
                                "detail": "您没有权限访问该品牌的数据",
                                "error_code": "BRAND_ACCESS_DENIED",
                                "brand_id": request_brand_id,
                            },
                        )

                    if brand_id:
                        try:
                            TenantContext.set_current_brand(brand_id)
                            logger.debug("Brand context set in middleware", brand_id=brand_id)
                        except ValueError:
                            pass

            # 继续处理请求
            response = await call_next(request)

            # 清除上下文
            TenantContext.clear_current_tenant()
            TenantContext.clear_current_brand()

            return response

        except Exception as e:
            logger.error("Store access middleware error", error=str(e))
            # 确保清除上下文
            TenantContext.clear_current_tenant()
            TenantContext.clear_current_brand()
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
        从请求中提取 store_id

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
                body = await request.body()
                if body:
                    import json

                    try:
                        data = json.loads(body)
                        if isinstance(data, dict) and "store_id" in data:
                            return data["store_id"]
                    except json.JSONDecodeError:
                        logger.debug("request_body_not_json", path=str(request.url.path))
            except Exception as e:
                logger.warning("request_body_parse_failed", error=str(e))

    async def _extract_brand_id(self, request: Request, user: dict) -> Optional[str]:
        """从请求中提取 brand_id（用于跨品牌访问检测）"""
        # 1. 从query参数获取
        brand_id = request.query_params.get("brand_id")
        if brand_id:
            return brand_id

        # 2. 从path参数获取
        if "brand_id" in request.path_params:
            return request.path_params["brand_id"]

        # 3. 从request body获取
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    import json

                    try:
                        data = json.loads(body)
                        if isinstance(data, dict) and "brand_id" in data:
                            return data["brand_id"]
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.debug("extract_brand_id_failed", error=str(e))

        return None

    async def _validate_store_access(self, request: Request, store_id: str) -> bool:
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
        if isinstance(user_stores, list) and user_stores:
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
    if isinstance(stores, list) and stores:
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
