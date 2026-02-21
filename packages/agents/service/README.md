# 智能服务Agent (Intelligent Service Agent)

提供客户反馈管理、服务质量监控、投诉处理、服务改进建议等功能的AI Agent。

## 核心功能 (Core Features)

### 1. 客户反馈管理 (Customer Feedback Management)
- 收集多渠道客户反馈(App/微信/电话/现场)
- 自动分类反馈类型(表扬/建议/投诉/咨询)
- 情感分析和关键词提取
- 支持按日期范围和类型筛选

### 2. 服务质量监控 (Service Quality Monitoring)
- 实时监控服务质量指标
- 计算满意度、投诉率、响应时间、解决率
- 分类统计和趋势分析
- 自动检查质量阈值并预警

### 3. 投诉处理 (Complaint Handling)
- 智能优先级评估(低/中/高/紧急)
- 自动生成解决方案建议
- 智能补偿方案推荐
- 自动分配处理人
- 全流程状态跟踪

### 4. 员工表现追踪 (Staff Performance Tracking)
- 追踪员工服务表现
- 计算服务得分(0-100)
- 统计表扬和投诉数量
- 识别改进领域
- 排名和对比分析

### 5. 服务改进建议 (Service Improvement Recommendations)
- 基于数据分析生成改进建议
- 识别根本原因
- 评估优先级和预期影响
- 提供具体行动方案

### 6. 综合报告 (Comprehensive Reports)
- 服务质量综合报告
- 员工表现排行榜
- 紧急改进事项
- 投诉统计摘要

## 工作流程 (Workflow)

```
1. collect_feedback()
   ↓
2. analyze_feedback()
   ↓
3. handle_complaint()
   ↓
4. monitor_service_quality()
   ↓
5. track_staff_performance()
   ↓
6. generate_improvements()
```

## 使用示例 (Usage Examples)

### 基础使用

```python
from src.agent import ServiceAgent, FeedbackType

# 初始化Agent
agent = ServiceAgent(
    store_id="STORE001",
    aoqiwei_adapter=aoqiwei_adapter,  # 可选
    quality_thresholds={
        "min_satisfaction_rate": 0.85,
        "max_complaint_rate": 0.05,
        "max_response_time": 30,
        "min_resolution_rate": 0.90,
    }
)

# 收集反馈
feedbacks = await agent.collect_feedback()
print(f"总反馈数: {len(feedbacks)}")

# 收集投诉
complaints = await agent.collect_feedback(feedback_type=FeedbackType.COMPLAINT)
```

### 分析反馈

```python
# 分析单条反馈
feedback = feedbacks[0]
analysis = await agent.analyze_feedback(feedback)

print(f"情感: {analysis['sentiment']}")
print(f"关键词: {analysis['keywords']}")
print(f"分类: {analysis['category']}")
print(f"优先级: {analysis['priority']}")
print(f"需要处理: {analysis['requires_action']}")
```

### 处理投诉

```python
# 处理投诉
complaint = await agent.handle_complaint(
    feedback=feedback,
    assigned_to="MANAGER_001"  # 可选,不指定则自动分配
)

print(f"投诉ID: {complaint['complaint_id']}")
print(f"优先级: {complaint['priority']}")
print(f"处理人: {complaint['assigned_to']}")
print(f"解决方案: {complaint['resolution']}")
print(f"补偿方案: {complaint['compensation']}")
```

### 监控服务质量

```python
# 监控服务质量
metrics = await agent.monitor_service_quality()

print(f"平均评分: {metrics['average_rating']}")
print(f"满意度: {metrics['satisfaction_rate']:.2%}")
print(f"投诉率: {metrics['complaint_rate']:.2%}")
print(f"响应时间: {metrics['response_time_avg']}分钟")
print(f"解决率: {metrics['resolution_rate']:.2%}")
print(f"趋势: {metrics['trend']}")
```

### 追踪员工表现

```python
# 追踪所有员工
performances = await agent.track_staff_performance()

for perf in performances[:5]:  # 前5名
    print(f"{perf['staff_name']}: 服务得分{perf['service_score']}")
    print(f"  表扬: {perf['praise_count']}, 投诉: {perf['complaint_count']}")
    print(f"  改进领域: {perf['improvement_areas']}")

# 追踪特定员工
staff_perf = await agent.track_staff_performance(staff_id="STAFF001")
```

### 生成改进建议

```python
# 生成改进建议
improvements = await agent.generate_improvements()

for improvement in improvements:
    print(f"[{improvement['priority']}] {improvement['category']}")
    print(f"问题: {improvement['issue']}")
    print(f"原因: {improvement['root_cause']}")
    print(f"建议: {improvement['recommendation']}")
    print(f"预期影响: {improvement['estimated_impact']}")
```

### 获取综合报告

```python
# 获取完整的服务报告
report = await agent.get_service_report()

print(f"满意度: {report['quality_metrics']['satisfaction_rate']:.2%}")
print(f"员工总数: {len(report['staff_performances'])}")
print(f"改进建议: {len(report['improvements'])}条")
print(f"紧急改进: {len(report['urgent_improvements'])}条")
print(f"投诉总数: {report['complaints_summary']['total']}")
```

## 数据结构 (Data Structures)

### CustomerFeedback (客户反馈)
```python
{
    "feedback_id": "FB20260214001",
    "customer_id": "CUST1234",
    "customer_name": "张三",
    "store_id": "STORE001",
    "feedback_type": "complaint",
    "category": "food_quality",
    "rating": 2,
    "content": "菜品质量差,味道不好",
    "staff_id": "STAFF001",
    "order_id": "ORD12345",
    "created_at": "2026-02-14T12:00:00",
    "source": "app"
}
```

### Complaint (投诉)
```python
{
    "complaint_id": "COMP_FB20260214001",
    "feedback_id": "FB20260214001",
    "customer_id": "CUST1234",
    "store_id": "STORE001",
    "category": "food_quality",
    "priority": "high",
    "status": "in_progress",
    "description": "菜品质量差",
    "staff_id": "STAFF001",
    "assigned_to": "CHEF_MANAGER_001",
    "resolution": "1. 向客户道歉 2. 重新制作菜品...",
    "compensation": {
        "type": "coupon",
        "amount_fen": 3000,
        "description": "30元代金券"
    },
    "created_at": "2026-02-14T12:00:00",
    "updated_at": "2026-02-14T12:05:00",
    "resolved_at": None
}
```

### StaffPerformance (员工表现)
```python
{
    "staff_id": "STAFF001",
    "staff_name": "员工001",
    "store_id": "STORE001",
    "period_start": "2026-01-15T00:00:00",
    "period_end": "2026-02-14T00:00:00",
    "total_feedbacks": 45,
    "praise_count": 30,
    "complaint_count": 5,
    "average_rating": 4.2,
    "service_score": 85.6,
    "improvement_areas": ["waiting_time", "service_attitude"]
}
```

### ServiceQualityMetrics (服务质量指标)
```python
{
    "store_id": "STORE001",
    "period_start": "2026-01-15T00:00:00",
    "period_end": "2026-02-14T00:00:00",
    "total_feedbacks": 150,
    "average_rating": 4.1,
    "satisfaction_rate": 0.87,
    "complaint_rate": 0.04,
    "response_time_avg": 25.0,
    "resolution_rate": 0.92,
    "category_breakdown": {
        "food_quality": 45,
        "service_attitude": 38,
        "environment": 25,
        "waiting_time": 22,
        "price": 20
    },
    "trend": "improving"
}
```

## 反馈类型 (Feedback Types)

- **PRAISE**: 表扬
- **SUGGESTION**: 建议
- **COMPLAINT**: 投诉
- **INQUIRY**: 咨询

## 投诉优先级 (Complaint Priority)

- **LOW**: 低(评分3-4,一般问题)
- **MEDIUM**: 中(评分3,需要关注)
- **HIGH**: 高(评分2,需要优先处理)
- **URGENT**: 紧急(评分1或包含紧急关键词)

## 投诉状态 (Complaint Status)

- **PENDING**: 待处理
- **IN_PROGRESS**: 处理中
- **RESOLVED**: 已解决
- **CLOSED**: 已关闭

## 服务分类 (Service Categories)

- **FOOD_QUALITY**: 菜品质量
- **SERVICE_ATTITUDE**: 服务态度
- **ENVIRONMENT**: 环境卫生
- **WAITING_TIME**: 等待时间
- **PRICE**: 价格
- **OTHER**: 其他

## 配置参数 (Configuration)

```python
quality_thresholds = {
    "min_satisfaction_rate": 0.85,  # 最低满意度85%
    "max_complaint_rate": 0.05,     # 最高投诉率5%
    "max_response_time": 30,        # 最长响应时间30分钟
    "min_resolution_rate": 0.90,    # 最低解决率90%
}
```

## 自动分配规则 (Auto-Assignment Rules)

- **紧急投诉** → 店长(MANAGER)
- **菜品质量** → 厨师长(CHEF_MANAGER)
- **服务态度** → 服务经理(SERVICE_MANAGER)
- **其他** → 客服专员(CUSTOMER_SERVICE)

## 补偿方案 (Compensation Suggestions)

| 优先级 | 分类 | 补偿方案 |
|--------|------|----------|
| 紧急 | 菜品质量 | 全额退款 + 100元代金券 |
| 紧急 | 其他 | 50元代金券 + 诚挚道歉 |
| 高 | 所有 | 30元代金券 |
| 中 | 所有 | 10元代金券或折扣 |
| 低 | 所有 | 无需补偿 |

## 测试 (Testing)

```bash
# 运行所有测试
pytest tests/test_agent.py -v

# 运行特定测试
pytest tests/test_agent.py::test_collect_feedback_all -v

# 查看测试覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 依赖 (Dependencies)

- Python 3.8+
- structlog: 结构化日志
- pytest: 单元测试
- pytest-asyncio: 异步测试支持

## 集成 (Integration)

### 与奥琦韦会员系统集成

```python
from packages.api_adapters.aoqiwei.src.adapter import AoqiweiAdapter

# 创建奥琦韦适配器
aoqiwei_adapter = AoqiweiAdapter(
    app_id="your_app_id",
    app_secret="your_app_secret",
    base_url="https://api.aoqiwei.com"
)

# 传入Agent
agent = ServiceAgent(
    store_id="STORE001",
    aoqiwei_adapter=aoqiwei_adapter
)

# Agent会自动从奥琦韦系统获取客户反馈数据
feedbacks = await agent.collect_feedback()
```

## 最佳实践 (Best Practices)

1. **及时响应**: 紧急投诉应在1小时内响应,高优先级投诉2小时内响应
2. **主动跟进**: 对所有投诉进行主动跟进,确保客户满意
3. **数据分析**: 定期分析服务质量趋势,及时发现问题
4. **员工培训**: 根据表现数据针对性培训员工
5. **持续改进**: 实施改进建议并跟踪效果
6. **客户关怀**: 对投诉客户提供额外关怀,挽回客户信任

## 许可证 (License)

MIT
