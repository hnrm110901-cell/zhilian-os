# Makefile for Zhilian OS
# 智链OS开发辅助命令

.PHONY: help install dev test lint format clean run docker staging-up staging-down staging-logs staging-migrate staging-health prod-env-check prod-deploy prod-health prod-scheduler-patrol prod-monitor-up prod-monitor-down prod-monitor-status prod-monitor-lint prod-alert-test prod-alert-webhook-smoke prod-alert-e2e prod-ops-report prod-install-ops-timer

# 默认目标
help:
	@echo "智链OS - 可用命令:"
	@echo "  make install         - 安装项目依赖"
	@echo "  make dev             - 安装开发依赖"
	@echo "  make test            - 运行所有测试"
	@echo "  make lint            - 代码检查"
	@echo "  make format          - 代码格式化"
	@echo "  make clean           - 清理临时文件"
	@echo "  make run             - 启动API Gateway"
	@echo "  make docker          - 构建Docker镜像"
	@echo ""
	@echo "数据库迁移:"
	@echo "  make migrate-gen msg=<描述>  - 生成迁移文件"
	@echo "  make migrate-up              - 执行所有待迁移"
	@echo "  make migrate-down            - 回滚上一次迁移"
	@echo "  make migrate-status          - 查看当前版本"
	@echo "  make migrate-history         - 查看迁移历史"
	@echo ""
	@echo "Staging 环境:"
	@echo "  make staging-up              - 构建并启动 staging 栈"
	@echo "  make staging-down            - 停止 staging 栈"
	@echo "  make staging-logs            - 查看 staging 日志"
	@echo "  make staging-migrate         - 对 staging DB 执行 Alembic 迁移"
	@echo "  make staging-health          - 检查 staging API 健康状态"
	@echo ""
	@echo "Production 运维:"
	@echo "  make prod-env-check          - 校验生产环境变量与 compose 配置"
	@echo "  make prod-deploy             - 执行生产部署（compose + worker + beat）"
	@echo "  make prod-health             - 生产健康巡检（health/live/ready）"
	@echo "  make prod-scheduler-patrol   - 07:00/夜间任务巡检（需 TOKEN）"
	@echo "  make prod-monitor-up         - 启动 Prometheus/Grafana/Alertmanager"
	@echo "  make prod-monitor-down       - 停止监控栈"
	@echo "  make prod-monitor-status     - 查看监控栈状态"
	@echo "  make prod-monitor-lint       - 校验 Prometheus/Alertmanager 配置"
	@echo "  make prod-alert-test         - 注入一条测试告警到 Alertmanager"
	@echo "  make prod-alert-webhook-smoke - 直测 API 告警 webhook 接收端点"
	@echo "  make prod-alert-e2e          - 端到端告警链路检查"
	@echo "  make prod-ops-report         - 生成每日巡检报告（logs/ops）"
	@echo "  make prod-install-ops-timer  - 安装 systemd 定时巡检（需 root）"

# 安装生产依赖
install:
	pip install -r requirements.txt

# 安装开发依赖
dev:
	pip install -e ".[dev]"

# 运行所有测试
test:
	pytest packages/*/tests -v --cov=packages --cov-report=html --cov-report=term

# 运行特定Agent的测试
test-schedule:
	pytest packages/agents/schedule/tests -v

test-order:
	pytest packages/agents/order/tests -v

test-inventory:
	pytest packages/agents/inventory/tests -v

test-service:
	pytest packages/agents/service/tests -v

test-training:
	pytest packages/agents/training/tests -v

test-decision:
	pytest packages/agents/decision/tests -v

test-banquet:
	python3 -m pytest packages/agents/banquet/tests/test_agent.py -q

test-dish-rd:
	python3 -m pytest packages/agents/dish_rd/tests/test_agent.py -q

# 代码检查
lint:
	ruff check packages/ apps/
	mypy packages/ apps/ --ignore-missing-imports

# 代码格式化
format:
	black packages/ apps/
	ruff check --fix packages/ apps/

# 清理临时文件
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -rf dist/
	rm -rf build/

# 启动API Gateway
run:
	cd apps/api-gateway && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 构建Docker镜像
docker:
	docker build -t zhilian-os:latest .

# 启动所有服务(使用docker-compose)
up:
	docker-compose up -d

# 停止所有服务
down:
	docker-compose down

# 查看日志
logs:
	docker-compose logs -f

# 初始化开发环境
init:
	cp .env.example .env
	@echo "请编辑 .env 文件配置环境变量"
	make dev
	@echo "开发环境初始化完成!"

# 运行代码覆盖率检查
coverage:
	pytest packages/*/tests --cov=packages --cov-report=html
	@echo "覆盖率报告已生成: htmlcov/index.html"

# 生成依赖关系图
deps:
	pipdeptree

# 更新依赖
update:
	pip install --upgrade -r requirements.txt

# ============================================================
# 数据库迁移（Alembic）
# 使用前请确保 DATABASE_URL 环境变量已设置
# ============================================================
ALEMBIC = cd apps/api-gateway && alembic

# 生成新的迁移文件（自动检测 model 变化）
migrate-gen:
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

# 执行所有待执行的迁移（升级到最新）
migrate-up:
	$(ALEMBIC) upgrade head

# 回滚最后一次迁移
migrate-down:
	$(ALEMBIC) downgrade -1

# 回滚到指定版本：make migrate-to rev=<revision_id>
migrate-to:
	$(ALEMBIC) upgrade $(rev)

# 查看当前迁移版本
migrate-status:
	$(ALEMBIC) current

# 查看迁移历史
migrate-history:
	$(ALEMBIC) history --verbose

# 生成 SQL 脚本（不执行，仅预览）
migrate-sql:
	$(ALEMBIC) upgrade head --sql

# ============================================================
# Staging 环境
# 使用前：cp .env.staging.example .env.staging 并填入真实密钥
# ============================================================
staging-up:
	docker-compose -f docker-compose.staging.yml up -d --build

staging-down:
	docker-compose -f docker-compose.staging.yml down

staging-logs:
	docker-compose -f docker-compose.staging.yml logs -f

staging-migrate:
	docker-compose -f docker-compose.staging.yml exec api-gateway alembic upgrade head

staging-health:
	@curl -sf http://localhost:8001/api/v1/health && echo "✅ API healthy" || echo "❌ API unhealthy"

# ============================================================
# Production 运维脚本
# 默认读取 .env.prod + apps/api-gateway/.env.production
# ============================================================
prod-env-check:
	bash scripts/ops/prod_env_check.sh

prod-deploy:
	bash scripts/ops/deploy_prod.sh

prod-health:
	bash scripts/ops/health_check_prod.sh

prod-scheduler-patrol:
	bash scripts/ops/scheduler_patrol.sh

prod-monitor-up:
	ACTION=up bash scripts/ops/monitoring_stack.sh

prod-monitor-down:
	ACTION=down bash scripts/ops/monitoring_stack.sh

prod-monitor-status:
	ACTION=status bash scripts/ops/monitoring_stack.sh

prod-monitor-lint:
	bash scripts/ops/monitoring_lint.sh

prod-alert-test:
	bash scripts/ops/alertmanager_test.sh

prod-alert-webhook-smoke:
	bash scripts/ops/alert_webhook_smoke.sh

prod-alert-e2e:
	bash scripts/ops/alert_e2e_check.sh

prod-ops-report:
	bash scripts/ops/daily_ops_report.sh

prod-install-ops-timer:
	sudo bash scripts/ops/install_systemd_timer.sh
