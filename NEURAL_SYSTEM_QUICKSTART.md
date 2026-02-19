# 智链OS神经系统快速开始指南

## 概述

智链OS神经系统是餐饮门店的智能中枢，提供事件处理、语义搜索和联邦学习能力。

## 快速开始

### 1. 启动基础设施

使用Docker Compose启动所需的服务（PostgreSQL、Redis、Qdrant）：

```bash
# 开发环境
docker-compose up -d

# 生产环境
docker-compose -f docker-compose.prod.yml up -d
```

验证服务状态：
```bash
# 检查所有服务
docker-compose ps

# 访问Qdrant管理界面
open http://localhost:6333/dashboard
```

### 2. 安装依赖

```bash
cd apps/api-gateway
pip install -r requirements.txt
```

主要依赖：
- `qdrant-client==1.7.3` - 向量数据库客户端
- `sentence-transformers==2.3.1` - 文本嵌入模型
- `torch==2.1.2` - PyTorch深度学习框架
- `numpy==1.26.3` - 数值计算库

### 3. 配置环境变量

复制环境变量模板：
```bash
cp .env.example .env
```

关键配置项：
```bash
# 向量数据库
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# 神经系统
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSION=384
NEURAL_SYSTEM_ENABLED=true

# 联邦学习
FL_MIN_STORES=3
FL_AGGREGATION_THRESHOLD=0.8
FL_LEARNING_RATE=0.01
```

### 4. 启动API服务

```bash
cd apps/api-gateway
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

访问API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API使用示例

### 1. 发射事件

```bash
curl -X POST "http://localhost:8000/api/v1/neural/events/emit" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "order",
    "store_id": "store_001",
    "data": {
      "order_id": "ORD20260219001",
      "total_amount": 158.50,
      "status": "completed",
      "items": [
        {"dish_name": "宫保鸡丁", "quantity": 1, "price": 48.00},
        {"dish_name": "麻婆豆腐", "quantity": 2, "price": 38.00}
      ]
    }
  }'
```

### 2. 语义搜索订单

```bash
curl -X POST "http://localhost:8000/api/v1/neural/search/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "今天下午的大额订单",
    "store_id": "store_001",
    "top_k": 10
  }'
```

### 3. 语义搜索菜品

```bash
curl -X POST "http://localhost:8000/api/v1/neural/search/dishes" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "低卡路里的素食菜品",
    "store_id": "store_001",
    "top_k": 5
  }'
```

### 4. 参与联邦学习

```bash
curl -X POST "http://localhost:8000/api/v1/neural/federated-learning/participate" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "store_001",
    "local_model_path": "/models/local_model.pkl",
    "training_samples": 1000,
    "metrics": {
      "accuracy": 0.95,
      "loss": 0.05
    }
  }'
```

### 5. 查看系统状态

```bash
curl -X GET "http://localhost:8000/api/v1/neural/status"
```

### 6. 健康检查

```bash
curl -X GET "http://localhost:8000/api/v1/neural/health"
```

## Python SDK使用示例

### 初始化神经系统

```python
from src.services.neural_system import NeuralSystemOrchestrator
from src.schemas.restaurant_standard_schema import NeuralEventSchema
from datetime import datetime

# 创建神经系统实例
neural_system = NeuralSystemOrchestrator()
```

### 发射订单事件

```python
# 创建订单事件
order_event = NeuralEventSchema(
    event_id="order_store_001_1708329600",
    event_type="order",
    store_id="store_001",
    timestamp=datetime.now(),
    data={
        "order_id": "ORD20260219001",
        "total_amount": 158.50,
        "status": "completed",
        "items": [
            {"dish_name": "宫保鸡丁", "quantity": 1, "price": 48.00},
            {"dish_name": "麻婆豆腐", "quantity": 2, "price": 38.00}
        ]
    },
    metadata={"source": "pos_system"}
)

# 发射事件
await neural_system.emit_event(order_event)
```

### 语义搜索

```python
# 搜索订单
results = await neural_system.semantic_search_orders(
    query="今天下午的大额订单",
    store_id="store_001",
    top_k=10
)

for result in results:
    print(f"订单ID: {result['payload']['order_id']}")
    print(f"相似度: {result['score']}")
    print(f"金额: {result['payload']['total_amount']}")
    print("---")
```

### 参与联邦学习

```python
# 训练本地模型
local_model = {"weights": [...], "bias": [...]}

# 参与联邦学习
success = await neural_system.participate_in_federated_learning(
    store_id="store_001",
    local_model=local_model,
    training_samples=1000
)

if success:
    print("成功参与联邦学习")
```

## 架构说明

### 五大核心维度

1. **订单维度** - 订单信息、订单项、金额、时间、人员
2. **菜品维度** - 菜品信息、配料、营养、价格、制作
3. **人员维度** - 员工信息、班次、绩效、技能
4. **时间维度** - 时间段、营业时间、高峰时段
5. **金额维度** - 交易信息、财务汇总

### 三大核心服务

1. **向量数据库服务** - Qdrant + Sentence-Transformers
2. **联邦学习服务** - FedAvg算法 + 数据隔离
3. **神经系统编排器** - 事件驱动 + Agent集成

### 数据隔离

- 向量数据库层：强制 `store_id` 过滤
- 联邦学习层：仅上传模型参数，原始数据不出门店
- API层：权限验证，跨门店访问被拒绝

## 故障排查

### Qdrant连接失败

```bash
# 检查Qdrant服务状态
docker ps | grep qdrant

# 查看Qdrant日志
docker logs zhilian-qdrant-dev

# 重启Qdrant
docker-compose restart qdrant
```

### 模型下载慢

首次运行时，sentence-transformers会下载预训练模型（约400MB）。如果下载慢，可以：

```bash
# 设置镜像源
export HF_ENDPOINT=https://hf-mirror.com

# 或手动下载模型
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### 内存不足

向量数据库和嵌入模型需要较多内存。建议：
- 开发环境：至少8GB RAM
- 生产环境：至少16GB RAM

## 性能优化

### 批量索引

```python
# 批量索引订单
orders = [order1, order2, order3, ...]
for order in orders:
    await neural_system.vector_db.index_order(order, store_id)
```

### 缓存嵌入

```python
# 缓存常用查询的嵌入向量
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_query_embedding(query: str):
    return neural_system.vector_db.embedding_model.encode(query)
```

## 下一步

- 查看完整文档：[NEURAL_SYSTEM_IMPLEMENTATION.md](./NEURAL_SYSTEM_IMPLEMENTATION.md)
- 集成到现有系统：参考 `apps/api-gateway/src/services/neural_system.py`
- 自定义事件处理器：扩展 `NeuralSystemOrchestrator` 类

## 技术支持

如有问题，请查看：
- API文档：http://localhost:8000/docs
- 项目文档：[NEURAL_SYSTEM_IMPLEMENTATION.md](./NEURAL_SYSTEM_IMPLEMENTATION.md)
- GitHub Issues：https://github.com/hnrm110901-cell/zhilian-os/issues
