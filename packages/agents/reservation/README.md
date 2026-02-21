# 预定宴会Agent - Reservation & Banquet Agent

智能预定和宴会管理系统，提供完整的预定流程、座位分配、通知服务和数据分析功能。

## 核心功能 Core Features

### 1. 预定管理 Reservation Management
- 创建预定（普通/VIP/包间/宴会）
- 确认预定和座位分配
- 取消预定和退款处理
- 预定状态跟踪
- 冲突检测和可用性检查

### 2. 宴会管理 Banquet Management
- 婚宴、生日宴、公司宴请等多种类型
- 自定义菜单和价格
- 场地和桌数管理
- 定金和总金额计算

### 3. 座位分配 Seating Allocation
- 智能座位优化算法
- 桌型推荐（小桌/中桌/大桌/圆桌/宴会桌）
- 座位利用率分析
- 动态座位调整

### 4. 通知服务 Notification Services
- 预定确认通知
- 提醒通知（提前2小时）
- 取消通知
- 修改通知
- 多渠道支持（短信/微信/电话）

### 5. 统计分析 Analytics & Reporting
- 预定确认率、取消率、未到店率
- 平均人数分析
- 高峰时段识别
- 预定收入统计

## 安装 Installation

```bash
cd packages/agents/reservation
pnpm install
```

## 使用示例 Usage Examples

### 创建普通预定

```python
from src.agent import ReservationAgent, ReservationType

agent = ReservationAgent(store_id="STORE001")

reservation = await agent.create_reservation(
    customer_id="CUST001",
    customer_name="张三",
    customer_phone="13800138000",
    reservation_date="2026-02-20",
    reservation_time="18:00",
    party_size=4,
    reservation_type=ReservationType.REGULAR,
    special_requests="需要靠窗位置"
)

print(f"预定ID: {reservation['reservation_id']}")
print(f"桌型: {reservation['table_type']}")
print(f"预估消费: {reservation['estimated_amount'] / 100}元")
```

### 创建宴会

```python
from src.agent import BanquetType

menu_items = [
    {"name": "佛跳墙", "price": 28800},
    {"name": "清蒸石斑鱼", "price": 18800},
    {"name": "红烧鲍鱼", "price": 38800}
]

banquet = await agent.create_banquet(
    customer_id="CUST010",
    customer_name="新郎新娘",
    customer_phone="13800138000",
    banquet_type=BanquetType.WEDDING,
    banquet_date="2026-03-15",
    banquet_time="18:00",
    guest_count=200,
    table_count=20,
    venue="宴会厅A",
    menu_items=menu_items,
    price_per_table=288000,
    special_requirements="需要舞台和音响"
)

print(f"宴会ID: {banquet['banquet_id']}")
print(f"总金额: {banquet['total_amount'] / 100}元")
print(f"定金: {banquet['deposit_amount'] / 100}元")
```

### 确认预定

```python
reservation = await agent.confirm_reservation("RES_20260220180000_0001")

print(f"状态: {reservation['status']}")
print(f"桌号: {reservation['table_number']}")
print(f"确认时间: {reservation['confirmed_at']}")
```

### 取消预定

```python
reservation = await agent.cancel_reservation(
    "RES_20260220180000_0001",
    reason="客户临时有事"
)

print(f"状态: {reservation['status']}")
```

### 分配座位

```python
plan = await agent.allocate_seating(
    date="2026-02-20",
    time_slot="18:00-20:00"
)

print(f"方案ID: {plan['plan_id']}")
print(f"利用率: {plan['utilization_rate'] * 100}%")
print(f"分配桌位: {len(plan['tables'])}个")

for table in plan['tables']:
    print(f"  桌号{table['table_number']}: {table['customer_name']} ({table['party_size']}人)")
```

### 发送提醒

```python
notification = await agent.send_reminder("RES_20260220180000_0001")

print(f"通知ID: {notification['notification_id']}")
print(f"渠道: {notification['channel']}")
print(f"内容: {notification['content']}")
```

### 分析预定数据

```python
from datetime import datetime, timedelta

start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
end_date = datetime.now().date().isoformat()

analytics = await agent.analyze_reservations(
    start_date=start_date,
    end_date=end_date
)

print(f"总预定数: {analytics['total_reservations']}")
print(f"确认率: {analytics['confirmation_rate'] * 100}%")
print(f"取消率: {analytics['cancellation_rate'] * 100}%")
print(f"未到店率: {analytics['no_show_rate'] * 100}%")
print(f"平均人数: {analytics['average_party_size']}人")
print(f"高峰时段: {', '.join(analytics['peak_hours'])}")
print(f"预定收入: {analytics['revenue_from_reservations'] / 100}元")
```

## 数据结构 Data Structures

### Reservation 预定

```python
{
    "reservation_id": str,        # 预定ID
    "customer_id": str,           # 客户ID
    "customer_name": str,         # 客户姓名
    "customer_phone": str,        # 客户电话
    "store_id": str,              # 门店ID
    "reservation_type": str,      # 预定类型
    "reservation_date": str,      # 预定日期
    "reservation_time": str,      # 预定时间
    "party_size": int,            # 人数
    "table_type": str,            # 桌型
    "table_number": str,          # 桌号
    "special_requests": str,      # 特殊要求
    "status": str,                # 状态
    "deposit_amount": int,        # 定金(分)
    "estimated_amount": int,      # 预估消费(分)
    "created_at": str,            # 创建时间
    "updated_at": str,            # 更新时间
    "confirmed_at": str,          # 确认时间
    "seated_at": str,             # 入座时间
    "completed_at": str           # 完成时间
}
```

### Banquet 宴会

```python
{
    "banquet_id": str,            # 宴会ID
    "reservation_id": str,        # 关联预定ID
    "customer_id": str,           # 客户ID
    "customer_name": str,         # 客户姓名
    "customer_phone": str,        # 客户电话
    "store_id": str,              # 门店ID
    "banquet_type": str,          # 宴会类型
    "banquet_date": str,          # 宴会日期
    "banquet_time": str,          # 宴会时间
    "guest_count": int,           # 宾客人数
    "table_count": int,           # 桌数
    "venue": str,                 # 场地
    "menu_id": str,               # 菜单ID
    "menu_items": list,           # 菜单项
    "price_per_table": int,       # 每桌价格(分)
    "total_amount": int,          # 总金额(分)
    "deposit_amount": int,        # 定金(分)
    "special_requirements": str,  # 特殊要求
    "status": str,                # 状态
    "created_at": str,            # 创建时间
    "updated_at": str             # 更新时间
}
```

## 枚举类型 Enums

### ReservationType 预定类型
- `REGULAR` - 普通预定
- `BANQUET` - 宴会
- `PRIVATE_ROOM` - 包间
- `VIP` - VIP预定

### ReservationStatus 预定状态
- `PENDING` - 待确认
- `CONFIRMED` - 已确认
- `SEATED` - 已入座
- `COMPLETED` - 已完成
- `CANCELLED` - 已取消
- `NO_SHOW` - 未到店

### BanquetType 宴会类型
- `WEDDING` - 婚宴
- `BIRTHDAY` - 生日宴
- `CORPORATE` - 公司宴请
- `FAMILY` - 家庭聚会
- `CONFERENCE` - 会议餐
- `OTHER` - 其他

### TableType 桌型
- `SMALL` - 小桌(2-4人)
- `MEDIUM` - 中桌(4-6人)
- `LARGE` - 大桌(6-10人)
- `ROUND` - 圆桌(10-12人)
- `BANQUET` - 宴会桌(12+人)

### NotificationType 通知类型
- `CONFIRMATION` - 确认通知
- `REMINDER` - 提醒通知
- `CANCELLATION` - 取消通知
- `MODIFICATION` - 修改通知

## 配置参数 Configuration

```python
config = {
    "advance_booking_days": 30,    # 提前预定天数
    "min_party_size": 1,           # 最小人数
    "max_party_size": 50,          # 最大人数
    "deposit_rate": 0.3,           # 定金比例
    "cancellation_hours": 24,      # 取消提前时间(小时)
    "reminder_hours": 2,           # 提醒提前时间(小时)
}

agent = ReservationAgent(store_id="STORE001", config=config)
```

## 测试 Testing

运行所有测试：

```bash
pytest tests/
```

运行特定测试：

```bash
pytest tests/test_agent.py::TestReservationCreation
pytest tests/test_agent.py::TestBanquetManagement
pytest tests/test_agent.py::TestSeatingAllocation
```

查看测试覆盖率：

```bash
pytest --cov=src --cov-report=html tests/
```

## 工作流程 Workflow

```
1. 客户创建预定
   ↓
2. 系统验证参数和可用性
   ↓
3. 计算预估消费和定金
   ↓
4. 创建预定记录（PENDING状态）
   ↓
5. 发送确认通知
   ↓
6. 客户支付定金
   ↓
7. 确认预定（CONFIRMED状态）
   ↓
8. 分配座位和桌号
   ↓
9. 发送提醒通知（提前2小时）
   ↓
10. 客户到店（SEATED状态）
    ↓
11. 用餐完成（COMPLETED状态）
```

## 集成 Integration

### 与订单Agent集成

```python
from src.agent import ReservationAgent

# 创建预定Agent并关联订单Agent
reservation_agent = ReservationAgent(
    store_id="STORE001",
    order_agent=order_agent
)

# 预定完成后自动创建订单
reservation = await reservation_agent.create_reservation(...)
if reservation_agent.order_agent:
    order = await reservation_agent.order_agent.create_order_from_reservation(
        reservation_id=reservation["reservation_id"]
    )
```

## 性能优化 Performance

- 使用异步I/O处理并发预定
- 缓存可用桌位信息
- 批量发送通知
- 定期清理过期预定数据

## 安全性 Security

- 验证客户身份
- 加密敏感信息（电话号码）
- 防止重复预定
- 限流保护

## 监控指标 Metrics

- 预定创建成功率
- 平均响应时间
- 座位利用率
- 通知发送成功率
- 预定确认率
- 取消率和未到店率

## 许可证 License

MIT

## 作者 Author

智链餐厅OS团队
