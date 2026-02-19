# 智链OS API适配器集成指南

## 概述

智链OS API适配器集成服务提供统一的接口，用于连接各种第三方餐饮管理系统（天财商龙、美团SAAS、奥琦韦、品智等），并与智链OS神经系统深度集成，实现数据的实时同步和智能处理。

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      智链OS神经系统                          │
│  (Neural System - 事件驱动 + 向量数据库 + 联邦学习)          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              API适配器集成服务                               │
│        (Adapter Integration Service)                        │
│  - 适配器注册管理                                            │
│  - 数据格式转换                                              │
│  - 事件路由分发                                              │
│  - 错误处理重试                                              │
└─────┬──────┬──────┬──────┬──────────────────────────────────┘
      │      │      │      │
      ↓      ↓      ↓      ↓
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│天财商龙 │ │美团SAAS │ │ 奥琦韦  │ │  品智   │
│ Adapter │ │ Adapter │ │ Adapter │ │ Adapter │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
      │          │          │          │
      ↓          ↓          ↓          ↓
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│天财商龙 │ │美团开放 │ │奥琦韦API│ │品智API  │
│   API   │ │ 平台API │ │         │ │         │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

## 支持的适配器

### 1. 天财商龙 (Tiancai Shanglong)
- **类型**: 餐饮管理系统
- **功能**: 订单管理、菜品管理、会员管理、库存管理
- **适配器**: `TiancaiShanglongAdapter`
- **文档**: [天财商龙适配器文档](../tiancai-shanglong/README.md)

### 2. 美团SAAS (Meituan SAAS)
- **类型**: 外卖平台
- **功能**: 订单管理、商品管理、门店管理、配送管理
- **适配器**: `MeituanSaasAdapter`
- **文档**: [美团SAAS适配器文档](../meituan-saas/README.md)

### 3. 奥琦韦 (Aoqiwei)
- **类型**: 会员管理系统
- **功能**: 会员管理、交易处理、储值管理、优惠券管理
- **适配器**: `AoqiweiAdapter`
- **文档**: [奥琦韦适配器文档](../aoqiwei/README.md)

### 4. 品智 (Pinzhi)
- **类型**: 餐饮管理系统
- **功能**: 订单管理、会员管理
- **适配器**: `PinzhiAdapter`

## 快速开始

### 1. 安装依赖

```bash
cd /Users/lichun/Desktop/zhilian-os
pip install httpx structlog pydantic qdrant-client sentence-transformers
```

### 2. 配置适配器

创建配置文件 `config/adapters.yaml`:

```yaml
adapters:
  tiancai:
    base_url: "https://api.tiancai.com"
    app_id: "your-app-id"
    app_secret: "your-app-secret"
    store_id: "STORE001"
    timeout: 30
    retry_times: 3

  meituan:
    base_url: "https://waimaiopen.meituan.com"
    app_key: "your-app-key"
    app_secret: "your-app-secret"
    poi_id: "POI001"
    timeout: 30
    retry_times: 3

  aoqiwei:
    base_url: "https://api.aoqiwei.com"
    api_key: "your-api-key"
    timeout: 30
    retry_times: 3

  pinzhi:
    base_url: "https://api.pinzhi.com"
    api_key: "your-api-key"
    timeout: 30
    retry_times: 3
```

### 3. 启动API服务

```bash
cd apps/api-gateway
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 注册适配器

```bash
# 注册天财商龙适配器
curl -X POST http://localhost:8000/api/adapters/register \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_name": "tiancai",
    "config": {
      "base_url": "https://api.tiancai.com",
      "app_id": "your-app-id",
      "app_secret": "your-app-secret",
      "store_id": "STORE001"
    }
  }'

# 注册美团适配器
curl -X POST http://localhost:8000/api/adapters/register \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_name": "meituan",
    "config": {
      "base_url": "https://waimaiopen.meituan.com",
      "app_key": "your-app-key",
      "app_secret": "your-app-secret",
      "poi_id": "POI001"
    }
  }'
```

## 使用场景

### 场景1: 订单同步

当天财商龙或美团收到新订单时，自动同步到智链OS神经系统：

```bash
# 从天财商龙同步订单
curl -X POST http://localhost:8000/api/adapters/sync/order \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD20240001",
    "store_id": "STORE001",
    "source_system": "tiancai"
  }'

# 从美团同步订单
curl -X POST http://localhost:8000/api/adapters/sync/order \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "MT20240001",
    "store_id": "STORE001",
    "source_system": "meituan"
  }'
```

**智链OS处理流程**:
1. 接收订单数据
2. 转换为标准格式
3. 发送到神经系统事件队列
4. 向量化订单信息并存储到Qdrant
5. 触发联邦学习更新
6. 生成智能推荐

### 场景2: 菜品同步

定期从各系统同步菜品信息到智链OS：

```bash
# 从天财商龙同步菜品
curl -X POST http://localhost:8000/api/adapters/sync/dishes \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "STORE001",
    "source_system": "tiancai"
  }'

# 从美团同步商品
curl -X POST http://localhost:8000/api/adapters/sync/dishes \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "STORE001",
    "source_system": "meituan"
  }'
```

**智链OS处理流程**:
1. 批量获取菜品数据
2. 转换为标准格式
3. 向量化菜品描述
4. 存储到向量数据库
5. 支持语义搜索

### 场景3: 库存同步

智链OS检测到库存变化时，同步到各平台：

```bash
# 同步库存到美团
curl -X POST http://localhost:8000/api/adapters/sync/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "F001",
    "quantity": 50,
    "target_system": "meituan"
  }'

# 同步库存到天财商龙
curl -X POST http://localhost:8000/api/adapters/sync/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "M001",
    "quantity": 50.5,
    "target_system": "tiancai",
    "operation_type": 1
  }'
```

### 场景4: 全量同步

首次接入或数据恢复时，执行全量同步：

```bash
# 从天财商龙全量同步
curl -X POST http://localhost:8000/api/adapters/sync/all/tiancai/STORE001

# 从美团全量同步
curl -X POST http://localhost:8000/api/adapters/sync/all/meituan/STORE001
```

## Python SDK使用

### 基础使用

```python
from apps.api_gateway.src.services.adapter_integration_service import AdapterIntegrationService
from apps.api_gateway.src.services.neural_system import neural_system
from packages.api_adapters.tiancai_shanglong.src import TiancaiShanglongAdapter
from packages.api_adapters.meituan_saas.src import MeituanSaasAdapter

# 初始化集成服务
integration_service = AdapterIntegrationService(neural_system=neural_system)

# 注册适配器
tiancai_adapter = TiancaiShanglongAdapter({
    "base_url": "https://api.tiancai.com",
    "app_id": "your-app-id",
    "app_secret": "your-app-secret",
    "store_id": "STORE001"
})
integration_service.register_adapter("tiancai", tiancai_adapter, config)

meituan_adapter = MeituanSaasAdapter({
    "base_url": "https://waimaiopen.meituan.com",
    "app_key": "your-app-key",
    "app_secret": "your-app-secret",
    "poi_id": "POI001"
})
integration_service.register_adapter("meituan", meituan_adapter, config)

# 同步订单
result = await integration_service.sync_order_from_tiancai(
    order_id="ORD20240001",
    store_id="STORE001"
)

# 同步菜品
result = await integration_service.sync_dishes_from_meituan(
    store_id="STORE001"
)

# 关闭服务
await integration_service.close()
```

### 高级使用 - 自定义事件处理

```python
from apps.api_gateway.src.services.neural_system import NeuralSystemOrchestrator

# 创建自定义神经系统
custom_neural_system = NeuralSystemOrchestrator()

# 注册自定义事件处理器
@custom_neural_system.register_handler("order.created")
async def handle_order_created(event_data):
    """处理订单创建事件"""
    order = event_data["data"]
    print(f"收到新订单: {order['order_id']}")

    # 自定义业务逻辑
    if order["total_amount"] > 1000:
        # 大额订单特殊处理
        await send_notification(order)

# 使用自定义神经系统
integration_service = AdapterIntegrationService(neural_system=custom_neural_system)
```

## 数据格式标准

### 标准订单格式

```python
{
    "order_id": "ORD20240001",
    "order_no": "NO20240001",
    "source_system": "tiancai",  # tiancai, meituan, aoqiwei, pinzhi
    "store_id": "STORE001",
    "order_time": "2024-01-15 10:30:00",
    "total_amount": 158.00,  # 元
    "discount_amount": 10.00,
    "real_amount": 148.00,
    "status": 2,  # 1-待支付 2-已支付 3-已取消
    "dishes": [
        {
            "dish_id": "D001",
            "dish_name": "宫保鸡丁",
            "price": 48.00,
            "quantity": 2,
            "amount": 96.00
        }
    ]
}
```

### 标准菜品格式

```python
{
    "dish_id": "D001",
    "dish_name": "宫保鸡丁",
    "source_system": "tiancai",
    "category_id": "C001",
    "category_name": "热菜",
    "price": 48.00,  # 元
    "unit": "份",
    "status": 1,  # 1-在售 0-停售
    "stock": 100
}
```

## 错误处理

### 错误类型

1. **适配器未注册**: 使用前需先注册适配器
2. **API调用失败**: 网络问题或API错误
3. **数据格式错误**: 数据转换失败
4. **神经系统错误**: 事件处理失败

### 错误处理示例

```python
try:
    result = await integration_service.sync_order_from_tiancai(
        order_id="ORD20240001",
        store_id="STORE001"
    )
except ValueError as e:
    # 适配器未注册或参数错误
    logger.error(f"参数错误: {e}")
except Exception as e:
    # API调用失败或其他错误
    logger.error(f"同步失败: {e}")
    # 可以实现重试逻辑
    await retry_sync(order_id, store_id)
```

## 性能优化

### 1. 批量同步

```python
# 批量同步订单
order_ids = ["ORD001", "ORD002", "ORD003"]
tasks = [
    integration_service.sync_order_from_tiancai(order_id, "STORE001")
    for order_id in order_ids
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 2. 缓存机制

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
async def get_dish_info(dish_id: str):
    """缓存菜品信息"""
    return await adapter.query_dish(dish_id=dish_id)
```

### 3. 异步处理

```python
# 使用后台任务处理同步
from fastapi import BackgroundTasks

@router.post("/sync/order/background")
async def sync_order_background(
    request: OrderSyncRequest,
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(
        integration_service.sync_order_from_tiancai,
        request.order_id,
        request.store_id
    )
    return {"status": "queued"}
```

## 监控和日志

### 日志配置

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
```

### 监控指标

- 同步成功率
- API响应时间
- 错误率
- 数据量统计

## 安全建议

1. **API密钥管理**: 使用环境变量或密钥管理服务
2. **签名验证**: 验证所有API请求的签名
3. **HTTPS**: 生产环境必须使用HTTPS
4. **访问控制**: 限制API访问权限
5. **数据加密**: 敏感数据加密存储

## 常见问题

### Q1: 如何添加新的适配器？

1. 在 `packages/api-adapters/` 创建新目录
2. 实现适配器类，继承 `BaseAdapter`
3. 在集成服务中注册适配器
4. 添加数据转换方法

### Q2: 如何处理API限流？

使用指数退避重试策略：

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60)
)
async def sync_with_retry(order_id, store_id):
    return await integration_service.sync_order_from_tiancai(order_id, store_id)
```

### Q3: 如何实现实时同步？

使用Webhook回调：

```python
@router.post("/webhook/tiancai/order")
async def tiancai_order_webhook(request: Request):
    data = await request.json()
    await integration_service.sync_order_from_tiancai(
        order_id=data["order_id"],
        store_id=data["store_id"]
    )
    return {"code": 0, "message": "success"}
```

## 下一步

1. 阅读各适配器的详细文档
2. 配置适配器参数
3. 测试API接口
4. 部署到生产环境
5. 监控运行状态

## 参考资料

- [天财商龙适配器文档](../tiancai-shanglong/README.md)
- [美团SAAS适配器文档](../meituan-saas/README.md)
- [奥琦韦适配器文档](../aoqiwei/README.md)
- [智链OS神经系统文档](../../apps/api-gateway/docs/NEURAL_SYSTEM.md)

## 许可证

MIT License
