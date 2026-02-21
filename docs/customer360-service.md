# Customer360 客户画像服务

## 概述

Customer360是智链OS的统一客户视图服务，聚合所有客户触点数据，生成完整的客户画像和时间线。

## 功能特性

### 1. 多源数据聚合

Customer360从以下数据源聚合客户信息：

- **订单系统** (Order): 堂食、外卖、自提订单
- **预订系统** (Reservation): 本地预订 + 易订等外部系统同步
- **POS系统** (POSTransaction): 品智POS交易记录
- **会员系统** (MemberSync): 奥琦韦会员数据同步
- **审计日志** (AuditLog): 用户活动追踪

### 2. 客户时间线

按时间倒序展示客户的所有活动事件：
- 订单事件（下单、支付、完成）
- 预订事件（预订、确认、到店、取消）
- POS交易事件
- 会员活动事件

### 3. 客户价值评估

基于RFM模型计算客户价值：

- **R (Recency)**: 最近消费时间
- **F (Frequency)**: 消费频率
- **M (Monetary)**: 消费金额

输出指标：
- 总消费金额
- 订单数量
- 平均订单金额
- 客户生命周期（天数）
- 消费频率（每月订单数）
- RFM评分（0-100）
- 客户等级（VIP、高价值、中价值、低价值、流失风险）

### 4. 智能标签

自动生成客户标签：
- 会员标签（会员、会员等级）
- 价值标签（VIP、高价值、中价值等）
- 消费习惯（高频消费、高客单价）
- 预订习惯（预订常客）
- 活跃度（活跃用户、沉睡用户、流失用户）

## API端点

### 1. 获取客户360画像

```http
GET /api/v1/customer360/profile
```

**参数**:
- `customer_identifier` (required): 客户标识（手机号、会员ID等）
- `identifier_type` (optional): 标识类型，默认`phone`
  - `phone`: 手机号
  - `member_id`: 会员ID
  - `email`: 邮箱
- `store_id` (optional): 门店ID（多租户隔离）

**响应示例**:
```json
{
  "success": true,
  "data": {
    "customer_identifier": "13800138000",
    "identifier_type": "phone",
    "member_info": {
      "member_id": "M123456",
      "name": "张三",
      "phone": "13800138000",
      "level": "金卡",
      "points": 1500,
      "balance": 200.00
    },
    "customer_value": {
      "total_spent": 5280.00,
      "total_orders": 24,
      "avg_order_value": 220.00,
      "customer_lifetime_days": 180,
      "order_frequency_per_month": 4.0,
      "rfm_score": 75.5,
      "customer_tier": "高价值"
    },
    "customer_tags": [
      "会员",
      "会员等级:金卡",
      "高价值",
      "高频消费",
      "活跃用户"
    ],
    "statistics": {
      "total_orders": 24,
      "total_reservations": 8,
      "total_pos_transactions": 15,
      "total_activities": 50
    },
    "timeline": [
      {
        "event_type": "order",
        "event_time": "2026-02-18T19:30:00",
        "title": "订单 ORD20260218001",
        "description": "堂食 - ¥280.00",
        "status": "completed"
      },
      {
        "event_type": "reservation",
        "event_time": "2026-02-15T18:00:00",
        "title": "预订 - 4人",
        "description": "状态: completed",
        "status": "completed"
      }
    ],
    "recent_orders": [...],
    "recent_reservations": [...],
    "generated_at": "2026-02-20T17:00:00"
  }
}
```

### 2. 获取客户时间线

```http
GET /api/v1/customer360/timeline
```

**参数**:
- `customer_identifier` (required): 客户标识
- `identifier_type` (optional): 标识类型
- `store_id` (optional): 门店ID
- `limit` (optional): 返回事件数量，默认50，最大200

**响应示例**:
```json
{
  "success": true,
  "data": {
    "customer_identifier": "13800138000",
    "timeline": [
      {
        "event_type": "order",
        "event_time": "2026-02-18T19:30:00",
        "title": "订单 ORD20260218001",
        "description": "堂食 - ¥280.00",
        "status": "completed",
        "data": {
          "order_id": "...",
          "order_number": "ORD20260218001",
          "total": 280.00
        }
      }
    ],
    "total_events": 47
  }
}
```

### 3. 获取客户价值指标

```http
GET /api/v1/customer360/value
```

**参数**:
- `customer_identifier` (required): 客户标识
- `identifier_type` (optional): 标识类型
- `store_id` (optional): 门店ID

**响应示例**:
```json
{
  "success": true,
  "data": {
    "customer_identifier": "13800138000",
    "customer_value": {
      "total_spent": 5280.00,
      "total_orders": 24,
      "avg_order_value": 220.00,
      "rfm_score": 75.5,
      "customer_tier": "高价值"
    },
    "customer_tags": ["会员", "高价值", "高频消费"],
    "statistics": {
      "total_orders": 24,
      "total_reservations": 8
    }
  }
}
```

### 4. 搜索客户

```http
GET /api/v1/customer360/search
```

**参数**:
- `query` (required): 搜索关键词（姓名、手机号）
- `store_id` (optional): 门店ID
- `limit` (optional): 返回数量，默认20

**状态**: 开发中

## 使用场景

### 1. 客服场景

客服人员接到客户电话时，快速查看客户完整画像：

```bash
curl -X GET "http://localhost:8000/api/v1/customer360/profile?customer_identifier=13800138000" \
  -H "Authorization: Bearer <token>"
```

### 2. 营销场景

根据客户价值和标签进行精准营销：

```python
# 获取高价值客户
profile = await customer360_service.get_customer_profile("13800138000")

if profile["customer_value"]["customer_tier"] == "VIP":
    # 发送VIP专属优惠
    await send_vip_promotion(profile)
```

### 3. 运营分析

分析客户生命周期和流失风险：

```python
# 识别流失风险客户
if "流失风险" in profile["customer_tags"]:
    # 触发挽回策略
    await trigger_retention_campaign(profile)
```

### 4. 个性化服务

根据客户历史偏好提供个性化推荐：

```python
# 分析客户订单历史
recent_orders = profile["recent_orders"]
favorite_dishes = analyze_favorite_dishes(recent_orders)

# 推荐相似菜品
recommendations = recommend_similar_dishes(favorite_dishes)
```

## 数据隐私

Customer360服务遵循数据隐私保护原则：

1. **多租户隔离**: 非超级管理员只能查看本店客户数据
2. **访问控制**: 需要认证和授权才能访问
3. **敏感信息脱敏**: 手机号、邮箱等敏感信息可配置脱敏
4. **审计日志**: 所有查询操作记录审计日志

## 性能优化

### 1. 数据库索引

确保以下字段有索引：
- `Order.customer_phone`
- `Order.member_id`
- `Reservation.customer_phone`
- `MemberSync.phone`
- `MemberSync.member_id`

### 2. 缓存策略

对于高频查询的客户画像，可以使用Redis缓存：

```python
# 缓存客户画像30分钟
cache_key = f"customer360:{customer_identifier}"
cached_profile = await redis.get(cache_key)

if cached_profile:
    return json.loads(cached_profile)

profile = await customer360_service.get_customer_profile(...)
await redis.setex(cache_key, 1800, json.dumps(profile))
```

### 3. 异步加载

对于大数据量客户，可以异步加载部分数据：

```python
# 先返回基础信息
basic_profile = await get_basic_profile(customer_identifier)

# 异步加载详细时间线
asyncio.create_task(load_detailed_timeline(customer_identifier))
```

## 扩展功能

### 1. 客户分群

基于RFM模型和标签进行客户分群：

```python
# 高价值活跃客户
high_value_active = filter_customers(
    rfm_score__gte=70,
    tags__contains=["活跃用户"]
)

# 流失风险客户
churn_risk = filter_customers(
    tags__contains=["流失风险"]
)
```

### 2. 预测模型

基于历史数据预测客户行为：

```python
# 预测客户流失概率
churn_probability = predict_churn(profile)

# 预测客户生命周期价值
ltv = predict_lifetime_value(profile)
```

### 3. 推荐引擎

基于客户画像进行个性化推荐：

```python
# 菜品推荐
dish_recommendations = recommend_dishes(profile)

# 优惠券推荐
coupon_recommendations = recommend_coupons(profile)
```

## 故障排查

### 问题1: 客户画像数据不完整

**可能原因**:
- 数据源未正确同步
- 客户标识不匹配

**解决方案**:
1. 检查数据同步状态
2. 验证客户标识映射
3. 查看日志中的错误信息

### 问题2: 查询性能慢

**可能原因**:
- 缺少数据库索引
- 数据量过大
- 未使用缓存

**解决方案**:
1. 添加必要的数据库索引
2. 限制查询时间范围
3. 启用Redis缓存
4. 使用分页加载

### 问题3: RFM评分不准确

**可能原因**:
- 算法参数需要调整
- 数据质量问题

**解决方案**:
1. 根据业务特点调整RFM权重
2. 清洗异常数据
3. 定期校准评分模型

## 相关文档

- [Neural System实现指南](../NEURAL_SYSTEM_IMPLEMENTATION.md)
- [会员系统集成](./member-system-integration.md)
- [数据隐私保护](./data-privacy.md)
- [API认证授权](./api-authentication.md)
