# 多租户数据隔离方案

## 概述

智链OS采用多层次的租户隔离机制，确保不同门店的数据完全隔离，防止数据泄露。

## 架构设计

### 1. 租户上下文管理 (Tenant Context)

使用Python的`ContextVar`实现线程安全的租户上下文：

```python
from src.core.tenant_context import TenantContext

# 设置当前租户
TenantContext.set_current_tenant("STORE001")

# 获取当前租户
tenant_id = TenantContext.get_current_tenant()

# 要求必须有租户上下文
tenant_id = TenantContext.require_tenant()  # 如果未设置会抛出异常
```

### 2. 中间件自动注入

`StoreAccessMiddleware`在每个请求处理时自动：
1. 从请求中提取`store_id`
2. 验证用户是否有权访问该门店
3. 设置租户上下文
4. 请求结束后清除租户上下文

```python
# 在main.py中注册中间件
from src.middleware.store_access import StoreAccessMiddleware

app.add_middleware(StoreAccessMiddleware)
```

### 3. 数据库层隔离

#### 方案A：PostgreSQL Row-Level Security (RLS)

**优点**：
- 数据库层面的强制隔离
- 即使应用层代码有bug也无法跨租户访问
- 性能优秀

**实施步骤**：

1. 运行迁移脚本启用RLS：
```bash
alembic upgrade rls_001_tenant_isolation
```

2. Session会自动设置PostgreSQL session变量：
```python
# 自动执行
SELECT set_config('app.current_tenant', 'STORE001', FALSE);
```

3. RLS策略自动过滤所有查询：
```sql
-- 所有SELECT/INSERT/UPDATE/DELETE都会自动添加条件
WHERE store_id = current_setting('app.current_tenant')
```

#### 方案B：ORM级别过滤器

如果不使用PostgreSQL或RLS，系统会自动降级到ORM级别的过滤器：

```python
# 自动在所有查询中添加WHERE条件
SELECT * FROM orders WHERE store_id = 'STORE001'
```

### 4. Service层使用

#### 旧的方式（已废弃）：
```python
# ❌ 不推荐：硬编码默认值
class OrderService:
    def __init__(self, store_id: str = "STORE001"):
        self.store_id = store_id

# ❌ 不推荐：全局单例
order_service = OrderService()
```

#### 新的方式（推荐）：
```python
# ✅ 推荐：继承BaseService
from src.services.base_service import BaseService

class OrderService(BaseService):
    def __init__(self, store_id: Optional[str] = None):
        super().__init__(store_id)  # 自动从TenantContext获取

    async def get_orders(self):
        # store_id自动从租户上下文获取
        async with self.get_session() as session:
            # 查询自动添加租户过滤
            result = await session.execute(
                select(Order)  # 自动添加 WHERE store_id = current_tenant
            )
            return result.scalars().all()
```

#### API层使用：
```python
from fastapi import Depends
from src.core.dependencies import get_current_user

@app.get("/orders")
async def get_orders(current_user: User = Depends(get_current_user)):
    # 租户上下文已由中间件设置
    # 直接创建Service，无需传递store_id
    service = OrderService()
    return await service.get_orders()
```

## 安全保障

### 多层防护

1. **中间件层**：验证用户权限，拒绝未授权访问
2. **应用层**：TenantContext确保代码使用正确的租户ID
3. **ORM层**：自动过滤查询，防止遗漏
4. **数据库层**：RLS策略作为最后一道防线

### 超级管理员

超级管理员可以访问所有门店数据：

```python
# 禁用租户隔离
async with get_db_session(enable_tenant_isolation=False) as session:
    # 可以查询所有门店的数据
    all_orders = await session.execute(select(Order))
```

## 迁移指南

### 1. 更新Service类

```python
# 旧代码
class MyService:
    def __init__(self, store_id: str = "STORE001"):
        self.store_id = store_id

# 新代码
from src.services.base_service import BaseService

class MyService(BaseService):
    def __init__(self, store_id: Optional[str] = None):
        super().__init__(store_id)
```

### 2. 移除全局Service实例

```python
# 旧代码 - 删除
my_service = MyService()  # 全局单例

# 新代码 - 在需要时创建
def some_function():
    service = MyService()  # 从租户上下文获取store_id
    return service.do_something()
```

### 3. 更新API端点

```python
# 旧代码
@app.get("/orders")
async def get_orders(current_user: User = Depends(get_current_user)):
    service = OrderService(store_id=current_user.store_id)  # 手动传递
    return await service.get_orders()

# 新代码
@app.get("/orders")
async def get_orders(current_user: User = Depends(get_current_user)):
    service = OrderService()  # 自动从租户上下文获取
    return await service.get_orders()
```

## 测试

### 单元测试

```python
from src.core.tenant_context import TenantContext, with_tenant

@with_tenant("TEST_STORE")
async def test_order_service():
    service = OrderService()
    assert service.get_store_id() == "TEST_STORE"

    orders = await service.get_orders()
    # 所有订单都属于TEST_STORE
    assert all(o.store_id == "TEST_STORE" for o in orders)
```

### 集成测试

```python
async def test_tenant_isolation():
    # 创建两个门店的数据
    TenantContext.set_current_tenant("STORE_A")
    await create_order(name="Order A")

    TenantContext.set_current_tenant("STORE_B")
    await create_order(name="Order B")

    # 验证隔离
    TenantContext.set_current_tenant("STORE_A")
    orders_a = await get_orders()
    assert len(orders_a) == 1
    assert orders_a[0].name == "Order A"

    TenantContext.set_current_tenant("STORE_B")
    orders_b = await get_orders()
    assert len(orders_b) == 1
    assert orders_b[0].name == "Order B"
```

## 性能考虑

1. **RLS性能**：PostgreSQL RLS使用索引，性能影响极小（< 5%）
2. **索引优化**：所有租户表的`store_id`字段都已建立索引
3. **复合索引**：常用查询使用`(store_id, other_column)`复合索引

## 故障排查

### 问题：查询返回空结果

**原因**：租户上下文未设置

**解决**：
```python
# 检查租户上下文
tenant_id = TenantContext.get_current_tenant()
if not tenant_id:
    logger.error("Tenant context not set!")
```

### 问题：跨租户数据泄露

**检查清单**：
1. 中间件是否正确注册
2. RLS策略是否启用：`SELECT * FROM pg_policies;`
3. Service是否继承BaseService
4. 是否有代码绕过了租户过滤

## 最佳实践

1. **始终使用BaseService**：所有Service类继承BaseService
2. **避免全局实例**：不要创建全局Service实例
3. **测试隔离性**：为每个Service编写租户隔离测试
4. **监控日志**：关注"Tenant context not set"警告
5. **定期审计**：检查是否有代码禁用了租户隔离

## 相关文件

- `src/core/tenant_context.py` - 租户上下文管理
- `src/core/tenant_filter.py` - SQLAlchemy过滤器
- `src/core/database.py` - 数据库Session配置
- `src/middleware/store_access.py` - 权限验证中间件
- `src/services/base_service.py` - Service基类
- `alembic/versions/rls_001_tenant_isolation.py` - RLS迁移脚本
