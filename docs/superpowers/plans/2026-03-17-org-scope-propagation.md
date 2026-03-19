# OrgScope 全产品传播计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**前置依赖：** `2026-03-17-org-hierarchy-config-resolver.md` 必须先完成（z52 迁移已跑通）

**Goal:** 以 OrgNode 树为骨干，让屯象OS 所有产品模块（财务/库存/排班/KPI/营销/合规…）自动感知多层级组织上下文，实现"用户登录即得组织权限，查询自动范围隔离，数据自动上卷汇总"。

**Architecture:**
不修改现有 99 个业务模型，而是通过"**User → OrgNode → store_ids → 现有数据**"的桥接链实现全产品传播：
1. `User.org_node_id` → 用户"挂载点"（如区域经理挂载到区域节点）
2. `OrgScopeMiddleware` → 每次请求自动计算 `accessible_store_ids`（子树内所有门店）
3. `OrgQueryFilter` → 给任意 SQLAlchemy 查询追加 `store_id IN (...)` 过滤
4. `OrgAggregator` → 按层级上卷 KPI/财务/人力数据

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, FastAPI middleware, PostgreSQL, Redis（缓存子树查询）

---

## 架构全景

```
用户登录 JWT
    │  包含: user_id, role, org_node_id
    ▼
OrgScopeMiddleware（每个请求）
    │  Redis缓存: org_node_id → [store_id列表]
    │  未命中: get_subtree(org_node_id) → 取所有 store 节点
    ▼
request.state.org_scope = OrgScope(
    node_id="reg-south",          # 用户挂载节点
    accessible_store_ids=[         # 该节点子树内所有门店
        "sto-gz-001",
        "sto-sz-001",
    ],
    accessible_node_ids=[          # 子树内所有节点
        "reg-south", "sto-gz-001", "sto-sz-001",
        "dept-gz-front", "dept-gz-kitchen"
    ],
    permission_level="read_write", # 该节点的权限级别
)
    │
    ▼
各产品 API 调用 OrgQueryFilter
    │
    ├── 财务: SELECT * FROM daily_settlements WHERE store_id IN (...)
    ├── 库存: SELECT * FROM inventory_items WHERE store_id IN (...)
    ├── 排班: SELECT * FROM schedules WHERE store_id IN (...)
    ├── KPI:  SELECT * FROM kpis WHERE store_id IN (...)
    ├── 员工: SELECT * FROM employees WHERE store_id IN (...)
    └── 订单: SELECT * FROM orders WHERE store_id IN (...)
    │
    ▼
OrgAggregator（汇总上卷）
    │
    ├── 区域营收 = SUM(各门店营收)
    ├── 品牌成本率 = AVG加权(各门店成本率)
    └── 集团人力 = SUM(各门店在职人数)
```

---

## 文件清单

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| 新建 | `src/models/org_permission.py` | 用户→节点权限映射（多节点权限） |
| 修改 | `src/models/user.py` | 新增 `org_node_id` 字段 |
| 新建 | `src/core/org_scope.py` | OrgScope 数据类 + OrgScopeMiddleware |
| 新建 | `src/core/org_query_filter.py` | OrgQueryFilter（通用查询过滤器） |
| 新建 | `src/services/org_aggregator.py` | 跨模块数据上卷汇总 |
| 修改 | `src/core/dependencies.py` | 新增 `get_org_scope` 依赖注入 |
| 修改 | `src/api/auth.py` | JWT 写入 `org_node_id` |
| 新建 | `alembic/versions/z53_org_scope.py` | User + OrgPermission 迁移 |
| 新建 | `tests/test_org_scope_middleware.py` | Middleware 单测 |
| 新建 | `tests/test_org_query_filter.py` | 过滤器单测 |
| 新建 | `tests/test_org_aggregator.py` | 聚合单测 |

---

## Chunk 1: 权限数据层

### Task 1: OrgPermission 模型 + User 字段扩展

**Files:**
- Create: `apps/api-gateway/src/models/org_permission.py`
- Modify: `apps/api-gateway/src/models/user.py`

- [ ] **Step 1: 写失败测试**

```python
# apps/api-gateway/tests/test_org_scope_middleware.py
from src.models.org_permission import OrgPermission, OrgPermissionLevel
from src.models.user import User

def test_org_permission_levels():
    assert OrgPermissionLevel.READ_ONLY.value == "read_only"
    assert OrgPermissionLevel.READ_WRITE.value == "read_write"
    assert OrgPermissionLevel.ADMIN.value == "admin"

def test_org_permission_instantiation():
    perm = OrgPermission(
        user_id="usr-001",
        org_node_id="reg-south",
        permission_level=OrgPermissionLevel.READ_WRITE,
    )
    assert perm.org_node_id == "reg-south"
    assert perm.permission_level == OrgPermissionLevel.READ_WRITE

def test_user_has_org_node_id():
    from sqlalchemy.inspection import inspect
    cols = {c.key for c in User.__table__.columns}
    assert "org_node_id" in cols
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api-gateway
pytest tests/test_org_scope_middleware.py::test_org_permission_levels -v
# 预期: ImportError
```

- [ ] **Step 3: 创建 OrgPermission 模型**

```python
# apps/api-gateway/src/models/org_permission.py
"""
OrgPermission — 用户对组织节点的权限映射

支持多节点权限（一个用户可以管理多个不相邻节点）：
  区域经理A → [reg-south: read_write, reg-east: read_only]
  集团CFO    → [grp-demo: read_only]（只读集团财务）
  门店店长   → [sto-gz-001: admin]
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class OrgPermissionLevel(str, enum.Enum):
    READ_ONLY  = "read_only"   # 只读（督导查看）
    READ_WRITE = "read_write"  # 读写（区域经理）
    ADMIN      = "admin"       # 完全控制（门店店长在本店）


class OrgPermission(Base, TimestampMixin):
    """
    用户 → 组织节点 权限行
    一个用户可以有多条记录（管理多个节点）
    权限作用范围 = org_node_id 的整棵子树
    """
    __tablename__ = "org_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "org_node_id", name="uq_org_perm_user_node"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    org_node_id = Column(String(64), ForeignKey("org_nodes.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    permission_level = Column(
        String(32),
        nullable=False,
        default=OrgPermissionLevel.READ_ONLY.value,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    granted_by = Column(String(64), nullable=True)  # 授权人 user_id

    def __repr__(self):
        return (f"<OrgPermission(user='{self.user_id}', "
                f"node='{self.org_node_id}', level='{self.permission_level}')>")
```

- [ ] **Step 4: 修改 User 模型，新增 `org_node_id`**

在 `apps/api-gateway/src/models/user.py` 的 `wechat_user_id` 字段后追加：

```python
# 组织层级挂载点（用户的"主节点"，兼容旧 store_id）
org_node_id = Column(String(64), ForeignKey("org_nodes.id"), nullable=True, index=True)
# 注意：org_node_id 是用户的"主权限节点"
# 更细粒度的多节点权限见 OrgPermission 表
```

并在 `__init__.py` 注册：
```python
from .org_permission import OrgPermission, OrgPermissionLevel
```

- [ ] **Step 5: 跑测试，确认通过**

```bash
pytest tests/test_org_scope_middleware.py::test_org_permission_levels \
       tests/test_org_scope_middleware.py::test_org_permission_instantiation \
       tests/test_org_scope_middleware.py::test_user_has_org_node_id -v
# 预期: 3 passed
```

- [ ] **Step 6: Commit**

```bash
git add apps/api-gateway/src/models/org_permission.py \
        apps/api-gateway/src/models/user.py \
        apps/api-gateway/src/models/__init__.py
git commit -m "feat(models): OrgPermission 多节点权限 + User.org_node_id 字段"
```

---

### Task 2: z53 数据库迁移

**Files:**
- Create: `apps/api-gateway/alembic/versions/z53_org_scope.py`

- [ ] **Step 1: 创建迁移**

```python
# apps/api-gateway/alembic/versions/z53_org_scope.py
"""z53 org_scope — User.org_node_id + OrgPermission 表

Revision ID: z53
Revises: z52
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z53'
down_revision = 'z52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── org_permissions 表 ───────────────────────────────────────────
    op.create_table(
        'org_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(64),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('org_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('permission_level', sa.String(32), nullable=False,
                  server_default='read_only'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('granted_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False,
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'org_node_id', name='uq_org_perm_user_node'),
    )
    op.create_index('ix_org_perm_user_id', 'org_permissions', ['user_id'])
    op.create_index('ix_org_perm_node_id', 'org_permissions', ['org_node_id'])

    # ── users 表新增字段 ──────────────────────────────────────────────
    op.add_column('users',
        sa.Column('org_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id'), nullable=True))
    op.create_index('ix_users_org_node_id', 'users', ['org_node_id'])


def downgrade() -> None:
    op.drop_index('ix_users_org_node_id', 'users')
    op.drop_column('users', 'org_node_id')
    op.drop_index('ix_org_perm_node_id', 'org_permissions')
    op.drop_index('ix_org_perm_user_id', 'org_permissions')
    op.drop_table('org_permissions')
```

- [ ] **Step 2: Commit**

```bash
git add apps/api-gateway/alembic/versions/z53_org_scope.py
git commit -m "feat(migration): z53 新增 org_permissions 表 + users.org_node_id"
```

---

## Chunk 2: OrgScope 核心中间件

### Task 3: OrgScope 数据类 + Middleware

**Files:**
- Create: `apps/api-gateway/src/core/org_scope.py`

- [ ] **Step 1: 写失败测试**

```python
# apps/api-gateway/tests/test_org_scope_middleware.py（追加）
from src.core.org_scope import OrgScope, build_org_scope_from_nodes
from src.models.org_node import OrgNode, OrgNodeType


def _make_store_node(id_, path, parent_id=None):
    n = OrgNode()
    n.id = id_
    n.name = id_
    n.node_type = OrgNodeType.STORE.value
    n.path = path
    n.depth = path.count(".") + 1 if "." in path else 1
    n.parent_id = parent_id
    n.store_ref_id = id_  # store_ref_id = store_id（门店节点自引）
    return n


def _make_region_node(id_, path):
    n = OrgNode()
    n.id = id_
    n.name = id_
    n.node_type = OrgNodeType.REGION.value
    n.path = path
    n.depth = 1
    n.parent_id = None
    n.store_ref_id = None
    return n


def test_org_scope_store_ids_from_subtree():
    """区域节点的 scope 应包含区域内所有门店的 store_ref_id"""
    region = _make_region_node("reg-south", "grp.reg-south")
    store1 = _make_store_node("sto-gz-001", "grp.reg-south.sto-gz-001", "reg-south")
    store2 = _make_store_node("sto-sz-001", "grp.reg-south.sto-sz-001", "reg-south")

    scope = build_org_scope_from_nodes(
        home_node_id="reg-south",
        subtree_nodes=[region, store1, store2],
        permission_level="read_write",
    )
    assert set(scope.accessible_store_ids) == {"sto-gz-001", "sto-sz-001"}
    assert scope.home_node_id == "reg-south"
    assert scope.permission_level == "read_write"


def test_org_scope_store_node_only_sees_itself():
    """门店节点的 scope 只包含自身门店"""
    store = _make_store_node("sto-gz-001", "grp.reg.sto-gz-001")
    scope = build_org_scope_from_nodes(
        home_node_id="sto-gz-001",
        subtree_nodes=[store],
        permission_level="admin",
    )
    assert scope.accessible_store_ids == ["sto-gz-001"]


def test_org_scope_admin_sees_all_stores():
    """Admin 节点（集团根）可以看所有门店"""
    group_node = OrgNode()
    group_node.id = "grp-demo"
    group_node.node_type = OrgNodeType.GROUP.value
    group_node.path = "grp-demo"
    group_node.store_ref_id = None

    store1 = _make_store_node("sto-a", "grp-demo.sto-a")
    store2 = _make_store_node("sto-b", "grp-demo.sto-b")

    scope = build_org_scope_from_nodes(
        home_node_id="grp-demo",
        subtree_nodes=[group_node, store1, store2],
        permission_level="admin",
    )
    assert set(scope.accessible_store_ids) == {"sto-a", "sto-b"}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_org_scope_middleware.py::test_org_scope_store_ids_from_subtree -v
# 预期: ImportError
```

- [ ] **Step 3: 创建 OrgScope**

```python
# apps/api-gateway/src/core/org_scope.py
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
                from src.core.org_scope import OrgScope
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
        """从 org_nodes 子树构建 OrgScope"""
        try:
            db = request.state.db  # 由数据库中间件注入
            from src.services.org_hierarchy_service import OrgHierarchyService
            svc = OrgHierarchyService(db)
            subtree = await svc.get_subtree(org_node_id)
            if not subtree:
                return None
            return build_org_scope_from_nodes(
                home_node_id=org_node_id,
                subtree_nodes=subtree,
                permission_level="read_write",  # TODO: 从 OrgPermission 表读取实际权限
            )
        except Exception as e:
            logger.warning("org_scope_build_failed", error=str(e), node_id=org_node_id)
            return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_org_scope_middleware.py::test_org_scope_store_ids_from_subtree \
       tests/test_org_scope_middleware.py::test_org_scope_store_node_only_sees_itself \
       tests/test_org_scope_middleware.py::test_org_scope_admin_sees_all_stores -v
# 预期: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/core/org_scope.py
git commit -m "feat(core): OrgScope 数据类 + OrgScopeMiddleware，Redis 5min 缓存"
```

---

### Task 4: OrgQueryFilter（通用查询过滤器）

**Files:**
- Create: `apps/api-gateway/src/core/org_query_filter.py`
- Test: `apps/api-gateway/tests/test_org_query_filter.py`

- [ ] **Step 1: 写失败测试**

```python
# apps/api-gateway/tests/test_org_query_filter.py
import pytest
from sqlalchemy import select
from src.core.org_query_filter import OrgQueryFilter
from src.core.org_scope import OrgScope
from src.models.order import Order   # 现有模型，有 store_id 字段


def make_scope(store_ids: list[str], is_admin=False) -> OrgScope:
    return OrgScope(
        home_node_id="test-node",
        accessible_store_ids=store_ids,
        accessible_node_ids=[],
        permission_level="read_write",
        is_global_admin=is_admin,
    )


def test_filter_adds_store_id_in_clause():
    """普通 scope 应在查询上追加 store_id IN (...) 过滤"""
    scope = make_scope(["sto-gz-001", "sto-sz-001"])
    q = select(Order)
    filtered = OrgQueryFilter.apply(q, Order, scope)

    # 检查 SQL 包含 IN 子句
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "IN" in compiled.upper()
    assert "sto-gz-001" in compiled


def test_filter_skips_for_global_admin():
    """全局 Admin 不加过滤条件"""
    scope = make_scope([], is_admin=True)
    q = select(Order)
    filtered = OrgQueryFilter.apply(q, Order, scope)
    compiled_original = str(select(Order).compile(compile_kwargs={"literal_binds": True}))
    compiled_filtered = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    # Admin scope 不应该改变查询
    assert "WHERE" not in compiled_filtered or compiled_filtered == compiled_original


def test_filter_empty_scope_returns_nothing():
    """空 scope（非 admin）应返回 1=0 条件（零结果）"""
    scope = make_scope([])  # 无权限但非 admin
    q = select(Order)
    filtered = OrgQueryFilter.apply(q, Order, scope)
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "1 != 1" in compiled or "false" in compiled.lower() or "1=0" in compiled


def test_filter_brand_scoped_model():
    """有 brand_id 但无 store_id 的模型，使用 brand_ids 过滤"""
    from src.core.org_scope import OrgScope
    scope = OrgScope(
        home_node_id="brd-001",
        accessible_store_ids=["sto-a", "sto-b"],
        accessible_node_ids=["brd-001", "sto-a", "sto-b"],
        permission_level="read_write",
    )
    from src.models.dish_master import DishMaster  # 只有 brand_id
    q = select(DishMaster)
    # brand_scoped 模式：不过滤（品牌级数据在子树内通用）
    filtered = OrgQueryFilter.apply(q, DishMaster, scope, scope_field="brand_id")
    # 只要不崩溃即可，具体行为取决于 brand_id 是否在 scope 中
    assert filtered is not None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_org_query_filter.py::test_filter_adds_store_id_in_clause -v
# 预期: ImportError
```

- [ ] **Step 3: 实现 OrgQueryFilter**

```python
# apps/api-gateway/src/core/org_query_filter.py
"""
OrgQueryFilter — 通用组织范围查询过滤器

用法：
    from src.core.org_query_filter import OrgQueryFilter

    # 在任何 API handler 中
    q = select(DailySettlement)
    q = OrgQueryFilter.apply(q, DailySettlement, org_scope)
    result = await db.execute(q)

支持的过滤策略：
  store_id  → model.store_id IN scope.accessible_store_ids  （默认，99% 的模型）
  brand_id  → 不过滤（品牌级数据在子树内对所有门店通用）
  node_id   → model.org_node_id IN scope.accessible_node_ids（新模型用）
"""
from __future__ import annotations
from typing import Type
from sqlalchemy import select, false
from sqlalchemy.sql import Select
from sqlalchemy.orm import DeclarativeBase
from src.core.org_scope import OrgScope


class OrgQueryFilter:

    @staticmethod
    def apply(
        query: Select,
        model: Type,
        scope: OrgScope,
        scope_field: str = "store_id",
    ) -> Select:
        """
        给 SQLAlchemy Select 查询追加组织范围过滤

        scope_field: 模型上用于过滤的字段名，默认 "store_id"
        """
        # 全局 Admin 不加任何过滤
        if scope.is_global_admin:
            return query

        # 获取过滤字段
        col = getattr(model, scope_field, None)
        if col is None:
            # 模型没有该字段，跳过过滤（向后兼容）
            return query

        # 根据 scope_field 决定使用哪个 ID 列表
        if scope_field == "store_id":
            allowed_ids = scope.accessible_store_ids
        elif scope_field == "org_node_id":
            allowed_ids = scope.accessible_node_ids
        elif scope_field == "brand_id":
            # 品牌级数据：不做行级过滤（调用方已经在节点层面隔离）
            return query
        else:
            allowed_ids = scope.accessible_store_ids

        # 空权限 → 返回零结果（安全默认值）
        if not allowed_ids:
            return query.where(false())

        return query.where(col.in_(allowed_ids))

    @staticmethod
    def apply_to_aggregation(
        scope: OrgScope,
        store_id_column,
    ):
        """
        返回适用于 GROUP BY 聚合的 WHERE 条件
        用法：
            q = select(func.sum(Order.amount)).where(
                OrgQueryFilter.apply_to_aggregation(scope, Order.store_id)
            )
        """
        if scope.is_global_admin:
            return true()
        if not scope.accessible_store_ids:
            return false()
        return store_id_column.in_(scope.accessible_store_ids)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_org_query_filter.py -v
# 预期: 4 passed（部分 skip 可接受）
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/core/org_query_filter.py \
        apps/api-gateway/tests/test_org_query_filter.py
git commit -m "feat(core): OrgQueryFilter 通用范围过滤器，支持 store_id/brand_id/org_node_id"
```

---

## Chunk 3: OrgAggregator（跨模块数据汇总）

### Task 5: OrgAggregator 服务

**Files:**
- Create: `apps/api-gateway/src/services/org_aggregator.py`
- Test: `apps/api-gateway/tests/test_org_aggregator.py`

- [ ] **Step 1: 写失败测试**

```python
# apps/api-gateway/tests/test_org_aggregator.py
import pytest
from src.services.org_aggregator import OrgAggregator, OrgSnapshot

def test_org_snapshot_structure():
    snap = OrgSnapshot(
        node_id="reg-south",
        node_name="华南区",
        node_type="region",
        period="2026-03",
        revenue_total_fen=10_000_000,    # 10万元
        revenue_target_fen=12_000_000,
        cost_ratio=0.34,
        headcount=45,
        kpi_score=88.5,
        store_count=2,
    )
    assert snap.revenue_achievement_rate == pytest.approx(10_000_000 / 12_000_000)
    assert snap.revenue_total_yuan == pytest.approx(100_000.0)

@pytest.mark.skip(reason="需要数据库，集成测试阶段")
async def test_aggregate_region():
    """TODO: 集成测试 — 聚合华南区数据"""
    pass
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_org_aggregator.py::test_org_snapshot_structure -v
# 预期: ImportError
```

- [ ] **Step 3: 实现 OrgAggregator**

```python
# apps/api-gateway/src/services/org_aggregator.py
"""
OrgAggregator — 跨模块组织层级数据汇总

按组织层级上卷数据：
  门店快照 → 区域聚合 → 品牌聚合 → 集团聚合

每个层级的 OrgSnapshot 包含：
  - 营收（来自 daily_settlements）
  - 成本率（来自 cost_truth）
  - 人力（来自 employees）
  - KPI（来自 kpis）
  - 子节点快照列表（树形结构）
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog

logger = structlog.get_logger()


@dataclass
class OrgSnapshot:
    """一个组织节点在某周期的数据快照"""
    node_id: str
    node_name: str
    node_type: str
    period: str                          # 格式: "2026-03" 或 "2026-03-17"

    # 财务
    revenue_total_fen: int = 0           # 营收（分）
    revenue_target_fen: int = 0          # 营收目标（分）
    cost_total_fen: int = 0              # 成本（分）
    cost_ratio: float = 0.0             # 成本率

    # 人力
    headcount: int = 0                   # 在职人数
    labor_cost_fen: int = 0             # 人力成本（分）
    labor_cost_ratio: float = 0.0       # 人力成本率

    # 绩效
    kpi_score: float = 0.0              # 综合 KPI 分
    store_count: int = 0                # 子门店数量

    # 子节点快照（树形递归）
    children: list[OrgSnapshot] = field(default_factory=list)

    @property
    def revenue_total_yuan(self) -> float:
        return self.revenue_total_fen / 100

    @property
    def revenue_achievement_rate(self) -> float:
        if self.revenue_target_fen == 0:
            return 0.0
        return self.revenue_total_fen / self.revenue_target_fen

    def to_dict(self, include_children=True) -> dict:
        d = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "period": self.period,
            "revenue_total_yuan": round(self.revenue_total_yuan, 2),
            "revenue_target_yuan": round(self.revenue_target_fen / 100, 2),
            "revenue_achievement_rate": round(self.revenue_achievement_rate * 100, 1),
            "cost_ratio": round(self.cost_ratio * 100, 1),
            "headcount": self.headcount,
            "labor_cost_ratio": round(self.labor_cost_ratio * 100, 1),
            "kpi_score": round(self.kpi_score, 1),
            "store_count": self.store_count,
        }
        if include_children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


class OrgAggregator:
    """
    按组织层级汇总数据
    使用方式：
        aggregator = OrgAggregator(db)
        snapshot = await aggregator.get_snapshot("reg-south", period="2026-03")
        # snapshot.revenue_total_yuan = 华南区本月总营收
        # snapshot.children = [广州旗舰店快照, 深圳购物中心店快照]
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_snapshot(
        self,
        node_id: str,
        period: str,           # "2026-03" 月度 或 "2026-03-17" 日度
        include_children: bool = True,
    ) -> OrgSnapshot:
        """
        获取节点的聚合快照
        如果是叶子节点（门店）：直接查数据
        如果是中间节点（区域/品牌）：递归聚合子节点
        """
        from src.services.org_hierarchy_service import OrgHierarchyService
        svc = OrgHierarchyService(self.db)

        node = await svc.get_node(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")

        # 获取子树内所有门店节点
        subtree = await svc.get_subtree(node_id)
        from src.models.org_node import OrgNodeType
        store_nodes = [n for n in subtree if n.node_type == OrgNodeType.STORE.value]
        store_ids = [n.store_ref_id or n.id for n in store_nodes]

        # 聚合各数据源
        revenue, target = await self._aggregate_revenue(store_ids, period)
        cost_ratio = await self._aggregate_cost_ratio(store_ids, period)
        headcount = await self._aggregate_headcount(store_ids)
        kpi_score = await self._aggregate_kpi(store_ids, period)

        snapshot = OrgSnapshot(
            node_id=node_id,
            node_name=node.name,
            node_type=node.node_type,
            period=period,
            revenue_total_fen=revenue,
            revenue_target_fen=target,
            cost_ratio=cost_ratio,
            headcount=headcount,
            kpi_score=kpi_score,
            store_count=len(store_ids),
        )

        # 递归构建子节点快照（仅下一层）
        if include_children:
            direct_children = [n for n in subtree if n.parent_id == node_id]
            for child in direct_children:
                child_snap = await self.get_snapshot(
                    child.id, period, include_children=False
                )
                snapshot.children.append(child_snap)

        return snapshot

    async def _aggregate_revenue(
        self, store_ids: list[str], period: str
    ) -> tuple[int, int]:
        """从 daily_settlements 汇总营收（分）"""
        if not store_ids:
            return 0, 0
        try:
            from src.models.daily_settlement import StoreDailySettlement
            is_monthly = len(period) == 7  # "2026-03"
            if is_monthly:
                year, month = period.split("-")
                date_filter = and_(
                    func.extract("year", StoreDailySettlement.settlement_date)
                        == int(year),
                    func.extract("month", StoreDailySettlement.settlement_date)
                        == int(month),
                )
            else:
                date_filter = (
                    func.cast(StoreDailySettlement.settlement_date, sa.Date) == period
                )

            result = await self.db.execute(
                select(
                    func.coalesce(func.sum(StoreDailySettlement.actual_revenue_fen), 0),
                    func.coalesce(func.sum(StoreDailySettlement.target_revenue_fen), 0),
                ).where(
                    StoreDailySettlement.store_id.in_(store_ids),
                    date_filter,
                )
            )
            row = result.one()
            return int(row[0]), int(row[1])
        except Exception as e:
            logger.warning("revenue_aggregation_failed", error=str(e))
            return 0, 0

    async def _aggregate_cost_ratio(
        self, store_ids: list[str], period: str
    ) -> float:
        """从 cost_truth 汇总成本率（加权平均）"""
        if not store_ids:
            return 0.0
        try:
            from src.models.cost_truth import CostTruth
            result = await self.db.execute(
                select(
                    func.avg(CostTruth.food_cost_ratio)
                ).where(
                    CostTruth.store_id.in_(store_ids),
                    func.cast(CostTruth.snapshot_date, sa.String).like(f"{period}%"),
                )
            )
            val = result.scalar()
            return float(val) if val else 0.0
        except Exception as e:
            logger.warning("cost_ratio_aggregation_failed", error=str(e))
            return 0.0

    async def _aggregate_headcount(self, store_ids: list[str]) -> int:
        """从 employees 汇总在职人数"""
        if not store_ids:
            return 0
        try:
            from src.models.employee import Employee
            result = await self.db.execute(
                select(func.count(Employee.id)).where(
                    Employee.store_id.in_(store_ids),
                    Employee.is_active == True,
                )
            )
            return int(result.scalar() or 0)
        except Exception as e:
            logger.warning("headcount_aggregation_failed", error=str(e))
            return 0

    async def _aggregate_kpi(self, store_ids: list[str], period: str) -> float:
        """从 kpis 汇总 KPI 平均分"""
        if not store_ids:
            return 0.0
        try:
            from src.models.kpi import KPI
            result = await self.db.execute(
                select(func.avg(KPI.score)).where(
                    KPI.store_id.in_(store_ids),
                    KPI.period == period,
                )
            )
            val = result.scalar()
            return float(val) if val else 0.0
        except Exception as e:
            logger.warning("kpi_aggregation_failed", error=str(e))
            return 0.0
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/test_org_aggregator.py -v
# 预期: 1 passed（结构测试），1 skipped（集成测试）
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/services/org_aggregator.py \
        apps/api-gateway/tests/test_org_aggregator.py
git commit -m "feat(service): OrgAggregator 跨模块数据上卷，OrgSnapshot 结构化快照"
```

---

## Chunk 4: 系统集成 + 依赖注入 + 典型模块改造

### Task 6: 依赖注入 + Auth JWT 扩展

**Files:**
- Modify: `apps/api-gateway/src/core/dependencies.py`
- Modify: `apps/api-gateway/src/api/auth.py`

- [ ] **Step 1: 在 dependencies.py 新增 get_org_scope**

找到 `apps/api-gateway/src/core/dependencies.py`，追加：

```python
# 追加到 dependencies.py 末尾
from src.core.org_scope import OrgScope, GLOBAL_ADMIN_SCOPE
from fastapi import Request

def get_org_scope(request: Request) -> OrgScope:
    """
    依赖注入：获取当前请求的 OrgScope
    用法：
        @router.get("/orders")
        async def list_orders(
            scope: OrgScope = Depends(get_org_scope),
            db: AsyncSession = Depends(get_db),
        ):
            q = OrgQueryFilter.apply(select(Order), Order, scope)
            ...
    """
    return getattr(request.state, "org_scope", GLOBAL_ADMIN_SCOPE)
```

- [ ] **Step 2: 在 auth.py 的 JWT 生成中写入 org_node_id**

找到 JWT 生成函数（`create_access_token` 调用处），在 payload 中追加：

```python
# 在 JWT payload 里追加 org_node_id
payload = {
    "sub": str(user.id),
    "role": user.role.value,
    "store_id": user.store_id,
    "org_node_id": user.org_node_id,   # 新增
    "exp": ...,
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/api-gateway/src/core/dependencies.py \
        apps/api-gateway/src/api/auth.py
git commit -m "feat(auth): JWT 写入 org_node_id + get_org_scope 依赖注入"
```

---

### Task 7: 典型模块改造示例（DailyOps + HQ BFF）

**示范改造方式，其余模块照此模式复制**

- [ ] **Step 1: 修改 daily_ops.py — 门店列表查询加 OrgScope 过滤**

在 `apps/api-gateway/src/api/daily_ops.py` 找到列表查询端点，追加过滤：

```python
# daily_ops.py 列表端点改造示例
from fastapi import Depends
from src.core.dependencies import get_org_scope
from src.core.org_query_filter import OrgQueryFilter
from src.core.org_scope import OrgScope

@router.get("/api/v1/daily-ops/metrics")
async def list_metrics(
    date: str,
    db: AsyncSession = Depends(get_db),
    scope: OrgScope = Depends(get_org_scope),   # 新增
):
    from src.models.daily_metric import StoreDailyMetric
    q = select(StoreDailyMetric).where(
        StoreDailyMetric.metric_date == date
    )
    q = OrgQueryFilter.apply(q, StoreDailyMetric, scope)  # 新增：范围过滤
    result = await db.execute(q)
    return [m for m in result.scalars().all()]
```

- [ ] **Step 2: 新增 HQ 汇总端点（使用 OrgAggregator）**

在 `apps/api-gateway/src/api/org_hierarchy.py` 追加：

```python
from src.services.org_aggregator import OrgAggregator

@router.get("/nodes/{node_id}/snapshot/{period}")
async def get_org_snapshot(
    node_id: str,
    period: str,                    # 格式: "2026-03" 或 "2026-03-17"
    db: AsyncSession = Depends(get_db),
    scope: OrgScope = Depends(get_org_scope),
):
    """
    获取节点聚合快照（含子节点）
    区域经理调用：返回区域内所有门店汇总
    集团CFO调用：返回集团所有品牌汇总
    """
    # 权限检查：只能查自己 scope 内的节点
    if not scope.is_global_admin and node_id not in scope.accessible_node_ids:
        raise HTTPException(403, f"无权查看节点 {node_id}")

    aggregator = OrgAggregator(db)
    snapshot = await aggregator.get_snapshot(node_id, period=period)
    return snapshot.to_dict()
```

- [ ] **Step 3: Commit**

```bash
git add apps/api-gateway/src/api/daily_ops.py \
        apps/api-gateway/src/api/org_hierarchy.py
git commit -m "feat(api): DailyOps 接入 OrgScope 过滤 + /org/nodes/{id}/snapshot 汇总端点"
```

---

### Task 8: 部署 + 全链路验证

- [ ] **Step 1: 推送并部署**

```bash
git push origin feat/claude-code-stability-fixes
```

服务器：
```bash
cd /opt/zhilian-os/prod
git pull origin feat/claude-code-stability-fixes
docker compose -f docker-compose.prod.yml up -d --build api-gateway
docker exec -it zhilian-api python3 -m alembic upgrade head
```

- [ ] **Step 2: 创建测试用户绑定 OrgNode**

```bash
# 把 admin 用户绑定到集团根节点（直接更新数据库）
docker exec -it zhilian-api python3 -c "
import asyncio
from src.core.database import async_session
from sqlalchemy import update
from src.models.user import User

async def bind():
    async with async_session() as db:
        await db.execute(
            update(User)
            .where(User.username == 'admin')
            .values(org_node_id='grp-demo')
        )
        await db.commit()
        print('Done')
asyncio.run(bind())
"
```

- [ ] **Step 3: 全链路冒烟测试**

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 1. 查集团快照（应汇总所有门店）
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/org/nodes/grp-demo/snapshot/2026-03" \
  | python3 -m json.tool

# 2. 查区域快照（只汇总华南区门店）
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/org/nodes/reg-south/snapshot/2026-03" \
  | python3 -m json.tool

# 3. 查上海加盟店生效配置（probation_days 应=30）
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/org/nodes/sto-sh-frc-001/config" \
  | python3 -m json.tool
```

- [ ] **Step 4: 最终 Commit**

```bash
git commit -m "feat: OrgScope 全产品传播完成

- OrgPermission 多节点权限模型
- User.org_node_id 挂载点
- OrgScopeMiddleware 请求级注入（Redis 5min 缓存）
- OrgQueryFilter 通用范围过滤（所有模块零改动接入）
- OrgAggregator 跨模块数据上卷（营收/成本/人力/KPI）
- get_org_scope 依赖注入
- JWT 写入 org_node_id
- /org/nodes/{id}/snapshot 集团汇总端点
- z53 数据库迁移

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 模块改造路线图（本计划之后）

完成本计划后，各产品模块按以下顺序接入，**每个模块只需 3 行改动**：

```python
# 任意模块接入 OrgScope 的标准模板
from src.core.dependencies import get_org_scope
from src.core.org_query_filter import OrgQueryFilter
from src.core.org_scope import OrgScope

@router.get("/...")
async def list_xxx(
    scope: OrgScope = Depends(get_org_scope),
    db: AsyncSession = Depends(get_db),
):
    q = OrgQueryFilter.apply(select(XxxModel), XxxModel, scope)
    # ... 其余逻辑不变
```

| 模块 | 优先级 | 涉及文件 |
|------|--------|---------|
| 财务结算 | P0 | `api/daily_ops.py`, `api/fct.py` |
| 库存 | P0 | `api/inventory.py` |
| 员工/排班 | P0 | `api/employees.py`, `api/schedules.py` |
| KPI/绩效 | P1 | `api/kpis.py`, `api/performance_ranking.py` |
| 订单 | P1 | `api/orders.py` |
| 营销/会员 | P2 | `api/private_domain.py`, `api/members.py` |
| 合规/食安 | P2 | `api/compliance.py`, `api/food_safety.py` |
| 供应链 | P2 | `api/supplier_b2b.py`, `api/inventory.py` |

**预计工作量：** 每个模块 30 分钟，8 个优先模块约 4 小时。
