# 智能培训Agent (Intelligent Training Agent)

提供培训需求评估、培训计划生成、培训进度追踪、培训效果评估等功能的AI Agent。

## 核心功能 (Core Features)

### 1. 培训需求评估 (Training Needs Assessment)
- 基于员工表现识别培训需求
- 分析技能差距
- 自动推荐培训课程
- 优先级评估(低/中/高/紧急)

### 2. 培训计划生成 (Training Plan Generation)
- 自动生成个性化培训计划
- 智能课程安排和时间规划
- 考虑前置课程要求
- 控制培训时长和强度

### 3. 培训进度追踪 (Training Progress Tracking)
- 实时追踪培训进度
- 监控出勤和完成情况
- 自动更新培训状态
- 识别延期和未完成培训

### 4. 培训效果评估 (Training Effectiveness Evaluation)
- 计算完成率和通过率
- 统计平均分数
- 按课程分析效果
- 综合评级(优秀/良好/满意/需改进/差)

### 5. 技能差距分析 (Skill Gap Analysis)
- 对比当前技能与岗位要求
- 计算技能差距分数(0-100)
- 识别关键技能缺口
- 优先级排序

### 6. 证书管理 (Certification Management)
- 自动颁发培训证书
- 追踪证书有效期
- 识别即将过期证书
- 管理证书续期

### 7. 综合报告 (Comprehensive Reports)
- 培训需求统计
- 培训进度概览
- 培训效果分析
- 证书状态汇总

## 工作流程 (Workflow)

```
1. assess_training_needs()
   ↓
2. generate_training_plan()
   ↓
3. track_training_progress()
   ↓
4. evaluate_training_effectiveness()
   ↓
5. issue_certificate()
```

## 使用示例 (Usage Examples)

### 基础使用

```python
from src.agent import TrainingAgent, TrainingType, SkillLevel

# 初始化Agent
agent = TrainingAgent(
    store_id="STORE001",
    training_config={
        "min_passing_score": 70,
        "max_training_hours_per_month": 40,
        "certificate_validity_months": 12,
        "mandatory_training_types": [
            TrainingType.SAFETY,
            TrainingType.COMPLIANCE
        ]
    }
)
```

### 评估培训需求

```python
# 评估所有员工的培训需求
needs = await agent.assess_training_needs()

for need in needs[:5]:  # 前5个需求
    print(f"[{need['priority']}] {need['staff_name']}")
    print(f"  技能差距: {need['skill_gap']}")
    print(f"  当前水平: {need['current_level']} → 目标: {need['target_level']}")
    print(f"  推荐课程: {need['recommended_courses']}")

# 评估特定员工
staff_needs = await agent.assess_training_needs(staff_id="STAFF001")

# 按岗位评估
waiter_needs = await agent.assess_training_needs(position="服务员")
```

### 生成培训计划

```python
# 自动生成培训计划
plan = await agent.generate_training_plan(staff_id="STAFF001")

print(f"计划ID: {plan['plan_id']}")
print(f"课程数: {len(plan['courses'])}")
print(f"总时长: {plan['total_hours']}小时")
print(f"开始日期: {plan['start_date']}")
print(f"结束日期: {plan['end_date']}")
print(f"优先级: {plan['priority']}")

# 基于特定需求生成计划
needs = await agent.assess_training_needs(staff_id="STAFF001")
plan = await agent.generate_training_plan(
    staff_id="STAFF001",
    training_needs=needs,
    start_date="2026-03-01T00:00:00"
)
```

### 追踪培训进度

```python
# 追踪所有培训进度
records = await agent.track_training_progress()

for record in records:
    print(f"{record['staff_id']} - {record['course_id']}")
    print(f"  状态: {record['status']}")
    print(f"  出勤: {record['attendance_hours']}小时")
    if record.get('score'):
        print(f"  分数: {record['score']}")

# 追踪特定员工
staff_records = await agent.track_training_progress(staff_id="STAFF001")

# 追踪特定计划
plan_records = await agent.track_training_progress(plan_id="PLAN_001")
```

### 评估培训效果

```python
# 评估整体培训效果
evaluation = await agent.evaluate_training_effectiveness()

print(f"参与人数: {evaluation['total_participants']}")
print(f"完成率: {evaluation['completion_rate']:.2%}")
print(f"通过率: {evaluation['pass_rate']:.2%}")
print(f"平均分: {evaluation['average_score']}")
print(f"效果评级: {evaluation['effectiveness_rating']}")

# 评估特定课程
course_eval = await agent.evaluate_training_effectiveness(
    course_id="COURSE_SERVICE_001"
)

# 按时间段评估
period_eval = await agent.evaluate_training_effectiveness(
    start_date="2026-01-01T00:00:00",
    end_date="2026-01-31T23:59:59"
)
```

### 分析技能差距

```python
# 分析员工技能差距
gaps = await agent.analyze_skill_gaps(staff_id="STAFF001")

for gap in gaps:
    print(f"技能: {gap['skill_name']}")
    print(f"  当前: {gap['current_level']} → 要求: {gap['required_level']}")
    print(f"  差距分数: {gap['gap_score']}")
    print(f"  优先级: {gap['priority']}")
```

### 管理证书

```python
# 获取所有有效证书
certificates = await agent.manage_certificates()

for cert in certificates:
    print(f"{cert['staff_name']} - {cert['course_name']}")
    print(f"  颁发日期: {cert['issue_date']}")
    print(f"  过期日期: {cert['expiry_date']}")
    print(f"  状态: {cert['status']}")

# 获取特定员工的证书
staff_certs = await agent.manage_certificates(staff_id="STAFF001")

# 包含过期证书
all_certs = await agent.manage_certificates(include_expired=True)

# 颁发证书
certificate = await agent.issue_certificate(
    staff_id="STAFF001",
    course_id="COURSE_SERVICE_001",
    record_id="REC001"
)
```

### 获取综合报告

```python
# 获取完整的培训报告
report = await agent.get_training_report()

print(f"培训需求: {report['training_needs']['total']}个")
print(f"  紧急: {report['training_needs']['urgent']}个")
print(f"  高优先级: {report['training_needs']['high']}个")

print(f"\n培训进度:")
print(f"  总记录: {report['training_progress']['total_records']}")
print(f"  完成率: {report['training_progress']['completion_rate']:.2%}")

print(f"\n培训效果:")
print(f"  评级: {report['training_effectiveness']['effectiveness_rating']}")

print(f"\n证书:")
print(f"  总数: {report['certificates']['total']}")
print(f"  有效: {report['certificates']['valid']}")
print(f"  即将过期: {report['certificates']['expiring_soon']}")
```

## 数据结构 (Data Structures)

### TrainingNeed (培训需求)
```python
{
    "need_id": "NEED_STAFF001_服务礼仪_20260214120000",
    "staff_id": "STAFF001",
    "staff_name": "张三",
    "position": "服务员",
    "skill_gap": "服务礼仪",
    "current_level": "beginner",
    "target_level": "intermediate",
    "priority": "high",
    "recommended_courses": ["COURSE_SERVICE_001"],
    "reason": "技能差距分数: 33, 需要从beginner提升到intermediate",
    "identified_at": "2026-02-14T12:00:00"
}
```

### TrainingPlan (培训计划)
```python
{
    "plan_id": "PLAN_STAFF001_20260214120000",
    "staff_id": "STAFF001",
    "staff_name": "张三",
    "courses": ["COURSE_SERVICE_001", "COURSE_SAFETY_001"],
    "start_date": "2026-02-15T00:00:00",
    "end_date": "2026-02-22T00:00:00",
    "total_hours": 12.0,
    "priority": "high",
    "status": "not_started",
    "progress_percentage": 0.0,
    "created_at": "2026-02-14T12:00:00",
    "updated_at": "2026-02-14T12:00:00"
}
```

### TrainingRecord (培训记录)
```python
{
    "record_id": "REC0001",
    "staff_id": "STAFF001",
    "course_id": "COURSE_SERVICE_001",
    "plan_id": "PLAN_STAFF001_001",
    "start_date": "2026-02-15T00:00:00",
    "completion_date": "2026-02-20T00:00:00",
    "status": "completed",
    "attendance_hours": 8.0,
    "score": 85,
    "passed": true,
    "feedback": "培训效果良好",
    "created_at": "2026-02-15T00:00:00"
}
```

### SkillGap (技能差距)
```python
{
    "staff_id": "STAFF001",
    "staff_name": "张三",
    "position": "服务员",
    "skill_name": "服务礼仪",
    "current_level": "beginner",
    "required_level": "intermediate",
    "gap_score": 33,
    "priority": "high"
}
```

### Certificate (证书)
```python
{
    "certificate_id": "CERT_STAFF001_COURSE001_20260220120000",
    "staff_id": "STAFF001",
    "staff_name": "张三",
    "course_id": "COURSE_SERVICE_001",
    "course_name": "优质服务培训",
    "issue_date": "2026-02-20T12:00:00",
    "expiry_date": "2027-02-20T12:00:00",
    "certificate_url": "https://certificates.zhilian-os.com/STAFF001/COURSE001",
    "status": "valid"
}
```

## 培训类型 (Training Types)

- **ONBOARDING**: 入职培训
- **SKILL_UPGRADE**: 技能提升
- **COMPLIANCE**: 合规培训
- **SAFETY**: 安全培训
- **MANAGEMENT**: 管理培训
- **PRODUCT_KNOWLEDGE**: 产品知识
- **CUSTOMER_SERVICE**: 客户服务

## 培训状态 (Training Status)

- **NOT_STARTED**: 未开始
- **IN_PROGRESS**: 进行中
- **COMPLETED**: 已完成
- **EXPIRED**: 已过期
- **FAILED**: 未通过

## 技能水平 (Skill Levels)

- **BEGINNER**: 初级(0分)
- **INTERMEDIATE**: 中级(33分)
- **ADVANCED**: 高级(66分)
- **EXPERT**: 专家(100分)

## 培训优先级 (Training Priority)

- **LOW**: 低(差距<33分)
- **MEDIUM**: 中(差距33-66分)
- **HIGH**: 高(差距>66分或关键技能差距>30分)
- **URGENT**: 紧急(关键技能差距>50分)

## 效果评级 (Effectiveness Rating)

- **excellent**: 优秀(综合得分≥90)
- **good**: 良好(综合得分≥80)
- **satisfactory**: 满意(综合得分≥70)
- **needs_improvement**: 需改进(综合得分≥60)
- **poor**: 差(综合得分<60)

综合得分 = 完成率×30% + 通过率×40% + 平均分/100×30%

## 岗位技能要求 (Position Skill Requirements)

### 服务员
- 服务礼仪: 中级
- 客户沟通: 中级
- 菜品知识: 初级
- 食品安全: 初级

### 厨师
- 菜品制作: 高级
- 食品安全: 中级
- 厨房管理: 中级

### 收银员
- 收银操作: 中级
- 客户沟通: 初级
- 系统操作: 中级

### 店长
- 团队管理: 高级
- 运营管理: 高级
- 客户服务: 中级
- 财务管理: 中级

## 配置参数 (Configuration)

```python
training_config = {
    "min_passing_score": 70,              # 最低及格分数
    "max_training_hours_per_month": 40,   # 每月最大培训时长
    "certificate_validity_months": 12,    # 证书有效期(月)
    "mandatory_training_types": [         # 强制培训类型
        TrainingType.SAFETY,
        TrainingType.COMPLIANCE
    ]
}
```

## 测试 (Testing)

```bash
# 运行所有测试
pytest tests/test_agent.py -v

# 运行特定测试
pytest tests/test_agent.py::test_assess_training_needs_all_staff -v

# 查看测试覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 依赖 (Dependencies)

- Python 3.8+
- structlog: 结构化日志
- pytest: 单元测试
- pytest-asyncio: 异步测试支持

## 最佳实践 (Best Practices)

1. **定期评估**: 每季度评估一次员工培训需求
2. **优先处理**: 优先安排紧急和高优先级培训
3. **跟踪进度**: 每周检查培训进度,及时干预延期培训
4. **效果评估**: 培训结束后立即评估效果
5. **证书管理**: 提前30天提醒证书续期
6. **持续改进**: 根据评估结果优化培训内容和方式
7. **技能认证**: 关键岗位必须持证上岗

## 许可证 (License)

MIT
