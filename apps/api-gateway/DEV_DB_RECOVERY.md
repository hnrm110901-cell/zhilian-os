# 开发库恢复方案

更新日期：2026-03-12

## 结论

本地开发库 `zhilian_os` 不应再继续按“逐个补丁修旧库”的方式维护。

当前观察结果：

- `alembic_version` 停在 `i82f9hh95j0h`
- 实际只有 `31` 张表
- fresh head 数据库有 `234` 张表
- 差集为 `203` 张表

这说明 `zhilian_os` 本质上是早期原型库，不是一个“只差几步迁移”的正常开发库。

## 推荐策略

优先策略：直接重建开发库。

理由：

- 已验证 fresh DB 可以完整执行 `alembic upgrade head`
- 旧库缺失对象过多，继续写兼容迁移的收益很低
- 每为旧库补一条特殊兼容逻辑，都会增加未来维护成本

## 重建命令

前提：

- 根目录开发容器已启动
- PostgreSQL 容器名默认是 `zhilian-postgres-dev`

建议顺序：

```bash
make dev-db-backup
make dev-db-rebuild
```

执行：

```bash
cd apps/api-gateway
CONFIRM_REBUILD=1 bash scripts/rebuild_dev_database.sh
```

默认会重建：

```bash
zhilian_os
```

## 脚本做的事情

[`scripts/rebuild_dev_database.sh`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/scripts/rebuild_dev_database.sh)

按以下步骤执行：

1. `DROP DATABASE IF EXISTS zhilian_os WITH (FORCE)`
2. `CREATE DATABASE zhilian_os`
3. `python3 -m alembic upgrade head`
4. 查询 `alembic_version`

## 备份命令

如果旧库里还有参考数据，先执行：

```bash
make dev-db-backup
```

或手动执行：

```bash
cd apps/api-gateway
bash scripts/backup_dev_database.sh
```

默认输出目录：

```bash
apps/api-gateway/backups/
```

## 何时不该直接重建

以下情况不要直接执行：

- `zhilian_os` 里还有需要保留的人工测试数据
- 有其他本地服务正依赖当前这份旧库
- 你准备做“旧库到新库的数据迁移”，而不是纯开发环境重置

## 如果必须保留旧数据

那就不要重建 `zhilian_os`，改走：

1. 保留旧库
2. 新建 fresh 库作为标准结构
3. 按业务表逐步导数
4. 完成后再切换应用连接

这属于数据迁移项目，不再是单纯 Alembic 升级问题。
