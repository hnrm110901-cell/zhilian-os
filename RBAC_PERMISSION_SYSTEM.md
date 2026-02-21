# RBAC权限系统文档

## 概述

智联OS采用基于角色的访问控制(RBAC)系统，为不同岗位的员工提供精细化的权限管理。系统支持13种角色和35+种权限，确保每个用户只能访问其职责范围内的功能。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      API Gateway                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              FastAPI Endpoints                         │ │
│  │  @require_permission(Permission.AGENT_ORDER_READ)      │ │
│  └────────────────────────────────────────────────────────┘ │
│                           ↓                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │          Permission Dependency Checker                 │ │
│  │  - 验证用户身份                                          │ │
│  │  - 检查角色权限                                          │ │
│  │  - 记录审计日志                                          │ │
│  └────────────────────────────────────────────────────────┘ │
│                           ↓                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           ROLE_PERMISSIONS Mapping                     │ │
│  │  UserRole.WAITER → {AGENT_ORDER_READ, ...}            │ │
│  │  UserRole.CHEF → {AGENT_INVENTORY_READ, ...}          │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 角色定义

### 管理层角色

#### 1. 系统管理员 (ADMIN)
- **权限**: 拥有所有系统权限
- **职责**: 系统配置、用户管理、全局监控
- **使用场景**: IT管理员、系统维护人员

#### 2. 店长 (STORE_MANAGER)
- **权限**: 门店所有运营权限（除系统配置外）
- **职责**: 门店全面管理、人员调度、业务决策
- **核心权限**:
  - 排班管理（读写）
  - 订单管理（读写）
  - 库存管理（读写）
  - 服务管理（读写）
  - 培训管理（读写）
  - 决策支持（读写）
  - 预订管理（读写）
  - 用户管理（读写）
  - 门店信息（读）
  - 系统日志（读）

#### 3. 店长助理 (ASSISTANT_MANAGER)
- **权限**: 协助店长管理，部分写权限受限
- **职责**: 协助日常运营、执行管理决策
- **限制**: 无库存写权限、无决策写权限

### 前厅角色

#### 4. 楼面经理 (FLOOR_MANAGER)
- **权限**: 前厅运营管理
- **职责**: 前厅服务质量、客户体验、人员调度
- **核心权限**:
  - 排班查看
  - 订单管理（读写）
  - 服务管理（读写）
  - 培训查看
  - 预订管理（读写）

#### 5. 客户经理 (CUSTOMER_MANAGER)
- **权限**: 客户关系和预订管理
- **职责**: VIP客户维护、预订协调、客户服务
- **核心权限**:
  - 订单查看
  - 服务管理（读写）
  - 预订管理（读写）
  - 决策查看

#### 6. 领班 (TEAM_LEADER)
- **权限**: 前厅基层管理
- **职责**: 班组管理、服务监督、现场协调
- **核心权限**:
  - 排班查看
  - 订单管理（读写）
  - 服务查看
  - 预订查看
  - 培训查看

#### 7. 服务员 (WAITER)
- **权限**: 基础服务操作
- **职责**: 点单、上菜、客户服务
- **核心权限**:
  - 订单管理（读写）
  - 服务查看
  - 预订查看

### 后厨角色

#### 8. 厨师长 (HEAD_CHEF)
- **权限**: 后厨全面管理
- **职责**: 菜品质量、人员管理、库存监督
- **核心权限**:
  - 排班管理（读写）
  - 订单查看
  - 库存管理（读写）
  - 培训查看
  - 决策查看
  - 用户查看

#### 9. 档口负责人 (STATION_MANAGER)
- **权限**: 档口运营管理
- **职责**: 档口生产、质量控制、库存管理
- **核心权限**:
  - 排班查看
  - 订单查看
  - 库存查看
  - 培训查看

#### 10. 厨师 (CHEF)
- **权限**: 基础后厨操作
- **职责**: 菜品制作、库存查看
- **核心权限**:
  - 订单查看
  - 库存查看

### 支持角色

#### 11. 库管 (WAREHOUSE_MANAGER)
- **权限**: 库存管理
- **职责**: 库存盘点、出入库管理、库存预警
- **核心权限**:
  - 库存管理（读写）
  - 决策查看
  - 门店信息查看

#### 12. 财务 (FINANCE)
- **权限**: 财务数据访问
- **职责**: 财务核算、报表分析、成本控制
- **核心权限**:
  - 订单查看
  - 库存查看
  - 决策查看
  - 门店信息查看
  - 系统日志查看

#### 13. 采购 (PROCUREMENT)
- **权限**: 采购和库存
- **职责**: 供应商管理、采购计划、库存补充
- **核心权限**:
  - 库存管理（读写）
  - 决策查看

## 权限类型

### Agent访问权限

#### 排班管理
- `AGENT_SCHEDULE_READ`: 查看排班信息
- `AGENT_SCHEDULE_WRITE`: 创建/修改排班

#### 订单管理
- `AGENT_ORDER_READ`: 查看订单信息
- `AGENT_ORDER_WRITE`: 创建/修改订单

#### 库存管理
- `AGENT_INVENTORY_READ`: 查看库存信息
- `AGENT_INVENTORY_WRITE`: 创建/修改库存

#### 服务管理
- `AGENT_SERVICE_READ`: 查看服务信息
- `AGENT_SERVICE_WRITE`: 创建/修改服务

#### 培训管理
- `AGENT_TRAINING_READ`: 查看培训信息
- `AGENT_TRAINING_WRITE`: 创建/修改培训

#### 决策支持
- `AGENT_DECISION_READ`: 查看决策建议
- `AGENT_DECISION_WRITE`: 创建/修改决策

#### 预订管理
- `AGENT_RESERVATION_READ`: 查看预订信息
- `AGENT_RESERVATION_WRITE`: 创建/修改预订

### 用户管理权限
- `USER_READ`: 查看用户信息
- `USER_WRITE`: 创建/修改用户
- `USER_DELETE`: 删除用户

### 门店管理权限
- `STORE_READ`: 查看门店信息
- `STORE_WRITE`: 创建/修改门店
- `STORE_DELETE`: 删除门店

### 系统配置权限
- `SYSTEM_CONFIG`: 系统配置管理
- `SYSTEM_LOGS`: 系统日志查看

## 使用方法

### 1. 在API端点中使用权限检查

```python
from fastapi import APIRouter, Depends
from src.core.dependencies import require_permission, get_current_active_user
from src.core.permissions import Permission
from src.models.user import User

router = APIRouter()

# 单个权限检查
@router.get("/orders")
async def get_orders(
    current_user: User = Depends(require_permission(Permission.AGENT_ORDER_READ))
):
    """查看订单 - 需要订单读权限"""
    return {"orders": []}

# 多个权限检查（任意一个）
@router.get("/inventory")
async def get_inventory(
    current_user: User = Depends(
        require_permission(
            Permission.AGENT_INVENTORY_READ,
            Permission.AGENT_INVENTORY_WRITE
        )
    )
):
    """查看库存 - 需要库存读或写权限"""
    return {"inventory": []}

# 所有权限检查
@router.post("/store/config")
async def update_store_config(
    current_user: User = Depends(
        require_all_permissions(
            Permission.STORE_WRITE,
            Permission.SYSTEM_CONFIG
        )
    )
):
    """更新门店配置 - 需要门店写和系统配置权限"""
    return {"success": True}
```

### 2. 在代码中检查权限

```python
from src.core.permissions import (
    has_permission,
    has_any_permission,
    has_all_permissions,
    Permission
)
from src.models.user import UserRole

# 检查单个权限
if has_permission(user.role, Permission.AGENT_ORDER_READ):
    # 用户有订单读权限
    pass

# 检查任意权限
if has_any_permission(user.role, [
    Permission.AGENT_INVENTORY_READ,
    Permission.AGENT_INVENTORY_WRITE
]):
    # 用户有库存读或写权限
    pass

# 检查所有权限
if has_all_permissions(user.role, [
    Permission.STORE_WRITE,
    Permission.SYSTEM_CONFIG
]):
    # 用户同时拥有门店写和系统配置权限
    pass
```

### 3. 角色权限检查

```python
from src.core.dependencies import require_role
from src.models.user import UserRole

@router.post("/admin/users")
async def create_user(
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER))
):
    """创建用户 - 需要管理员或店长角色"""
    return {"success": True}
```

## 权限层级关系

### 管理层级
```
ADMIN (所有权限)
  ├─ STORE_MANAGER (门店所有运营权限)
  │   └─ ASSISTANT_MANAGER (协助管理，部分写权限受限)
  │       └─ FLOOR_MANAGER (前厅管理)
  │           └─ TEAM_LEADER (班组管理)
  │               └─ WAITER (基础服务)
  │
  └─ HEAD_CHEF (后厨管理)
      └─ STATION_MANAGER (档口管理)
          └─ CHEF (基础制作)
```

### 职责分离原则

1. **前厅与后厨分离**
   - 服务员无库存写权限
   - 厨师无订单写权限

2. **操作与监督分离**
   - 财务只有查看权限，无修改权限
   - 采购有库存写权限，但无订单权限

3. **管理与执行分离**
   - 领班可管理订单，但无排班写权限
   - 档口负责人可查看库存，但无写权限

## 安全特性

### 1. 自动权限检查
- 所有API端点自动进行权限验证
- 未授权访问返回403 Forbidden
- 详细的错误信息提示所需权限

### 2. 审计日志
- 记录所有权限检查结果
- 包含用户ID、角色、请求权限、时间戳
- 支持权限拒绝告警

### 3. 管理员特权
- 管理员自动拥有所有权限
- 无需单独配置每个权限
- 便于紧急情况处理

### 4. 最小权限原则
- 每个角色只分配必需的权限
- 避免权限过度授予
- 定期审查权限配置

## 测试覆盖

权限系统包含18个测试用例，覆盖：

1. **权限检查函数测试** (9个测试)
   - 获取用户权限
   - 单个权限检查
   - 任意权限检查
   - 所有权限检查

2. **权限装饰器测试** (4个测试)
   - 权限授予场景
   - 权限拒绝场景
   - 管理员特权

3. **角色权限映射测试** (3个测试)
   - 所有角色权限定义
   - 角色层级关系
   - 职责分离验证

4. **权限日志测试** (2个测试)
   - 权限授予日志
   - 权限拒绝日志

测试覆盖率: **100%** (permissions.py)

## 配置管理

### 添加新权限

1. 在`Permission`枚举中添加新权限:
```python
class Permission(str, Enum):
    # 新权限
    AGENT_REPORT_READ = "agent:report:read"
    AGENT_REPORT_WRITE = "agent:report:write"
```

2. 更新`ROLE_PERMISSIONS`映射:
```python
ROLE_PERMISSIONS = {
    UserRole.STORE_MANAGER: {
        # 现有权限...
        Permission.AGENT_REPORT_READ,
        Permission.AGENT_REPORT_WRITE,
    },
}
```

3. 添加测试用例验证新权限

### 添加新角色

1. 在`UserRole`枚举中添加新角色:
```python
class UserRole(str, Enum):
    NEW_ROLE = "new_role"
```

2. 在`ROLE_PERMISSIONS`中定义角色权限:
```python
ROLE_PERMISSIONS = {
    UserRole.NEW_ROLE: {
        Permission.AGENT_ORDER_READ,
        # 其他权限...
    },
}
```

3. 更新数据库迁移脚本
4. 添加测试用例验证新角色

## 最佳实践

### 1. API设计
- 使用`require_permission`而不是手动检查
- 在路由级别声明权限要求
- 提供清晰的权限错误信息

### 2. 权限粒度
- 读写权限分离
- 按业务模块划分权限
- 避免过于细粒度的权限

### 3. 角色设计
- 基于实际岗位定义角色
- 遵循最小权限原则
- 定期审查角色权限配置

### 4. 测试策略
- 为每个权限编写测试
- 测试权限拒绝场景
- 验证角色层级关系

## 故障排查

### 常见问题

#### 1. 403 Forbidden错误
**原因**: 用户角色没有所需权限
**解决**:
- 检查用户角色: `user.role`
- 检查所需权限: 查看错误信息
- 验证角色权限映射: `ROLE_PERMISSIONS[user.role]`

#### 2. 管理员无法访问
**原因**: 权限检查逻辑错误
**解决**:
- 确认使用`require_permission`而不是自定义检查
- 管理员应自动拥有所有权限

#### 3. 权限检查不生效
**原因**: 未使用权限装饰器
**解决**:
- 确保端点使用`Depends(require_permission(...))`
- 检查依赖注入配置

## 性能优化

### 1. 权限缓存
- 角色权限映射在内存中
- 无需数据库查询
- O(1)时间复杂度

### 2. 批量检查
- 使用`has_any_permission`代替多次`has_permission`
- 减少函数调用开销

### 3. 早期返回
- 管理员检查优先
- 避免不必要的权限遍历

## 未来扩展

### 1. 动态权限
- 支持运行时权限配置
- 权限持久化到数据库
- 权限热更新

### 2. 资源级权限
- 支持特定资源的权限控制
- 例如: 只能访问自己门店的数据

### 3. 权限继承
- 支持权限组
- 简化权限配置

### 4. 权限审批流程
- 权限申请工作流
- 临时权限授予
- 权限过期机制

## 相关文档

- [用户认证系统](./AUTH_SYSTEM.md)
- [审计日志系统](./AUDIT_LOG_SYSTEM.md)
- [API文档](./API_DOCUMENTATION.md)

## 联系方式

如有问题或建议，请联系:
- 技术支持: support@zhilian-os.com
- 文档反馈: docs@zhilian-os.com
