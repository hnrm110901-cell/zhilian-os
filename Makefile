# Makefile for Zhilian OS
# 智链OS开发辅助命令

.PHONY: help install dev test lint format clean run docker

# 默认目标
help:
	@echo "智链OS - 可用命令:"
	@echo "  make install    - 安装项目依赖"
	@echo "  make dev        - 安装开发依赖"
	@echo "  make test       - 运行所有测试"
	@echo "  make lint       - 代码检查"
	@echo "  make format     - 代码格式化"
	@echo "  make clean      - 清理临时文件"
	@echo "  make run        - 启动API Gateway"
	@echo "  make docker     - 构建Docker镜像"

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
