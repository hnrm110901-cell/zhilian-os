# CI/CD 流水线文档

## 概述

本项目使用GitHub Actions实现持续集成和持续部署（CI/CD），确保代码质量和自动化测试。

## 工作流程

### 触发条件

CI/CD流水线在以下情况下自动触发：
- 推送代码到`main`或`develop`分支
- 创建针对`main`或`develop`分支的Pull Request

### 流水线阶段

#### 1. 测试阶段 (Test)

**服务依赖**:
- PostgreSQL 13 (测试数据库)
- Redis 6 (缓存和消息队列)

**执行步骤**:
1. **代码格式检查 (Black)**
   - 检查代码是否符合Black格式规范
   - 配置: 最大行长度127字符

2. **代码风格检查 (Flake8)**
   - 检查Python代码风格
   - 检测语法错误和潜在问题
   - 最大复杂度: 10

3. **类型检查 (MyPy)**
   - 静态类型检查
   - 提高代码可维护性

4. **单元测试 (Pytest)**
   - 运行所有单元测试
   - 生成测试覆盖率报告
   - 上传到Codecov

#### 2. 构建阶段 (Build)

**执行步骤**:
1. 验证Python语法
2. 检查模块导入
3. 确保应用可以正常启动

## 本地开发

### 安装开发工具

```bash
cd apps/api-gateway
pip install black flake8 mypy pytest pytest-asyncio pytest-cov
```

### 代码格式化

```bash
# 检查代码格式
black --check src/ tests/

# 自动格式化代码
black src/ tests/
```

### 代码风格检查

```bash
# 运行Flake8
flake8 src/

# 只检查严重错误
flake8 src/ --select=E9,F63,F7,F82
```

### 类型检查

```bash
# 运行MyPy
mypy src/ --ignore-missing-imports
```

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/test_task_service.py

# 查看测试覆盖率
pytest tests/ --cov=src --cov-report=html

# 打开覆盖率报告
open htmlcov/index.html
```

## 配置文件

### .flake8

Flake8配置文件，定义代码风格规则。

```ini
[flake8]
max-line-length = 127
exclude = .git,__pycache__,.venv,venv,alembic/versions
ignore = E203,E501,W503,E402
max-complexity = 10
```

### pyproject.toml

项目配置文件，包含Black、MyPy和Pytest的配置。

**Black配置**:
- 行长度: 127字符
- 目标Python版本: 3.9

**MyPy配置**:
- 忽略缺失的导入
- 排除测试和迁移文件

**Pytest配置**:
- 自动发现测试
- 生成覆盖率报告
- 异步测试支持

## Pre-commit Hooks

建议安装pre-commit hooks，在提交前自动检查代码：

```bash
# 安装pre-commit
pip install pre-commit

# 安装hooks
pre-commit install

# 手动运行所有hooks
pre-commit run --all-files
```

创建`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.9

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

## 测试覆盖率

### 查看覆盖率

测试覆盖率报告会自动生成：
- 终端输出: 显示缺失覆盖的行
- HTML报告: `htmlcov/index.html`
- XML报告: `coverage.xml` (用于CI)

### 覆盖率目标

- 总体覆盖率: ≥ 80%
- 核心业务逻辑: ≥ 90%
- 新增代码: ≥ 85%

### 排除规则

以下代码不计入覆盖率：
- 测试文件
- 数据库迁移
- `__repr__`方法
- 抽象方法
- `if __name__ == "__main__"`

## 持续改进

### 代码质量指标

定期检查以下指标：
1. **测试覆盖率**: 保持在80%以上
2. **代码复杂度**: 单个函数不超过10
3. **代码重复**: 使用工具检测重复代码
4. **技术债务**: 定期重构和优化

### 最佳实践

1. **提交前检查**
   - 运行所有测试
   - 检查代码格式
   - 确保类型正确

2. **编写测试**
   - 新功能必须有测试
   - 修复bug时添加回归测试
   - 保持测试简单明了

3. **代码审查**
   - 所有PR必须经过审查
   - 检查测试覆盖率
   - 确保CI通过

4. **文档更新**
   - 更新API文档
   - 更新配置说明
   - 记录重要变更

## 故障排查

### CI失败常见原因

1. **测试失败**
   - 检查测试日志
   - 本地运行失败的测试
   - 确保数据库连接正确

2. **代码格式问题**
   - 运行`black src/ tests/`自动格式化
   - 检查`.flake8`配置

3. **类型错误**
   - 添加类型注解
   - 使用`# type: ignore`忽略特定行

4. **导入错误**
   - 检查依赖是否安装
   - 确保模块路径正确

### 本地调试

```bash
# 模拟CI环境
docker run -it --rm \
  -v $(pwd):/app \
  -w /app/apps/api-gateway \
  python:3.9 \
  bash -c "pip install -r requirements.txt && pytest tests/"

# 使用docker-compose
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

## 参考资料

- [GitHub Actions文档](https://docs.github.com/en/actions)
- [Black文档](https://black.readthedocs.io/)
- [Flake8文档](https://flake8.pycqa.org/)
- [MyPy文档](https://mypy.readthedocs.io/)
- [Pytest文档](https://docs.pytest.org/)
- [Codecov文档](https://docs.codecov.com/)
