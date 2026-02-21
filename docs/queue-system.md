# 排队/等位系统

## 概述

排队/等位系统是智链OS的POS数据接入的重要组成部分，实现餐厅客流管理和等位服务的数字化。

## 核心功能

### 1. 排队管理

- **加入排队**: 客户到店后登记排队
- **自动叫号**: 系统自动叫下一位客户
- **入座确认**: 确认客户已入座并分配桌号
- **取消排队**: 客户主动取消或超时未到

### 2. 智能预估

- **等待时间预估**: 基于当前排队人数和历史数据
- **动态调整**: 根据实际入座速度实时调整
- **人数影响**: 大桌等待时间相应延长

### 3. 实时通知

- **叫号通知**: 通过企微/短信通知客户
- **状态更新**: 实时更新排队状态
- **异常提醒**: 超时未到场自动提醒

### 4. 数据统计

- **当前等待人数**: 实时显示
- **今日排队总数**: 统计分析
- **平均等待时间**: 服务质量指标

## 数据模型

### Queue（排队记录）

```python
class Queue:
    queue_id: str  # 排队ID
    queue_number: int  # 排队号码
    store_id: str  # 门店ID

    # 客户信息
    customer_name: str  # 客户姓名
    customer_phone: str  # 客户电话
    party_size: int  # 就餐人数

    # 状态信息
    status: QueueStatus  # 排队状态

    # 时间信息
    created_at: datetime  # 创建时间
    called_at: datetime  # 叫号时间
    seated_at: datetime  # 入座时间
    cancelled_at: datetime  # 取消时间

    # 预估信息
    estimated_wait_time: int  # 预估等待时间（分钟）
    actual_wait_time: int  # 实际等待时间（分钟）

    # 桌台信息
    table_number: str  # 分配的桌号
    table_type: str  # 桌台类型

    # 备注信息
    special_requests: str  # 特殊要求
    notes: str  # 备注
```

### QueueStatus（排队状态）

- `waiting`: 等待中
- `called`: 已叫号
- `seated`: 已入座
- `cancelled`: 已取消
- `no_show`: 未到场

## API端点

### 1. 添加到排队队列

```http
POST /api/v1/queue/add
```

**请求体**:
```json
{
  "customer_name": "张三",
  "customer_phone": "13800138000",
  "party_size": 4,
  "special_requests": "需要儿童座椅",
  "store_id": "store_123"
}
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "queue_id": "uuid",
    "queue_number": 15,
    "estimated_wait_time": 30,
    "status": "waiting"
  },
  "message": "已加入排队，您的号码是 15"
}
```

### 2. 叫号（叫下一位）

```http
POST /api/v1/queue/call-next
```

**请求体**:
```json
{
  "store_id": "store_123",
  "table_number": "A01"
}
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "queue_id": "uuid",
    "queue_number": 15,
    "customer_name": "张三",
    "customer_phone": "13800138000",
    "party_size": 4,
    "table_number": "A01",
    "status": "called"
  },
  "message": "已叫号 15"
}
```

### 3. 标记为已入座

```http
PUT /api/v1/queue/{queue_id}/seated
```

**请求体**:
```json
{
  "table_number": "A01"
}
```

### 4. 取消排队

```http
DELETE /api/v1/queue/{queue_id}
```

**请求体**:
```json
{
  "reason": "客户主动取消"
}
```

### 5. 获取排队列表

```http
GET /api/v1/queue/list?store_id=store_123&status=waiting&limit=50
```

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "queue_id": "uuid",
      "queue_number": 15,
      "customer_name": "张三",
      "party_size": 4,
      "status": "waiting",
      "estimated_wait_time": 30,
      "created_at": "2026-02-20T12:00:00"
    }
  ],
  "total": 10
}
```

### 6. 获取排队统计

```http
GET /api/v1/queue/stats?store_id=store_123
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "waiting_count": 10,
    "today_total": 45,
    "avg_wait_time": 25.5,
    "store_id": "store_123"
  }
}
```

### 7. POS集成 - 获取当前排队情况

```http
GET /api/v1/pos/queue/current?store_id=store_123
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "queues": [...],
    "stats": {
      "waiting_count": 10,
      "today_total": 45,
      "avg_wait_time": 25.5
    }
  }
}
```

## 业务流程

### 标准流程

1. **客户到店**
   - 前台登记客户信息
   - 系统生成排队号码
   - 预估等待时间

2. **等待期间**
   - 客户可查看当前排队进度
   - 系统实时更新预估时间
   - 可选择取消排队

3. **叫号通知**
   - 系统自动叫下一位
   - 通过企微/短信通知客户
   - 分配桌号

4. **入座确认**
   - 前台确认客户已入座
   - 记录实际等待时间
   - 更新桌台状态

### 异常处理

1. **客户未到场**
   - 叫号后5分钟未响应
   - 标记为no_show
   - 自动叫下一位

2. **客户取消**
   - 客户主动取消排队
   - 记录取消原因
   - 更新统计数据

3. **系统故障**
   - 自动降级到手工登记
   - 保留排队数据
   - 恢复后自动同步

## 集成方式

### 1. Neural System集成

排队事件自动触发Neural System：

```python
# 事件类型
- queue.added: 客户加入排队
- queue.called: 叫号
- queue.seated: 客户入座
- queue.cancelled: 取消排队
```

### 2. 企微推送集成

自动触发企微通知：

```python
# 叫号通知
await wechat_trigger_service.trigger_push(
    event_type="queue.called",
    event_data={
        "queue_number": 15,
        "customer_name": "张三",
        "table_number": "A01",
    },
    store_id=store_id,
)
```

### 3. POS系统集成

POS前台可直接查看和管理排队：

```python
# 获取当前排队情况
GET /api/v1/pos/queue/current
```

## 使用场景

### 1. 高峰期管理

```python
# 查看当前等待人数
stats = await queue_service.get_queue_stats(store_id)
if stats["waiting_count"] > 20:
    # 触发高峰期预警
    await send_alert("排队人数过多，请增加服务人员")
```

### 2. 客户体验优化

```python
# 预估等待时间
estimated_time = await queue_service._estimate_wait_time(
    session, store_id, party_size
)

# 如果等待时间过长，提供优惠券
if estimated_time > 60:
    await send_coupon(customer_phone, "等待优惠券")
```

### 3. 数据分析

```python
# 分析高峰时段
peak_hours = analyze_queue_data(store_id, date_range)

# 优化排班
optimize_staff_schedule(peak_hours)
```

## 性能优化

### 1. 数据库索引

确保以下字段有索引：
- `store_id`
- `status`
- `customer_phone`
- `created_at`

### 2. 缓存策略

高频查询使用Redis缓存：

```python
# 缓存当前排队列表
cache_key = f"queue:list:{store_id}"
await redis.setex(cache_key, 30, json.dumps(queues))
```

### 3. 实时更新

使用WebSocket推送实时更新：

```python
# 排队状态变更时推送
await websocket.send_json({
    "type": "queue_update",
    "data": queue.to_dict(),
})
```

## 监控和告警

### 关键指标

1. **等待人数**: 实时监控
2. **平均等待时间**: 服务质量指标
3. **取消率**: 客户满意度指标
4. **叫号响应时间**: 运营效率指标

### 告警规则

```python
# 等待人数过多
if waiting_count > 30:
    alert("排队人数超过30人")

# 平均等待时间过长
if avg_wait_time > 60:
    alert("平均等待时间超过1小时")

# 取消率过高
if cancel_rate > 0.2:
    alert("排队取消率超过20%")
```

## 扩展功能

### 1. 线上排队

支持客户通过小程序提前排队：

```python
# 线上排队
POST /api/v1/queue/online-add
```

### 2. 智能推荐

根据历史数据推荐最佳到店时间：

```python
# 推荐到店时间
recommended_time = predict_best_arrival_time(store_id, party_size)
```

### 3. VIP优先

会员等级高的客户优先叫号：

```python
# VIP优先队列
if customer.level == "VIP":
    queue.priority = 10
```

## 相关文档

- [POS系统集成](./pos-integration.md)
- [Neural System事件](../NEURAL_SYSTEM_IMPLEMENTATION.md)
- [企微推送触发](./wechat-push-triggers.md)
- [实时通知系统](./realtime-notifications.md)
