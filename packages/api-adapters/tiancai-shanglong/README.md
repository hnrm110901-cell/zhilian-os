# 天财商龙餐饮管理系统 API 适配器

## 概述

天财商龙餐饮管理系统API适配器，提供订单管理、菜品管理、会员管理、库存管理等功能的Python封装，支持与屯象OS神经系统深度集成。

## 功能特性

### 1. 订单管理
- ✅ 查询订单详情
- ✅ 创建订单
- ✅ 更新订单状态
- ⏳ 订单退款
- ⏳ 订单统计

### 2. 菜品管理
- ✅ 查询菜品列表
- ✅ 更新菜品状态（上架/下架）
- ⏳ 菜品价格调整
- ⏳ 菜品库存管理

### 3. 会员管理
- ✅ 查询会员信息
- ✅ 新增会员
- ✅ 会员充值
- ⏳ 会员积分管理
- ⏳ 会员等级调整

### 4. 库存管理
- ✅ 查询库存
- ✅ 更新库存（入库/出库/盘点）
- ⏳ 库存预警
- ⏳ 库存报表

## 安装

```bash
# 在项目根目录
cd packages/api-adapters/tiancai-shanglong
pip install -r requirements.txt
```

## 配置

```python
config = {
    "base_url": "https://api.tiancai.com",  # API基础URL
    "app_id": "your-app-id",                # 应用ID
    "app_secret": "your-app-secret",        # 应用密钥
    "store_id": "STORE001",                 # 门店ID
    "timeout": 30,                          # 超时时间（秒）
    "retry_times": 3                        # 重试次数
}
```

## 使用示例

### 初始化适配器

```python
from packages.api_adapters.tiancai_shanglong.src import TiancaiShanglongAdapter

# 创建适配器实例
adapter = TiancaiShanglongAdapter(config)
```

### 订单管理

```python
# 查询订单
order = await adapter.query_order(order_id="ORD20240001")
print(f"订单号: {order['order_no']}")
print(f"桌号: {order['table_no']}")
print(f"总金额: {order['total_amount']} 分")
print(f"实付金额: {order['real_amount']} 分")

# 创建订单
new_order = await adapter.create_order(
    table_no="A01",
    dishes=[
        {"dish_id": "D001", "quantity": 2, "price": 4800},
        {"dish_id": "D002", "quantity": 1, "price": 3800}
    ],
    member_id="M20240001"
)
print(f"订单创建成功: {new_order['order_id']}")

# 更新订单状态
result = await adapter.update_order_status(
    order_id="ORD20240001",
    status=2,  # 已支付
    pay_type=2,  # 微信支付
    pay_amount=14800
)
```

### 菜品管理

```python
# 查询菜品
dishes = await adapter.query_dish(category_id="C001")
for dish in dishes:
    print(f"菜品: {dish['dish_name']}, 价格: {dish['price']} 分")

# 更新菜品状态
result = await adapter.update_dish_status(
    dish_id="D001",
    status=0  # 停售
)
```

### 会员管理

```python
# 查询会员
member = await adapter.query_member(mobile="13800138000")
print(f"会员姓名: {member['name']}")
print(f"会员等级: {member['level']}")
print(f"积分: {member['points']}")
print(f"余额: {member['balance']} 分")

# 新增会员
new_member = await adapter.add_member(
    mobile="13900139000",
    name="李四",
    card_no="C20240002"
)

# 会员充值
recharge = await adapter.member_recharge(
    member_id="M20240001",
    amount=100000,  # 1000元 = 100000分
    pay_type=2  # 微信支付
)
```

### 库存管理

```python
# 查询库存
inventory = await adapter.query_inventory(material_id="M001")
for item in inventory:
    print(f"原料: {item['material_name']}, 库存: {item['quantity']} {item['unit']}")

# 更新库存
result = await adapter.update_inventory(
    material_id="M001",
    quantity=50.5,
    operation_type=1  # 入库
)
```

## 与屯象OS集成

### 通过集成服务使用

```python
from apps.api_gateway.src.services.adapter_integration_service import AdapterIntegrationService
from apps.api_gateway.src.services.neural_system import neural_system

# 初始化集成服务
integration_service = AdapterIntegrationService(neural_system=neural_system)

# 注册天财商龙适配器
adapter = TiancaiShanglongAdapter(config)
integration_service.register_adapter("tiancai", adapter, config)

# 同步订单到屯象OS
result = await integration_service.sync_order_from_tiancai(
    order_id="ORD20240001",
    store_id="STORE001"
)

# 同步菜品到屯象OS
result = await integration_service.sync_dishes_from_tiancai(
    store_id="STORE001"
)

# 全量同步
result = await integration_service.sync_all_from_tiancai(
    store_id="STORE001"
)
```

### 通过API接口使用

```bash
# 注册适配器
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

# 同步订单
curl -X POST http://localhost:8000/api/adapters/sync/order \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD20240001",
    "store_id": "STORE001",
    "source_system": "tiancai"
  }'

# 同步菜品
curl -X POST http://localhost:8000/api/adapters/sync/dishes \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "STORE001",
    "source_system": "tiancai"
  }'

# 全量同步
curl -X POST http://localhost:8000/api/adapters/sync/all/tiancai/STORE001
```

## 数据类型约定

### 金额单位
**重要**: 所有金额字段的单位均为"分"（cent），而非"元"（yuan）

| 实际金额 | API参数值 |
|----------|-----------|
| ¥1.00    | 100       |
| ¥100.00  | 10000     |
| ¥0.50    | 50        |

### 日期时间格式
| 格式     | 说明           | 示例                |
|----------|----------------|---------------------|
| 日期时间 | YYYY-MM-DD HH:mm:ss | 2024-01-15 10:30:00 |

### 订单状态
| 状态码 | 说明   |
|--------|--------|
| 1      | 待支付 |
| 2      | 已支付 |
| 3      | 已取消 |

### 支付方式
| 代码 | 支付方式   |
|------|------------|
| 1    | 现金       |
| 2    | 微信支付   |
| 3    | 支付宝     |
| 4    | 会员卡     |

### 库存操作类型
| 类型 | 说明 |
|------|------|
| 1    | 入库 |
| 2    | 出库 |
| 3    | 盘点 |

## 签名算法

天财商龙API使用MD5签名算法：

1. 将所有请求参数按key排序
2. 拼接字符串：`app_id={app_id}&key1=value1&key2=value2&timestamp={timestamp}&app_secret={app_secret}`
3. 对拼接字符串进行MD5加密
4. 将签名转换为大写

## 错误处理

```python
try:
    order = await adapter.query_order(order_id="ORD20240001")
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

## 注意事项

1. **API密钥安全**: 不要将API密钥硬编码在代码中，使用环境变量
2. **金额单位**: 所有金额必须使用"分"作为单位
3. **异步调用**: 所有API方法都是异步的，需要使用`await`
4. **错误处理**: 建议使用try-except捕获异常
5. **资源释放**: 使用完毕后调用`await adapter.close()`释放资源
6. **签名验证**: 确保app_id和app_secret正确，否则签名验证会失败

## 开发状态

- ✅ 已完成: 核心功能实现
- ⏳ 进行中: 实际API调用集成（需要实际API文档）
- 📝 计划中: 更多高级功能

## 许可证

MIT License
