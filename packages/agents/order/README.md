# 订单协同Agent

## 概述

订单协同Agent是智链OS的核心Agent之一，处理从预定到结账的完整订单生命周期，包括预定管理、排队等位、智能点单、结账支付等功能。

## 功能特性

### 1. 预定管理
- 在线/电话/现场预定
- 时间可用性检查
- 替代时间建议
- 特殊需求处理

### 2. 排队等位管理
- 自动生成排队号
- 智能等待时间预估
- 实时排队状态查询
- 叫号通知

### 3. 智能点单
- 创建订单
- 添加/修改菜品
- 智能菜品推荐
- 特殊要求备注

### 4. 结账支付
- 账单计算
- 会员折扣
- 优惠券核销
- 多种支付方式

### 5. 订单管理
- 订单状态跟踪
- 订单查询
- 订单取消
- 状态更新通知

## 安装

```bash
# 在项目根目录
pnpm install
```

## 使用示例

### 基本使用

```python
from packages.agents.order.src import OrderAgent, PaymentMethod

# 初始化Agent
config = {
    "average_wait_time": 30,      # 平均等待时间（分钟）
    "average_dining_time": 90,    # 平均用餐时间（分钟）
}
agent = OrderAgent(config)
```

### 预定管理

```python
# 创建预定
result = await agent.create_reservation(
    store_id="STORE001",
    customer_name="张三",
    customer_mobile="13800138000",
    party_size=4,
    reservation_time="2024-01-20 18:00",
    special_requests="靠窗座位"
)

if result["success"]:
    reservation = result["reservation"]
    print(f"预定成功！预定号：{reservation['reservation_id']}")
else:
    print(f"预定失败：{result['message']}")
    print(f"建议时间：{result['alternative_times']}")
```

### 排队等位

```python
# 加入排队
result = await agent.join_queue(
    store_id="STORE001",
    customer_name="李四",
    customer_mobile="13900139000",
    party_size=2
)

queue_info = result["queue_info"]
print(f"排队号：{queue_info['queue_number']}")
print(f"预计等待：{queue_info['estimated_wait_minutes']}分钟")

# 查询排队状态
status = await agent.get_queue_status(queue_info["queue_id"])
print(f"前面还有{status['ahead_count']}桌")
```

### 点单流程

```python
# 1. 创建订单
order_result = await agent.create_order(
    store_id="STORE001",
    table_id="T001",
    customer_id="C001"
)
order_id = order_result["order"]["order_id"]

# 2. 获取推荐菜品
recommendations = await agent.recommend_dishes(
    store_id="STORE001",
    customer_id="C001",
    party_size=4
)

for dish in recommendations["recommendations"]:
    print(f"{dish['dish_name']} - ¥{dish['price']}")
    print(f"推荐理由：{dish['reason']}")

# 3. 添加菜品
await agent.add_dish(
    order_id=order_id,
    dish_id="D001",
    dish_name="宫保鸡丁",
    price=48.0,
    quantity=2,
    special_instructions="少辣"
)

await agent.add_dish(
    order_id=order_id,
    dish_id="D002",
    dish_name="麻婆豆腐",
    price=32.0,
    quantity=1
)
```

### 结账支付

```python
# 1. 计算账单
bill_result = await agent.calculate_bill(
    order_id=order_id,
    member_id="M001",
    coupon_codes=["COUPON001"]
)

bill = bill_result["bill"]
print(f"菜品总额：¥{bill['total_amount']}")
print(f"会员折扣：-¥{bill['member_discount']}")
print(f"优惠券：-¥{bill['coupon_discount']}")
print(f"实付金额：¥{bill['final_amount']}")

# 2. 处理支付
payment_result = await agent.process_payment(
    order_id=order_id,
    payment_method=PaymentMethod.WECHAT.value,
    amount=bill["final_amount"]
)

if payment_result["success"]:
    print("支付成功！")
    print(f"支付单号：{payment_result['payment']['payment_id']}")
```

## 数据模型

### 订单状态流转

```
RESERVED (已预定)
    ↓
WAITING (等位中)
    ↓
SEATED (已入座)
    ↓
ORDERING (点餐中)
    ↓
ORDERED (已下单)
    ↓
COOKING (制作中)
    ↓
SERVED (已上菜)
    ↓
PAYING (结账中)
    ↓
PAID (已支付)
    ↓
COMPLETED (已完成)

可随时转到：CANCELLED (已取消)
```

### 支付方式

| 方式 | 说明 |
|------|------|
| cash | 现金 |
| wechat | 微信支付 |
| alipay | 支付宝 |
| card | 银行卡 |
| member | 会员储值 |

### 预定类型

| 类型 | 说明 |
|------|------|
| online | 线上预定 |
| phone | 电话预定 |
| walkin | 现场预定 |

## API参考

### 预定管理

#### create_reservation
创建预定

**参数**:
- `store_id`: 门店ID
- `customer_name`: 客户姓名
- `customer_mobile`: 客户手机号
- `party_size`: 用餐人数
- `reservation_time`: 预定时间 (YYYY-MM-DD HH:mm)
- `special_requests`: 特殊需求（可选）

**返回**: 预定结果

### 排队管理

#### join_queue
加入排队

**参数**:
- `store_id`: 门店ID
- `customer_name`: 客户姓名
- `customer_mobile`: 客户手机号
- `party_size`: 用餐人数

**返回**: 排队信息（包含排队号和预估等待时间）

#### get_queue_status
查询排队状态

**参数**:
- `queue_id`: 排队ID

**返回**: 排队状态（前面人数、预估等待时间）

### 点单管理

#### create_order
创建订单

**参数**:
- `store_id`: 门店ID
- `table_id`: 桌台ID
- `customer_id`: 客户ID（可选）

**返回**: 订单信息

#### add_dish
添加菜品

**参数**:
- `order_id`: 订单ID
- `dish_id`: 菜品ID
- `dish_name`: 菜品名称
- `price`: 价格
- `quantity`: 数量
- `special_instructions`: 特殊要求（可选）

**返回**: 添加结果

#### recommend_dishes
推荐菜品

**参数**:
- `store_id`: 门店ID
- `customer_id`: 客户ID（可选）
- `party_size`: 用餐人数（可选）

**返回**: 推荐菜品列表

### 结账管理

#### calculate_bill
计算账单

**参数**:
- `order_id`: 订单ID
- `member_id`: 会员ID（可选）
- `coupon_codes`: 优惠券码列表（可选）

**返回**: 账单详情

#### process_payment
处理支付

**参数**:
- `order_id`: 订单ID
- `payment_method`: 支付方式
- `amount`: 支付金额
- `payment_details`: 支付详情（可选）

**返回**: 支付结果

## 集成示例

### 与API适配器集成

```python
from packages.api_adapters.pinzhi.src import PinzhiAdapter
from packages.api_adapters.aoqiwei.src import AoqiweiAdapter
from packages.agents.order.src import OrderAgent

# 初始化适配器
pinzhi = PinzhiAdapter(pinzhi_config)
aoqiwei = AoqiweiAdapter(aoqiwei_config)
agent = OrderAgent(agent_config)

# 获取菜品信息
dishes = await pinzhi.get_dishes()

# 创建订单并添加菜品
order = await agent.create_order(store_id="STORE001", table_id="T001")
for dish in selected_dishes:
    await agent.add_dish(
        order_id=order["order"]["order_id"],
        dish_id=dish["dishesId"],
        dish_name=dish["dishesName"],
        price=dish["dishPrice"],
        quantity=1
    )

# 使用奥琦韦处理会员支付
bill = await agent.calculate_bill(
    order_id=order["order"]["order_id"],
    member_id="M001"
)

# 调用奥琦韦交易接口
trade_result = await aoqiwei.trade_submit(
    card_no="M001",
    store_id="STORE001",
    cashier="收银员001",
    amount=int(bill["bill"]["final_amount"] * 100),  # 转换为分
    pay_type=3,
    trade_no=order["order"]["order_id"]
)
```

## 测试

```bash
# 运行单元测试
cd packages/agents/order
pytest tests/ -v

# 运行特定测试
pytest tests/test_agent.py::TestWorkflow::test_complete_order_workflow -v

# 查看测试覆盖率
pytest tests/ -v --cov=src --cov-report=html
```

## 未来优化

### 短期
- [ ] 集成真实的桌台管理系统
- [ ] 实现订单状态机验证
- [ ] 添加订单修改功能
- [ ] 支持拼桌功能

### 中期
- [ ] 基于机器学习的菜品推荐
- [ ] 动态定价策略
- [ ] 预定冲突智能解决
- [ ] 多语言菜单支持

### 长期
- [ ] AR菜单展示
- [ ] 语音点单
- [ ] 个性化用餐建议
- [ ] 跨门店预定

## 许可证

MIT License
