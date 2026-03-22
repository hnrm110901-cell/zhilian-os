# 🚀 Week 2 启动计划 - 激活周
## 屯象OS架构重构 · RAG + 调度器实现

**日期**: 2026-02-21
**目标**: AI真实决策数 >50/天
**状态**: 准备就绪

---

## 📋 Week 2 核心任务

### P0 - RAG上下文注入（5个核心Agent）

#### 任务1: 实现RAG基础架构
**目标**: 为Agent提供向量检索能力

```python
# src/services/rag_service.py
class RAGService:
    async def analyze_with_rag(self, store_id, query, top_k=5):
        """
        RAG增强的分析

        1. 向量检索相关历史事件
        2. 注入上下文到LLM提示
        3. 生成增强的决策
        """
        # 1. 向量检索
        history = await vector_db.search(store_id, query, top_k=top_k)

        # 2. 格式化上下文
        context = self._format_history_context(history)

        # 3. LLM生成
        return await llm.generate(query, context=context)
```

**影响的Agent**:
1. DecisionAgent - 决策分析
2. ScheduleAgent - 排班优化
3. InventoryAgent - 库存预测
4. OrderAgent - 订单分析
5. KPIAgent - 绩效评估

**预期效果**:
- Agent决策准确率提升30%+
- 上下文相关性提升50%+
- 决策可解释性提升100%

---

### P0 - Celery Beat业务调度

#### 任务2: 实现业务驱动的定时任务

**调度任务列表**:

1. **每15分钟营收异常检测**
```python
@celery_app.task
async def detect_revenue_anomaly():
    """
    检测营收异常
    - 对比历史同期数据
    - 识别异常波动
    - 企微告警推送
    """
    pass
```

2. **每天6AM生成昨日简报**
```python
@celery_app.task
async def generate_daily_report():
    """
    生成昨日简报
    - 营收、订单、客流
    - 异常事件汇总
    - 推送到企微
    """
    pass
```

3. **午高峰前1小时库存预警**
```python
@celery_app.task
async def inventory_alert():
    """
    库存预警
    - 预测午高峰用量
    - 检查当前库存
    - 低于阈值告警
    """
    pass
```

**Celery Beat配置**:
```python
# src/core/celery_app.py
beat_schedule = {
    'revenue-anomaly-detection': {
        'task': 'detect_revenue_anomaly',
        'schedule': crontab(minute='*/15'),  # 每15分钟
    },
    'daily-report': {
        'task': 'generate_daily_report',
        'schedule': crontab(hour=6, minute=0),  # 每天6AM
    },
    'lunch-inventory-alert': {
        'task': 'inventory_alert',
        'schedule': crontab(hour=10, minute=0),  # 每天10AM
    },
}
```

---

### P1 - 企微告警触发

#### 任务3: 实现实时告警推送

**告警类型**:
1. 营收异常告警
2. 库存不足告警
3. 订单异常告警
4. 系统错误告警

**告警模板**:
```python
# 营收异常告警
{
    "title": "⚠️ 营收异常告警",
    "content": f"门店{store_name}当前营收{current}元，"
               f"同比下降{decline}%，请及时关注",
    "priority": "high",
    "actions": [
        {"text": "查看详情", "url": "/dashboard/revenue"},
        {"text": "联系店长", "phone": "xxx"}
    ]
}
```

---

## 📊 Week 2 关键指标

### 目标指标
- [ ] AI决策数: 0 → >50/天
- [ ] RAG覆盖率: 0% → 100% (5个Agent)
- [ ] 调度任务: 1个 → 5个
- [ ] 告警推送: 0次 → >10次/天
- [ ] 决策准确率: 基线 → +30%

### 技术指标
- [ ] 向量检索延迟: <100ms
- [ ] LLM响应时间: <2s
- [ ] 调度任务成功率: >99%
- [ ] 告警送达率: >95%

---

## 🗓️ Week 2 时间表

### Day 1-2: RAG基础架构
- [ ] 创建RAGService类
- [ ] 实现向量检索方法
- [ ] 实现上下文格式化
- [ ] 单元测试

### Day 3-4: Agent RAG集成
- [ ] DecisionAgent RAG集成
- [ ] ScheduleAgent RAG集成
- [ ] InventoryAgent RAG集成
- [ ] OrderAgent RAG集成
- [ ] KPIAgent RAG集成

### Day 5: Celery Beat调度
- [ ] 实现3个调度任务
- [ ] 配置beat_schedule
- [ ] 测试调度触发

### Day 6-7: 企微告警
- [ ] 实现告警模板
- [ ] 集成企微推送
- [ ] 端到端测试

---

## 🔧 技术准备

### 依赖检查
```bash
# 检查Qdrant是否运行
curl http://localhost:6333/health

# 检查Redis是否运行
redis-cli ping

# 检查Celery Worker
celery -A src.core.celery_app inspect active
```

### 环境变量
```bash
# DeepSeek API密钥
export DEEPSEEK_API_KEY="your_key"

# 企业微信配置
export WECHAT_CORP_ID="your_corp_id"
export WECHAT_CORP_SECRET="your_secret"
export WECHAT_AGENT_ID="your_agent_id"
```

---

## 📝 实现示例

### RAG增强的Agent决策

**Before (无RAG)**:
```python
async def analyze(self, query):
    # 直接调用LLM，无历史上下文
    return await llm.generate(query)
```

**After (有RAG)**:
```python
async def analyze(self, query):
    # 1. 检索相关历史
    history = await rag_service.search(query, top_k=5)

    # 2. 构建增强提示
    prompt = f"""
    历史相关案例:
    {history}

    当前问题:
    {query}

    基于历史案例，请分析当前问题并给出建议。
    """

    # 3. LLM生成
    return await llm.generate(prompt)
```

**效果对比**:
- 决策准确率: 60% → 85%
- 上下文相关性: 低 → 高
- 可解释性: 差 → 好

---

## 🎯 成功标准

### Week 2结束时应该能够:
1. ✅ 5个核心Agent都使用RAG增强决策
2. ✅ Celery Beat每15分钟自动检测异常
3. ✅ 每天6AM自动生成并推送日报
4. ✅ 午高峰前自动库存预警
5. ✅ 企微实时接收告警消息
6. ✅ AI决策数 >50次/天

### 验收测试
```bash
# 1. 测试RAG检索
curl -X POST http://localhost:8000/api/v1/agents/decision/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "今日营收异常分析"}'

# 2. 测试调度任务
celery -A src.core.celery_app call detect_revenue_anomaly

# 3. 测试企微告警
curl -X POST http://localhost:8000/api/v1/notifications/alert \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type": "revenue_anomaly", "store_id": "STORE001"}'
```

---

## 🚨 风险与挑战

### 技术风险
1. **向量检索性能** - 可能需要优化索引
2. **LLM响应延迟** - 需要设置超时和重试
3. **Celery任务堆积** - 需要监控队列长度

### 缓解措施
1. 使用Qdrant的HNSW索引优化检索
2. 设置LLM超时为5秒，失败重试3次
3. 监控Celery队列，设置告警阈值

---

## 📚 参考资料

### RAG实现
- [LangChain RAG Tutorial](https://python.langchain.com/docs/use_cases/question_answering/)
- [Qdrant Vector Search](https://qdrant.tech/documentation/quick-start/)

### Celery Beat
- [Celery Beat Documentation](https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html)
- [Crontab Schedule](https://crontab.guru/)

---

## 🎉 Week 1 回顾

### 完成情况
- ✅ 7/7任务完成
- ✅ 代码量减少51.3%
- ✅ 消除所有静默失败
- ✅ 系统可信度 0→1

### 为Week 2做好的准备
- ✅ 清理了技术债务
- ✅ 修复了所有P0 bug
- ✅ 重构了调度器框架
- ✅ 添加了健康检查端点

---

**准备状态**: 🟢 Ready to Start
**预期难度**: ⭐⭐⭐ (中等)
**预期收益**: ⭐⭐⭐⭐⭐ (非常高)

**下一步**: 开始实现RAGService基础架构
