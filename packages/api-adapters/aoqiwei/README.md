# 奥琦韦微生活系统 API 适配器

## 概述

奥琦韦微生活系统API适配器，提供会员管理、交易处理、储值管理、优惠券管理等功能的Python封装。

## 功能特性

### 1. 会员管理
- ✅ 查询会员详情（支持卡号/手机号/openid查询）
- ✅ 新增会员
- ✅ 修改会员信息
- ⏳ 会员标签管理
- ⏳ 会员等级调整

### 2. 交易处理
- ✅ 交易预览（计算优惠）
- ✅ 交易提交
- ✅ 交易查询
- ✅ 交易撤销
- ⏳ 交易锁定/解锁
- ⏳ 交易部分退

### 3. 储值管理
- ✅ 储值提交
- ✅ 储值查询
- ⏳ 储值明细
- ⏳ 储值退款

### 4. 优惠券管理
- ✅ 查询可用券
- ✅ 券码核销
- ⏳ 券码撤销
- ⏳ 批量核销
- ⏳ 新券发放

## 安装

```bash
# 在项目根目录
pnpm install
```

## 使用示例

### 初始化适配器

```python
from packages.api_adapters.aoqiwei.src import AoqiweiAdapter

# 配置
config = {
    "base_url": "https://api.aoqiwei.com",
    "api_key": "your-api-key",
    "timeout": 30,
    "retry_times": 3
}

# 创建适配器实例
adapter = AoqiweiAdapter(config)
```

### 会员管理

```python
# 查询会员
member = await adapter.query_member(card_no="M20240001")
print(f"会员姓名: {member['name']}")
print(f"会员等级: {member['level']}")
print(f"积分余额: {member['points']}")
print(f"储值余额: {member['balance']} 分")

# 新增会员
new_member = await adapter.add_member(
    mobile="13800138000",
    name="张三",
    sex=1,
    birthday="1990-01-01",
    store_id="STORE001"
)
print(f"新会员卡号: {new_member['cardNo']}")

# 修改会员信息
result = await adapter.update_member(
    card_no="M20240001",
    update_data={"name": "张三三", "sex": 2}
)
```

### 交易处理

```python
# 交易预览
preview = await adapter.trade_preview(
    card_no="M20240001",
    store_id="STORE001",
    cashier="收银员001",
    amount=10000,  # 100元 = 10000分
    dish_list=[
        {
            "dishId": "DISH001",
            "dishName": "宫保鸡丁",
            "price": 5000,
            "count": 2
        }
    ]
)
print(f"消费总额: {preview['totalAmount']} 分")
print(f"优惠金额: {preview['discountAmount']} 分")
print(f"应付金额: {preview['payAmount']} 分")

# 交易提交
trade = await adapter.trade_submit(
    card_no="M20240001",
    store_id="STORE001",
    cashier="收银员001",
    amount=9000,
    pay_type=3,  # 店内微信支付
    trade_no="T202401010001",
    discount_plan={
        "pointsDeduction": 500,
        "couponDeduction": 500,
        "balanceDeduction": 8000
    }
)
print(f"交易ID: {trade['tradeId']}")
print(f"交易状态: {trade['status']}")
```

### 储值管理

```python
# 储值提交
recharge = await adapter.recharge_submit(
    card_no="M20240001",
    store_id="STORE001",
    cashier="收银员001",
    amount=100000,  # 1000元 = 100000分
    pay_type=3,
    trade_no="R202401010001"
)
print(f"充值ID: {recharge['rechargeId']}")
print(f"当前余额: {recharge['balance']} 分")

# 查询储值
balance = await adapter.recharge_query(card_no="M20240001")
print(f"储值余额: {balance['balance']} 分")
```

### 优惠券管理

```python
# 查询可用优惠券
coupons = await adapter.coupon_list(
    card_no="M20240001",
    store_id="STORE001"
)
for coupon in coupons:
    print(f"优惠券: {coupon['couponName']}, 面值: {coupon['faceValue']} 分")

# 券码核销
result = await adapter.coupon_use(
    code="COUPON001",
    store_id="STORE001",
    cashier="收银员001",
    amount=9000
)
print(f"优惠券: {result['couponName']}")
print(f"面值: {result['faceValue']} 分")
print(f"使用规则: {result['useRule']}")
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
| 日期 | YYYY-MM-DD | 2024-01-15 |
| 日期时间 | YYYY-MM-DD HH:mm:ss | 2024-01-15 10:30:00 |

### 支付方式代码
| 代码 | 支付方式 |
|------|----------|
| 1 | 现金 |
| 2 | 银行卡 |
| 3 | 店内微信 |
| 4 | 店内支付宝 |
| 6 | 线上微信 |
| 8 | 美团 |
| 9 | 大众点评 |

## 错误处理

适配器会抛出以下异常：

```python
try:
    member = await adapter.query_member(card_no="M20240001")
except ValueError as e:
    # 参数错误
    print(f"参数错误: {e}")
except Exception as e:
    # API调用失败
    print(f"API错误: {e}")
```

## 测试

```bash
# 运行单元测试
cd packages/api-adapters/aoqiwei
pytest tests/ -v

# 运行测试并查看覆盖率
pytest tests/ -v --cov=src --cov-report=html
```

## 注意事项

1. **API密钥安全**: 不要将API密钥硬编码在代码中，使用环境变量
2. **金额单位**: 所有金额必须使用"分"作为单位
3. **异步调用**: 所有API方法都是异步的，需要使用`await`
4. **错误处理**: 建议使用try-except捕获异常
5. **资源释放**: 使用完毕后调用`await adapter.close()`释放资源

## 开发状态

- ✅ 已完成: 核心功能实现
- ⏳ 进行中: 实际API调用集成
- 📝 计划中: 更多高级功能

## 许可证

MIT License
