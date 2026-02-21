# Agent集成改造指南
## 将现有Agent接入Human-in-the-loop审批流

**目标**: 改造现有的5个Agent，使其决策需要经过店长审批
**优先级**: P0
**预计工时**: 2-3天

---

## 📋 改造清单

需要改造的Agent:
1. ✅ DecisionAgent - 决策支持Agent
2. ✅ ScheduleAgent - 智能排班Agent
3. ✅ InventoryAgent - 库存管理Agent
4. ✅ OrderAgent - 订单管理Agent
5. ✅ KPIAgent - 绩效管理Agent

---

## 🔧 改造模式

### 原有流程
```python
async def analyze_revenue_anomaly(self, store_id: str, db: Session):
    # 1. 分析数据
    analysis = await self._analyze_with_rag(...)

    # 2. 直接执行决策
    result = await self._execute_action(analysis)

    # 3. 返回结果
    return result
```

### 新流程（Human-in-the-loop）
```python
async def analyze_revenue_anomaly(self, store_id: str, db: Session):
    # 1. 分析数据
    analysis = await self._analyze_with_rag(...)

    # 2. 创建审批请求（新增）
    from ..services.approval_service import approval_service
    from ..models.decision_log import DecisionType

    decision_log = await approval_service.create_approval_request(
        decision_type=DecisionType.REVENUE_ANOMALY,
        agent_type="DecisionAgent",
        agent_method="analyze_revenue_anomaly",
        store_id=store_id,
        ai_suggestion=analysis["suggestion"],
        ai_confidence=analysis["confidence"],
        ai_reasoning=analysis["reasoning"],
        ai_alternatives=analysis.get("alternatives", []),
        context_data=analysis.get("context", {}),
        rag_context=analysis.get("rag_context", {}),
        db=db
    )

    # 3. 返回决策ID，等待审批
    return {
        "decision_id": decision_log.id,
        "status": "pending_approval",
        "ai_suggestion": analysis,
        "message": "决策建议已发送给店长审批"
    }
```

---

## 📝 详细改造步骤

### Step 1: 导入必要的模块

在每个Agent文件顶部添加:
```python
from ..services.approval_service import approval_service
from ..models.decision_log import DecisionType
```

### Step 2: 修改决策方法

对于每个需要审批的方法，按以下模式修改:

#### 2.1 识别需要审批的方法

**DecisionAgent**:
- `analyze_revenue_anomaly()` → DecisionType.REVENUE_ANOMALY
- `generate_business_insights()` → DecisionType.COST_OPTIMIZATION

**ScheduleAgent**:
- `optimize_schedule()` → DecisionType.SCHEDULE_OPTIMIZATION

**InventoryAgent**:
- `check_inventory_alerts()` → DecisionType.INVENTORY_ALERT
- `generate_purchase_plan()` → DecisionType.PURCHASE_SUGGESTION

**OrderAgent**:
- `analyze_order_anomaly()` → DecisionType.ORDER_ANOMALY
- `optimize_menu_pricing()` → DecisionType.MENU_PRICING

**KPIAgent**:
- `generate_improvement_plan()` → DecisionType.KPI_IMPROVEMENT

#### 2.2 修改方法实现

```python
async def [method_name](self, store_id: str, db: Session, **kwargs):
    """
    [原有文档字符串]

    注意: 此方法现在返回审批请求，需要店长批准后才会执行。
    """
    try:
        # 1. 原有的分析逻辑保持不变
        analysis_result = await self._analyze_with_rag(
            query=...,
            store_id=store_id,
            context=...
        )

        # 2. 构建AI建议
        ai_suggestion = {
            "action": "...",  # 建议的操作
            "parameters": {...},  # 操作参数
            "expected_impact": {...},  # 预期影响
            "risk_level": "low/medium/high"  # 风险等级
        }

        # 3. 构建备选方案（可选）
        ai_alternatives = [
            {
                "action": "...",
                "parameters": {...},
                "pros": ["优点1", "优点2"],
                "cons": ["缺点1", "缺点2"]
            },
            # ... 更多备选方案
        ]

        # 4. 创建审批请求
        decision_log = await approval_service.create_approval_request(
            decision_type=DecisionType.[TYPE],  # 对应的决策类型
            agent_type=self.__class__.__name__,  # Agent类名
            agent_method="[method_name]",  # 方法名
            store_id=store_id,
            ai_suggestion=ai_suggestion,
            ai_confidence=analysis_result.get("confidence", 0.8),
            ai_reasoning=analysis_result.get("reasoning", ""),
            ai_alternatives=ai_alternatives,
            context_data={
                "input_params": kwargs,
                "analysis_data": analysis_result
            },
            rag_context=analysis_result.get("rag_context", {}),
            db=db
        )

        # 5. 返回审批请求信息
        return {
            "decision_id": decision_log.id,
            "status": "pending_approval",
            "ai_suggestion": ai_suggestion,
            "ai_confidence": analysis_result.get("confidence", 0.8),
            "ai_reasoning": analysis_result.get("reasoning", ""),
            "ai_alternatives": ai_alternatives,
            "message": "决策建议已发送给店长审批，请等待审批结果"
        }

    except Exception as e:
        logger.error(
            f"{self.__class__.__name__}.{method_name}_failed",
            error=str(e),
            store_id=store_id
        )
        raise
```

### Step 3: 添加决策执行方法

为每个Agent添加一个新的执行方法，用于在审批通过后执行决策:

```python
async def execute_approved_decision(
    self,
    decision_log: DecisionLog,
    db: Session
) -> Dict[str, Any]:
    """
    执行已批准的决策

    Args:
        decision_log: 决策日志对象
        db: 数据库会话

    Returns:
        Dict: 执行结果
    """
    try:
        # 获取决策内容（可能是AI建议或店长修改后的决策）
        decision = decision_log.manager_decision or decision_log.ai_suggestion

        # 根据决策类型执行相应操作
        if decision_log.decision_type == DecisionType.REVENUE_ANOMALY:
            result = await self._execute_revenue_action(decision, db)
        elif decision_log.decision_type == DecisionType.INVENTORY_ALERT:
            result = await self._execute_inventory_action(decision, db)
        # ... 其他决策类型

        # 记录执行结果
        await approval_service.record_decision_outcome(
            decision_id=decision_log.id,
            outcome=DecisionOutcome.SUCCESS if result["success"] else DecisionOutcome.FAILURE,
            actual_result=result,
            expected_result=decision.get("expected_impact", {}),
            business_impact=result.get("business_impact", {}),
            db=db
        )

        return result

    except Exception as e:
        logger.error(
            f"execute_approved_decision_failed",
            decision_id=decision_log.id,
            error=str(e)
        )

        # 记录失败结果
        await approval_service.record_decision_outcome(
            decision_id=decision_log.id,
            outcome=DecisionOutcome.FAILURE,
            actual_result={"error": str(e)},
            expected_result={},
            db=db
        )

        raise
```

---

## 🔄 ApprovalService执行逻辑更新

需要更新`ApprovalService._execute_decision()`方法，使其能够调用相应Agent的执行方法:

```python
async def _execute_decision(self, decision_log: DecisionLog, db: Session):
    """执行决策"""
    try:
        # 根据Agent类型获取Agent实例
        from ..services.agent_service import agent_service

        agent = agent_service.get_agent(decision_log.agent_type)
        if not agent:
            raise ValueError(f"Agent not found: {decision_log.agent_type}")

        # 调用Agent的执行方法
        result = await agent.execute_approved_decision(decision_log, db)

        # 更新决策状态
        decision_log.decision_status = DecisionStatus.EXECUTED
        decision_log.executed_at = datetime.utcnow()

        db.commit()

        logger.info(
            "decision_executed",
            decision_id=decision_log.id,
            decision_type=decision_log.decision_type.value,
            result=result
        )

        return result

    except Exception as e:
        logger.error("execute_decision_failed", error=str(e))
        raise
```

---

## 📊 改造优先级

### 高优先级（立即改造）
1. **DecisionAgent.analyze_revenue_anomaly()** - 营收异常是最关键的决策
2. **InventoryAgent.check_inventory_alerts()** - 库存预警直接影响运营
3. **InventoryAgent.generate_purchase_plan()** - 采购决策涉及资金

### 中优先级（本周完成）
4. **ScheduleAgent.optimize_schedule()** - 排班影响人力成本
5. **OrderAgent.analyze_order_anomaly()** - 订单异常需要及时处理

### 低优先级（下周完成）
6. **OrderAgent.optimize_menu_pricing()** - 定价调整可以延后
7. **KPIAgent.generate_improvement_plan()** - 改进计划不紧急
8. **DecisionAgent.generate_business_insights()** - 洞察生成可以延后

---

## 🧪 测试清单

改造完成后，需要测试以下场景:

### 1. 基本流程测试
- [ ] Agent生成决策建议
- [ ] 创建审批请求成功
- [ ] 企微通知发送成功
- [ ] 店长批准决策
- [ ] 决策执行成功
- [ ] 结果记录成功

### 2. 异常流程测试
- [ ] 店长拒绝决策
- [ ] 店长修改决策
- [ ] 决策执行失败
- [ ] 网络异常处理

### 3. 性能测试
- [ ] 审批请求响应时间 < 1s
- [ ] 企微通知送达时间 < 5s
- [ ] 决策执行时间合理

### 4. 数据完整性测试
- [ ] 决策日志完整记录
- [ ] 审批链正确记录
- [ ] 信任度评分正确计算

---

## 📝 示例代码

### DecisionAgent改造示例

```python
# src/agents/decision_agent.py

from ..services.approval_service import approval_service
from ..models.decision_log import DecisionType, DecisionLog, DecisionOutcome
import structlog

logger = structlog.get_logger()

class DecisionAgent:
    """决策支持Agent"""

    async def analyze_revenue_anomaly(
        self,
        store_id: str,
        date: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        营收异常分析（需要审批）

        Args:
            store_id: 门店ID
            date: 日期
            db: 数据库会话

        Returns:
            Dict: 审批请求信息
        """
        try:
            # 1. 获取营收数据
            revenue_data = await self._get_revenue_data(store_id, date, db)

            # 2. RAG增强分析
            analysis = await self.rag_service.analyze_with_rag(
                query=f"分析{store_id}门店{date}的营收异常",
                store_id=store_id,
                context={
                    "revenue_data": revenue_data,
                    "date": date
                },
                top_k=5
            )

            # 3. 构建AI建议
            ai_suggestion = {
                "action": "adjust_pricing",  # 调整定价
                "parameters": {
                    "dishes": ["宫保鸡丁", "鱼香肉丝"],
                    "adjustment": -0.10,  # 降价10%
                    "duration_days": 7  # 持续7天
                },
                "expected_impact": {
                    "revenue_increase": 0.15,  # 预期营收增长15%
                    "customer_increase": 0.20  # 预期客流增长20%
                },
                "risk_level": "low"
            }

            # 4. 构建备选方案
            ai_alternatives = [
                {
                    "action": "marketing_campaign",
                    "parameters": {
                        "type": "coupon",
                        "discount": 0.20,
                        "budget": 5000
                    },
                    "pros": ["快速见效", "吸引新客"],
                    "cons": ["成本较高", "可能影响利润率"]
                },
                {
                    "action": "menu_optimization",
                    "parameters": {
                        "remove_dishes": ["低销量菜品"],
                        "add_dishes": ["季节性菜品"]
                    },
                    "pros": ["优化成本", "提升效率"],
                    "cons": ["需要时间", "可能流失老客户"]
                }
            ]

            # 5. 创建审批请求
            decision_log = await approval_service.create_approval_request(
                decision_type=DecisionType.REVENUE_ANOMALY,
                agent_type="DecisionAgent",
                agent_method="analyze_revenue_anomaly",
                store_id=store_id,
                ai_suggestion=ai_suggestion,
                ai_confidence=analysis.get("confidence", 0.85),
                ai_reasoning=analysis.get("reasoning", ""),
                ai_alternatives=ai_alternatives,
                context_data={
                    "date": date,
                    "revenue_data": revenue_data,
                    "analysis": analysis
                },
                rag_context=analysis.get("rag_context", {}),
                db=db
            )

            logger.info(
                "revenue_anomaly_analysis_created",
                decision_id=decision_log.id,
                store_id=store_id,
                date=date
            )

            # 6. 返回审批请求信息
            return {
                "decision_id": decision_log.id,
                "status": "pending_approval",
                "ai_suggestion": ai_suggestion,
                "ai_confidence": analysis.get("confidence", 0.85),
                "ai_reasoning": analysis.get("reasoning", ""),
                "ai_alternatives": ai_alternatives,
                "message": "营收异常分析完成，决策建议已发送给店长审批"
            }

        except Exception as e:
            logger.error(
                "analyze_revenue_anomaly_failed",
                error=str(e),
                store_id=store_id,
                date=date
            )
            raise

    async def execute_approved_decision(
        self,
        decision_log: DecisionLog,
        db: Session
    ) -> Dict[str, Any]:
        """
        执行已批准的决策

        Args:
            decision_log: 决策日志对象
            db: 数据库会话

        Returns:
            Dict: 执行结果
        """
        try:
            decision = decision_log.manager_decision or decision_log.ai_suggestion

            if decision_log.decision_type == DecisionType.REVENUE_ANOMALY:
                # 执行营收异常处理
                if decision["action"] == "adjust_pricing":
                    result = await self._adjust_pricing(
                        store_id=decision_log.store_id,
                        dishes=decision["parameters"]["dishes"],
                        adjustment=decision["parameters"]["adjustment"],
                        duration_days=decision["parameters"]["duration_days"],
                        db=db
                    )
                elif decision["action"] == "marketing_campaign":
                    result = await self._launch_marketing_campaign(
                        store_id=decision_log.store_id,
                        campaign_type=decision["parameters"]["type"],
                        discount=decision["parameters"]["discount"],
                        budget=decision["parameters"]["budget"],
                        db=db
                    )
                else:
                    raise ValueError(f"Unknown action: {decision['action']}")

                return result

            else:
                raise ValueError(f"Unknown decision type: {decision_log.decision_type}")

        except Exception as e:
            logger.error(
                "execute_approved_decision_failed",
                decision_id=decision_log.id,
                error=str(e)
            )
            raise

    async def _adjust_pricing(
        self,
        store_id: str,
        dishes: List[str],
        adjustment: float,
        duration_days: int,
        db: Session
    ) -> Dict[str, Any]:
        """执行定价调整"""
        # 实际的定价调整逻辑
        # ...
        return {
            "success": True,
            "dishes_adjusted": len(dishes),
            "adjustment": adjustment,
            "duration_days": duration_days,
            "business_impact": {
                "estimated_revenue_change": adjustment * 1000  # 示例
            }
        }
```

---

## 🎯 完成标准

Agent集成改造完成的标准:
1. ✅ 所有5个Agent的关键方法都已改造
2. ✅ 所有改造的方法都能创建审批请求
3. ✅ 所有Agent都实现了execute_approved_decision方法
4. ✅ ApprovalService能够正确调用Agent执行方法
5. ✅ 所有测试用例通过
6. ✅ 文档更新完成

---

## 📚 相关文档

- [Phase 1进度报告](./PHASE1_PROGRESS.md)
- [产品功能明细](./PRODUCT_FEATURES.md)
- [ApprovalService API文档](./src/api/approval.py)
- [DecisionLog模型文档](./src/models/decision_log.py)

---

**最后更新**: 2026-02-21
**状态**: 待实施
**预计完成**: Week 5

---

*本文档由 Claude Sonnet 4.5 自动生成*
*Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>*
