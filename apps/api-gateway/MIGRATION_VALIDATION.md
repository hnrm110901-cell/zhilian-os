# 迁移验证说明

更新日期：2026-03-12

## 最短路径

从仓库根目录启动本地依赖：

```bash
docker-compose up -d postgres redis
```

然后执行迁移校验：

```bash
make migrate-verify
```

默认使用的本地连接为：

```bash
DATABASE_URL=postgresql+asyncpg://zhilian:zhilian@localhost:5432/zhilian_os
```

这套默认值与根目录 [`docker-compose.yml`](/Users/lichun/Documents/GitHub/zhilian-os/docker-compose.yml) 的开发 PostgreSQL 配置一致。

## 脚本做了什么

[`scripts/verify_migrations.sh`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/scripts/verify_migrations.sh) 会顺序执行：

1. `python3 -m alembic heads`
2. `python3 -m alembic upgrade head --sql`
3. `python3 -m alembic current`
4. `python3 -m alembic upgrade head`
5. 再次执行 `python3 -m alembic current`

离线 SQL 默认输出到：

```bash
/tmp/zhilian_alembic_upgrade.sql
```

## 只做离线验证

如果本机还没有数据库实例，可以先只做结构校验：

```bash
cd apps/api-gateway
SKIP_ONLINE=1 bash scripts/verify_migrations.sh
```

## 常见失败

`Connection refused`

- PostgreSQL 没启动
- 端口不是 `5432`
- 本机没有按根目录 `docker-compose.yml` 起开发库

`password authentication failed`

- `DATABASE_URL` 用户名或密码与实际实例不一致

`database does not exist`

- 目标库名不对
- 当前默认库名是 `zhilian_os`

## 旧开发库说明

当前本地 `zhilian_os` 不是 clean install 基线库，而是早期原型遗留库。

如果你只是想恢复一个和当前代码一致的开发库，不建议继续对旧库补丁升级，直接参考：

- [`DEV_DB_RECOVERY.md`](/Users/lichun/Documents/GitHub/zhilian-os/apps/api-gateway/DEV_DB_RECOVERY.md)
- 根目录快捷命令：
  - `make dev-db-backup`
  - `make dev-db-rebuild`
