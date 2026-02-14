# 智能库存预警Agent (Intelligent Inventory Alert Agent)

提供实时库存监控、消耗预测、智能补货提醒、保质期管理等功能的AI Agent。

## 核心功能 (Core Features)

### 1. 实时库存监控 (Real-time Inventory Monitoring)
- 监控所有物料的库存状态
- 自动分析库存水平(充足/偏低/严重不足/缺货)
- 支持按分类筛选
- 计算库存总价值

### 2. 消耗预测 (Consumption Prediction)
支持多种预测方法:
- **移动平均** (Moving Average): 使用最近7天的平均消耗
- **加权平均** (Weighted Average): 近期数据权重更高
- **线性回归** (Linear Regression): 基于趋势预测
- **季节性预测** (Seasonal): 考虑周期性波动(按星期几)

### 3. 智能补货提醒 (Intelligent Restock Alerts)
- 多级预警系统(信息/警告/紧急/严重)
- 自动计算建议补货量
- 预测缺货日期
- 考虑采购周期和消耗趋势

### 4. 保质期管理 (Expiration Management)
- 监控即将过期的物料
- 分级预警(7天/3天/已过期)
- 提供处理建议(促销/内部消耗/下架)

### 5. 库存优化 (Stock Level Optimization)
- 基于历史数据优化安全库存
- 计算最优最低/最高库存
- 考虑消耗波动和采购周期
- 提供95%服务水平保障

## 工作流程 (Workflow)

```
1. monitor_inventory()
   ↓
2. predict_consumption()
   ↓
3. generate_restock_alerts()
   ↓
4. check_expiration()
   ↓
5. optimize_stock_levels()
```

## 使用示例 (Usage Examples)

### 基础使用

```python
from src.agent import InventoryAgent, PredictionMethod

# 初始化Agent
agent = InventoryAgent(
    store_id="STORE001",
    pinzhi_adapter=pinzhi_adapter,  # 可选
    alert_thresholds={
        "low_stock_ratio": 0.3,
        "critical_stock_ratio": 0.1,
        "expiring_soon_days": 7,
        "expiring_urgent_days": 3,
    }
)

# 监控库存
inventory = await agent.monitor_inventory()
print(f"总物料数: {len(inventory)}")

# 监控特定分类
meat_inventory = await agent.monitor_inventory(category="meat")
```

### 消耗预测

```python
# 使用加权平均预测
prediction = await agent.predict_consumption(
    item_id="INV001",
    history_days=30,
    forecast_days=7,
    method=PredictionMethod.WEIGHTED_AVERAGE
)

print(f"预测7天消耗: {prediction['predicted_consumption']}")
print(f"置信度: {prediction['confidence']}")
print(f"预计{prediction['days_until_stockout']}天后缺货")
```

### 生成补货提醒

```python
# 生成所有补货提醒
alerts = await agent.generate_restock_alerts()

for alert in alerts:
    print(f"{alert['item_name']}: {alert['reason']}")
    print(f"建议补货: {alert['recommended_quantity']}")
    print(f"预警级别: {alert['alert_level']}")
```

### 检查保质期

```python
# 检查即将过期的物料
expiration_alerts = await agent.check_expiration()

for alert in expiration_alerts:
    print(f"{alert['item_name']}: {alert['days_until_expiration']}天后过期")
    print(f"建议: {alert['recommended_action']}")
```

### 优化库存水平

```python
# 基于90天历史数据优化
optimization = await agent.optimize_stock_levels(
    item_id="INV001",
    analysis_days=90
)

print("当前库存水平:")
print(optimization['current_levels'])

print("推荐库存水平:")
print(optimization['recommended_levels'])
```

### 获取综合报告

```python
# 获取完整的库存报告
report = await agent.get_inventory_report()

print(f"总物料数: {report['summary']['total_items']}")
print(f"库存总价值: {report['summary']['total_value_fen']/100}元")
print(f"补货提醒: {report['summary']['restock_alerts_count']}条")
print(f"保质期预警: {report['summary']['expiration_alerts_count']}条")
```

## 数据结构 (Data Structures)

### InventoryItem (库存项目)
```python
{
    "item_id": "INV001",
    "item_name": "鸡胸肉",
    "category": "meat",
    "unit": "kg",
    "current_stock": 15.5,
    "safe_stock": 50.0,
    "min_stock": 20.0,
    "max_stock": 100.0,
    "unit_cost": 2500,  # 分
    "supplier_id": "SUP001",
    "lead_time_days": 2,
    "expiration_date": "2026-02-19T00:00:00",
    "location": "冷藏区A1"
}
```

### RestockAlert (补货提醒)
```python
{
    "alert_id": "restock_INV001_20260214120000",
    "item_id": "INV001",
    "item_name": "鸡胸肉",
    "current_stock": 15.5,
    "recommended_quantity": 84.5,
    "alert_level": "warning",
    "reason": "库存偏低 Low stock",
    "estimated_stockout_date": "2026-02-20T00:00:00",
    "created_at": "2026-02-14T12:00:00"
}
```

### ExpirationAlert (保质期预警)
```python
{
    "alert_id": "expiration_INV001_20260214120000",
    "item_id": "INV001",
    "item_name": "鸡胸肉",
    "current_stock": 15.5,
    "expiration_date": "2026-02-19T00:00:00",
    "days_until_expiration": 5,
    "alert_level": "warning",
    "recommended_action": "安排促销活动 Plan promotion",
    "created_at": "2026-02-14T12:00:00"
}
```

## 预警级别 (Alert Levels)

- **INFO**: 信息提示
- **WARNING**: 警告(库存偏低或7天内过期)
- **URGENT**: 紧急(库存严重不足或3天内过期)
- **CRITICAL**: 严重(缺货或已过期)

## 库存状态 (Inventory Status)

- **SUFFICIENT**: 充足
- **LOW**: 偏低(低于安全库存的30%)
- **CRITICAL**: 严重不足(低于最低库存)
- **OUT_OF_STOCK**: 缺货
- **EXPIRING_SOON**: 即将过期

## 配置参数 (Configuration)

```python
alert_thresholds = {
    "low_stock_ratio": 0.3,        # 低库存比例
    "critical_stock_ratio": 0.1,   # 严重不足比例
    "expiring_soon_days": 7,       # 即将过期天数
    "expiring_urgent_days": 3,     # 紧急过期天数
}
```

## 测试 (Testing)

```bash
# 运行所有测试
pytest tests/test_agent.py -v

# 运行特定测试
pytest tests/test_agent.py::test_monitor_inventory_all_categories -v

# 查看测试覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 依赖 (Dependencies)

- Python 3.8+
- structlog: 结构化日志
- pytest: 单元测试
- pytest-asyncio: 异步测试支持

## 集成 (Integration)

### 与品智收银系统集成

```python
from packages.api_adapters.pinzhi.src.adapter import PinzhiAdapter

# 创建品智适配器
pinzhi_adapter = PinzhiAdapter(
    app_id="your_app_id",
    app_secret="your_app_secret",
    base_url="https://api.pinzhi.com"
)

# 传入Agent
agent = InventoryAgent(
    store_id="STORE001",
    pinzhi_adapter=pinzhi_adapter
)

# Agent会自动从品智系统获取实时库存数据
inventory = await agent.monitor_inventory()
```

## 最佳实践 (Best Practices)

1. **定期监控**: 建议每小时执行一次库存监控
2. **及时响应**: 对CRITICAL级别的预警立即处理
3. **数据积累**: 至少积累30天历史数据才能获得准确预测
4. **季节调整**: 对于季节性商品,使用SEASONAL预测方法
5. **定期优化**: 每季度重新优化一次库存水平

## 许可证 (License)

MIT
