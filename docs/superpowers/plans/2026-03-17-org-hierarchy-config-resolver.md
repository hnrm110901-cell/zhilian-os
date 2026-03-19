# OrgHierarchy + ConfigResolver 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为屯象OS建立多层级组织架构模型（集团→品牌→区域→城市→门店）和配置继承引擎，使每个层级可独立设置游戏规则，下层继承上层并可选择性覆盖。

**Architecture:** 引入 `OrgNode` 树形模型作为全局组织节点，`OrgConfig` 存储各节点的 KV 配置，`ConfigResolver` 服务按优先级链（门店→区域→品牌→集团→默认值）解析最终生效配置。Store 和 Employee 新增 `org_node_id` 外键挂载到节点树。

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, PostgreSQL ltree（路径查询）, Alembic z52, FastAPI, pytest-asyncio

---

## 文件清单

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| 新建 | `src/models/org_node.py` | OrgNode 树形模型 + StoreType/OperationMode/OrgNodeType 枚举 |
| 新建 | `src/models/org_config.py` | OrgConfig KV 配置存储（含 scope + key + value + 覆盖标记）|
| 修改 | `src/models/store.py` | 新增 `org_node_id`, `store_type`, `operation_mode` 字段 |
| 修改 | `src/models/employee.py` | 新增 `dept_node_id`（指向部门节点） |
| 修改 | `src/models/__init__.py` | 注册 OrgNode, OrgConfig |
| 新建 | `src/services/org_hierarchy_service.py` | 节点 CRUD、子树查询、scope 链构建 |
| 新建 | `src/services/config_resolver.py` | 继承链解析引擎（核心：resolve / resolve_all / set_config）|
| 新建 | `src/api/org_hierarchy.py` | REST 端点（节点树、配置读写）|
| 修改 | `src/main.py` | 注册 org_hierarchy router |
| 新建 | `alembic/versions/z52_org_hierarchy.py` | 数据库迁移 |
| 新建 | `src/seeds/org_hierarchy_seed.py` | 初始化"屯象示例集团"节点树 |
| 新建 | `tests/test_org_hierarchy_service.py` | 节点增删改查单测 |
| 新建 | `tests/test_config_resolver.py` | 继承、覆盖、默认值解析单测（核心！）|

---

## Chunk 1: 数据模型层

### Task 1: OrgNode 模型

**Files:**
- Create: `apps/api-gateway/src/models/org_node.py`

- [ ] **Step 1: 写失败测试（验证模型可实例化）**

```python
# tests/test_org_hierarchy_service.py
import pytest
from src.models.org_node import OrgNode, OrgNodeType, StoreType, OperationMode

def test_org_node_enums_exist():
    assert OrgNodeType.GROUP.value == "group"
    assert OrgNodeType.BRAND.value == "brand"
    assert OrgNodeType.REGION.value == "region"
    assert OrgNodeType.CITY.value == "city"
    assert OrgNodeType.STORE.value == "store"
    assert OrgNodeType.DEPARTMENT.value == "department"

def test_store_type_enums_exist():
    assert StoreType.FLAGSHIP.value == "flagship"
    assert StoreType.STANDARD.value == "standard"
    assert StoreType.MALL.value == "mall"
    assert StoreType.DARK_KITCHEN.value == "dark_kitchen"
    assert StoreType.FRANCHISE.value == "franchise"

def test_operation_mode_enums_exist():
    assert OperationMode.DIRECT.value == "direct"
    assert OperationMode.FRANCHISE.value == "franchise"
    assert OperationMode.JOINT.value == "joint"
    assert OperationMode.MANAGED.value == "managed"

def test_org_node_instantiation():
    node = OrgNode(
        id="group-001",
        name="徐记集团",
        node_type=OrgNodeType.GROUP,
        path="group-001",
        depth=0,
    )
    assert node.name == "徐记集团"
    assert node.node_type == OrgNodeType.GROUP
    assert node.parent_id is None
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
cd apps/api-gateway
pytest tests/test_org_hierarchy_service.py::test_org_node_enums_exist -v
# 预期: ImportError: cannot import name 'OrgNode'
```

- [ ] **Step 3: 创建 OrgNode 模型**

```python
# apps/api-gateway/src/models/org_node.py
"""
OrgNode — 通用组织层级节点
支持：集团 → 品牌 → 区域 → 城市 → 门店 → 部门（任意深度）
使用 path 字符串（ltree 风格）支持高效子树查询
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, Integer, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class OrgNodeType(str, enum.Enum):
    GROUP      = "group"       # 集团
    BRAND      = "brand"       # 品牌
    REGION     = "region"      # 大区（如华南区）
    CITY       = "city"        # 城市
    STORE      = "store"       # 门店
    DEPARTMENT = "department"  # 部门（门店内部，如前厅/后厨）


class StoreType(str, enum.Enum):
    FLAGSHIP     = "flagship"      # 旗舰店
    STANDARD     = "standard"      # 标准店
    MALL         = "mall"          # 购物中心店
    DARK_KITCHEN = "dark_kitchen"  # 暗厨/纯外卖
    FRANCHISE    = "franchise"     # 加盟店（门店层面标记）
    KIOSK        = "kiosk"         # 快取店/档口


class OperationMode(str, enum.Enum):
    DIRECT    = "direct"     # 直营
    FRANCHISE = "franchise"  # 加盟
    JOINT     = "joint"      # 联营
    MANAGED   = "managed"    # 托管


class OrgNode(Base, TimestampMixin):
    """
    通用组织节点树
    path 格式：parent_id.child_id.grandchild_id（点分隔，便于 LIKE 查询子树）
    示例：
      集团根节点  path="grp001"          depth=0
      品牌节点    path="grp001.brd001"   depth=1
      区域节点    path="grp001.brd001.reg001"  depth=2
      门店节点    path="grp001.brd001.reg001.sto001"  depth=3
    """
    __tablename__ = "org_nodes"

    id = Column(String(64), primary_key=True)          # 业务 ID，如 "grp-xj-001"
    name = Column(String(128), nullable=False)          # 显示名称
    code = Column(String(32), unique=True, nullable=True)  # 编码（可选，用于对接外部系统）
    node_type = Column(String(32), nullable=False, index=True)

    # 树形结构
    parent_id = Column(String(64), ForeignKey("org_nodes.id"), nullable=True, index=True)
    path = Column(String(512), nullable=False, index=True)  # 用点分隔的完整路径
    depth = Column(Integer, nullable=False, default=0)      # 层级深度，0=根

    # 门店级专属字段（node_type=store 时有意义）
    store_type     = Column(String(32), nullable=True)   # StoreType 枚举值
    operation_mode = Column(String(32), nullable=True)   # OperationMode 枚举值
    store_ref_id   = Column(String(50), ForeignKey("stores.id"), nullable=True)  # 关联 stores 表

    # 元数据
    description  = Column(Text, nullable=True)
    extra        = Column(JSON, default=dict)   # 扩展字段（如企微部门ID、POS编码）
    is_active    = Column(Boolean, default=True, nullable=False)
    sort_order   = Column(Integer, default=0)

    # 关系
    parent   = relationship("OrgNode", remote_side="OrgNode.id", foreign_keys=[parent_id])
    configs  = relationship("OrgConfig", back_populates="org_node", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<OrgNode(id='{self.id}', name='{self.name}', type='{self.node_type}', path='{self.path}')>"

    def get_ancestor_ids(self) -> list[str]:
        """从 path 解析出所有祖先节点 ID（从根到父）"""
        parts = self.path.split(".")
        return parts[:-1]  # 排除自身

    def is_ancestor_of(self, other_path: str) -> bool:
        """判断本节点是否是另一个节点的祖先"""
        return other_path.startswith(self.path + ".")
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest tests/test_org_hierarchy_service.py::test_org_node_enums_exist \
       tests/test_org_hierarchy_service.py::test_store_type_enums_exist \
       tests/test_org_hierarchy_service.py::test_operation_mode_enums_exist \
       tests/test_org_hierarchy_service.py::test_org_node_instantiation -v
# 预期: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/models/org_node.py \
        apps/api-gateway/tests/test_org_hierarchy_service.py
git commit -m "feat(models): 新增 OrgNode 树形组织模型 + StoreType/OperationMode 枚举"
```

---

### Task 2: OrgConfig 模型

**Files:**
- Create: `apps/api-gateway/src/models/org_config.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_org_hierarchy_service.py
from src.models.org_config import OrgConfig

def test_org_config_instantiation():
    cfg = OrgConfig(
        org_node_id="store-001",
        config_key="max_consecutive_work_days",
        config_value="6",
        value_type="int",
        is_override=False,
    )
    assert cfg.config_key == "max_consecutive_work_days"
    assert cfg.typed_value() == 6

def test_org_config_override_flag():
    cfg = OrgConfig(
        org_node_id="store-001",
        config_key="split_shift_allowed",
        config_value="false",
        value_type="bool",
        is_override=True,  # 此节点明确覆盖父级
    )
    assert cfg.typed_value() is False
    assert cfg.is_override is True
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/test_org_hierarchy_service.py::test_org_config_instantiation -v
# 预期: ImportError
```

- [ ] **Step 3: 创建 OrgConfig 模型**

```python
# apps/api-gateway/src/models/org_config.py
"""
OrgConfig — 组织节点配置存储
每行 = 某节点在某 config_key 上的配置值
ConfigResolver 负责按继承链读取最终生效值
"""
import uuid
import json
from sqlalchemy import Column, String, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


# 已知 config_key 常量（不枚举，允许自由扩展）
class ConfigKey:
    # ── 排班规则 ──────────────────────────────────
    MAX_CONSECUTIVE_WORK_DAYS = "max_consecutive_work_days"   # int, 默认 6
    MIN_REST_HOURS_BETWEEN_SHIFTS = "min_rest_hours"          # int, 默认 8
    SPLIT_SHIFT_ALLOWED = "split_shift_allowed"               # bool, 默认 false
    OVERTIME_MULTIPLIER = "overtime_multiplier"               # float, 默认 1.5
    WEEKEND_PREMIUM = "weekend_premium"                       # float, 默认 1.0

    # ── 人力成本 ──────────────────────────────────
    LABOR_COST_RATIO_TARGET = "labor_cost_ratio_target"       # float, 默认 0.30
    MIN_HOURLY_WAGE = "min_hourly_wage"                       # float（元/小时）

    # ── 试用期规则 ────────────────────────────────
    PROBATION_DAYS = "probation_days"                         # int, 默认 90
    TRIAL_DAYS = "trial_days"                                 # int, 默认 3

    # ── KPI 基线 ──────────────────────────────────
    CUSTOMER_SATISFACTION_TARGET = "csat_target"             # float, 默认 4.5
    FOOD_COST_RATIO_TARGET = "food_cost_ratio_target"         # float, 默认 0.35

    # ── 企业微信 ──────────────────────────────────
    WECHAT_CORP_ID = "wechat_corp_id"                         # str
    WECHAT_AGENT_ID = "wechat_agent_id"                       # str

    # ── 考勤 ──────────────────────────────────────
    ATTENDANCE_GRACE_MINUTES = "attendance_grace_minutes"     # int, 默认 5（迟到宽限）
    ATTENDANCE_MODE = "attendance_mode"                       # str: wechat/machine/manual


class OrgConfig(Base, TimestampMixin):
    """
    组织节点配置行
    唯一约束：(org_node_id, config_key)
    """
    __tablename__ = "org_configs"
    __table_args__ = (
        UniqueConstraint("org_node_id", "config_key", name="uq_org_config_node_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_node_id  = Column(String(64), ForeignKey("org_nodes.id"), nullable=False, index=True)
    config_key   = Column(String(128), nullable=False, index=True)
    config_value = Column(Text, nullable=False)           # 序列化为字符串存储
    value_type   = Column(String(16), default="str")      # str / int / float / bool / json
    description  = Column(Text, nullable=True)            # 可选说明
    is_override  = Column(Boolean, default=False)         # True = 明确覆盖父节点（不继续向上查找）
    set_by       = Column(String(64), nullable=True)      # 设置人 user_id

    # 关系
    org_node = relationship("OrgNode", back_populates="configs")

    def typed_value(self):
        """返回强类型值"""
        v = self.config_value
        if self.value_type == "int":
            return int(v)
        if self.value_type == "float":
            return float(v)
        if self.value_type == "bool":
            return v.lower() in ("true", "1", "yes")
        if self.value_type == "json":
            return json.loads(v)
        return v  # str

    def __repr__(self):
        return f"<OrgConfig(node='{self.org_node_id}', key='{self.config_key}', value='{self.config_value}')>"
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest tests/test_org_hierarchy_service.py::test_org_config_instantiation \
       tests/test_org_hierarchy_service.py::test_org_config_override_flag -v
# 预期: 2 passed
```

- [ ] **Step 5: 注册模型 + Commit**

```python
# apps/api-gateway/src/models/__init__.py — 在现有 imports 末尾追加
from .org_node import OrgNode, OrgNodeType, StoreType, OperationMode
from .org_config import OrgConfig, ConfigKey
```

```bash
git add apps/api-gateway/src/models/org_config.py \
        apps/api-gateway/src/models/__init__.py
git commit -m "feat(models): 新增 OrgConfig 配置存储模型 + ConfigKey 常量表"
```

---

### Task 3: Store + Employee 模型扩展

**Files:**
- Modify: `apps/api-gateway/src/models/store.py`
- Modify: `apps/api-gateway/src/models/employee.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_org_hierarchy_service.py
from src.models.store import Store

def test_store_has_org_node_id():
    """Store 必须有 org_node_id 和 operation_mode 字段"""
    cols = {c.key for c in Store.__table__.columns}
    assert "org_node_id" in cols
    assert "store_type" in cols
    assert "operation_mode" in cols

from src.models.employee import Employee

def test_employee_has_dept_node_id():
    cols = {c.key for c in Employee.__table__.columns}
    assert "dept_node_id" in cols
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/test_org_hierarchy_service.py::test_store_has_org_node_id -v
# 预期: AssertionError (字段不存在)
```

- [ ] **Step 3: 修改 Store 模型**

在 `apps/api-gateway/src/models/store.py` 的 `brand_id` 字段后追加：

```python
# 追加到 store.py class Store 的字段区，brand_id 之后
from sqlalchemy import Column, String, ForeignKey   # 确保 ForeignKey 已 import

# 组织层级挂载点
org_node_id    = Column(String(64), ForeignKey("org_nodes.id"), nullable=True, index=True)
store_type     = Column(String(32), nullable=True)   # StoreType 枚举值
operation_mode = Column(String(32), nullable=True)   # OperationMode 枚举值
```

同时在 `to_dict()` 方法中追加三个字段：
```python
"org_node_id":    self.org_node_id,
"store_type":     self.store_type,
"operation_mode": self.operation_mode,
```

- [ ] **Step 4: 修改 Employee 模型**

在 `apps/api-gateway/src/models/employee.py` 的 `store_id` 字段后追加：

```python
# 部门节点（指向 org_nodes 中 node_type=department 的节点）
dept_node_id = Column(String(64), ForeignKey("org_nodes.id"), nullable=True, index=True)
```

- [ ] **Step 5: 跑测试，确认通过**

```bash
pytest tests/test_org_hierarchy_service.py::test_store_has_org_node_id \
       tests/test_org_hierarchy_service.py::test_employee_has_dept_node_id -v
# 预期: 2 passed
```

- [ ] **Step 6: Commit**

```bash
git add apps/api-gateway/src/models/store.py \
        apps/api-gateway/src/models/employee.py
git commit -m "feat(models): Store/Employee 新增 org_node_id 组织树挂载字段"
```

---

### Task 4: Alembic 迁移 z52

**Files:**
- Create: `apps/api-gateway/alembic/versions/z52_org_hierarchy.py`

- [ ] **Step 1: 创建迁移文件**

```python
# apps/api-gateway/alembic/versions/z52_org_hierarchy.py
"""z52 org_hierarchy — 组织层级模型 + Store/Employee 字段扩展

Revision ID: z52
Revises: z51
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z52'
down_revision = 'z51'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. org_nodes 表 ───────────────────────────────────────────────
    op.create_table(
        'org_nodes',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('code', sa.String(32), unique=True, nullable=True),
        sa.Column('node_type', sa.String(32), nullable=False),
        sa.Column('parent_id', sa.String(64), sa.ForeignKey('org_nodes.id'), nullable=True),
        sa.Column('path', sa.String(512), nullable=False),
        sa.Column('depth', sa.Integer, nullable=False, server_default='0'),
        sa.Column('store_type', sa.String(32), nullable=True),
        sa.Column('operation_mode', sa.String(32), nullable=True),
        sa.Column('store_ref_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('extra', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_org_nodes_node_type', 'org_nodes', ['node_type'])
    op.create_index('ix_org_nodes_parent_id', 'org_nodes', ['parent_id'])
    op.create_index('ix_org_nodes_path', 'org_nodes', ['path'])

    # ── 2. org_configs 表 ────────────────────────────────────────────
    op.create_table(
        'org_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_node_id', sa.String(64), sa.ForeignKey('org_nodes.id'), nullable=False),
        sa.Column('config_key', sa.String(128), nullable=False),
        sa.Column('config_value', sa.Text, nullable=False),
        sa.Column('value_type', sa.String(16), server_default='str'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_override', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('set_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('org_node_id', 'config_key', name='uq_org_config_node_key'),
    )
    op.create_index('ix_org_configs_node_id', 'org_configs', ['org_node_id'])
    op.create_index('ix_org_configs_key', 'org_configs', ['config_key'])

    # ── 3. stores 表新增字段 ─────────────────────────────────────────
    op.add_column('stores', sa.Column('org_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id'), nullable=True))
    op.add_column('stores', sa.Column('store_type', sa.String(32), nullable=True))
    op.add_column('stores', sa.Column('operation_mode', sa.String(32), nullable=True))
    op.create_index('ix_stores_org_node_id', 'stores', ['org_node_id'])

    # ── 4. employees 表新增字段 ──────────────────────────────────────
    op.add_column('employees', sa.Column('dept_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id'), nullable=True))
    op.create_index('ix_employees_dept_node_id', 'employees', ['dept_node_id'])


def downgrade() -> None:
    op.drop_index('ix_employees_dept_node_id', 'employees')
    op.drop_column('employees', 'dept_node_id')
    op.drop_index('ix_stores_org_node_id', 'stores')
    op.drop_column('stores', 'operation_mode')
    op.drop_column('stores', 'store_type')
    op.drop_column('stores', 'org_node_id')
    op.drop_index('ix_org_configs_key', 'org_configs')
    op.drop_index('ix_org_configs_node_id', 'org_configs')
    op.drop_table('org_configs')
    op.drop_index('ix_org_nodes_path', 'org_nodes')
    op.drop_index('ix_org_nodes_parent_id', 'org_nodes')
    op.drop_index('ix_org_nodes_node_type', 'org_nodes')
    op.drop_table('org_nodes')
```

- [ ] **Step 2: 验证迁移文件语法**

```bash
cd apps/api-gateway
python3 -c "import alembic.versions.z52_org_hierarchy; print('OK')"
# 预期: OK
```

- [ ] **Step 3: Commit**

```bash
git add apps/api-gateway/alembic/versions/z52_org_hierarchy.py
git commit -m "feat(migration): z52 新增 org_nodes + org_configs 表，Store/Employee 加字段"
```

---

## Chunk 2: ConfigResolver 核心引擎

### Task 5: ConfigResolver 服务（最核心）

**Files:**
- Create: `apps/api-gateway/src/services/config_resolver.py`
- Test: `apps/api-gateway/tests/test_config_resolver.py`

- [ ] **Step 1: 写失败测试（覆盖继承、覆盖、默认值三大场景）**

```python
# apps/api-gateway/tests/test_config_resolver.py
"""
ConfigResolver 单元测试
不依赖数据库：用内存 OrgNode/OrgConfig 对象直接测试解析逻辑
"""
import pytest
from src.services.config_resolver import ConfigResolver
from src.models.org_node import OrgNode, OrgNodeType
from src.models.org_config import OrgConfig, ConfigKey


def make_node(id_, name, parent_id=None, depth=0, path=None) -> OrgNode:
    path = path or id_
    node = OrgNode()
    node.id = id_
    node.name = name
    node.node_type = OrgNodeType.STORE if depth > 0 else OrgNodeType.GROUP
    node.parent_id = parent_id
    node.path = path
    node.depth = depth
    node.configs = []
    return node


def make_config(node_id, key, value, value_type="str", is_override=False) -> OrgConfig:
    cfg = OrgConfig()
    cfg.org_node_id = node_id
    cfg.config_key = key
    cfg.config_value = value
    cfg.value_type = value_type
    cfg.is_override = is_override
    return cfg


# ── 场景 1: 无配置时返回默认值 ──────────────────────────────────────────
def test_resolve_returns_default_when_no_config():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve(
        node_id="sto",
        key=ConfigKey.MAX_CONSECUTIVE_WORK_DAYS,
        default=6,
    )
    assert result == 6


# ── 场景 2: 子节点继承父节点配置 ────────────────────────────────────────
def test_resolve_inherits_from_parent():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    # 集团设置了配置，门店没有
    group.configs = [
        make_config("grp", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "5", "int")
    ]
    store.configs = []

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("sto", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, default=6)
    assert result == 5  # 继承自集团


# ── 场景 3: 门店配置覆盖集团配置 ────────────────────────────────────────
def test_resolve_store_overrides_group():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    group.configs = [
        make_config("grp", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "5", "int")
    ]
    store.configs = [
        make_config("sto", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "4", "int", is_override=True)
    ]

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("sto", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, default=6)
    assert result == 4  # 门店自己覆盖


# ── 场景 4: 三层继承（集团→品牌→门店）────────────────────────────────
def test_resolve_three_level_chain():
    group  = make_node("grp", "集团", depth=0, path="grp")
    brand  = make_node("brd", "品牌A", parent_id="grp", depth=1, path="grp.brd")
    store  = make_node("sto", "门店A", parent_id="brd", depth=2, path="grp.brd.sto")

    group.configs = [make_config("grp", ConfigKey.PROBATION_DAYS, "90", "int")]
    brand.configs = [make_config("brd", ConfigKey.PROBATION_DAYS, "60", "int")]
    store.configs = []  # 门店没配置，继承品牌的

    node_map = {"grp": group, "brd": brand, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("sto", ConfigKey.PROBATION_DAYS, default=90)
    assert result == 60  # 最近的祖先（品牌）生效


# ── 场景 5: resolve_all 返回完整配置字典 ────────────────────────────────
def test_resolve_all_merges_chain():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    group.configs = [
        make_config("grp", ConfigKey.PROBATION_DAYS, "90", "int"),
        make_config("grp", ConfigKey.OVERTIME_MULTIPLIER, "1.5", "float"),
    ]
    store.configs = [
        make_config("sto", ConfigKey.OVERTIME_MULTIPLIER, "2.0", "float", is_override=True),
    ]

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    all_cfg = resolver.resolve_all("sto")
    assert all_cfg[ConfigKey.PROBATION_DAYS] == 90        # 继承集团
    assert all_cfg[ConfigKey.OVERTIME_MULTIPLIER] == 2.0  # 门店覆盖


# ── 场景 6: bool 类型正确解析 ────────────────────────────────────────────
def test_resolve_bool_type():
    group = make_node("grp", "集团", depth=0, path="grp")
    group.configs = [
        make_config("grp", ConfigKey.SPLIT_SHIFT_ALLOWED, "true", "bool")
    ]
    node_map = {"grp": group}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("grp", ConfigKey.SPLIT_SHIFT_ALLOWED, default=False)
    assert result is True
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/test_config_resolver.py -v
# 预期: ImportError: cannot import name 'ConfigResolver'
```

- [ ] **Step 3: 实现 ConfigResolver**

```python
# apps/api-gateway/src/services/config_resolver.py
"""
ConfigResolver — 组织配置继承引擎

解析规则（优先级从高到低）：
  1. 当前节点自身配置
  2. 父节点配置（逐层向上直到根）
  3. 默认值

is_override=True 的配置：
  表示该节点"强制覆盖"，不向上继承同 key 的祖先值。
  实际上默认行为就是就近优先，is_override=True 仅作标注，
  提醒运维"这个值是主动覆盖的，不要轻易删除"。
"""
from __future__ import annotations
from typing import Any, Optional
from src.models.org_node import OrgNode
from src.models.org_config import OrgConfig


class ConfigResolver:
    """
    纯内存解析器（不直接依赖数据库，方便单元测试和缓存）

    使用方式（在 Service 层）：
        nodes = await org_hierarchy_service.get_scope_chain(store_id)
        node_map = {n.id: n for n in nodes}
        resolver = ConfigResolver(node_map=node_map)
        value = resolver.resolve(store_id, ConfigKey.PROBATION_DAYS, default=90)
    """

    def __init__(self, node_map: dict[str, OrgNode]):
        """
        node_map: {node_id -> OrgNode}（OrgNode.configs 已预加载）
        """
        self._node_map = node_map

    def _get_scope_chain(self, node_id: str) -> list[OrgNode]:
        """
        返回从当前节点到根节点的路径（当前节点在前，根节点在后）
        基于 path 字段构造，O(depth) 时间复杂度
        """
        node = self._node_map.get(node_id)
        if not node:
            return []

        # 从 path 解析祖先链，如 "grp.brd.sto" → ["grp", "brd", "sto"]
        path_parts = node.path.split(".")
        chain: list[OrgNode] = []
        for part in reversed(path_parts):  # 从当前节点往上
            ancestor = self._node_map.get(part)
            if ancestor:
                chain.append(ancestor)
        return chain  # chain[0] = 当前节点, chain[-1] = 根节点

    def _find_config(self, node: OrgNode, key: str) -> Optional[OrgConfig]:
        """在指定节点的 configs 列表中查找 key"""
        for cfg in (node.configs or []):
            if cfg.config_key == key:
                return cfg
        return None

    def resolve(self, node_id: str, key: str, default: Any = None) -> Any:
        """
        解析指定节点在指定 key 上的最终生效值

        就近原则：当前节点 > 父节点 > 祖父节点 > ... > 默认值
        """
        chain = self._get_scope_chain(node_id)
        for node in chain:
            cfg = self._find_config(node, key)
            if cfg is not None:
                return cfg.typed_value()
        return default

    def resolve_all(self, node_id: str) -> dict[str, Any]:
        """
        返回该节点所有配置 key 的最终生效值字典
        合并所有祖先节点的配置，当前节点优先级最高
        """
        chain = self._get_scope_chain(node_id)
        # 从根节点往下合并（后面的覆盖前面的 = 当前节点优先）
        merged: dict[str, Any] = {}
        for node in reversed(chain):  # 根节点先写，当前节点后写（覆盖）
            for cfg in (node.configs or []):
                merged[cfg.config_key] = cfg.typed_value()
        return merged

    def set_config(
        self,
        node: OrgNode,
        key: str,
        value: Any,
        value_type: str = "str",
        is_override: bool = False,
    ) -> OrgConfig:
        """
        在内存中设置节点配置（调用方负责持久化到数据库）
        如果 key 已存在则更新，否则新建
        """
        existing = self._find_config(node, key)
        if existing:
            existing.config_value = str(value)
            existing.value_type = value_type
            existing.is_override = is_override
            return existing

        cfg = OrgConfig()
        cfg.org_node_id = node.id
        cfg.config_key = key
        cfg.config_value = str(value)
        cfg.value_type = value_type
        cfg.is_override = is_override
        if node.configs is None:
            node.configs = []
        node.configs.append(cfg)
        return cfg
```

- [ ] **Step 4: 跑全部测试**

```bash
pytest tests/test_config_resolver.py -v
# 预期: 6 passed
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/services/config_resolver.py \
        apps/api-gateway/tests/test_config_resolver.py
git commit -m "feat(service): ConfigResolver 继承链解析引擎，6个单测覆盖全场景"
```

---

## Chunk 3: OrgHierarchyService（数据库操作层）

### Task 6: OrgHierarchyService

**Files:**
- Create: `apps/api-gateway/src/services/org_hierarchy_service.py`

- [ ] **Step 1: 写核心接口测试**

```python
# 追加到 tests/test_org_hierarchy_service.py
# （需要数据库，用 pytest-asyncio + 测试 DB fixture，可先 skip）
import pytest

@pytest.mark.skip(reason="需要测试数据库，集成测试阶段执行")
async def test_create_and_get_node():
    """TODO: 集成测试 — 创建节点并查询"""
    pass

@pytest.mark.skip(reason="需要测试数据库")
async def test_get_subtree():
    """TODO: 集成测试 — 子树查询"""
    pass
```

- [ ] **Step 2: 实现 OrgHierarchyService**

```python
# apps/api-gateway/src/services/org_hierarchy_service.py
"""
OrgHierarchyService — 组织层级 CRUD + 查询
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.models.org_node import OrgNode
from src.models.org_config import OrgConfig
from src.services.config_resolver import ConfigResolver
import structlog

logger = structlog.get_logger()


class OrgHierarchyService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 节点 CRUD ──────────────────────────────────────────────────────

    async def create_node(
        self,
        id_: str,
        name: str,
        node_type: str,
        parent_id: Optional[str] = None,
        **kwargs,
    ) -> OrgNode:
        """创建组织节点，自动计算 path 和 depth"""
        if parent_id:
            parent = await self.get_node(parent_id)
            if not parent:
                raise ValueError(f"父节点不存在: {parent_id}")
            path = f"{parent.path}.{id_}"
            depth = parent.depth + 1
        else:
            path = id_
            depth = 0

        node = OrgNode(
            id=id_,
            name=name,
            node_type=node_type,
            parent_id=parent_id,
            path=path,
            depth=depth,
            **kwargs,
        )
        self.db.add(node)
        await self.db.flush()
        logger.info("org_node_created", node_id=id_, node_type=node_type, path=path)
        return node

    async def get_node(self, node_id: str) -> Optional[OrgNode]:
        result = await self.db.execute(
            select(OrgNode).where(OrgNode.id == node_id)
        )
        return result.scalar_one_or_none()

    async def get_subtree(self, node_id: str) -> list[OrgNode]:
        """返回以 node_id 为根的整棵子树（含自身）"""
        node = await self.get_node(node_id)
        if not node:
            return []
        # path LIKE 'node_id%' 匹配自身及所有后代
        result = await self.db.execute(
            select(OrgNode).where(
                OrgNode.path.like(f"{node.path}%")
            ).order_by(OrgNode.depth, OrgNode.sort_order)
        )
        return list(result.scalars().all())

    async def get_scope_chain(self, node_id: str) -> list[OrgNode]:
        """
        返回从当前节点到根节点的路径链（含配置预加载）
        用于 ConfigResolver 初始化
        """
        node = await self.get_node(node_id)
        if not node:
            return []
        ancestor_ids = node.path.split(".")
        result = await self.db.execute(
            select(OrgNode).where(OrgNode.id.in_(ancestor_ids))
        )
        nodes = {n.id: n for n in result.scalars().all()}

        # 预加载各节点的 configs
        cfg_result = await self.db.execute(
            select(OrgConfig).where(OrgConfig.org_node_id.in_(ancestor_ids))
        )
        configs_by_node: dict[str, list[OrgConfig]] = {}
        for cfg in cfg_result.scalars().all():
            configs_by_node.setdefault(cfg.org_node_id, []).append(cfg)
        for nid, node_obj in nodes.items():
            node_obj.configs = configs_by_node.get(nid, [])

        return list(nodes.values())

    # ── 配置 CRUD ──────────────────────────────────────────────────────

    async def set_config(
        self,
        node_id: str,
        key: str,
        value: str,
        value_type: str = "str",
        is_override: bool = False,
        set_by: Optional[str] = None,
    ) -> OrgConfig:
        """设置节点配置（upsert）"""
        result = await self.db.execute(
            select(OrgConfig).where(
                OrgConfig.org_node_id == node_id,
                OrgConfig.config_key == key,
            )
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            cfg.config_value = value
            cfg.value_type = value_type
            cfg.is_override = is_override
            if set_by:
                cfg.set_by = set_by
        else:
            cfg = OrgConfig(
                org_node_id=node_id,
                config_key=key,
                config_value=value,
                value_type=value_type,
                is_override=is_override,
                set_by=set_by,
            )
            self.db.add(cfg)
        await self.db.flush()
        return cfg

    async def get_resolver(self, node_id: str) -> ConfigResolver:
        """获取针对指定节点的 ConfigResolver（已预加载继承链）"""
        chain = await self.get_scope_chain(node_id)
        node_map = {n.id: n for n in chain}
        return ConfigResolver(node_map=node_map)

    async def resolve(self, node_id: str, key: str, default=None):
        """便捷方法：直接解析一个配置值"""
        resolver = await self.get_resolver(node_id)
        return resolver.resolve(node_id, key, default=default)
```

- [ ] **Step 3: Commit**

```bash
git add apps/api-gateway/src/services/org_hierarchy_service.py
git commit -m "feat(service): OrgHierarchyService CRUD + 子树查询 + ConfigResolver 集成"
```

---

## Chunk 4: API 端点 + Seed 数据 + 系统集成

### Task 7: API 路由

**Files:**
- Create: `apps/api-gateway/src/api/org_hierarchy.py`
- Modify: `apps/api-gateway/src/main.py`

- [ ] **Step 1: 创建路由文件**

```python
# apps/api-gateway/src/api/org_hierarchy.py
"""
OrgHierarchy API
GET  /api/v1/org/nodes/{node_id}          — 获取节点详情
GET  /api/v1/org/nodes/{node_id}/subtree  — 获取子树
GET  /api/v1/org/nodes/{node_id}/config   — 获取节点生效配置（含继承）
POST /api/v1/org/nodes                    — 创建节点
POST /api/v1/org/nodes/{node_id}/config   — 设置节点配置
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.org_hierarchy_service import OrgHierarchyService

router = APIRouter(prefix="/api/v1/org", tags=["org-hierarchy"])


class CreateNodeRequest(BaseModel):
    id: str
    name: str
    node_type: str
    parent_id: Optional[str] = None
    store_type: Optional[str] = None
    operation_mode: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0


class SetConfigRequest(BaseModel):
    key: str
    value: str
    value_type: str = "str"
    is_override: bool = False
    description: Optional[str] = None


@router.get("/nodes/{node_id}")
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgHierarchyService(db)
    node = await svc.get_node(node_id)
    if not node:
        raise HTTPException(404, f"节点不存在: {node_id}")
    return {
        "id": node.id, "name": node.name, "node_type": node.node_type,
        "parent_id": node.parent_id, "path": node.path, "depth": node.depth,
        "store_type": node.store_type, "operation_mode": node.operation_mode,
    }


@router.get("/nodes/{node_id}/subtree")
async def get_subtree(node_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgHierarchyService(db)
    nodes = await svc.get_subtree(node_id)
    return [{"id": n.id, "name": n.name, "node_type": n.node_type,
              "parent_id": n.parent_id, "depth": n.depth} for n in nodes]


@router.get("/nodes/{node_id}/config")
async def get_effective_config(node_id: str, db: AsyncSession = Depends(get_db)):
    """返回该节点继承链解析后的所有生效配置"""
    svc = OrgHierarchyService(db)
    resolver = await svc.get_resolver(node_id)
    return resolver.resolve_all(node_id)


@router.post("/nodes", status_code=201)
async def create_node(req: CreateNodeRequest, db: AsyncSession = Depends(get_db)):
    svc = OrgHierarchyService(db)
    node = await svc.create_node(
        id_=req.id, name=req.name, node_type=req.node_type,
        parent_id=req.parent_id, store_type=req.store_type,
        operation_mode=req.operation_mode, description=req.description,
        sort_order=req.sort_order,
    )
    await db.commit()
    return {"id": node.id, "path": node.path, "depth": node.depth}


@router.post("/nodes/{node_id}/config", status_code=200)
async def set_config(
    node_id: str, req: SetConfigRequest, db: AsyncSession = Depends(get_db)
):
    svc = OrgHierarchyService(db)
    node = await svc.get_node(node_id)
    if not node:
        raise HTTPException(404, f"节点不存在: {node_id}")
    cfg = await svc.set_config(
        node_id=node_id, key=req.key, value=req.value,
        value_type=req.value_type, is_override=req.is_override,
    )
    await db.commit()
    return {"node_id": node_id, "key": cfg.config_key,
            "effective_value": cfg.typed_value()}
```

- [ ] **Step 2: 注册到 main.py**

在 `apps/api-gateway/src/main.py` 找到现有 router 注册区，追加：

```python
from src.api.org_hierarchy import router as org_hierarchy_router
app.include_router(org_hierarchy_router)
```

- [ ] **Step 3: Commit**

```bash
git add apps/api-gateway/src/api/org_hierarchy.py \
        apps/api-gateway/src/main.py
git commit -m "feat(api): 新增 /api/v1/org 组织层级 + 配置管理端点"
```

---

### Task 8: Seed 数据（示例集团节点树）

**Files:**
- Create: `apps/api-gateway/src/seeds/org_hierarchy_seed.py`

- [ ] **Step 1: 创建 Seed 脚本**

```python
# apps/api-gateway/src/seeds/org_hierarchy_seed.py
"""
初始化示例集团的组织层级树
运行：docker exec -it -w /app zhilian-api python3 -m src.seeds.org_hierarchy_seed
"""
import asyncio
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.core.config import get_settings
from src.services.org_hierarchy_service import OrgHierarchyService
from src.models.org_config import ConfigKey

logger = structlog.get_logger()
settings = get_settings()


SAMPLE_TREE = [
    # (id, name, node_type, parent_id, store_type, operation_mode)
    ("grp-demo",       "屯象示例集团",   "group",  None,       None,            None),
    ("brd-zhengcan",   "示例正餐品牌",   "brand",  "grp-demo", None,            None),
    ("brd-kuaican",    "示例快餐品牌",   "brand",  "grp-demo", None,            None),
    ("reg-south",      "华南区",        "region", "brd-zhengcan", None,         None),
    ("reg-east",       "华东区",        "region", "brd-zhengcan", None,         None),
    ("sto-gz-001",     "广州旗舰店",     "store",  "reg-south", "flagship",     "direct"),
    ("sto-sz-001",     "深圳购物中心店", "store",  "reg-south", "mall",         "direct"),
    ("sto-sh-frc-001", "上海加盟店A",   "store",  "reg-east",  "franchise",    "franchise"),
    ("dept-gz-front",  "广州旗舰-前厅", "department", "sto-gz-001", None,      None),
    ("dept-gz-kitchen","广州旗舰-后厨", "department", "sto-gz-001", None,      None),
]

SAMPLE_CONFIGS = [
    # (node_id, key, value, value_type, is_override)
    # 集团级默认配置
    ("grp-demo", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS,   "6",    "int",   False),
    ("grp-demo", ConfigKey.MIN_REST_HOURS_BETWEEN_SHIFTS,"8",   "int",   False),
    ("grp-demo", ConfigKey.PROBATION_DAYS,              "90",   "int",   False),
    ("grp-demo", ConfigKey.OVERTIME_MULTIPLIER,         "1.5",  "float", False),
    ("grp-demo", ConfigKey.FOOD_COST_RATIO_TARGET,      "0.35", "float", False),
    ("grp-demo", ConfigKey.ATTENDANCE_GRACE_MINUTES,    "5",    "int",   False),
    # 快餐品牌：连续上班天数更严
    ("brd-kuaican", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "5",   "int",   True),
    ("brd-kuaican", ConfigKey.SPLIT_SHIFT_ALLOWED,       "true","bool",  True),
    # 华东区（上海）：劳动法加班系数更高
    ("reg-east", ConfigKey.OVERTIME_MULTIPLIER,          "2.0", "float", True),
    # 加盟店：试用期更短（加盟商自定义）
    ("sto-sh-frc-001", ConfigKey.PROBATION_DAYS,         "30",  "int",   True),
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        svc = OrgHierarchyService(db)
        created_nodes = skipped_nodes = created_configs = skipped_configs = 0

        # 节点
        for id_, name, node_type, parent_id, store_type, op_mode in SAMPLE_TREE:
            existing = await svc.get_node(id_)
            if existing:
                skipped_nodes += 1
                continue
            await svc.create_node(
                id_=id_, name=name, node_type=node_type, parent_id=parent_id,
                store_type=store_type, operation_mode=op_mode,
            )
            created_nodes += 1
            logger.info("写入节点", id=id_, name=name)

        # 配置
        for node_id, key, value, value_type, is_override in SAMPLE_CONFIGS:
            await svc.set_config(
                node_id=node_id, key=key, value=value,
                value_type=value_type, is_override=is_override,
            )
            created_configs += 1

        await db.commit()

    print(f"\n组织层级种子数据写入完成:")
    print(f"  节点  — 新增: {created_nodes}, 跳过: {skipped_nodes}")
    print(f"  配置  — 写入: {created_configs}")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Commit**

```bash
git add apps/api-gateway/src/seeds/org_hierarchy_seed.py
git commit -m "feat(seeds): 屯象示例集团节点树 seed（10节点 + 12项继承配置）"
```

---

### Task 9: 部署验证

- [ ] **Step 1: TS 编译检查（前端无变更，快速确认）**

```bash
cd apps/web && npx tsc --noEmit --skipLibCheck
# 预期: 零错误
```

- [ ] **Step 2: 推送并部署到生产**

```bash
cd /Users/lichun/tunxiang
git push origin feat/claude-code-stability-fixes
```

服务器执行：
```bash
cd /opt/zhilian-os/prod
git pull origin feat/claude-code-stability-fixes
docker compose -f docker-compose.prod.yml up -d --build api-gateway

# 运行迁移
docker exec -it zhilian-api python3 -m alembic upgrade head

# 运行 Seed
docker exec -it -w /app zhilian-api python3 -m src.seeds.org_hierarchy_seed
```

- [ ] **Step 3: 冒烟测试**

```bash
# 获取 token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 查询示例集团节点
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/org/nodes/grp-demo | python3 -m json.tool

# 查询广州旗舰店的生效配置（应继承集团配置）
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/org/nodes/sto-gz-001/config | python3 -m json.tool

# 查询上海加盟店配置（probation_days 应为 30，覆盖集团的 90）
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/org/nodes/sto-sh-frc-001/config | python3 -m json.tool
# 预期: probation_days=30, overtime_multiplier=2.0（继承华东区）
```

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "feat: OrgHierarchy + ConfigResolver 完整上线

- OrgNode 树形模型（6种节点类型）
- OrgConfig KV 配置存储
- ConfigResolver 继承链引擎（6个单测）
- OrgHierarchyService CRUD + 子树查询
- /api/v1/org 完整 REST 端点
- z52 数据库迁移
- 示例集团 Seed（10节点 + 12项分层配置）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 后续扩展路径（本计划不含）

| 功能 | 依赖本计划 | 说明 |
|------|-----------|------|
| 权限隔离中间件 | ✅ OrgNode | `OrgScopeMiddleware` 按 path LIKE 过滤数据 |
| 企微组织架构同步 | ✅ OrgNode | 把企微部门树同步到 org_nodes |
| HR 岗位标准层级化 | ✅ OrgNode | JobStandard 加 `org_node_id` 字段 |
| 排班规则继承 | ✅ ConfigResolver | ScheduleAgent 调 `resolve(store_id, key)` |
| 跨店人力调度 | ✅ get_subtree | 基于子树查询同区域可用人力 |
