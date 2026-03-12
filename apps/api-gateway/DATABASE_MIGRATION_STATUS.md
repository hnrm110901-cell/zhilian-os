# 数据库迁移状态

更新日期：2026-03-12

## 结论

当前 `src/models` 中声明的业务表已全部具备 Alembic 迁移覆盖。

本轮除补齐 [`z41_forecast_results.py`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/alembic/versions/z41_forecast_results.py) 外，还修复了历史迁移链断裂、重复 revision 和多头问题。当前仓库状态：

- `python3 -m alembic heads` 返回单头：`z42_merge_all_heads (head)`
- `python3 -m alembic upgrade head --sql` 已可成功离线导出整条迁移链
- 已在本地 fresh DB `zhilian_migration_test` 上成功完成一次真实 `alembic upgrade head`

## 本次核对方法

使用以下规则做静态比对：

- 从 `src/models/*.py` 提取所有 `__tablename__`
- 从 `alembic/versions/*.py` 提取所有 `op.create_table(...)`
- 计算差集：`models - migrations`

结果：

- ORM 表：`180`
- 已有迁移表：`228`
- ORM 未覆盖迁移：`0`

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

## 当前验证范围

已完成：

- 静态比对：模型表名与 `op.create_table(...)` 差集校验
- 迁移图校验：重复 revision / 错误 `down_revision` / 多头已修复
- 离线升级校验：`alembic upgrade head --sql`
- 自动化回归：[`tests/test_alembic_migrations.py`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/tests/test_alembic_migrations.py)
- 在线升级校验：本地 fresh DB `zhilian_migration_test`

未完成：

- 业务现有开发库 `zhilian_os` 的历史脏状态修复或重建策略
- 非本机环境（CI / staging / prod）的真实数据库升级演练

本机验证现状：

- 已使用根目录开发容器提供的 PostgreSQL 成功验证 fresh DB：
  - `DATABASE_URL=postgresql+asyncpg://zhilian:zhilian@localhost:5432/zhilian_migration_test`
  - `alembic upgrade head` 成功到 `z42_merge_all_heads`
- 现有开发库 `zhilian_os` 仍然是历史半迁移状态：
  - Alembic 版本落后
  - 部分表/类型已提前存在
  - 不适合直接作为 clean install 验证依据
- 已补充最短执行说明：[`MIGRATION_VALIDATION.md`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/MIGRATION_VALIDATION.md)

## 迁移落地建议

短期：

- 对现有开发库 `zhilian_os` 决定策略：重建到 fresh schema，或单独编写“历史脏库修复”迁移
- 确认 `forecast_results`、`edge_hubs`、`biz_metric_snapshots`、`people_shift_records` 等近期新增表在 fresh DB 已实际落库
- 对使用预测持久化的服务补一条在线集成校验
- 若本机未启动 PostgreSQL，先按仓库已有指南启动依赖：
  - [`TEST_EXECUTION_GUIDE.md`](/Users/lichun/Documents/GitHub/zhilian-os/TEST_EXECUTION_GUIDE.md)
  - [`apps/api-gateway/DOCKER.md`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/DOCKER.md)

中期：

- 将 [`tests/test_alembic_migrations.py`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/tests/test_alembic_migrations.py) 接入 CI
- 对仍包含运行时探测逻辑的旧迁移做一次系统梳理，减少 offline / online 分支复杂度

## 备注

- `alembic/versions` 中存在大量“迁移表多于 ORM 表”的历史表，这是正常现象：
  - 部分是旧表/兼容表
  - 部分是拆分实现后不再保留 ORM 映射
  - 因此当前真正重要的是“ORM 是否全部有迁移”，而不是总数完全相等
