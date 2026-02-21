# 美团餐饮SAAS平台 API 适配器

## 概述

美团餐饮SAAS平台API适配器，提供订单管理、门店管理、商品管理、配送管理等功能的Python封装，支持与智链OS神经系统深度集成。

## 功能特性

### 1. 订单管理
- ✅ 查询订单详情
- ✅ 确认订单
- ✅ 取消订单
- ✅ 订单退款
- ⏳ 订单统计

### 2. 商品管理
- ✅ 查询商品列表
- ✅ 更新商品库存
- ✅ 更新商品价格
- ✅ 商品上架/下架
- ⏳ 批量操作

### 3. 门店管理
- ✅ 查询门店信息
- ✅ 更新门店营业状态
- ⏳ 门店配置管理

### 4. 配送管理
- ✅ 查询配送信息
- ⏳ 配送状态更新
- ⏳ 骑手信息查询

## 安装

```bash
# 在项目根目录
cd packages/api-adapters/meituan-saas
pip install -r requirements.txt
```

## 配置

```python
config = {
    "base_url": "https://waimaiopen.meituan.com",  # API基础URL
    "app_key": "your-app-key",                     # 应用Key
    "app_secret": "your-app-secret",               # 应用密钥
    "poi_id": "POI001",                            # 门店ID (Point of Interest)
    "timeout": 30,                                 # 超时时间（秒）
    "retry_times": 3                               # 重试次数
}
```

## 使用示例

### 初始化适配器

```python
from packages.api_adapters.meituan_saas.src import MeituanSaasAdapter

# 创建适配器实例
adapter = MeituanSaasAdapter(config)
```

### 订单管理

```python
# 查询订单
order = await adapter.query_order(order_id="MT20240001")
print(f"订单号: {order['order_id']}")
print(f"收货人: {order['recipient_name']}")
print(f"收货地址: {order['recipient_address']}")
print(f"订单金额: {order['total']} 分")

# 确认订单
result = await adapter.confirm_order(order_id="MT20240001")
print(f"订单确认成功")

# 取消订单
result = await adapter.cancel_order(
    order_id="MT20240001",
    reason_code=1001,
    reason="商品售罄"
)

# 订单退款
result = await adapter.refund_order(
    order_id="MT20240001",
    reason="用户要求退款"
)
```

### 商品管理

```python
# 查询商品
foods = await adapter.query_food(category_id="C001")
for food in foods:
    print(f"商品: {food['food_name']}, 价格: {food['price']} 分, 库存: {food['stock']}")

# 更新商品库存
result = await adapter.update_food_stock(
    food_id="F001",
    stock=100
)

# 更新商品价格
result = await adapter.update_food_price(
    food_id="F001",
    price=4800  # 48元 = 4800分
)

# 商品售罄
result = await adapter.sold_out_food(food_id="F001")

# 商品上架
result = await adapter.on_sale_food(food_id="F001")
```

### 门店管理

```python
# 查询门店信息
poi_info = await adapter.query_poi_info()
print(f"门店名称: {poi_info['poi_name']}")
print(f"门店地址: {poi_info['address']}")
print(f"营业状态: {'营业中' if poi_info['is_online'] == 1 else '休息中'}")
print(f"营业时间: {poi_info['open_time']} - {poi_info['close_time']}")

# 更新门店营业状态
result = await adapter.update_poi_status(is_online=1)  # 1-营业中 0-休息中
```

### 配送管理

```python
# 查询配送信息
logistics = await adapter.query_logistics(order_id="MT20240001")
print(f"配送状态: {logistics['logistics_status']}")
print(f"骑手姓名: {logistics['courier_name']}")
print(f"骑手电话: {logistics['courier_phone']}")
print(f"当前位置: ({logistics['latitude']}, {logistics['longitude']})")
```

## 与智链OS集成

### 通过集成服务使用

```python
from apps.api_gateway.src.services.adapter_integration_service import AdapterIntegrationService
from apps.api_gateway.src.services.neural_system import neural_system

# 初始化集成服务
integration_service = AdapterIntegrationService(neural_system=neural_system)

# 注册美团适配器
adapter = MeituanSaasAdapter(config)
integration_service.register_adapter("meituan", adapter, config)

# 同步订单到智链OS
result = await integration_service.sync_order_from_meituan(
    order_id="MT20240001",
    store_id="STORE001"
)

# 同步商品到智链OS
result = await integration_service.sync_dishes_from_meituan(
    store_id="STORE001"
)

# 同步库存到美团
result = await integration_service.sync_inventory_to_meituan(
    food_id="F001",
    stock=100
)

# 全量同步
result = await integration_service.sync_all_from_meituan(
    store_id="STORE001"
)
```

### 通过API接口使用

```bash
# 注册适配器
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

# 同步订单
curl -X POST http://localhost:8000/api/adapters/sync/order \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "MT20240001",
    "store_id": "STORE001",
    "source_system": "meituan"
  }'

# 同步商品
curl -X POST http://localhost:8000/api/adapters/sync/dishes \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "STORE001",
    "source_system": "meituan"
  }'

# 同步库存
curl -X POST http://localhost:8000/api/adapters/sync/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "F001",
    "quantity": 100,
    "target_system": "meituan"
  }'

# 全量同步
curl -X POST http://localhost:8000/api/adapters/sync/all/meituan/STORE001
```

## 数据类型约定

### 金额单位
**重要**: 所有金额字段的单位均为"分"（cent），而非"元"（yuan）

| 实际金额 | API参数值 |
|----------|-----------|
| ¥1.00    | 100       |
| ¥100.00  | 10000     |
| ¥0.50    | 50        |

### 时间戳格式
美团API使用Unix时间戳（秒）

```python
import time
timestamp = int(time.time())  # 当前时间戳
```

### 订单状态
| 状态码 | 说明       |
|--------|------------|
| 2      | 已确认     |
| 4      | 配送中     |
| 8      | 已完成     |
| 9      | 已取消     |

### 配送状态
| 状态码 | 说明       |
|--------|------------|
| 0      | 待调度     |
| 10     | 待取货     |
| 20     | 配送中     |
| 30     | 已送达     |
| 100    | 已取消     |

### 取消原因代码
| 代码 | 说明       |
|------|------------|
| 1001 | 商品售罄   |
| 1002 | 门店休息   |
| 1003 | 配送范围外 |
| 1004 | 其他原因   |

## 签名算法

美团API使用MD5签名算法：

1. 将所有请求参数（包括app_key和timestamp）按key排序
2. 拼接字符串：`{app_secret}key1value1key2value2{app_secret}`
3. 对拼接字符串进行MD5加密
4. 将签名转换为小写

示例：
```python
import hashlib

params = {"app_key": "test", "timestamp": "1234567890", "order_id": "123"}
sorted_params = sorted(params.items())

sign_str = "secret"  # app_secret
for k, v in sorted_params:
    sign_str += f"{k}{v}"
sign_str += "secret"

sign = hashlib.md5(sign_str.encode()).hexdigest().lower()
```

## Webhook回调

美团会通过Webhook推送订单状态变更：

```python
from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/webhook/meituan/order")
async def meituan_order_webhook(request: Request):
    """接收美团订单回调"""
    data = await request.json()

    # 验证签名
    sign = data.get("sign")
    # ... 验证逻辑

    # 处理订单事件
    order_id = data.get("order_id")
    status = data.get("status")

    # 同步到智链OS
    await integration_service.sync_order_from_meituan(
        order_id=order_id,
        store_id="STORE001"
    )

    return {"code": "ok"}
```

## 错误处理

```python
try:
    order = await adapter.query_order(order_id="MT20240001")
except ValueError as e:
    # 参数错误
    print(f"参数错误: {e}")
except Exception as e:
    # API调用失败
    print(f"API错误: {e}")
finally:
    # 关闭适配器
    await adapter.close()
```

## 常见错误码

| 错误码 | 说明               | 解决方案                   |
|--------|--------------------|-----------------------------|
| 1001   | 签名错误           | 检查app_key和app_secret     |
| 1002   | 参数错误           | 检查必填参数                |
| 1003   | 门店不存在         | 检查poi_id是否正确          |
| 2001   | 订单不存在         | 检查order_id是否正确        |
| 2002   | 订单状态不允许操作 | 检查订单当前状态            |

## 注意事项

1. **API密钥安全**: 不要将API密钥硬编码在代码中，使用环境变量
2. **金额单位**: 所有金额必须使用"分"作为单位
3. **时间戳**: 使用Unix时间戳（秒），注意时区问题
4. **异步调用**: 所有API方法都是异步的，需要使用`await`
5. **错误处理**: 建议使用try-except捕获异常
6. **资源释放**: 使用完毕后调用`await adapter.close()`释放资源
7. **签名验证**: 确保app_key和app_secret正确，否则签名验证会失败
8. **Webhook回调**: 需要配置公网可访问的回调地址
9. **请求频率**: 注意API调用频率限制，避免被限流

## 开发状态

- ✅ 已完成: 核心功能实现
- ⏳ 进行中: 实际API调用集成（需要实际API文档）
- 📝 计划中: Webhook回调处理、批量操作

## 参考资料

- [美团开放平台文档](https://open.meituan.com/)
- [美团外卖开放平台](https://waimaiopen.meituan.com/)

## 许可证

MIT License
