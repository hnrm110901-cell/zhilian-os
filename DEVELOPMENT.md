# 开发指南 (Development Guide)

## 快速开始 (Quick Start)

### 1. 环境准备

**系统要求:**
- Python 3.8+
- Node.js 16+ (用于pnpm)
- Git

**推荐使用Python 3.11**

### 2. 克隆项目

```bash
git clone https://github.com/hnrm110901-cell/zhilian-os.git
cd zhilian-os
```

### 3. 初始化开发环境

```bash
# 方式1: 使用Makefile (推荐)
make init

# 方式2: 手动安装
cp .env.example .env
pip install -e ".[dev]"
```

### 4. 配置环境变量

编辑 `.env` 文件，配置必要的API密钥和数据库连接。

### 5. 运行测试

```bash
# 运行所有测试
make test

# 运行特定Agent的测试
make test-schedule
make test-order
make test-inventory
make test-service
make test-training
make test-decision
```

### 6. 启动服务

```bash
# 启动API Gateway
make run

# 或者直接使用uvicorn
cd apps/api-gateway
uvicorn src.main:app --reload
```

## 项目结构

```
zhilian-os/
├── apps/                      # 应用程序
│   └── api-gateway/          # API网关
├── packages/                  # 核心包
│   ├── agents/               # AI Agents
│   │   ├── schedule/        # 排班Agent
│   │   ├── order/           # 订单Agent
│   │   ├── inventory/       # 库存Agent
│   │   ├── service/         # 服务Agent
│   │   ├── training/        # 培训Agent
│   │   └── decision/        # 决策Agent
│   ├── api-adapters/        # API适配器
│   │   ├── aoqiwei/        # 奥琦韦适配器
│   │   ├── pinzhi/         # 品智适配器
│   │   └── base/           # 基础适配器
│   ├── shared/              # 共享代码
│   ├── types/               # 类型定义
│   └── llm-core/            # LLM核心
├── docs/                     # 文档
├── scripts/                  # 脚本
├── .env.example             # 环境变量模板
├── pyproject.toml           # 项目配置
├── requirements.txt         # Python依赖
└── Makefile                 # 开发命令
```

## 开发工作流

### 1. 创建新分支

```bash
git checkout -b feature/your-feature-name
```

### 2. 开发代码

遵循项目的代码规范：
- 使用类型注解
- 编写单元测试
- 添加文档字符串

### 3. 代码检查和格式化

```bash
# 格式化代码
make format

# 检查代码质量
make lint
```

### 4. 运行测试

```bash
# 运行所有测试
make test

# 查看覆盖率
make coverage
```

### 5. 提交代码

```bash
git add .
git commit -m "feat: 添加新功能"
git push origin feature/your-feature-name
```

### 6. 创建Pull Request

在GitHub上创建PR，等待代码审查。

## 常用命令

```bash
# 安装依赖
make install          # 生产依赖
make dev             # 开发依赖

# 测试
make test            # 所有测试
make test-schedule   # 排班Agent测试
make coverage        # 测试覆盖率

# 代码质量
make lint            # 代码检查
make format          # 代码格式化

# 运行
make run             # 启动API Gateway

# 清理
make clean           # 清理临时文件

# Docker
make docker          # 构建镜像
make up              # 启动服务
make down            # 停止服务
make logs            # 查看日志
```

## 编写新的Agent

### 1. 创建目录结构

```bash
mkdir -p packages/agents/your-agent/src
mkdir -p packages/agents/your-agent/tests
```

### 2. 创建Agent类

```python
# packages/agents/your-agent/src/agent.py
import structlog
from typing import TypedDict, List, Optional

logger = structlog.get_logger()

class YourAgent:
    def __init__(self, store_id: str):
        self.store_id = store_id
        self.logger = logger.bind(agent="your-agent", store_id=store_id)

    async def your_method(self):
        self.logger.info("doing_something")
        # 实现逻辑
        pass
```

### 3. 编写测试

```python
# packages/agents/your-agent/tests/test_agent.py
import pytest
from src.agent import YourAgent

@pytest.fixture
def agent():
    return YourAgent(store_id="STORE001")

@pytest.mark.asyncio
async def test_your_method(agent):
    result = await agent.your_method()
    assert result is not None
```

### 4. 添加文档

创建 `packages/agents/your-agent/README.md`

## 代码规范

### Python代码风格

- 使用 Black 进行代码格式化
- 使用 Ruff 进行代码检查
- 使用 MyPy 进行类型检查
- 行长度限制: 100字符

### 命名规范

- 类名: PascalCase (例如: `ScheduleAgent`)
- 函数名: snake_case (例如: `generate_schedule`)
- 常量: UPPER_SNAKE_CASE (例如: `MAX_RETRIES`)
- 私有方法: _snake_case (例如: `_internal_method`)

### 类型注解

```python
from typing import List, Optional, Dict, Any

async def process_data(
    data: List[Dict[str, Any]],
    options: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    pass
```

### 文档字符串

```python
def calculate_score(value: float, weight: float) -> float:
    """
    计算加权分数

    Args:
        value: 原始值
        weight: 权重

    Returns:
        加权后的分数
    """
    return value * weight
```

## 测试规范

### 测试文件命名

- 测试文件: `test_*.py`
- 测试类: `Test*`
- 测试方法: `test_*`

### 异步测试

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

### Mock和Fixture

```python
@pytest.fixture
def mock_adapter():
    return MockAdapter()

def test_with_mock(mock_adapter):
    agent = Agent(adapter=mock_adapter)
    result = agent.process()
    assert result is not None
```

## 调试技巧

### 1. 使用日志

```python
self.logger.info("processing_data", count=len(data))
self.logger.error("process_failed", error=str(e))
```

### 2. 使用断点

```python
import pdb; pdb.set_trace()
```

### 3. 使用pytest调试

```bash
pytest -v -s tests/test_agent.py::test_specific_function
```

## 性能优化

### 1. 使用异步并发

```python
import asyncio

results = await asyncio.gather(
    task1(),
    task2(),
    task3()
)
```

### 2. 缓存结果

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_calculation(x: int) -> int:
    return x ** 2
```

## 故障排查

### 常见问题

1. **导入错误**: 确保PYTHONPATH正确设置
2. **测试失败**: 检查依赖是否安装完整
3. **类型错误**: 运行 `make lint` 检查类型问题

### 获取帮助

- 查看文档: `docs/`
- 查看示例: 各Agent的README
- 提交Issue: GitHub Issues

## 贡献指南

1. Fork项目
2. 创建特性分支
3. 提交代码
4. 创建Pull Request
5. 等待代码审查

## 许可证

MIT License
