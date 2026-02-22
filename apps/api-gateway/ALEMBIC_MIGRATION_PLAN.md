# Alembic迁移文件补全计划

## 当前状态

根据代码审查，发现以下问题：
- **缺失表数量**：27个表（占总表数87%）
- **不规范revision ID**：4个迁移文件
- **RLS策略独立**：未链接到主迁移链

## 已完成

✅ 创建初始架构迁移文件（a1b2c3d4e5f6_initial_schema.py）
- 包含5个核心表：stores, users, employees, orders, order_items

## 待补全的表（按优先级）

### 优先级1：核心业务表（10个）
1. **inventory_items** - 库存项表
2. **inventory_transactions** - 库存交易表
3. **schedules** - 排班表
4. **shifts** - 班次表
5. **reservations** - 预订表
6. **queues** - 排队表
7. **notifications** - 通知表
8. **audit_logs** - 审计日志表
9. **decision_logs** - 决策日志表
10. **kpis** / **kpi_records** - KPI表

### 优先级2：财务和供应链表（7个）
11. **suppliers** - 供应商表
12. **purchase_orders** - 采购订单表
13. **financial_transactions** - 财务交易表
14. **budgets** - 预算表
15. **invoices** - 发票表
16. **financial_reports** - 财务报表
17. **supplier_orders** - 供应商订单表

### 优先级3：集成表（5个）
18. **external_systems** - 外部系统表
19. **sync_logs** - 同步日志表
20. **pos_transactions** - POS交易表
21. **member_syncs** - 会员同步表
22. **reservation_syncs** - 预订同步表

## 实施步骤

### 步骤1：完成初始架构迁移文件

在 `a1b2c3d4e5f6_initial_schema.py` 中补充所有27个表的定义。

**参考模型文件**：
- `src/models/inventory.py` - 库存相关表
- `src/models/schedule.py` - 排班相关表
- `src/models/reservation.py` - 预订表
- `src/models/kpi.py` - KPI表
- `src/models/supply_chain.py` - 供应链表
- `src/models/finance.py` - 财务表
- `src/models/notification.py` - 通知表
- `src/models/audit_log.py` - 审计日志表
- `src/models/queue.py` - 排队表
- `src/models/integration.py` - 集成表
- `src/models/decision_log.py` - 决策日志表

### 步骤2：修复现有迁移文件的revision ID

需要修复的文件：
1. `f59c6ee62g7e_add_wechat_user_id_to_users.py` → 生成新的规范ID
2. `g60d7ff73h8f_add_task_management_tables.py` → 生成新的规范ID
3. `h71e8gg84i9g_add_daily_reports_table.py` → 生成新的规范ID
4. `i82f9hh95j0h_add_reconciliation_records_table.py` → 生成新的规范ID

**修复方法**：
```python
# 使用Python生成规范的revision ID
import hashlib
import time

def generate_revision_id():
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
```

### 步骤3：调整迁移依赖关系

**新的迁移链**：
```
a1b2c3d4e5f6 (initial_schema) [root]
    ↓
e48b5dd51f6d (add_latitude_longitude_to_stores)
    ↓
[new_id_1] (add_wechat_user_id_to_users)
    ↓
[new_id_2] (add_task_management_tables)
    ↓
[new_id_3] (add_daily_reports_table)
    ↓
[new_id_4] (add_reconciliation_records_table)
    ↓
rls_001_tenant_isolation (RLS策略)
```

### 步骤4：更新RLS迁移的依赖

修改 `rls_001_tenant_isolation.py`：
```python
down_revision = '[new_id_4]'  # 链接到最后一个迁移
```

### 步骤5：验证迁移

```bash
# 检查迁移历史
alembic history

# 在测试数据库上验证
alembic upgrade head

# 验证降级
alembic downgrade base
alembic upgrade head
```

## 迁移文件模板

### 表定义模板

```python
op.create_table(
    'table_name',
    sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
    # ... 其他字段
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
)

# 创建索引
op.create_index('idx_table_name_store_id', 'table_name', ['store_id'])
```

### downgrade函数模板

```python
def downgrade() -> None:
    """删除表"""
    op.drop_table('table_name')
```

## 注意事项

1. **外键顺序**：确保被引用的表先创建
2. **索引命名**：使用 `idx_表名_字段名` 格式
3. **时间戳**：使用 `server_default=sa.text('now()')` 而不是Python的datetime
4. **UUID**：使用 `postgresql.UUID(as_uuid=True)` 而不是String
5. **JSON字段**：使用 `sa.JSON` 类型
6. **Numeric字段**：使用 `sa.Numeric(precision, scale)` 指定精度

## 测试清单

- [ ] 空数据库上执行 `alembic upgrade head` 成功
- [ ] 所有表都已创建
- [ ] 所有索引都已创建
- [ ] 外键约束正确
- [ ] `alembic downgrade base` 成功
- [ ] 再次 `alembic upgrade head` 成功
- [ ] 检查 `alembic history` 输出正确

## 风险评估

**当前风险**：🔴 高风险
- 生产环境无法从零初始化数据库
- 迁移历史不完整，无法追溯架构变更

**完成后风险**：🟢 低风险
- 完整的迁移历史
- 可重复的数据库初始化流程
- 支持版本回滚

## 时间估算

- 补全所有表定义：4-6小时
- 修复revision ID：1小时
- 调整依赖关系：1小时
- 测试验证：2小时
- **总计**：8-10小时

## 相关文件

- `alembic/versions/a1b2c3d4e5f6_initial_schema.py` - 初始架构（进行中）
- `alembic/env.py` - Alembic配置
- `src/models/` - 所有模型定义
- `alembic.ini` - Alembic配置文件
