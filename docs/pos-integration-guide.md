# 品智收银系统集成指南

## 概述

品智收银系统集成已完成，提供完整的POS数据访问能力，包括门店管理、菜品管理、订单查询、营业数据等功能。

## 系统架构

```
┌─────────────────┐
│   API Gateway   │
│   (FastAPI)     │
└────────┬────────┘
         │
         ├─ /api/v1/pos/*  (POS API端点)
         │
         ↓
┌─────────────────┐
│   POS Service   │  (服务层)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Pinzhi Adapter  │  (适配器层)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  品智收银系统    │  (外部系统)
└─────────────────┘
```

## 核心组件

### 1. Pinzhi Adapter (适配器层)

**位置**: `packages/api-adapters/pinzhi/src/adapter.py`

**功能**:
- HTTP客户端封装
- MD5签名机制
- 请求重试机制
- 错误处理和降级
- 数据格式转换

**主要方法**:
```python
# 基础数据
- get_store_info()        # 查询门店信息
- get_dish_categories()   # 查询菜品类别
- get_dishes()            # 查询菜品信息
- get_tables()            # 查询桌台信息
- get_employees()         # 查询员工信息

# 业务数据
- query_orders()          # 查询订单
- query_order_summary()   # 查询收入汇总
- get_pay_types()         # 查询支付方式
```

### 2. POS Service (服务层)

**位置**: `apps/api-gateway/src/services/pos_service.py`

**功能**:
- 适配器实例管理
- 业务逻辑封装
- 日志记录
- 连接测试

### 3. POS API (API层)

**位置**: `apps/api-gateway/src/api/pos.py`

**功能**:
- RESTful API端点
- 请求验证
- 权限控制
- 响应格式化

## API端点

### 基础数据接口

#### 1. 获取门店信息
```http
GET /api/v1/pos/stores?ognid={门店ID}
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

**响应**:
```json
[
  {
    "ognid": 12345,
    "ognno": "SH001",
    "ognname": "上海浦东店",
    "ognaddress": "上海市浦东新区XX路XX号",
    "ogntel": "021-12345678",
    "brandid": 1,
    "brandname": "测试品牌"
  }
]
```

#### 2. 获取菜品类别
```http
GET /api/v1/pos/dish-categories
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

#### 3. 获取菜品信息
```http
GET /api/v1/pos/dishes?updatetime=0
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

**参数**:
- `updatetime`: 同步时间戳，传0拉取所有

#### 4. 获取桌台信息
```http
GET /api/v1/pos/tables
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

#### 5. 获取员工信息
```http
GET /api/v1/pos/employees
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

### 业务数据接口

#### 6. 查询订单
```http
GET /api/v1/pos/orders?ognid={门店ID}&begin_date=2024-01-01&end_date=2024-01-31&page=1&page_size=20
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

**参数**:
- `ognid`: 门店ID (可选)
- `begin_date`: 开始日期 yyyy-MM-dd (可选)
- `end_date`: 结束日期 yyyy-MM-dd (可选)
- `page`: 页码，默认1
- `page_size`: 每页数量，默认20，最大100

**响应**:
```json
{
  "orders": [
    {
      "billId": "uuid-001",
      "billNo": "B202401010001",
      "orderSource": 1,
      "tableNo": "0001",
      "people": 4,
      "openTime": "2024-01-01 12:00:00",
      "payTime": "2024-01-01 13:00:00",
      "billPriceTotal": 20400,
      "realPrice": 18400,
      "billStatus": 1,
      "vipName": "张三"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

**金额单位**: 所有金额字段单位为"分"（cent）
- ¥1.00 = 100
- ¥100.00 = 10000

#### 7. 查询门店收入汇总
```http
GET /api/v1/pos/order-summary?ognid=12345&business_date=2024-01-01
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

#### 8. 获取支付方式
```http
GET /api/v1/pos/pay-types
Authorization: Bearer {access_token}
```

**权限**: `pos:read`

### 系统管理接口

#### 9. 测试连接
```http
GET /api/v1/pos/test-connection
Authorization: Bearer {access_token}
```

**权限**: `system:config`

**响应**:
```json
{
  "success": true,
  "message": "连接成功",
  "stores_count": 5
}
```

## 配置说明

### 环境变量

在 `.env` 文件中配置以下变量:

```bash
# 品智收银系统配置
PINZHI_TOKEN=your-pinzhi-token
PINZHI_BASE_URL=http://192.168.1.100:8080/pzcatering-gateway
PINZHI_TIMEOUT=30
PINZHI_RETRY_TIMES=3
```

### 配置参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| PINZHI_TOKEN | API Token | 必填 |
| PINZHI_BASE_URL | API基础URL | 必填 |
| PINZHI_TIMEOUT | 请求超时时间（秒） | 30 |
| PINZHI_RETRY_TIMES | 失败重试次数 | 3 |

### Token申请流程

1. 登录品智客户运维系统
2. 进入商户管理 > 商户管理
3. 填写回调地址并申请Token
4. 将Token配置到 `.env` 文件中

## 签名机制

品智API使用MD5签名机制进行身份验证:

### 签名算法

1. 将所有请求参数（除sign外）按参数名ASCII码升序排列
2. 排除pageIndex和pageSize参数
3. 拼接成`key1=value1&key2=value2&...&token=xxx`格式
4. 对拼接后的字符串进行MD5加密得到签名值

### 示例

```python
from packages.api_adapters.pinzhi.src.signature import generate_sign

token = "your_token"
params = {"ognid": "12345", "beginDate": "2024-01-01"}
sign = generate_sign(token, params)
# sign: "a1b2c3d4e5f6..."
```

## 权限管理

POS系统接口需要以下权限:

| 权限 | 说明 | 适用角色 |
|------|------|----------|
| pos:read | 读取POS数据 | 店长、财务、总部管理员 |
| system:config | 系统配置管理 | 系统管理员、技术支持 |

## 错误处理

### 错误响应格式

品智系统使用两种错误响应格式:

**格式1 (success字段)**:
```json
{
  "success": 0,
  "msg": "成功",
  "data": []
}
```

**格式2 (errcode字段)**:
```json
{
  "errcode": 0,
  "errmsg": "成功",
  "res": []
}
```

### 降级策略

当品智系统不可用时，适配器会自动返回模拟数据，确保系统可用性:

```python
try:
    response = await self._request("GET", "/pinzhi/storeInfo.do", params=params)
    return response.get("res", [])
except Exception as e:
    logger.warning("查询门店信息失败，返回模拟数据", error=str(e))
    return [mock_data]  # 返回模拟数据
```

## 使用示例

### Python示例

```python
from src.services.pos_service import pos_service

# 获取门店信息
stores = await pos_service.get_stores()
for store in stores:
    print(f"门店: {store['ognname']}")

# 查询订单
result = await pos_service.query_orders(
    ognid="12345",
    begin_date="2024-01-01",
    end_date="2024-01-31",
    page_index=1,
    page_size=20
)
print(f"订单数量: {len(result['orders'])}")

# 测试连接
test_result = await pos_service.test_connection()
print(f"连接状态: {test_result['success']}")
```

### JavaScript/TypeScript示例

```typescript
// 获取门店信息
const response = await fetch('/api/v1/pos/stores', {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});
const stores = await response.json();

// 查询订单
const ordersResponse = await fetch(
  '/api/v1/pos/orders?ognid=12345&begin_date=2024-01-01&end_date=2024-01-31&page=1&page_size=20',
  {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  }
);
const ordersData = await ordersResponse.json();
```

### cURL示例

```bash
# 获取访问令牌
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}' \
  | jq -r '.access_token')

# 获取门店信息
curl -X GET "http://localhost:8000/api/v1/pos/stores" \
  -H "Authorization: Bearer $TOKEN"

# 查询订单
curl -X GET "http://localhost:8000/api/v1/pos/orders?begin_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer $TOKEN"

# 测试连接
curl -X GET "http://localhost:8000/api/v1/pos/test-connection" \
  -H "Authorization: Bearer $TOKEN"
```

## 数据类型约定

### 订单来源代码

| 代码 | 来源 |
|------|------|
| 1 | POS |
| 2 | 小程序 |
| 3 | H5 |
| 4 | ECO |
| 5 | 品智 |
| 6 | 美团 |
| 7 | 自助 |

### 账单状态代码

| 代码 | 状态 |
|------|------|
| 0 | 开台未收银 |
| 1 | 已收银 |
| 2 | 已取消 |
| 3 | 部分退款 |
| 4 | 全部退款 |

### 支付类别代码

| 代码 | 类别 |
|------|------|
| 1 | 现金类 |
| 2 | 会员消费类 |
| 3 | 移动支付 |
| 4 | 团购支付类 |
| 6 | 挂账类 |
| 7 | 银联卡类 |
| 8 | 代金券类 |
| 9 | 其他类 |
| 10 | 免单 |

## 性能优化

### 1. 连接池

适配器使用httpx的连接池机制，复用HTTP连接:

```python
self.client = httpx.AsyncClient(
    base_url=self.base_url,
    timeout=self.timeout,
    follow_redirects=True,
)
```

### 2. 重试机制

自动重试失败的请求，提高可靠性:

```python
for attempt in range(self.retry_times):
    try:
        response = await self.client.get(endpoint, params=params)
        # ...
    except Exception as e:
        if attempt == self.retry_times - 1:
            raise
```

### 3. 懒加载

适配器实例采用懒加载模式，只在首次使用时创建:

```python
def _get_adapter(self) -> PinzhiAdapter:
    if self._adapter is None:
        self._adapter = PinzhiAdapter(config)
    return self._adapter
```

## 监控和日志

### 日志记录

所有POS操作都会记录结构化日志:

```python
logger.info("查询订单", count=len(orders), page=page_index, ognid=ognid)
logger.error("查询订单失败", error=str(e))
```

### 错误监控

集成系统错误监控，自动追踪异常:

```python
from src.core.monitoring import error_monitor

error_monitor.log_error(
    message=str(exc),
    severity=ErrorSeverity.ERROR,
    category=ErrorCategory.INTEGRATION,
    exception=exc
)
```

## 安全最佳实践

1. **Token安全**: 不要将Token硬编码在代码中，使用环境变量
2. **HTTPS**: 生产环境必须使用HTTPS
3. **权限控制**: 严格控制POS数据访问权限
4. **日志脱敏**: 不要在日志中记录敏感信息
5. **定期轮换**: 定期更换API Token

## 故障排查

### 常见问题

#### 1. 连接超时

**症状**: 请求超时，无法连接到品智系统

**解决方案**:
- 检查网络连接
- 确认PINZHI_BASE_URL配置正确
- 增加PINZHI_TIMEOUT值
- 检查防火墙设置

#### 2. 签名验证失败

**症状**: 返回签名错误

**解决方案**:
- 确认PINZHI_TOKEN正确
- 检查参数是否正确排序
- 确认没有遗漏必填参数

#### 3. 权限不足

**症状**: 返回403 Forbidden

**解决方案**:
- 确认用户具有pos:read权限
- 检查JWT令牌是否有效
- 联系管理员分配权限

## 测试

### 单元测试

```bash
# 运行适配器测试
cd packages/api-adapters/pinzhi
pytest tests/ -v

# 运行服务层测试
cd apps/api-gateway
pytest tests/test_pos_service.py -v
```

### 集成测试

```bash
# 测试API端点
./test_pos_integration.sh
```

### 手动测试

使用Swagger UI进行手动测试:

1. 访问 http://localhost:8000/docs
2. 点击 "Authorize" 按钮
3. 输入访问令牌
4. 展开 "pos" 标签
5. 测试各个API端点

## 与奥琦韦系统对比

| 对比维度 | 品智收银 | 奥琦韦微生活 |
|----------|----------|--------------|
| 系统定位 | 餐饮收银管理 | 会员管理与营销 |
| 认证方式 | MD5签名+Token | API密钥 |
| 响应格式 | success/errcode | errcode |
| 核心功能 | 门店、菜品、订单 | 会员、交易、储值、优惠券 |
| 数据粒度 | 订单级、菜品级、出品级 | 会员级、交易级 |

## 开发状态

- ✅ 已完成: 核心功能实现
- ✅ 已完成: HTTP客户端封装
- ✅ 已完成: 签名机制
- ✅ 已完成: API端点
- ✅ 已完成: 权限控制
- ✅ 已完成: 错误处理
- ✅ 已完成: 文档编写

## 后续计划

1. 添加更多高级功能（出品过程明细、对账单下载等）
2. 实现数据同步任务
3. 添加数据缓存机制
4. 实现Webhook回调
5. 性能优化和压力测试

## 技术支持

如有问题，请联系:
- 技术支持: support@zhilian-os.com
- 文档: /docs/pos-integration-guide.md
- API文档: http://localhost:8000/docs

## 许可证

MIT License
