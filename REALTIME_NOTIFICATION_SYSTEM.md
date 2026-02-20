# 智链OS实时通知系统文档

## 概述

智链OS实时通知系统提供了完整的通知解决方案,支持WebSocket实时推送、多渠道通知(邮件/短信/微信/飞书)、通知模板管理和故障转移机制。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      客户端应用层                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Web前端  │  │ 移动端   │  │ 小程序   │  │ 第三方   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
└───────┼─────────────┼─────────────┼─────────────┼──────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    WebSocket连接层         │
        │  (实时双向通信)             │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    通知服务层               │
        │  ┌──────────────────────┐ │
        │  │ 通知创建与管理        │ │
        │  │ 实时推送逻辑          │ │
        │  │ 通知查询与过滤        │ │
        │  └──────────────────────┘ │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    多渠道通知层             │
        │  ┌────┐ ┌────┐ ┌────┐    │
        │  │邮件│ │短信│ │微信│    │
        │  └────┘ └────┘ └────┘    │
        │  ┌────┐ ┌────┐ ┌────┐    │
        │  │飞书│ │推送│ │系统│    │
        │  └────┘ └────┘ └────┘    │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    数据持久化层             │
        │  (PostgreSQL)              │
        └───────────────────────────┘
```

## 核心功能

### 1. WebSocket实时推送

#### 连接建立

客户端通过WebSocket连接到服务器:

```javascript
// 前端连接示例
const token = localStorage.getItem('access_token');
const ws = new WebSocket(`ws://localhost:8000/api/v1/ws?token=${token}`);

ws.onopen = () => {
  console.log('WebSocket连接已建立');
  // 发送心跳包
  setInterval(() => {
    ws.send('ping');
  }, 30000);
};

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log('收到通知:', notification);
  // 显示通知
  showNotification(notification);
};

ws.onerror = (error) => {
  console.error('WebSocket错误:', error);
};

ws.onclose = () => {
  console.log('WebSocket连接已关闭');
  // 重连逻辑
  setTimeout(() => connectWebSocket(), 5000);
};
```

#### 推送类型

系统支持4种推送类型:

1. **个人推送** - 发送给特定用户
2. **角色推送** - 发送给特定角色的所有用户
3. **门店推送** - 发送给特定门店的所有用户
4. **广播推送** - 发送给所有在线用户

### 2. 通知管理API

#### 创建通知

```http
POST /api/v1/notifications
Content-Type: application/json
Authorization: Bearer <token>

{
  "title": "库存预警",
  "message": "鸡肉库存不足,当前库存: 5kg,请及时补货",
  "type": "warning",
  "priority": "high",
  "user_id": "user-123",  // 可选,发给特定用户
  "role": "store_manager",  // 可选,发给特定角色
  "store_id": "store-123",  // 可选,发给特定门店
  "extra_data": {
    "item_id": "item-456",
    "current_stock": 5
  },
  "source": "inventory_system"
}
```

**响应:**
```json
{
  "id": "notif-789",
  "title": "库存预警",
  "message": "鸡肉库存不足,当前库存: 5kg,请及时补货",
  "type": "warning",
  "priority": "high",
  "user_id": "user-123",
  "role": null,
  "store_id": null,
  "is_read": false,
  "read_at": null,
  "extra_data": {
    "item_id": "item-456",
    "current_stock": 5
  },
  "source": "inventory_system",
  "created_at": "2026-02-20T10:30:00"
}
```

#### 获取通知列表

```http
GET /api/v1/notifications?is_read=false&limit=20&offset=0
Authorization: Bearer <token>
```

**响应:**
```json
[
  {
    "id": "notif-789",
    "title": "库存预警",
    "message": "鸡肉库存不足...",
    "type": "warning",
    "priority": "high",
    "is_read": false,
    "created_at": "2026-02-20T10:30:00"
  }
]
```

#### 获取未读数量

```http
GET /api/v1/notifications/unread-count
Authorization: Bearer <token>
```

**响应:**
```json
{
  "unread_count": 5
}
```

#### 标记为已读

```http
PUT /api/v1/notifications/{notification_id}/read
Authorization: Bearer <token>
```

**响应:**
```json
{
  "success": true,
  "message": "已标记为已读"
}
```

#### 标记所有为已读

```http
PUT /api/v1/notifications/read-all
Authorization: Bearer <token>
```

**响应:**
```json
{
  "success": true,
  "message": "已标记5条通知为已读",
  "count": 5
}
```

#### 删除通知

```http
DELETE /api/v1/notifications/{notification_id}
Authorization: Bearer <token>
```

**响应:**
```json
{
  "success": true,
  "message": "通知已删除"
}
```

### 3. 多渠道通知

#### 发送多渠道通知

```http
POST /api/v1/notifications/multi-channel
Content-Type: application/json
Authorization: Bearer <token>

{
  "channels": ["email", "sms", "wechat"],
  "recipient": "user@example.com",  // 或手机号/微信ID
  "title": "订单确认",
  "content": "您的订单已确认,预计30分钟送达",
  "extra_data": {
    "order_id": "order-123"
  }
}
```

**响应:**
```json
{
  "success": true,
  "message": "通知已发送",
  "results": {
    "email": true,
    "sms": true,
    "wechat": false
  }
}
```

#### 使用模板发送通知

```http
POST /api/v1/notifications/template
Content-Type: application/json
Authorization: Bearer <token>

{
  "template_name": "inventory_low",
  "recipient": "manager@example.com",
  "template_vars": {
    "item_name": "鸡肉",
    "current_stock": 5
  }
}
```

**响应:**
```json
{
  "success": true,
  "message": "模板通知已发送",
  "template": "inventory_low",
  "results": {
    "email": true,
    "system": true
  }
}
```

#### 获取可用模板

```http
GET /api/v1/notifications/templates
Authorization: Bearer <token>
```

**响应:**
```json
{
  "templates": {
    "order_confirmed": {
      "title": "订单确认",
      "content": "您的订单 {order_id} 已确认，预计 {estimated_time} 送达。",
      "channels": ["sms", "app_push"],
      "priority": "normal"
    },
    "inventory_low": {
      "title": "库存预警",
      "content": "商品 {item_name} 库存不足，当前库存: {current_stock}，请及时补货。",
      "channels": ["email", "system"],
      "priority": "high"
    }
  },
  "count": 8
}
```

### 4. 通知类型

系统支持以下通知类型:

- `info` - 信息通知(蓝色)
- `success` - 成功通知(绿色)
- `warning` - 警告通知(橙色)
- `error` - 错误通知(红色)
- `alert` - 告警通知(红色闪烁)

### 5. 通知优先级

- `low` - 低优先级(可延迟处理)
- `normal` - 普通优先级(正常处理)
- `high` - 高优先级(优先处理)
- `urgent` - 紧急优先级(立即处理)

## 通知模板

系统预定义了8个常用通知模板:

| 模板名称 | 标题 | 使用场景 | 渠道 |
|---------|------|---------|------|
| order_confirmed | 订单确认 | 订单确认后 | SMS, APP |
| order_ready | 订单已完成 | 订单完成后 | SMS, APP |
| inventory_low | 库存预警 | 库存低于安全线 | Email, System |
| staff_schedule | 排班通知 | 排班更新后 | SMS, APP |
| payment_success | 支付成功 | 支付完成后 | SMS, WeChat |
| backup_completed | 数据备份完成 | 备份成功后 | Email, System |
| backup_failed | 数据备份失败 | 备份失败后 | Email, System |
| system_alert | 系统告警 | 系统异常时 | Email, SMS, System |

## 集成指南

### 企业微信集成

```python
# 配置企业微信
WECHAT_CORP_ID = "your_corp_id"
WECHAT_CORP_SECRET = "your_corp_secret"
WECHAT_AGENT_ID = "your_agent_id"

# 发送企业微信通知
from src.services.wechat_service import wechat_service

await wechat_service.send_message(
    user_id="zhangsan",
    message="库存预警: 鸡肉库存不足"
)
```

### 飞书集成

```python
# 配置飞书
FEISHU_APP_ID = "your_app_id"
FEISHU_APP_SECRET = "your_app_secret"

# 发送飞书通知
from src.services.feishu_service import feishu_service

await feishu_service.send_message(
    user_id="ou_xxx",
    message="订单已确认"
)
```

### 短信集成

```python
# 配置阿里云短信
ALIYUN_ACCESS_KEY = "your_access_key"
ALIYUN_ACCESS_SECRET = "your_access_secret"
ALIYUN_SMS_SIGN = "智链OS"

# 发送短信
from src.services.sms_service import sms_service

await sms_service.send_sms(
    phone="13800138000",
    template_code="SMS_123456",
    template_params={"code": "1234"}
)
```

### 邮件集成

```python
# 配置SMTP
SMTP_HOST = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "noreply@example.com"
SMTP_PASSWORD = "your_password"

# 发送邮件
from src.services.email_service import email_service

await email_service.send_email(
    to="user@example.com",
    subject="库存预警",
    body="鸡肉库存不足,请及时补货"
)
```

## 故障转移机制

系统实现了多层故障转移:

### 1. WebSocket故障转移

```
WebSocket推送失败
    ↓
尝试重连(3次)
    ↓
降级到轮询模式
    ↓
客户端定期查询未读通知
```

### 2. 多渠道故障转移

```
主渠道发送失败
    ↓
尝试备用渠道
    ↓
记录失败日志
    ↓
触发告警通知管理员
```

### 3. 数据库故障转移

```
主数据库不可用
    ↓
切换到从数据库(只读)
    ↓
通知缓存到Redis
    ↓
主数据库恢复后同步
```

## 性能优化

### 1. 连接池管理

- WebSocket连接池: 最大10000个并发连接
- 数据库连接池: 最大50个连接
- Redis连接池: 最大100个连接

### 2. 消息队列

使用Redis作为消息队列,实现异步通知发送:

```python
# 异步发送通知
await notification_queue.enqueue({
    "type": "notification",
    "data": notification_data
})
```

### 3. 批量操作

支持批量创建和批量标记已读:

```python
# 批量创建通知
await notification_service.create_bulk_notifications([
    {"title": "通知1", "message": "..."},
    {"title": "通知2", "message": "..."},
])

# 批量标记已读
await notification_service.mark_bulk_as_read([
    "notif-1", "notif-2", "notif-3"
])
```

### 4. 缓存策略

- 未读数量缓存: 5分钟
- 通知列表缓存: 1分钟
- 模板缓存: 永久(直到更新)

## 监控指标

### 关键指标

- `notification_created_total` - 创建的通知总数
- `notification_sent_total` - 发送的通知总数
- `notification_failed_total` - 发送失败的通知总数
- `websocket_connections_active` - 活跃WebSocket连接数
- `notification_delivery_duration_seconds` - 通知送达时间

### Prometheus查询示例

```promql
# 每分钟创建的通知数
rate(notification_created_total[1m])

# WebSocket连接数
websocket_connections_active

# 通知发送成功率
rate(notification_sent_total[5m]) / rate(notification_created_total[5m])

# P95通知送达时间
histogram_quantile(0.95, notification_delivery_duration_seconds_bucket)
```

## 故障排查

### 常见问题

#### 1. WebSocket连接失败

**症状:** 客户端无法建立WebSocket连接

**排查步骤:**
1. 检查token是否有效: `curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/health`
2. 检查WebSocket端点: `wscat -c "ws://localhost:8000/api/v1/ws?token=<token>"`
3. 检查防火墙规则
4. 检查Nginx配置(如果使用反向代理)

**解决方案:**
```nginx
# Nginx WebSocket配置
location /api/v1/ws {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}
```

#### 2. 通知未送达

**症状:** 创建了通知但用户未收到

**排查步骤:**
1. 检查通知是否创建成功: `GET /api/v1/notifications`
2. 检查WebSocket连接状态: `GET /api/v1/notifications/stats`
3. 检查用户是否在线
4. 检查通知过滤条件(user_id/role/store_id)

**解决方案:**
- 确保用户已建立WebSocket连接
- 检查通知的目标用户/角色/门店是否正确
- 查看服务器日志: `tail -f logs/notification.log`

#### 3. 多渠道通知失败

**症状:** 邮件/短信/微信通知发送失败

**排查步骤:**
1. 检查渠道配置: 环境变量是否正确
2. 检查网络连接: 能否访问第三方API
3. 检查API凭证: 是否过期或无效
4. 查看错误日志

**解决方案:**
```bash
# 测试邮件服务
python3 -c "from src.services.email_service import email_service; import asyncio; asyncio.run(email_service.test_connection())"

# 测试短信服务
python3 -c "from src.services.sms_service import sms_service; import asyncio; asyncio.run(sms_service.test_connection())"
```

## 安全性

### 1. 认证授权

- 所有API接口都需要JWT认证
- WebSocket连接需要有效token
- 用户只能查看/操作自己的通知

### 2. 数据加密

- WebSocket使用WSS(TLS加密)
- 敏感数据加密存储
- API通信使用HTTPS

### 3. 防护措施

- 限流: 每用户每分钟最多100个请求
- 防止XSS: 通知内容自动转义
- 防止注入: 使用参数化查询

## 最佳实践

### 1. 通知设计

- 标题简洁明了(< 50字符)
- 内容清晰具体(< 200字符)
- 包含可操作的信息
- 使用合适的类型和优先级

### 2. 性能优化

- 避免频繁创建通知
- 使用批量操作
- 合理设置缓存时间
- 定期清理过期通知

### 3. 用户体验

- 提供通知偏好设置
- 支持免打扰模式
- 通知分组和折叠
- 提供通知历史记录

## 更新日志

### v1.0.0 (2026-02-20)
- ✅ 实现WebSocket实时推送
- ✅ 实现多渠道通知(邮件/短信/微信/飞书)
- ✅ 实现通知模板管理
- ✅ 实现故障转移机制
- ✅ 添加Prometheus监控
- ✅ 完成API文档
- ✅ 创建测试套件(25个测试)

## 技术支持

如有问题,请联系:
- 技术支持邮箱: support@zhilian-os.com
- GitHub Issues: https://github.com/zhilian-os/issues
- 文档网站: https://docs.zhilian-os.com
