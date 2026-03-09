# Production Ops Runbook

本文档定义智链OS生产环境的配置和日常运维脚本用法。

## 1. 首次配置

1. 复制环境模板：

```bash
cp .env.prod.example .env.prod
cp apps/api-gateway/.env.production.example apps/api-gateway/.env.production
```

2. 填写密钥与连接串（至少以下变量）：
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `API_DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`

3. 执行预检：

```bash
make prod-env-check
```

## 2. 部署流程

```bash
make prod-deploy
```

该命令会执行：
- 生产变量预检
- 拉取镜像
- 启动依赖服务（Postgres/Redis/Qdrant）
- 启动 API + Celery Worker + Celery Beat + Web + Nginx
- 执行基础健康检查

如涉及数据库结构变更，部署后执行：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec api-gateway alembic upgrade head
```

## 3. 健康检查

无鉴权巡检（默认本机）：

```bash
make prod-health
```

指定地址：

```bash
bash scripts/ops/health_check_prod.sh https://your-domain.com
```

## 4. 调度巡检（重点）

### 目标
确认以下关键任务都在 Beat 配置中：
- `daily-workforce-advice`（默认 07:00）
- `daily-auto-workforce-schedule`（默认 07:00）
- `nightly-action-dispatch`（默认 04:30）

### 执行

```bash
TOKEN=<admin_jwt> make prod-scheduler-patrol
```

也可手动触发单任务（可选）：

```bash
TOKEN=<admin_jwt> TRIGGER_TASK=generate_daily_hub bash scripts/ops/scheduler_patrol.sh https://your-domain.com
```

## 5. 常见故障

1. `prod_env_check` 报 required variable is empty
- 说明 `.env.prod` 或 `apps/api-gateway/.env.production` 缺少必填项。

2. `api-gateway` healthy 失败
- 优先检查 `API_DATABASE_URL` 是否能连接 `postgres` 服务。
- 检查 `REDIS_PASSWORD` 与 redis/sentinel 配置是否一致。

3. 调度巡检失败
- 校验 `TOKEN` 是否有效。
- 检查 `celery-beat` 容器是否运行。
- 检查 `/api/v1/scheduler/schedule` 返回中是否包含关键任务。

## 6. 监控与告警运维

启动监控栈（Prometheus/Grafana/Alertmanager）：

```bash
make prod-monitor-up
```

查看状态：

```bash
make prod-monitor-status
```

配置校验（建议每次发布前执行）：

```bash
make prod-monitor-lint
```

注入测试告警（验证告警链路）：

```bash
make prod-alert-test
```

直测 API 告警 webhook（不经 Prometheus）：

```bash
ALERT_WEBHOOK_TOKEN=<token> make prod-alert-webhook-smoke
```

端到端告警链路检查（API webhook + Alertmanager 注入/查询）：

```bash
ALERT_WEBHOOK_TOKEN=<token> make prod-alert-e2e
```

停止监控栈：

```bash
make prod-monitor-down
```

## 7. 自动化巡检（Cron / Systemd）

### 每日巡检报告

手动执行：

```bash
make prod-ops-report
```

输出目录：`logs/ops/ops_report_*.md`

可选 webhook 推送：
- 设置 `OPS_REPORT_WEBHOOK_URL` 后，脚本会把报告文本推送到该地址。

### Systemd Timer（推荐）

模板文件：
- `scripts/ops/templates/systemd/zhilian-ops-patrol.service`
- `scripts/ops/templates/systemd/zhilian-ops-patrol.timer`

一键安装：

```bash
make prod-install-ops-timer
```

安装后检查：

```bash
systemctl status zhilian-ops-patrol.timer
systemctl list-timers | grep zhilian-ops-patrol
```

### Cron（备选）

模板文件：
- `scripts/ops/templates/cron/ops_daily_report.cron`

将模板内容按实际路径和 `TOKEN` 修改后加入 `crontab -e`。
