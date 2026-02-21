# 企业微信推送触发机制

## 概述

企业微信推送触发机制是智链OS的自动化通知系统，基于Neural System事件自动触发企业微信消息推送，实现实时业务通知和告警。

## 核心特性

### 1. 事件驱动

基于Neural System的事件总线，自动捕获业务事件并触发推送：

- **订单事件**: 新订单、订单完成、订单取消
- **预订事件**: 预订确认、预订取消、客人到店
- **会员事件**: 积分变动、会员升级
- **支付事件**: 支付完成、支付失败
- **库存事件**: 库存不足、库存耗尽
- **异常事件**: 系统错误、服务质量问题

### 2. 智能路由

根据事件类型和业务规则，自动推送给相关人员：

- **后厨人员**: 新订单通知
- **店长**: 订单取消、异常告警
- **前台**: 预订确认、客人到店
- **服务员**: 客人到店通知
- **收银员**: 支付完成/失败
- **库存管理员**: 库存预警
- **技术支持**: 系统异常告警

### 3. 优先级管理

支持4个优先级级别：

- **urgent**: 紧急（系统异常、库存耗尽）
- **high**: 高（订单取消、预订取消、库存不足）
- **normal**: 普通（订单完成、预订确认）
- **low**: 低（积分变动）

### 4. 异步处理

通过Celery任务队列异步处理推送，不阻塞主业务流程：

```python
# 事件触发后自动异步推送
await wechat_trigger_service.trigger_push(
    event_type="order.created",
    event_data=order_data,
    store_id=store_id,
)
```

## 触发规则配置

### 预定义规则

系统预置了13种常见业务场景的触发规则：

#### 订单相关

```python
"order.created": {
    "enabled": True,
    "template": "新订单提醒",
    "priority": "high",
    "target": "kitchen_staff",
    "message_template": "【新订单】\n订单号：{order_number}\n桌号：{table_number}\n金额：¥{total}\n时间：{order_time}",
}
```

#### 预订相关

```python
"reservation.confirmed": {
    "enabled": True,
    "template": "预订确认通知",
    "priority": "normal",
    "target": "front_desk",
    "message_template": "【预订确认】\n客户：{customer_name}\n电话：{customer_phone}\n人数：{party_size}人\n时间：{reservation_date}",
}
```

#### 库存相关

```python
"inventory.low_stock": {
    "enabled": True,
    "template": "库存不足预警",
    "priority": "high",
    "target": "inventory_manager",
    "message_template": "【库存预警】\n商品：{item_name}\n当前库存：{current_stock}\n预警阈值：{threshold}\n请及时补货！",
}
```

### 自定义规则

可以通过API动态添加或修改触发规则（开发中）。

## API端点

### 1. 获取所有触发规则

```http
GET /api/v1/wechat/triggers/rules
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "rules": {
      "order.created": {
        "enabled": true,
        "template": "新订单提醒",
        "priority": "high",
        "target": "kitchen_staff"
      },
      ...
    },
    "total": 13
  }
}
```

### 2. 获取指定事件的触发规则

```http
GET /api/v1/wechat/triggers/rules/{event_type}
```

**示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/wechat/triggers/rules/order.created" \
  -H "Authorization: Bearer <token>"
```

### 3. 启用/禁用触发规则

```http
PUT /api/v1/wechat/triggers/rules/{event_type}/toggle
```

**请求体**:
```json
{
  "enabled": false
}
```

**示例**:
```bash
curl -X PUT "http://localhost:8000/api/v1/wechat/triggers/rules/order.created/toggle" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### 4. 测试触发规则

```http
POST /api/v1/wechat/triggers/test
```

**请求体**:
```json
{
  "event_type": "order.created",
  "event_data": {
    "order_number": "ORD20260220001",
    "table_number": "A01",
    "total": 280.00,
    "order_time": "2026-02-20T12:30:00"
  },
  "store_id": "store_123"
}
```

### 5. 手动发送消息

```http
POST /api/v1/wechat/triggers/manual-send
```

**请求体**:
```json
{
  "content": "测试消息",
  "touser": "UserID1|UserID2",
  "toparty": "",
  "totag": ""
}
```

### 6. 获取触发统计

```http
GET /api/v1/wechat/triggers/stats
```

**状态**: 开发中

## 集成方式

### 1. Neural System自动触发

Neural System的所有事件会自动触发企微推送（如果配置了规则）：

```python
# 在celery_tasks.py中自动集成
async def process_neural_event(...):
    # 1. 向量化存储
    await vector_db_service.index_event(event)

    # 2. 触发企微推送
    await wechat_trigger_service.trigger_push(
        event_type=event_type,
        event_data=data,
        store_id=store_id,
    )

    # 3. 其他处理...
```

### 2. 手动触发

在业务代码中手动触发推送：

```python
from src.services.wechat_trigger_service import wechat_trigger_service

# 订单创建后触发推送
await wechat_trigger_service.trigger_push(
    event_type="order.created",
    event_data={
        "order_number": order.order_number,
        "table_number": order.table_number,
        "total": order.total,
        "order_time": order.order_time.isoformat(),
    },
    store_id=order.store_id,
)
```

### 3. Celery异步任务

使用Celery任务异步发送推送：

```python
from src.services.wechat_trigger_service import send_wechat_push_task

# 异步发送
task = send_wechat_push_task.delay(
    event_type="order.created",
    event_data=order_data,
    store_id=store_id,
)
```

## 消息模板

### 模板变量

消息模板支持使用事件数据中的字段作为变量：

```python
message_template = "【新订单】\n订单号：{order_number}\n金额：¥{total}"
```

### 模板示例

#### 订单通知
```
【新订单】
订单号：ORD20260220001
桌号：A01
金额：¥280.00
时间：2026-02-20 12:30:00
```

#### 预订通知
```
【预订确认】
客户：张三
电话：138****8000
人数：4人
时间：2026-02-21 18:00:00
```

#### 库存预警
```
【库存预警】
商品：宫保鸡丁
当前库存：5份
预警阈值：10份
请及时补货！
```

## 用户角色映射

### 角色定义

系统预定义了8种用户角色：

| 角色 | 企微用户组 | 接收通知类型 |
|------|-----------|-------------|
| kitchen_staff | 后厨人员 | 新订单 |
| manager | 店长 | 订单取消、异常告警 |
| front_desk | 前台 | 预订确认、客人到店 |
| service_staff | 服务员 | 客人到店 |
| member_manager | 会员管理员 | 积分变动、会员升级 |
| cashier | 收银员 | 支付完成/失败 |
| inventory_manager | 库存管理员 | 库存预警 |
| tech_support | 技术支持 | 系统异常 |

### 配置用户映射

在企业微信后台配置用户组，然后在代码中映射：

```python
role_user_mapping = {
    "kitchen_staff": "KitchenStaff",  # 企微用户组ID
    "manager": "Manager",
    ...
}
```

## 配置要求

### 环境变量

在 `.env` 文件中配置企业微信参数：

```bash
# 企业微信配置
WECHAT_CORP_ID=your_corp_id
WECHAT_CORP_SECRET=your_corp_secret
WECHAT_AGENT_ID=your_agent_id
```

### 企业微信应用配置

1. 登录企业微信管理后台
2. 创建自建应用
3. 获取 CorpID、Secret、AgentID
4. 配置可见范围（用户/部门）
5. 配置接收消息服务器（可选）

## 监控和日志

### 日志记录

所有推送操作都会记录详细日志：

```json
{
  "event": "企微推送触发成功",
  "event_type": "order.created",
  "target": "kitchen_staff",
  "result": {
    "errcode": 0,
    "errmsg": "ok"
  }
}
```

### 失败处理

推送失败时的处理策略：

1. **自动重试**: Celery任务自动重试3次
2. **降级处理**: 推送失败不影响主业务流程
3. **日志记录**: 记录失败原因和详情
4. **告警通知**: 连续失败时发送告警

## 性能优化

### 1. 异步处理

所有推送操作都通过Celery异步执行，不阻塞主流程：

```python
# 异步推送，立即返回
await wechat_trigger_service.trigger_push(...)
```

### 2. 批量推送

对于需要推送给多个用户的场景，使用批量推送：

```python
# 推送给多个用户
touser = "User1|User2|User3"
```

### 3. 消息合并

对于高频事件，可以配置消息合并策略（开发中）：

- 相同类型的消息在1分钟内只推送一次
- 合并多个相似事件为一条消息

## 故障排查

### 问题1: 推送未触发

**可能原因**:
- 触发规则未启用
- 事件类型不匹配
- 企微配置错误

**解决方案**:
1. 检查触发规则状态: `GET /api/v1/wechat/triggers/rules/{event_type}`
2. 验证事件类型是否正确
3. 测试企微连接: `POST /api/v1/wechat/triggers/test`

### 问题2: 推送失败

**可能原因**:
- access_token过期
- 用户不在可见范围
- 网络连接问题

**解决方案**:
1. 检查企微配置是否正确
2. 验证用户ID是否存在
3. 查看错误日志获取详细信息

### 问题3: 消息延迟

**可能原因**:
- Celery worker负载过高
- Redis队列堆积
- 企微API响应慢

**解决方案**:
1. 增加Celery worker数量
2. 检查Redis队列状态
3. 优化推送频率

## 扩展功能

### 1. 消息模板管理

支持通过API动态管理消息模板（开发中）：

```python
# 更新消息模板
PUT /api/v1/wechat/triggers/rules/{event_type}/template
```

### 2. 推送统计分析

记录和分析推送数据（开发中）：

- 推送成功率
- 推送响应时间
- 用户阅读率
- 按事件类型统计

### 3. 智能推送

基于用户行为和偏好优化推送（规划中）：

- 免打扰时段
- 推送频率限制
- 个性化推送内容

## 相关文档

- [企业微信API文档](https://developer.work.weixin.qq.com/document/)
- [Neural System实现指南](../NEURAL_SYSTEM_IMPLEMENTATION.md)
- [Celery任务队列集成](./celery-integration.md)
- [事件驱动架构](./event-driven-architecture.md)
