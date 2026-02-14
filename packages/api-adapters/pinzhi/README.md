# 品智收银系统 API 适配器

## 概述

品智收银系统API适配器，提供门店管理、菜品管理、订单查询、营业数据等功能的Python封装。

## 功能特性

### 1. 基础数据接口
- ✅ 门店信息查询
- ✅ 菜品类别查询
- ✅ 菜品信息查询
- ✅ 做法和配料查询
- ✅ 收银桌台查询
- ✅ 门店用户（员工）查询

### 2. 业务数据接口
- ✅ 按日期查询订单（支持分页）
- ✅ 按门店查询收入数据
- ✅ 查询所有门店营业额
- ✅ 查询出品过程明细
- ✅ 挂账客户管理

### 3. 支付相关接口
- ✅ 查询支付方式
- ✅ 下载微信支付宝对账单

### 4. 签名机制
- ✅ MD5签名生成
- ✅ 签名验证
- ✅ 参数排序和过滤

## 安装

```bash
# 在项目根目录
pnpm install
```

## 使用示例

### 初始化适配器

```python
from packages.api_adapters.pinzhi.src import PinzhiAdapter

# 配置
config = {
    "base_url": "http://192.168.1.100:8080/pzcatering-gateway",
    "token": "your-token",
    "timeout": 30,
    "retry_times": 3
}

# 创建适配器实例
adapter = PinzhiAdapter(config)
```

### 签名机制

品智API使用MD5签名机制进行身份验证：

```python
from packages.api_adapters.pinzhi.src import generate_sign, verify_sign

# 生成签名
token = "your_token"
params = {"ognid": "12345", "beginDate": "2024-01-01"}
sign = generate_sign(token, params)
print(f"签名: {sign}")

# 验证签名
is_valid = verify_sign(token, params, sign)
print(f"签名有效: {is_valid}")
```

**签名算法**：
1. 将所有请求参数（除sign外）按参数名ASCII码升序排列
2. 排除pageIndex和pageSize参数
3. 拼接成`key1=value1&key2=value2&...&token=xxx`格式
4. 对拼接后的字符串进行MD5加密得到签名值

### 基础数据查询

```python
# 查询门店信息
stores = await adapter.get_store_info()
for store in stores:
    print(f"门店: {store['ognname']}, 地址: {store['ognaddress']}")

# 查询指定门店
store = await adapter.get_store_info(ognid="12345")

# 查询菜品类别
categories = await adapter.get_dish_categories()
for cat in categories:
    print(f"类别: {cat['rcNAME']}, 父级ID: {cat['fatherId']}")

# 查询菜品信息
dishes = await adapter.get_dishes(updatetime=0)  # 0表示拉取所有
for dish in dishes:
    print(f"菜品: {dish['dishesName']}, 价格: {dish['dishPrice']}")

# 查询桌台信息
tables = await adapter.get_tables()
for table in tables:
    print(f"桌台: {table['tableName']}, 营业区: {table['blName']}")

# 查询员工信息
employees = await adapter.get_employees()
for emp in employees:
    print(f"员工: {emp['epName']}, 岗位: {emp['pgName']}")
```

### 订单查询

```python
# 查询订单（按日期范围）
orders = await adapter.query_orders(
    ognid="12345",
    begin_date="2024-01-01",
    end_date="2024-01-31",
    page_index=1,
    page_size=20
)

for order in orders:
    print(f"订单号: {order['billNo']}")
    print(f"桌台: {order['tableNo']}")
    print(f"人数: {order['people']}")
    print(f"账单总额: {order['billPriceTotal']} 分")
    print(f"实收金额: {order['realPrice']} 分")
    print(f"状态: {order['billStatus']}")
    print(f"会员: {order['vipName']}")
    print("---")

# 查询门店收入汇总
summary = await adapter.query_order_summary(
    ognid="12345",
    business_date="2024-01-01"
)
print(f"营业日: {summary['businesDate']}")
print(f"菜类汇总: {summary['rcIdList']}")
print(f"部门汇总: {summary['cdIdList']}")
```

### 营业数据查询

```python
# 查询所有门店营业额
store_summary = await adapter.query_store_summary_list(
    business_date="2024-01-01"
)

# 查询出品过程明细
cooking_details = await adapter.query_cooking_detail(
    business_date="2024-01-01"
)
for detail in cooking_details:
    print(f"菜品: {detail['dishName']}")
    print(f"下单时间: {detail['orderTime']}")
    print(f"配菜时长: {detail['garnishStayDuration']} 分钟")
    print(f"炒菜时长: {detail['cookStayDuration']} 分钟")
```

### 支付相关

```python
# 查询支付方式
pay_types = await adapter.get_pay_types()
for pt in pay_types:
    print(f"支付方式: {pt['name']}, 类别: {pt['category']}")

# 下载对账单
bill_data = await adapter.download_bill_data(
    ognid="12345",
    pay_date="2024-01-01",
    pay_type=1  # 1-微信，2-支付宝
)
```

## 数据类型约定

### 金额单位
**重要**: 所有金额字段的单位均为"分"（cent），而非"元"（yuan）

| 实际金额 | API参数值 |
|----------|-----------|
| ¥1.00 | 100 |
| ¥100.00 | 10000 |
| ¥0.50 | 50 |

### 日期时间格式
| 格式 | 说明 | 示例 |
|------|------|------|
| 日期 | yyyy-MM-dd | 2024-01-15 |
| 日期时间 | yyyy-MM-dd HH:mm:ss | 2024-01-15 10:30:00 |

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

## 错误处理

适配器会抛出以下异常：

```python
try:
    stores = await adapter.get_store_info()
except ValueError as e:
    # 参数错误
    print(f"参数错误: {e}")
except Exception as e:
    # API调用失败
    print(f"API错误: {e}")
```

品智系统使用两种错误响应格式：

1. **success字段**（大部分接口）：
```json
{
  "success": 0,  // 0表示成功，非0表示失败
  "msg": "成功",
  "data": []
}
```

2. **errcode字段**（部分接口）：
```json
{
  "errcode": 0,  // 0表示成功，非0表示失败
  "errmsg": "成功",
  "res": []
}
```

## 测试

```bash
# 运行单元测试
cd packages/api-adapters/pinzhi
pytest tests/ -v

# 运行测试并查看覆盖率
pytest tests/ -v --cov=src --cov-report=html

# 测试签名算法
pytest tests/test_adapter.py::TestSignature -v
```

## Token申请

1. 登录品智客户运维系统
2. 进入商户管理 > 商户管理
3. 填写回调地址并申请Token
4. 将Token配置到对接系统中

## 注意事项

1. **Token安全**: 不要将Token硬编码在代码中，使用环境变量
2. **金额单位**: 所有金额必须使用"分"作为单位
3. **签名计算**:
   - 参数必须按ASCII码排序
   - 排除sign、pageIndex、pageSize参数
   - Token作为最后一个参数参与签名
4. **异步调用**: 所有API方法都是异步的，需要使用`await`
5. **分页查询**: pageIndex和pageSize不参与签名计算
6. **资源释放**: 使用完毕后调用`await adapter.close()`释放资源

## 与奥琦韦系统对比

| 对比维度 | 品智收银 | 奥琦韦微生活 |
|----------|----------|--------------|
| 系统定位 | 餐饮收银管理 | 会员管理与营销 |
| 认证方式 | MD5签名+Token | API密钥 |
| 响应格式 | success/errcode | errcode |
| 核心功能 | 门店、菜品、订单 | 会员、交易、储值、优惠券 |
| 数据粒度 | 订单级、菜品级、出品级 | 会员级、交易级 |

## 开发状态

- ✅ 已完成: 核心功能实现和签名机制
- ⏳ 进行中: 实际API调用集成
- 📝 计划中: 更多高级功能

## 许可证

MIT License
