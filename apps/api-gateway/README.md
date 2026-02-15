# 智链OS API Gateway

智链OS的API网关服务，提供统一的HTTP API接口访问所有智能体。

## 功能特性

- 统一的Agent调用接口
- 自动错误处理和日志记录
- 执行时间统计
- CORS支持
- API文档自动生成

## 已集成的Agent

1. **排班Agent** (`/api/v1/agents/schedule`) - 智能排班建议
2. **订单Agent** (`/api/v1/agents/order`) - 订单协同处理
3. **库存Agent** (`/api/v1/agents/inventory`) - 库存预警
4. **服务Agent** (`/api/v1/agents/service`) - 服务质量分析
5. **培训Agent** (`/api/v1/agents/training`) - 培训辅导
6. **决策Agent** (`/api/v1/agents/decision`) - 决策支持
7. **预定Agent** (`/api/v1/agents/reservation`) - 预定宴会管理

## 快速开始

### 1. 安装依赖

```bash
cd apps/api-gateway
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑.env文件，填入必要的配置
```

### 3. 启动服务

```bash
# 开发模式
python -m src.main

# 或使用uvicorn
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问API文档

启动后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API使用示例

### 调用排班Agent

```bash
curl -X POST "http://localhost:8000/api/v1/agents/schedule" \\
  -H "Content-Type: application/json" \\
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "run",
      "store_id": "store_001",
      "date": "2024-02-20",
      "employees": [
        {
          "id": "emp_001",
          "name": "张三",
          "skills": ["waiter", "cashier"]
        }
      ]
    }
  }'
```

### 调用预定Agent

```bash
curl -X POST "http://localhost:8000/api/v1/agents/reservation" \\
  -H "Content-Type: application/json" \\
  -d '{
    "agent_type": "reservation",
    "input_data": {
      "action": "create",
      "reservation_data": {
        "customer_name": "张三",
        "customer_phone": "13800138000",
        "party_size": 4,
        "reservation_date": "2024-02-20",
        "reservation_time": "18:00"
      }
    }
  }'
```

## 请求格式

所有Agent接口使用统一的请求格式:

```json
{
  "agent_type": "agent类型",
  "input_data": {
    "action": "操作类型",
    ...其他参数
  }
}
```

## 响应格式

所有Agent接口返回统一的响应格式:

```json
{
  "agent_type": "agent类型",
  "output_data": {
    "success": true,
    ...结果数据
  },
  "execution_time": 0.123
}
```

## 测试

```bash
# 运行集成测试
python tests/test_agent_integration.py

# 运行所有测试
pytest tests/
```

## 项目结构

```
apps/api-gateway/
├── src/
│   ├── api/           # API路由
│   │   ├── agents.py  # Agent路由
│   │   └── health.py  # 健康检查
│   ├── core/          # 核心配置
│   │   └── config.py  # 配置管理
│   ├── services/      # 服务层
│   │   └── agent_service.py  # Agent服务
│   └── main.py        # 应用入口
├── tests/             # 测试文件
├── requirements.txt   # Python依赖
└── .env.example       # 环境变量示例
```

## 开发指南

### 添加新的Agent

1. 在 `packages/agents/` 创建新的Agent包
2. 在 `agent_service.py` 的 `_initialize_agents()` 中添加初始化代码
3. 在 `agent_service.py` 添加对应的 `_execute_xxx_agent()` 方法
4. 在 `agents.py` 添加新的路由

### 日志

使用structlog进行结构化日志记录:

```python
import structlog
logger = structlog.get_logger()

logger.info("操作完成", agent_type="schedule", result="success")
logger.error("操作失败", agent_type="schedule", exc_info=e)
```

## 故障排查

### Agent初始化失败

检查日志中的错误信息，确保:
1. Agent包路径正确
2. Agent类名正确
3. 所有依赖已安装

### 导入错误

确保Python路径包含agents包:
```python
sys.path.insert(0, str(agents_path))
```

## 许可证

MIT
