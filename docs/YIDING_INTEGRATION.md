# 易订预订系统集成文档

## 概述

易订(Yiding)是餐饮行业专业的预订管理系统。本文档说明如何将易订系统与智链OS集成,实现预订数据的实时同步和管理。

## 集成架构

```
易订系统 <---> 智链OS API <---> 智链OS数据库
    |                |
    |                |
Webhook推送      API同步
```

## 功能特性

### 1. 预订数据同步
- ✅ 实时接收易订系统推送的预订数据
- ✅ 支持预订创建、更新、取消事件
- ✅ 双向数据同步
- ✅ 保留原始数据用于审计

### 2. 预订状态管理
- `pending` - 待确认
- `confirmed` - 已确认
- `arrived` - 已到店
- `seated` - 已入座
- `completed` - 已完成
- `cancelled` - 已取消
- `no_show` - 未到店

### 3. 预订信息
- 客户信息(姓名、电话、人数)
- 预订时间(日期、时间段)
- 桌台信息(类型、桌号、区域)
- 特殊要求和备注
- 预付款信息
- 来源渠道追踪

## 集成步骤

### 步骤1: 创建易订系统配置

```bash
POST /api/v1/integrations/systems
Authorization: Bearer {token}
Content-Type: application/json

{
    "name": "易订预订管理系统",
    "type": "reservation",
    "provider": "Yiding",
    "store_id": "store-001",
    "config": {
        "api_endpoint": "https://api.yiding.com/reservation",
        "api_key": "your_yiding_api_key",
        "webhook_url": "https://your-domain/api/v1/integrations/webhooks/reservation/{system_id}"
    }
}
```

响应:
```json
{
    "id": "uuid",
    "name": "易订预订管理系统",
    "type": "reservation",
    "provider": "Yiding",
    "status": "inactive",
    "store_id": "store-001",
    ...
}
```

### 步骤2: 配置易订Webhook

在易订管理后台配置Webhook推送地址:
```
https://your-domain/api/v1/integrations/webhooks/reservation/{system_id}
```

易订系统会在以下事件发生时推送数据:
- 新预订创建 (`reservation.created`)
- 预订信息更新 (`reservation.updated`)
- 预订取消 (`reservation.cancelled`)

### 步骤3: 测试连接

```bash
POST /api/v1/integrations/systems/{system_id}/test
Authorization: Bearer {token}
```

## API接口

### 1. 同步预订数据

手动同步预订数据到智链OS:

```bash
POST /api/v1/integrations/reservation/{system_id}/sync
Authorization: Bearer {token}
Content-Type: application/json

{
    "reservation_id": "RES-2024-001",
    "external_id": "yiding_res_001",
    "reservation_number": "YD20240214001",
    "customer_name": "张三",
    "customer_phone": "13800138000",
    "customer_count": 4,
    "reservation_date": "2024-02-15T00:00:00",
    "reservation_time": "18:00-20:00",
    "table_type": "圆桌",
    "area": "大厅",
    "status": "confirmed",
    "special_requirements": "靠窗位置，需要儿童座椅",
    "notes": "客户是VIP会员",
    "deposit_required": true,
    "deposit_amount": 200.00,
    "deposit_paid": true,
    "source": "yiding",
    "channel": "微信小程序"
}
```

### 2. 获取预订列表

```bash
GET /api/v1/integrations/reservation/list?store_id=store-001&status=confirmed&date_from=2024-02-15T00:00:00&date_to=2024-02-15T23:59:59
Authorization: Bearer {token}
```

查询参数:
- `store_id`: 门店ID
- `status`: 预订状态
- `date_from`: 开始日期(ISO格式)
- `date_to`: 结束日期(ISO格式)
- `limit`: 返回数量限制(默认100)

### 3. 更新预订状态

```bash
PUT /api/v1/integrations/reservation/{reservation_id}/status?status=arrived&arrival_time=2024-02-15T18:05:00
Authorization: Bearer {token}
```

查询参数:
- `status`: 新状态(required)
- `arrival_time`: 到店时间(当status=arrived时)
- `table_number`: 桌号(当status=seated时)

### 4. Webhook接收端点

```bash
POST /api/v1/integrations/webhooks/reservation/{system_id}
Content-Type: application/json

{
    "event": "reservation.created",
    "data": {
        "reservation_id": "RES-2024-001",
        "customer_name": "张三",
        "customer_phone": "13800138000",
        "customer_count": 4,
        "reservation_date": "2024-02-15T00:00:00",
        "reservation_time": "18:00-20:00",
        "status": "pending",
        ...
    }
}
```

支持的事件类型:
- `reservation.created` - 新预订创建
- `reservation.updated` - 预订信息更新
- `reservation.cancelled` - 预订取消

## 数据模型

### ReservationSync

```python
{
    "id": "uuid",
    "system_id": "外部系统ID",
    "store_id": "门店ID",
    "reservation_id": "预订ID",
    "external_reservation_id": "易订系统预订ID",
    "reservation_number": "预订号",
    "customer_name": "客户姓名",
    "customer_phone": "客户电话",
    "customer_count": 4,
    "reservation_date": "2024-02-15T00:00:00",
    "reservation_time": "18:00-20:00",
    "arrival_time": "2024-02-15T18:05:00",
    "table_type": "圆桌",
    "table_number": "A08",
    "area": "大厅",
    "status": "seated",
    "special_requirements": "靠窗位置，需要儿童座椅",
    "notes": "客户是VIP会员",
    "deposit_required": true,
    "deposit_amount": 200.00,
    "deposit_paid": true,
    "source": "yiding",
    "channel": "微信小程序",
    "sync_status": "success",
    "synced_at": "2024-02-14T10:30:00",
    "created_at": "2024-02-14T10:30:00",
    "updated_at": "2024-02-15T18:05:00"
}
```

## 业务流程

### 流程1: 客户通过易订预订

```
1. 客户在易订小程序/网站预订
   ↓
2. 易订系统创建预订记录
   ↓
3. 易订推送Webhook到智链OS
   ↓
4. 智链OS接收并存储预订数据
   ↓
5. 智链OS通知相关人员(门店经理、楼面经理)
```

### 流程2: 客户到店

```
1. 客户到店
   ↓
2. 前台查询预订信息
   ↓
3. 更新预订状态为"已到店"
   ↓
4. 安排座位
   ↓
5. 更新预订状态为"已入座"，记录桌号
   ↓
6. 开始用餐服务
```

### 流程3: 预订取消

```
1. 客户在易订取消预订
   ↓
2. 易订推送取消Webhook
   ↓
3. 智链OS更新预订状态为"已取消"
   ↓
4. 释放预留的桌台资源
   ↓
5. 通知相关人员
```

## 权限要求

| 操作 | 所需角色 |
|------|---------|
| 创建易订系统配置 | admin, store_manager |
| 同步预订数据 | admin, store_manager, customer_manager |
| 查看预订列表 | 所有已认证用户 |
| 更新预订状态 | admin, store_manager, floor_manager |
| 接收Webhook | 无需认证(公开端点) |

## 测试

运行易订集成测试脚本:

```bash
./test_yiding_reservation.sh
```

测试脚本将验证:
1. ✓ 创建易订系统配置
2. ✓ 同步预订数据
3. ✓ 查询预订列表
4. ✓ 按状态筛选
5. ✓ 按日期范围筛选
6. ✓ 更新预订状态(到店、入座)
7. ✓ Webhook接收(新建、更新、取消)

## 常见问题

### Q1: 如何处理重复预订?

A: 系统使用`reservation_id`作为唯一标识,相同ID的预订会更新而不是创建新记录。

### Q2: 预订数据多久同步一次?

A: 通过Webhook实时推送,延迟通常在1-2秒内。也可以配置定时同步作为备份。

### Q3: 如何处理易订系统故障?

A: 系统会记录同步失败的日志,可以在易订恢复后手动重新同步。

### Q4: 是否支持批量导入历史预订?

A: 支持,可以通过API批量调用同步接口导入历史数据。

### Q5: 预订数据是否可以修改?

A: 可以通过更新状态接口修改预订状态,但建议保持与易订系统的数据一致性。

## 注意事项

1. **Webhook安全**: 建议验证Webhook请求来源,可以使用签名验证
2. **数据一致性**: 保持智链OS与易订系统的数据同步
3. **错误处理**: 记录所有同步错误,便于排查问题
4. **性能优化**: 高峰期可能有大量预订,注意API性能
5. **数据备份**: 定期备份预订数据,防止数据丢失

## 技术支持

如有问题,请联系:
- 智链OS技术支持: support@zhilian-os.com
- 易订技术支持: 参考易订官方文档

## 更新日志

### v1.0.0 (2024-02-14)
- ✅ 初始版本发布
- ✅ 支持易订预订数据同步
- ✅ 支持Webhook实时推送
- ✅ 支持预订状态管理
- ✅ 支持多维度查询筛选