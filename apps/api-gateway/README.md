# 屯象OS API Gateway

屯象OS的API网关服务，提供统一的HTTP API接口访问所有智能体和业务功能。

## 功能特性

### 核心功能
- 统一的Agent调用接口
- 自动错误处理和日志记录
- 执行时间统计
- CORS支持
- API文档自动生成

### MVP功能 (已完成)
- **任务管理系统**: 创建、分配、跟踪任务，支持优先级和状态管理
- **营业日报**: 自动生成每日营业报告，通过企业微信推送
- **POS对账系统**: 自动对比POS数据与实际订单，异常告警
- **企业微信集成**: 消息推送、用户查询、Webhook签名验证
- **多渠道通知**: 支持企业微信、飞书、短信、语音等多种通知方式
- **OAuth登录**: 支持企业微信、飞书、钉钉等企业OAuth登录
- **Redis缓存**: 提升系统性能和响应速度

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

企业集成最小配置:

```bash
# 企业微信
WECHAT_CORP_ID=your_corp_id
WECHAT_CORP_SECRET=your_corp_secret
WECHAT_AGENT_ID=1000001
WECHAT_TOKEN=your_callback_token
WECHAT_ENCODING_AES_KEY=your_encoding_aes_key

# 飞书
FEISHU_APP_ID=cli_your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_VERIFICATION_TOKEN=your_verification_token
FEISHU_ENCRYPT_KEY=your_encrypt_key
```

说明:
- 企业微信 webhook 依赖 `WECHAT_TOKEN` 和 `WECHAT_ENCODING_AES_KEY`
- 飞书 webhook 至少应配置 `FEISHU_VERIFICATION_TOKEN`
- 配置 `FEISHU_ENCRYPT_KEY` 后会启用请求签名校验
- 可通过 `/api/v1/health/config/validation` 检查 webhook 安全配置是否完整
- 可通过 `/api/v1/enterprise/support-matrix` 查看真实支持能力
- 可通过 `/api/v1/enterprise/readiness` 做上线前自检

树莓派 5 边缘节点 bootstrap 最小配置:

```bash
EDGE_BOOTSTRAP_TOKEN=replace-with-edge-bootstrap-token
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
- 详细API文档: [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- Postman集合: [postman_collection.json](postman_collection.json)
- 企业集成支持矩阵: [../docs/enterprise-integration-support-matrix.md](../docs/enterprise-integration-support-matrix.md)

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
# 运行所有测试
pytest tests/

# 运行迁移验证（head / offline SQL / online upgrade）
bash scripts/verify_migrations.sh

# 运行特定测试文件
pytest tests/test_task_service.py

# 查看测试覆盖率
pytest --cov=src --cov-report=html

# 运行集成测试
python tests/test_agent_integration.py
```

详细测试说明请查看 [tests/README.md](tests/README.md)
迁移验证与开发库恢复请查看 [MIGRATION_VALIDATION.md](MIGRATION_VALIDATION.md) 和 [DEV_DB_RECOVERY.md](DEV_DB_RECOVERY.md)

树莓派 5 边缘节点第一版安装器与差距清单请查看 [RASPBERRY_PI_EDGE_INSTALLER.md](RASPBERRY_PI_EDGE_INSTALLER.md) 和 [EDGE_NODE_GAP_ANALYSIS.md](EDGE_NODE_GAP_ANALYSIS.md)
现场远程安装手册请查看 [REMOTE_EDGE_INSTALL_RUNBOOK.md](REMOTE_EDGE_INSTALL_RUNBOOK.md)

常用树莓派 5 命令:

```bash
# 本地安装
bash scripts/install_raspberry_pi_edge.sh

# 远程 SSH 安装
bash scripts/install_raspberry_pi_edge_remote.sh

# 启用开机自动安装 / 自动注册
bash scripts/enable_raspberry_pi_edge_autoprovision.sh
```

## 部署

详细部署指南请查看 [DEPLOYMENT.md](DEPLOYMENT.md)

快速启动:

```bash
# 1. 运行数据库迁移
python3 -m alembic upgrade head

# 2. 启动API服务
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 3. 启动Celery Worker
celery -A src.core.celery_app worker --loglevel=info

# 4. 启动Celery Beat (定时任务)
./scripts/start_celery_beat.sh
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
