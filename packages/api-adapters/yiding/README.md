# 易订适配器 - YiDing Adapter

智链OS与易订预订系统的集成适配器。

## 功能特性

- ✅ 完整的预订管理API
- ✅ 客户信息查询和管理
- ✅ 桌台可用性查询
- ✅ 预订统计和分析
- ✅ 自动重试和错误处理
- ✅ 内存缓存优化性能
- ✅ 统一数据格式转换

## 安装

```bash
cd packages/api-adapters/yiding
pip install -r requirements.txt
```

## 使用示例

### 初始化适配器

```python
from yiding import YiDingAdapter, YiDingConfig

config: YiDingConfig = {
    "base_url": "https://api.yiding.com",
    "app_id": "your_app_id",
    "app_secret": "your_app_secret",
    "timeout": 10,
    "max_retries": 3,
    "cache_ttl": 300
}

adapter = YiDingAdapter(config)
```

### 创建预订

```python
from yiding import CreateReservationDTO, TableType

reservation_data: CreateReservationDTO = {
    "store_id": "STORE001",
    "customer_name": "张三",
    "customer_phone": "13800138000",
    "reservation_date": "2026-02-20",
    "reservation_time": "18:00",
    "party_size": 4,
    "table_type": TableType.MEDIUM,
    "special_requests": "靠窗位置"
}

reservation = await adapter.create_reservation(reservation_data)
print(f"预订成功: {reservation['id']}")
```

### 查询客户

```python
customer = await adapter.get_customer_by_phone("13800138000")

if customer:
    print(f"客户: {customer['name']}")
    print(f"累计消费: {customer['total_spent'] / 100}元")
    print(f"到店次数: {customer['total_visits']}次")
```

### 查询可用桌台

```python
tables = await adapter.get_available_tables(
    store_id="STORE001",
    date="2026-02-20",
    time="18:00",
    party_size=4
)

for table in tables:
    print(f"桌号: {table['table_number']}, 容量: {table['capacity']}人")
```

### 获取预订统计

```python
stats = await adapter.get_reservation_stats(
    store_id="STORE001",
    start_date="2026-02-01",
    end_date="2026-02-28"
)

print(f"总预订数: {stats['total_reservations']}")
print(f"确认率: {stats['confirmation_rate'] * 100}%")
print(f"取消率: {stats['cancellation_rate'] * 100}%")
```

## 数据格式

### UnifiedReservation

```python
{
    "id": "yiding_12345",
    "external_id": "12345",
    "source": "yiding",
    "store_id": "STORE001",
    "customer_name": "张三",
    "customer_phone": "13800138000",
    "reservation_date": "2026-02-20",
    "reservation_time": "18:00",
    "party_size": 4,
    "table_type": "medium",
    "status": "confirmed",
    "deposit_amount": 10000,  # 100元
    "estimated_amount": 40000,  # 400元
    ...
}
```

### UnifiedCustomer

```python
{
    "id": "yiding_67890",
    "external_id": "67890",
    "source": "yiding",
    "phone": "13800138000",
    "name": "张三",
    "member_level": "VIP",
    "total_visits": 15,
    "total_spent": 480000,  # 4800元
    "preferences": {
        "favorite_dishes": ["清蒸鲈鱼", "手撕包菜"],
        "table_preference": "8号包间",
        ...
    },
    ...
}
```

## 错误处理

```python
from yiding import YiDingAPIError

try:
    reservation = await adapter.create_reservation(data)
except YiDingAPIError as e:
    print(f"API错误: {e.message}")
    print(f"状态码: {e.status_code}")
    print(f"错误码: {e.error_code}")
```

## 缓存策略

适配器使用内存缓存来提升性能:

- 单个预订: 缓存5分钟
- 预订列表: 缓存5分钟
- 客户信息: 缓存5分钟

缓存会在数据更新时自动失效。

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_adapter.py::TestYiDingAdapter::test_create_reservation

# 查看覆盖率
pytest --cov=src --cov-report=html tests/
```

## API文档

详细API文档请参考: [易订开放平台文档](https://open.yiding.com/docs)

## 许可证

MIT
