# 智能决策Agent (Intelligent Decision Agent)

提供数据分析洞察、绩效指标分析、业务建议生成、趋势预测、资源优化等功能的AI Agent。

## 核心功能 (Core Features)

### 1. KPI指标分析 (KPI Analysis)
- 监控多维度KPI指标(营收/成本/效率/质量/客户)
- 计算达成率和趋势
- 自动评估指标状态(正常/风险/偏离)
- 对比当前值、目标值、上期值

### 2. 业务洞察生成 (Business Insights)
- 从数据中自动发现业务洞察
- 识别异常模式和机会
- 评估影响程度(低/中/高)
- 提供数据支撑

### 3. 业务建议生成 (Business Recommendations)
- 基于洞察生成可行建议
- 分类决策类型(运营/战术/战略)
- 评估优先级(低/中/高/关键)
- 提供行动项和预期影响
- 估算成本和ROI

### 4. 趋势预测 (Trend Forecasting)
- 预测未来业务趋势
- 支持多种指标预测
- 计算预测置信度
- 识别趋势方向(上升/下降/稳定/波动)

### 5. 资源优化 (Resource Optimization)
- 优化人员配置
- 优化库存配置
- 优化成本结构
- 评估实施难度和预期收益

### 6. 战略规划 (Strategic Planning)
- 创建中长期战略规划
- 设定目标和关键举措
- 定义成功指标
- 识别潜在风险

### 7. 综合决策报告 (Comprehensive Reports)
- KPI状态概览
- 关键洞察汇总
- 优先建议列表
- 整体健康分数

## 工作流程 (Workflow)

```
1. analyze_kpis()
   ↓
2. generate_insights()
   ↓
3. generate_recommendations()
   ↓
4. forecast_trends()
   ↓
5. optimize_resources()
   ↓
6. create_strategic_plan()
```

## 使用示例 (Usage Examples)

### 基础使用

```python
from src.agent import DecisionAgent, DecisionType

# 初始化Agent(可集成其他Agent)
agent = DecisionAgent(
    store_id="STORE001",
    schedule_agent=schedule_agent,
    order_agent=order_agent,
    inventory_agent=inventory_agent,
    service_agent=service_agent,
    training_agent=training_agent,
    kpi_targets={
        "revenue_growth": 0.15,
        "cost_ratio": 0.35,
        "customer_satisfaction": 0.90,
        "staff_efficiency": 0.85,
        "inventory_turnover": 12,
    }
)
```

### 分析KPI指标

```python
# 分析所有KPI
kpis = await agent.analyze_kpis()

for kpi in kpis:
    print(f"{kpi['metric_name']}: {kpi['current_value']:.2f}{kpi['unit']}")
    print(f"  目标: {kpi['target_value']:.2f}{kpi['unit']}")
    print(f"  达成率: {kpi['achievement_rate']:.1%}")
    print(f"  趋势: {kpi['trend']}")
    print(f"  状态: {kpi['status']}")

# 按日期范围分析
kpis = await agent.analyze_kpis(
    start_date="2026-01-01T00:00:00",
    end_date="2026-01-31T23:59:59"
)
```

### 生成业务洞察

```python
# 生成洞察
insights = await agent.generate_insights()

for insight in insights:
    print(f"[{insight['impact_level']}] {insight['title']}")
    print(f"  {insight['description']}")
    print(f"  数据点: {insight['data_points']}")
```

### 生成业务建议

```python
# 生成所有建议
recommendations = await agent.generate_recommendations()

for rec in recommendations:
    print(f"[{rec['priority']}] {rec['title']}")
    print(f"  类型: {rec['decision_type']}")
    print(f"  理由: {rec['rationale']}")
    print(f"  预期影响: {rec['expected_impact']}")
    print(f"  行动项:")
    for action in rec['action_items']:
        print(f"    - {action}")
    if rec.get('estimated_cost'):
        print(f"  预估成本: {rec['estimated_cost']/100}元")
    if rec.get('estimated_roi'):
        print(f"  预估ROI: {rec['estimated_roi']}")

# 按决策类型筛选
operational_recs = await agent.generate_recommendations(
    decision_type=DecisionType.OPERATIONAL
)
```

### 预测趋势

```python
# 预测营收趋势
forecast = await agent.forecast_trends(
    metric_name="营收",
    forecast_days=30,
    historical_days=90
)

print(f"当前值: {forecast['current_value']:.2f}")
print(f"预测周期: {forecast['forecast_period']}")
print(f"趋势方向: {forecast['trend_direction']}")
print(f"置信度: {forecast['confidence_level']:.1%}")
print(f"预测值: {forecast['forecasted_values'][:7]}")  # 前7天
```

### 优化资源配置

```python
# 优化人员配置
staff_opt = await agent.optimize_resources("staff")

print(f"当前配置: {staff_opt['current_allocation']}")
print(f"建议配置: {staff_opt['recommended_allocation']}")
print(f"预期节省: {staff_opt['expected_savings']/100}元/月")
print(f"预期改进: {staff_opt['expected_improvement']}")
print(f"实施难度: {staff_opt['implementation_difficulty']}")

# 优化库存配置
inventory_opt = await agent.optimize_resources("inventory")

# 优化成本配置
cost_opt = await agent.optimize_resources("cost")
```

### 创建战略规划

```python
# 创建1年战略规划
plan = await agent.create_strategic_plan(time_horizon="1年")

print(f"规划标题: {plan['title']}")
print(f"\n目标:")
for obj in plan['objectives']:
    print(f"  - {obj}")

print(f"\n关键举措:")
for initiative in plan['key_initiatives']:
    print(f"  - {initiative}")

print(f"\n成功指标:")
for metric in plan['success_metrics']:
    print(f"  - {metric}")

print(f"\n风险:")
for risk in plan['risks']:
    print(f"  - {risk}")
```

### 获取综合决策报告

```python
# 获取完整的决策报告
report = await agent.get_decision_report()

print(f"整体健康分数: {report['overall_health_score']}/100")
print(f"需要行动的事项: {report['action_required']}个")

print(f"\nKPI概况:")
print(f"  总数: {report['kpi_summary']['total_kpis']}")
print(f"  正常率: {report['kpi_summary']['on_track_rate']:.1%}")
print(f"  状态分布: {report['kpi_summary']['status_distribution']}")

print(f"\n洞察概况:")
print(f"  总数: {report['insights_summary']['total_insights']}")
print(f"  高影响: {report['insights_summary']['high_impact']}")

print(f"\n建议概况:")
print(f"  总数: {report['recommendations_summary']['total_recommendations']}")
print(f"  优先级分布: {report['recommendations_summary']['priority_distribution']}")
```

## 数据结构 (Data Structures)

### KPIMetric (KPI指标)
```python
{
    "metric_id": "KPI_REVENUE_001",
    "metric_name": "总营收",
    "category": "revenue",
    "current_value": 1000000.0,
    "target_value": 1150000.0,
    "previous_value": 950000.0,
    "unit": "元",
    "achievement_rate": 0.87,
    "trend": "increasing",
    "status": "at_risk"
}
```

### BusinessInsight (业务洞察)
```python
{
    "insight_id": "INSIGHT_SERVICE_20260214120000",
    "title": "午餐时段投诉率偏高",
    "description": "数据显示午餐时段(11:00-14:00)的客户投诉率比其他时段高30%",
    "category": "service",
    "impact_level": "high",
    "data_points": [
        {"label": "午餐投诉率", "value": 0.08},
        {"label": "其他时段投诉率", "value": 0.05}
    ],
    "discovered_at": "2026-02-14T12:00:00"
}
```

### Recommendation (业务建议)
```python
{
    "recommendation_id": "REC_INSIGHT_001",
    "title": "增加午餐时段人手",
    "description": "在午餐高峰时段增加2-3名服务人员",
    "decision_type": "operational",
    "priority": "high",
    "rationale": "午餐时段投诉率高30%,主要因等待时间过长",
    "expected_impact": "预计可降低投诉率30%,提升客户满意度5%",
    "action_items": [
        "调整排班计划,增加午餐时段人手",
        "培训员工提高服务效率",
        "优化点餐和上菜流程"
    ],
    "estimated_cost": 500000,
    "estimated_roi": 2.5,
    "created_at": "2026-02-14T12:00:00"
}
```

### TrendForecast (趋势预测)
```python
{
    "forecast_id": "FORECAST_营收_20260214120000",
    "metric_name": "营收",
    "current_value": 1000000.0,
    "forecasted_values": [1020000, 1040000, 1060000, ...],
    "forecast_period": "30天",
    "confidence_level": 0.85,
    "trend_direction": "increasing",
    "forecasted_at": "2026-02-14T12:00:00"
}
```

## 决策类型 (Decision Types)

- **OPERATIONAL**: 运营决策(日常运营优化)
- **TACTICAL**: 战术决策(中期策略调整)
- **STRATEGIC**: 战略决策(长期战略规划)

## 建议优先级 (Recommendation Priority)

- **LOW**: 低(可选优化)
- **MEDIUM**: 中(建议实施)
- **HIGH**: 高(应尽快实施)
- **CRITICAL**: 关键(必须立即实施)

## 趋势方向 (Trend Direction)

- **INCREASING**: 上升(增长>15%)
- **DECREASING**: 下降(下降>15%)
- **STABLE**: 稳定(变化<5%)
- **VOLATILE**: 波动(变化10-15%)

## 指标分类 (Metric Categories)

- **REVENUE**: 营收类(总营收、日均营收等)
- **COST**: 成本类(成本率、成本总额等)
- **EFFICIENCY**: 效率类(人效、坪效等)
- **QUALITY**: 质量类(准确率、合格率等)
- **CUSTOMER**: 客户类(满意度、复购率等)

## KPI状态 (KPI Status)

- **on_track**: 正常(达成率≥95%)
- **at_risk**: 风险(达成率85-95%)
- **off_track**: 偏离(达成率<85%)

## 配置参数 (Configuration)

```python
kpi_targets = {
    "revenue_growth": 0.15,        # 营收增长15%
    "cost_ratio": 0.35,            # 成本率35%
    "customer_satisfaction": 0.90,  # 客户满意度90%
    "staff_efficiency": 0.85,      # 员工效率85%
    "inventory_turnover": 12,      # 库存周转率12次/年
}
```

## 健康分数计算 (Health Score Calculation)

健康分数 = 所有KPI平均达成率 × 100

- 90-100分: 优秀
- 80-89分: 良好
- 70-79分: 一般
- 60-69分: 需改进
- <60分: 差

## 测试 (Testing)

```bash
# 运行所有测试
pytest tests/test_agent.py -v

# 运行特定测试
pytest tests/test_agent.py::test_analyze_kpis -v

# 查看测试覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 依赖 (Dependencies)

- Python 3.8+
- structlog: 结构化日志
- pytest: 单元测试
- pytest-asyncio: 异步测试支持
- 其他Agent: 可选集成其他5个Agent获取数据

## 集成其他Agent (Integration)

```python
from packages.agents.schedule.src.agent import ScheduleAgent
from packages.agents.order.src.agent import OrderAgent
from packages.agents.inventory.src.agent import InventoryAgent
from packages.agents.service.src.agent import ServiceAgent
from packages.agents.training.src.agent import TrainingAgent

# 创建各Agent实例
schedule_agent = ScheduleAgent(store_id="STORE001")
order_agent = OrderAgent(store_id="STORE001")
inventory_agent = InventoryAgent(store_id="STORE001")
service_agent = ServiceAgent(store_id="STORE001")
training_agent = TrainingAgent(store_id="STORE001")

# 创建决策Agent并集成
decision_agent = DecisionAgent(
    store_id="STORE001",
    schedule_agent=schedule_agent,
    order_agent=order_agent,
    inventory_agent=inventory_agent,
    service_agent=service_agent,
    training_agent=training_agent
)

# 决策Agent可以访问其他Agent的数据进行综合分析
report = await decision_agent.get_decision_report()
```

## 最佳实践 (Best Practices)

1. **定期监控**: 每日查看KPI状态和健康分数
2. **及时响应**: 对关键和高优先级建议立即采取行动
3. **数据驱动**: 基于数据洞察而非直觉做决策
4. **持续优化**: 定期评估优化效果并调整策略
5. **战略对齐**: 确保运营决策与战略目标一致
6. **风险管理**: 识别并主动应对潜在风险
7. **跨部门协作**: 整合各Agent数据进行全局优化

## 许可证 (License)

MIT
