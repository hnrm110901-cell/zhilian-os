# 数据库迁移状态

更新日期：2026-03-12

## 结论

当前 `src/models` 中声明的业务表共有 `180` 张；`alembic/versions` 中已覆盖其中 `179` 张。

本轮重新按代码实际比对后，历史文档里“还缺 15 张表”的结论已过时。那些表大多已在后续迁移中补齐。

当前真实缺口只剩 1 张表：

- `forecast_results`
  - 模型：[`src/models/forecast.py`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/src/models/forecast.py)
  - 迁移：[`alembic/versions/z41_forecast_results.py`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/alembic/versions/z41_forecast_results.py)
  - 状态：已新增迁移，待在目标环境执行 `alembic upgrade head`

## 本次核对方法

使用以下规则做静态比对：

- 从 `src/models/*.py` 提取所有 `__tablename__`
- 从 `alembic/versions/*.py` 提取所有 `op.create_table(...)`
- 计算差集：`models - migrations`

结果：

- ORM 表：`180`
- 已有迁移表：`227`
- ORM 未覆盖迁移：`1`

## 需要说明的历史差异

以下表在旧文档中曾被列为“待补充”，但现在已经有模型和迁移，不应再作为待办重复建设：

- `queues`
- `notifications`
- `audit_logs`
- `decision_logs`
- `kpis`
- `kpi_records`
- `suppliers`
- `purchase_orders`
- `financial_transactions`
- `budgets`
- `invoices`
- `financial_reports`
- `supplier_orders`
- `external_systems`
- `sync_logs`
- `pos_transactions`
- `member_syncs`
- `reservation_syncs`

## 迁移落地建议

短期：

- 在开发/测试库执行 `alembic upgrade head`
- 确认 `forecast_results` 已成功创建
- 对使用预测持久化的服务补一条集成校验

中期：

- 清理历史多分支迁移链，统一到单一可追踪 head
- 将“模型表名 vs Alembic create_table”校验加入 CI，避免再次出现“模型存在但无迁移”

## 备注

- `alembic/versions` 中存在大量“迁移表多于 ORM 表”的历史表，这是正常现象：
  - 部分是旧表/兼容表
  - 部分是拆分实现后不再保留 ORM 映射
  - 因此当前真正重要的是“ORM 是否全部有迁移”，而不是总数完全相等
