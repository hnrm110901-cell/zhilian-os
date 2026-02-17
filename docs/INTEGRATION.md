# 外部系统集成 (External System Integration)

## 概述

智链OS外部系统集成模块支持与POS系统、供应商系统、会员系统等第三方系统的数据对接和同步。

## 功能特性

### 1. 支持的集成类型

- **POS系统** (`pos`): 收银系统集成,实时同步交易数据
- **供应商系统** (`supplier`): 供应链管理,订单和配送跟踪
- **会员系统** (`member`): 会员数据同步,积分和等级管理
- **支付系统** (`payment`): 支付网关集成
- **配送系统** (`delivery`): 外卖配送平台对接
- **ERP系统** (`erp`): 企业资源计划系统集成

### 2. 核心功能

- ✅ 外部系统配置管理
- ✅ 连接测试和状态监控
- ✅ POS交易数据接收和存储
- ✅ 供应商订单管理
- ✅ 会员数据双向同步
- ✅ Webhook接收端点
- ✅ 同步日志和错误追踪
- ✅ 基于角色的权限控制

## 数据模型

### ExternalSystem (外部系统配置)

```python
{
    "id": "uuid",
    "name": "系统名称",
    "type": "pos|supplier|member|payment|delivery|erp",
    "provider": "提供商名称",
    "version": "版本号",
    "status": "active|inactive|error|testing",
    "store_id": "关联门店ID",
    "api_endpoint": "API端点URL",
    "api_key": "API密钥",
    "webhook_url": "Webhook URL",
    "config": {},  // 其他配置
    "sync_enabled": true,
    "sync_interval": 300,  // 同步间隔(秒)
    "last_sync_at": "最后同步时间",
    "last_sync_status": "success|failed|partial"
}
```

### POSTransaction (POS交易记录)

```python
{
    "id": "uuid",
    "system_id": "外部系统ID",
    "store_id": "门店ID",
    "pos_transaction_id": "POS交易ID",
    "pos_order_number": "POS订单号",
    "transaction_type": "sale|refund|void",
    "subtotal": 288.00,
    "tax": 28.80,
    "discount": 20.00,
    "total": 296.80,
    "payment_method": "wechat_pay|alipay|cash|card",
    "items": [],  // 订单项目
    "customer_info": {},  // 客户信息
    "sync_status": "pending|success|failed",
    "transaction_time": "交易时间"
}
```

### SupplierOrder (供应商订单)

```python
{
    "id": "uuid",
    "system_id": "外部系统ID",
    "store_id": "门店ID",
    "order_number": "订单号",
    "supplier_id": "供应商ID",
    "supplier_name": "供应商名称",
    "order_type": "purchase|return",
    "status": "pending|confirmed|shipped|delivered|cancelled",
    "subtotal": 5000.00,
    "tax": 500.00,
    "shipping": 200.00,
    "total": 5700.00,
    "items": [],  // 订单项目
    "delivery_info": {},  // 配送信息
    "order_date": "订单日期",
    "expected_delivery": "预计送达时间",
    "actual_delivery": "实际送达时间"
}
```

### MemberSync (会员同步记录)

```python
{
    "id": "uuid",
    "system_id": "外部系统ID",
    "member_id": "会员ID",
    "external_member_id": "外部系统会员ID",
    "phone": "手机号",
    "name": "姓名",
    "email": "邮箱",
    "level": "会员等级",
    "points": 1500,
    "balance": 200.00,
    "sync_status": "success|failed",
    "last_activity": "最后活动时间"
}
```

## API接口

### 系统管理

#### 创建外部系统
```bash
POST /api/v1/integrations/systems
Authorization: Bearer {token}
Content-Type: application/json

{
    "name": "美团POS系统",
    "type": "pos",
    "provider": "Meituan",
    "store_id": "store-001",
    "config": {
        "api_endpoint": "https://api.meituan.com/pos",
        "api_key": "your_api_key",
        "webhook_url": "http://your-domain/api/v1/integrations/webhooks/pos"
    }
}
```

#### 获取系统列表
```bash
GET /api/v1/integrations/systems?type=pos&store_id=store-001
Authorization: Bearer {token}
```

#### 更新系统配置
```bash
PUT /api/v1/integrations/systems/{system_id}
Authorization: Bearer {token}
Content-Type: application/json

{
    "status": "active",
    "sync_enabled": true,
    "sync_interval": 600
}
```

#### 测试系统连接
```bash
POST /api/v1/integrations/systems/{system_id}/test
Authorization: Bearer {token}
```

#### 删除系统
```bash
DELETE /api/v1/integrations/systems/{system_id}
Authorization: Bearer {token}
```

### POS集成

#### 创建POS交易
```bash
POST /api/v1/integrations/pos/{system_id}/transactions
Authorization: Bearer {token}
Content-Type: application/json

{
    "transaction_id": "TXN-2024-001",
    "order_number": "ORD-2024-001",
    "type": "sale",
    "subtotal": 288.00,
    "tax": 28.80,
    "discount": 20.00,
    "total": 296.80,
    "payment_method": "wechat_pay",
    "items": [
        {
            "name": "宫保鸡丁",
            "quantity": 2,
            "price": 68.00
        }
    ],
    "customer": {
        "phone": "13800138000",
        "name": "张三"
    }
}
```

#### 获取POS交易记录
```bash
GET /api/v1/integrations/pos/transactions?store_id=store-001&sync_status=success
Authorization: Bearer {token}
```

### 供应商集成

#### 创建供应商订单
```bash
POST /api/v1/integrations/supplier/{system_id}/orders
Authorization: Bearer {token}
Content-Type: application/json

{
    "order_number": "PO-2024-001",
    "supplier_id": "SUP-001",
    "supplier_name": "蜀海供应链",
    "type": "purchase",
    "status": "pending",
    "subtotal": 5000.00,
    "tax": 500.00,
    "shipping": 200.00,
    "total": 5700.00,
    "items": [
        {
            "name": "鸡肉",
            "quantity": 50,
            "unit": "kg",
            "price": 30.00
        }
    ],
    "delivery": {
        "address": "北京市朝阳区xxx路xxx号",
        "contact": "李四",
        "phone": "13900139000"
    },
    "expected_delivery": "2024-02-15T10:00:00"
}
```

#### 获取供应商订单
```bash
GET /api/v1/integrations/supplier/orders?store_id=store-001&status=pending
Authorization: Bearer {token}
```

### 会员集成

#### 同步会员数据
```bash
POST /api/v1/integrations/member/{system_id}/sync
Authorization: Bearer {token}
Content-Type: application/json

{
    "member_id": "MEM-001",
    "external_id": "wx_openid_123",
    "phone": "13800138000",
    "name": "张三",
    "email": "zhangsan@example.com",
    "level": "gold",
    "points": 1500,
    "balance": 200.00
}
```

### Webhook端点

#### POS Webhook
```bash
POST /api/v1/integrations/webhooks/pos/{system_id}
Content-Type: application/json

{
    "event": "transaction.created",
    "data": {
        "transaction_id": "TXN-2024-002",
        "total": 150.00
    }
}
```

#### 供应商Webhook
```bash
POST /api/v1/integrations/webhooks/supplier/{system_id}
Content-Type: application/json

{
    "event": "order.status_changed",
    "data": {
        "order_number": "PO-2024-001",
        "status": "shipped"
    }
}
```

### 同步日志

#### 获取同步日志
```bash
GET /api/v1/integrations/sync-logs?system_id={system_id}&limit=50
Authorization: Bearer {token}
```

## 权限要求

| 操作 | 所需角色 |
|------|---------|
| 创建/更新/删除系统 | admin, store_manager |
| 查看系统列表 | 所有已认证用户 |
| 测试连接 | admin, store_manager |
| 创建POS交易 | 所有已认证用户 |
| 创建供应商订单 | admin, store_manager, warehouse_manager |
| 同步会员数据 | admin, store_manager, customer_manager |
| 接收Webhook | 无需认证(公开端点) |

## 数据库迁移

运行以下命令创建集成相关表:

```bash
cd apps/api-gateway
python3 migrate_integration_tables.py
```

这将创建以下表:
- `external_systems` - 外部系统配置
- `sync_logs` - 同步日志
- `pos_transactions` - POS交易记录
- `supplier_orders` - 供应商订单
- `member_syncs` - 会员同步记录

## 测试

运行集成测试脚本:

```bash
./test_integrations.sh
```

测试脚本将:
1. 创建POS、供应商、会员系统配置
2. 创建测试交易和订单
3. 同步会员数据
4. 测试Webhook接收
5. 查看同步日志

## 集成示例

### 美团POS集成

```python
# 1. 创建美团POS系统配置
system = {
    "name": "美团POS系统",
    "type": "pos",
    "provider": "Meituan",
    "config": {
        "api_endpoint": "https://api.meituan.com/pos",
        "api_key": "your_meituan_key",
        "webhook_url": "https://your-domain/api/v1/integrations/webhooks/pos/{system_id}"
    }
}

# 2. 配置美团Webhook推送到你的端点
# 3. 接收实时交易数据
```

### 蜀海供应链集成

```python
# 1. 创建供应商系统配置
system = {
    "name": "蜀海供应链",
    "type": "supplier",
    "provider": "Shuhai",
    "config": {
        "api_endpoint": "https://api.shuhai.com",
        "api_key": "your_shuhai_key"
    }
}

# 2. 创建采购订单
# 3. 跟踪配送状态
```

### 微信会员集成

```python
# 1. 创建会员系统配置
system = {
    "name": "微信会员系统",
    "type": "member",
    "provider": "WeChat",
    "config": {
        "api_endpoint": "https://api.weixin.qq.com",
        "api_key": "your_wechat_key"
    }
}

# 2. 同步会员数据
# 3. 更新积分和等级
```

## 注意事项

1. **安全性**: API密钥和密钥应加密存储,不要在日志中输出
2. **幂等性**: 所有集成操作应支持幂等性,避免重复处理
3. **错误处理**: 记录详细的错误信息到sync_logs表
4. **限流**: 对外部API调用实施限流保护
5. **监控**: 监控同步状态和失败率,及时告警
6. **数据验证**: 验证外部系统推送的数据格式和完整性

## 未来扩展

- [ ] 自动重试机制
- [ ] 数据转换规则配置
- [ ] 批量同步优化
- [ ] 实时同步状态推送
- [ ] 集成健康度评分
- [ ] 数据冲突解决策略