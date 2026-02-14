# 智能排班Agent

## 概述

智能排班Agent是智链OS的核心Agent之一，基于客流预测和员工技能自动生成优化的排班表，帮助餐饮门店提高人力资源利用效率。

## 功能特性

### 1. 客流预测分析
- 基于历史数据预测未来客流
- 识别高峰时段
- 提供预测置信度

### 2. 人力需求计算
- 根据客流量计算各岗位人力需求
- 考虑不同班次的需求差异
- 动态调整需求配置

### 3. 智能排班生成
- 基于员工技能匹配岗位
- 考虑员工偏好和可用性
- 自动生成完整排班表

### 4. 排班优化
- 检查排班合理性
- 识别人力不足或过剩
- 提供优化建议

### 5. 劳动法规遵守
- 限制单班次工作时长
- 限制每周工作时长
- 确保休息时间

## 安装

```bash
# 在项目根目录
pnpm install
```

## 使用示例

### 基本使用

```python
from packages.agents.schedule.src import ScheduleAgent

# 初始化Agent
config = {
    "min_shift_hours": 4,      # 最小班次时长
    "max_shift_hours": 8,      # 最大班次时长
    "max_weekly_hours": 40,    # 每周最大工作时长
}
agent = ScheduleAgent(config)

# 准备员工数据
employees = [
    {
        "id": "E001",
        "name": "张三",
        "skills": ["waiter", "cashier"],
        "preferences": {"preferred_shifts": ["morning"]}
    },
    {
        "id": "E002",
        "name": "李四",
        "skills": ["chef"],
        "preferences": {"preferred_shifts": ["afternoon"]}
    },
    # ... 更多员工
]

# 生成排班
result = await agent.run(
    store_id="STORE001",
    date="2024-01-15",
    employees=employees
)

if result["success"]:
    print(f"排班成功，共{len(result['schedule'])}个班次")
    print(f"客流预测: {result['traffic_prediction']}")
    print(f"人力需求: {result['requirements']}")
    print(f"优化建议: {result['suggestions']}")
else:
    print(f"排班失败: {result['error']}")
```

### 查看排班结果

```python
# 排班结果示例
{
    "success": True,
    "store_id": "STORE001",
    "date": "2024-01-15",
    "schedule": [
        {
            "employee_id": "E001",
            "employee_name": "张三",
            "skill": "waiter",
            "shift": "morning",
            "date": "2024-01-15",
            "start_time": "06:00",
            "end_time": "14:00"
        },
        {
            "employee_id": "E002",
            "employee_name": "李四",
            "skill": "chef",
            "shift": "afternoon",
            "date": "2024-01-15",
            "start_time": "14:00",
            "end_time": "22:00"
        },
        # ... 更多排班记录
    ],
    "traffic_prediction": {
        "predicted_customers": {
            "morning": 50,
            "afternoon": 80,
            "evening": 120
        },
        "peak_hours": ["12:00-13:00", "18:00-20:00"],
        "confidence": 0.85
    },
    "requirements": {
        "morning": {"waiter": 5, "chef": 2, "cashier": 1},
        "afternoon": {"waiter": 8, "chef": 3, "cashier": 1},
        "evening": {"waiter": 12, "chef": 4, "cashier": 1}
    },
    "suggestions": [
        "evening班次缺少2名waiter",
        "建议增加晚班人手"
    ]
}
```

### 调整排班

```python
# 调整排班
adjustments = [
    {
        "employee_id": "E001",
        "new_shift": "afternoon",
        "reason": "员工请求调班"
    }
]

result = await agent.adjust_schedule(
    schedule_id="SCH001",
    adjustments=adjustments
)
```

### 查询排班

```python
# 查询指定时间范围的排班
result = await agent.get_schedule(
    store_id="STORE001",
    start_date="2024-01-15",
    end_date="2024-01-21"
)
```

## 数据模型

### 员工数据结构

```python
{
    "id": str,              # 员工ID
    "name": str,            # 员工姓名
    "skills": List[str],    # 技能列表 ["waiter", "cashier", "chef", "manager", "cleaner"]
    "preferences": {        # 偏好设置
        "preferred_shifts": List[str],  # 偏好班次
        "unavailable_dates": List[str]  # 不可用日期
    }
}
```

### 班次类型

| 班次 | 时间 | 说明 |
|------|------|------|
| morning | 06:00-14:00 | 早班 |
| afternoon | 14:00-22:00 | 中班 |
| evening | 18:00-02:00 | 晚班 |
| full_day | 09:00-21:00 | 全天班 |

### 员工技能

| 技能 | 说明 |
|------|------|
| cashier | 收银 |
| waiter | 服务员 |
| chef | 厨师 |
| manager | 店长 |
| cleaner | 清洁 |

## 工作流程

```
1. 分析客流 (analyze_traffic)
   ↓
   - 获取历史客流数据
   - 预测未来客流
   - 识别高峰时段

2. 计算需求 (calculate_requirements)
   ↓
   - 根据客流计算人力需求
   - 按班次和技能分类
   - 考虑业务规则

3. 生成排班 (generate_schedule)
   ↓
   - 匹配员工技能
   - 考虑员工偏好
   - 分配班次

4. 优化排班 (optimize_schedule)
   ↓
   - 检查需求覆盖
   - 检查工作时长
   - 生成优化建议
```

## 算法说明

### 人力需求计算

```python
# 简化算法（实际可以更复杂）
waiters_needed = max(2, predicted_customers // 10)
chefs_needed = max(1, predicted_customers // 30)
cashiers_needed = 1
```

### 技能匹配

1. 按班次遍历人力需求
2. 对每个技能需求，查找具备该技能的可用员工
3. 优先分配偏好该班次的员工
4. 确保每个员工不被重复分配到同一班次

### 优化检查

1. **需求覆盖检查**：实际分配人数 vs 需求人数
2. **工作时长检查**：单班次时长、每周总时长
3. **技能匹配检查**：员工技能 vs 岗位要求
4. **偏好匹配检查**：实际班次 vs 员工偏好

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| min_shift_hours | int | 4 | 最小班次时长（小时） |
| max_shift_hours | int | 8 | 最大班次时长（小时） |
| max_weekly_hours | int | 40 | 每周最大工作时长（小时） |
| customer_per_waiter | int | 10 | 每个服务员服务的客人数 |
| customer_per_chef | int | 30 | 每个厨师服务的客人数 |

## 测试

```bash
# 运行单元测试
cd packages/agents/schedule
pytest tests/ -v

# 运行特定测试
pytest tests/test_agent.py::TestScheduleAgent::test_run_complete_workflow -v

# 查看测试覆盖率
pytest tests/ -v --cov=src --cov-report=html
```

## 集成示例

### 与API适配器集成

```python
from packages.api_adapters.pinzhi.src import PinzhiAdapter
from packages.agents.schedule.src import ScheduleAgent

# 初始化适配器
pinzhi = PinzhiAdapter(config)

# 获取员工数据
employees_data = await pinzhi.get_employees()

# 转换为Agent所需格式
employees = [
    {
        "id": emp["epId"],
        "name": emp["epName"],
        "skills": ["waiter"],  # 需要根据岗位映射
    }
    for emp in employees_data
]

# 生成排班
agent = ScheduleAgent(config)
result = await agent.run(
    store_id="STORE001",
    date="2024-01-15",
    employees=employees
)
```

### 与企业微信集成

```python
# 推送排班通知到企业微信
if result["success"]:
    for shift in result["schedule"]:
        message = f"""
        【排班通知】
        员工：{shift['employee_name']}
        日期：{shift['date']}
        班次：{shift['shift']}
        时间：{shift['start_time']} - {shift['end_time']}
        岗位：{shift['skill']}
        """
        # 发送企业微信消息
        await wechat_service.send_message(
            user_id=shift['employee_id'],
            message=message
        )
```

## 未来优化方向

### 短期（1-2周）
- [ ] 集成真实的客流预测模型
- [ ] 支持员工请假和调班
- [ ] 添加排班冲突检测
- [ ] 实现排班历史记录

### 中期（1-2月）
- [ ] 使用机器学习优化排班算法
- [ ] 支持多门店协同排班
- [ ] 添加成本优化目标
- [ ] 实现自动化排班建议

### 长期（3-6月）
- [ ] 基于强化学习的动态排班
- [ ] 预测性排班调整
- [ ] 员工满意度优化
- [ ] 跨区域人力调配

## 注意事项

1. **数据准确性**：确保员工技能数据准确
2. **劳动法规**：遵守当地劳动法规定
3. **员工沟通**：排班前与员工充分沟通
4. **灵活调整**：保留人工调整的空间
5. **持续优化**：根据实际效果持续优化算法

## 许可证

MIT License
