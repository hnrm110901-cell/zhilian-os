"""
OrgScope — 请求级别的组织访问上下文

每个认证请求都会携带 OrgScope，记录：
  - 用户"挂载"在哪个节点（home_node_id）
  - 用户可访问的门店 ID 列表（accessible_store_ids）
  - 用户在该范围内的权限级别

OrgScopeMiddleware 将 OrgScope 注入 request.state.org_scope
各 API handler 通过 get_org_scope() 依赖获取
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from src.models.org_node import OrgNode, OrgNodeType
import structlog

logger = structlog.get_logger()


@dataclass
class OrgScope:
    """请求级别的组织上下文（只读）"""
    home_node_id: str                        # 用户主节点
    accessible_store_ids: list[str]          # 可访问的 store_id 列表
    accessible_node_ids: list[str]           # 可访问的全部节点 ID
    permission_level: str = "read_only"      # read_only / read_write / admin
    is_global_admin: bool = False            # True = 跳过范围限制

    def can_write(self) -> bool:
        return self.permission_level in ("read_write", "admin") or self.is_global_admin

    def can_admin(self) -> bool:
        return self.permission_level == "admin" or self.is_global_admin

    def filter_store_ids(self, store_ids: list[str]) -> list[str]:
        """从给定 store_id 列表中过滤出在范围内的"""
        if self.is_global_admin:
            return store_ids
        allowed = set(self.accessible_store_ids)
        return [s for s in store_ids if s in allowed]

    def assert_store_access(self, store_id: str) -> None:
        """如果无权访问指定门店，抛出 403"""
        from fastapi import HTTPException
        if not self.is_global_admin and store_id not in self.accessible_store_ids:
            raise HTTPException(
                status_code=403,
                detail=f"无权访问门店 {store_id}（当前节点: {self.home_node_id}）",
            )


def build_org_scope_from_nodes(
    home_node_id: str,
    subtree_nodes: list[OrgNode],
    permission_level: str = "read_only",
    is_global_admin: bool = False,
) -> OrgScope:
    """
    从子树节点列表构建 OrgScope
    accessible_store_ids = 子树内所有 node_type=store 节点的 store_ref_id
    """
    store_ids = []
    node_ids = []
    for node in subtree_nodes:
        node_ids.append(node.id)
        if node.node_type == OrgNodeType.STORE.value and node.store_ref_id:
            store_ids.append(node.store_ref_id)
        # 向后兼容：如果 store_ref_id 为空但 node_type=store，用 node.id 作为 store_id
        elif node.node_type == OrgNodeType.STORE.value:
            store_ids.append(node.id)

    return OrgScope(
        home_node_id=home_node_id,
        accessible_store_ids=list(dict.fromkeys(store_ids)),  # 保序去重
        accessible_node_ids=node_ids,
        permission_level=permission_level,
        is_global_admin=is_global_admin,
    )


# ── GLOBAL_ADMIN_SCOPE：用于系统级操作，不受范围限制 ────────────────────
GLOBAL_ADMIN_SCOPE = OrgScope(
    home_node_id="__global__",
    accessible_store_ids=[],
    accessible_node_ids=[],
    permission_level="admin",
    is_global_admin=True,
)


class OrgScopeMiddleware(BaseHTTPMiddleware):
    """
    FastAPI 中间件：每个认证请求注入 request.state.org_scope

    跳过范围：
    - 未认证请求（无 JWT）
    - /api/v1/health
    - /api/v1/auth/*

    Redis 缓存键：org_scope:{org_node_id} TTL=300s（5分钟）
    """

    SKIP_PATHS = {"/api/v1/health", "/api/v1/auth/login",
                  "/api/v1/auth/refresh", "/docs", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # 跳过不需要鉴权的路径
        if request.url.path in self.SKIP_PATHS or request.url.path.startswith("/docs"):
            request.state.org_scope = GLOBAL_ADMIN_SCOPE
            return await call_next(request)

        # 从请求上下文取用户信息（由 JWT 中间件先行注入）
        user = getattr(request.state, "current_user", None)
        if not user:
            request.state.org_scope = GLOBAL_ADMIN_SCOPE
            return await call_next(request)

        # Admin 角色跳过范围限制
        if getattr(user, "role", None) and user.role.value == "admin":
            request.state.org_scope = GLOBAL_ADMIN_SCOPE
            return await call_next(request)

        # 构建 OrgScope
        org_node_id = getattr(user, "org_node_id", None)
        if not org_node_id:
            # 向后兼容：没有 org_node_id 的用户，用 store_id 作为范围
            store_id = getattr(user, "store_id", None)
            if store_id:
                request.state.org_scope = OrgScope(
                    home_node_id=store_id,
                    accessible_store_ids=[store_id],
                    accessible_node_ids=[store_id],
                    permission_level="read_write",
                )
            else:
                request.state.org_scope = GLOBAL_ADMIN_SCOPE
            return await call_next(request)

        # 尝试从 Redis 缓存获取
        scope = await self._get_cached_scope(request, org_node_id, user)
        request.state.org_scope = scope

        return await call_next(request)

    async def _get_cached_scope(self, request, org_node_id: str, user) -> OrgScope:
        """从 Redis 读取缓存，未命中则从数据库构建"""
        redis = getattr(request.app.state, "redis", None)
        cache_key = f"org_scope:{org_node_id}"

        if redis:
            try:
                import json
                cached = await redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return OrgScope(**data)
            except Exception:
                pass  # 缓存失败不阻塞请求

        # 从数据库构建
        scope = await self._build_scope_from_db(request, org_node_id, user)

        # 写入缓存
        if redis and scope:
            try:
                import json
                from dataclasses import asdict
                await redis.setex(cache_key, 300, json.dumps(asdict(scope)))
            except Exception:
                pass

        return scope or GLOBAL_ADMIN_SCOPE

    async def _build_scope_from_db(self, request, org_node_id: str, user) -> Optional[OrgScope]:
        """从 org_nodes 子树构建 OrgScope，同时从 org_permissions 读取权限级别"""
        try:
            db = request.state.db  # 由数据库中间件注入
            from src.services.org_hierarchy_service import OrgHierarchyService
            from src.models.org_permission import OrgPermission
            from sqlalchemy import select
            svc = OrgHierarchyService(db)
            subtree = await svc.get_subtree(org_node_id)
            if not subtree:
                return None

            # 从 org_permissions 读取用户对该节点的权限级别
            perm_result = await db.execute(
                select(OrgPermission).where(
                    OrgPermission.user_id == str(getattr(user, "id", "")),
                    OrgPermission.org_node_id == org_node_id,
                    OrgPermission.is_active == True,
                )
            )
            perm = perm_result.scalar_one_or_none()
            # 无显式权限记录时降级为只读（最小权限原则）
            permission_level = perm.permission_level if perm else "read_only"

            return build_org_scope_from_nodes(
                home_node_id=org_node_id,
                subtree_nodes=subtree,
                permission_level=permission_level,
            )
        except Exception as e:
            logger.warning("org_scope_build_failed", error=str(e), node_id=org_node_id)
            return None
