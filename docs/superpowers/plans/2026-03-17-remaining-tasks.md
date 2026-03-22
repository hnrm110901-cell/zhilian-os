# 屯象OS 剩余任务实现计划（任务3-7）

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按顺序完成会员生命周期补全、19个Stub页面填充、知识OS层API/Service、Neo4j迁移规划、BettaFish迁移规划

**Architecture:** 后端用 FastAPI + SQLAlchemy async，前端 React + Z设计系统 + CSS Modules。每个任务独立可测试、独立可提交。

**Tech Stack:** Python 3.11+ / FastAPI / Celery / SQLAlchemy 2.0 / React 19 / TypeScript 5.9 / Ant Design 5 / Z组件

---

## Chunk 1: 任务3 — 会员生命周期补全

### Task 3.1: Celery 定时 RFM 重算任务

**Files:**
- Modify: `apps/api-gateway/src/core/celery_tasks.py` (在末尾添加新任务)
- Test: `apps/api-gateway/tests/test_cdp_rfm_celery.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cdp_rfm_celery.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def test_recalculate_rfm_daily_task_registered():
    """验证 celery 任务已注册"""
    from src.core.celery_tasks import app
    assert "recalculate_rfm_daily" in [t for t in app.tasks]

@patch("src.core.celery_tasks.cdp_rfm_service")
def test_recalculate_rfm_daily_calls_service(mock_svc):
    """验证任务调用 recalculate_all"""
    mock_svc.recalculate_all = AsyncMock(return_value={"updated": 50, "errors": []})
    from src.core.celery_tasks import recalculate_rfm_daily
    result = recalculate_rfm_daily()
    assert result["success"] is True
    assert result["updated"] == 50

@patch("src.core.celery_tasks.cdp_rfm_service")
@patch("src.core.celery_tasks.lifecycle_state_machine")
def test_rfm_triggers_lifecycle_transition(mock_lsm, mock_svc):
    """RFM等级变化时触发生命周期状态转移"""
    mock_svc.recalculate_all = AsyncMock(return_value={
        "updated": 2,
        "level_changes": [
            {"consumer_id": "C001", "old_level": "S3", "new_level": "S1"},
        ],
        "errors": []
    })
    mock_lsm.apply_trigger = AsyncMock()
    from src.core.celery_tasks import recalculate_rfm_daily
    result = recalculate_rfm_daily()
    assert result["lifecycle_transitions"] >= 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd apps/api-gateway && python -m pytest tests/test_cdp_rfm_celery.py -v
```

- [ ] **Step 3: 实现 Celery 任务**

在 `celery_tasks.py` 末尾添加：

```python
@app.task(bind=True, name="recalculate_rfm_daily")
def recalculate_rfm_daily(self):
    """每日 02:30 UTC 全量 RFM 重算 + 生命周期状态同步"""
    async def _run():
        from src.services.cdp_rfm_service import recalculate_all
        from src.services.lifecycle_state_machine import LifecycleStateMachine
        from src.core.database import get_db_session

        async with get_db_session() as db:
            rfm_result = await recalculate_all(db)
            transitions = 0
            lsm = LifecycleStateMachine()
            for change in rfm_result.get("level_changes", []):
                try:
                    await lsm.detect_and_sync(db, change["consumer_id"])
                    transitions += 1
                except Exception as e:
                    logger.warning(f"lifecycle sync failed for {change['consumer_id']}: {e}")
            await db.commit()
            return {
                "success": True,
                "updated": rfm_result.get("updated", 0),
                "lifecycle_transitions": transitions,
                "errors": rfm_result.get("errors", [])
            }

    return asyncio.run(_run())

# Beat 注册（在 beat_schedule 字典中添加）
# "recalculate-rfm-daily": {
#     "task": "recalculate_rfm_daily",
#     "schedule": crontab(hour=2, minute=30),
# },
```

- [ ] **Step 4: 运行测试验证通过**
- [ ] **Step 5: 提交**

```bash
git add apps/api-gateway/src/core/celery_tasks.py apps/api-gateway/tests/test_cdp_rfm_celery.py
git commit -m "feat: 定时 RFM 重算 Celery 任务 + 生命周期状态同步"
```

---

### Task 3.2: 会员等级升降自动推送

**Files:**
- Create: `apps/api-gateway/src/services/lifecycle_action_service.py`
- Test: `apps/api-gateway/tests/test_lifecycle_action_service.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_lifecycle_action_service.py
import pytest
from src.services.lifecycle_action_service import LifecycleActionService

def test_vip_upgrade_generates_welcome():
    svc = LifecycleActionService()
    action = svc.get_action("HIGH_FREQUENCY", "VIP", store_id="S001", customer_id="C001")
    assert action["type"] == "wechat_push"
    assert "VIP" in action["template"]
    assert action["priority"] == "high"

def test_at_risk_generates_retention():
    svc = LifecycleActionService()
    action = svc.get_action("VIP", "AT_RISK", store_id="S001", customer_id="C001")
    assert action["type"] == "journey_trigger"
    assert action["journey"] == "vip_retention"

def test_no_action_for_same_state():
    svc = LifecycleActionService()
    action = svc.get_action("REPEAT", "REPEAT", store_id="S001", customer_id="C001")
    assert action is None

def test_dormant_generates_reactivation():
    svc = LifecycleActionService()
    action = svc.get_action("AT_RISK", "DORMANT", store_id="S001", customer_id="C001")
    assert action["type"] == "journey_trigger"
    assert action["journey"] == "dormant_reactivation"
```

- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 实现 LifecycleActionService**

```python
# src/services/lifecycle_action_service.py
"""会员等级变更后的自动化行动服务"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 状态转移 → 行动映射
TRANSITION_ACTIONS: Dict[tuple, Dict[str, Any]] = {
    ("REPEAT", "HIGH_FREQUENCY"): {
        "type": "wechat_push",
        "template": "high_frequency_recognition",
        "priority": "medium",
        "message": "感谢您的频繁光顾！您已成为我们的高频贵客 🎉",
    },
    ("HIGH_FREQUENCY", "VIP"): {
        "type": "wechat_push",
        "template": "vip_welcome",
        "priority": "high",
        "message": "恭喜您成为 VIP 会员！专属特权已开通 👑",
    },
    ("VIP", "AT_RISK"): {
        "type": "journey_trigger",
        "journey": "vip_retention",
        "priority": "urgent",
    },
    ("HIGH_FREQUENCY", "AT_RISK"): {
        "type": "journey_trigger",
        "journey": "high_freq_win_back",
        "priority": "high",
    },
    ("AT_RISK", "DORMANT"): {
        "type": "journey_trigger",
        "journey": "dormant_reactivation",
        "priority": "high",
    },
    ("FIRST_ORDER_PENDING", "REPEAT"): {
        "type": "wechat_push",
        "template": "repeat_celebration",
        "priority": "medium",
        "message": "欢迎再次光临！您的回头客身份已确认 ✨",
    },
}

class LifecycleActionService:
    def get_action(
        self, from_state: str, to_state: str,
        store_id: str, customer_id: str
    ) -> Optional[Dict[str, Any]]:
        if from_state == to_state:
            return None
        action = TRANSITION_ACTIONS.get((from_state, to_state))
        if action:
            return {
                **action,
                "store_id": store_id,
                "customer_id": customer_id,
            }
        return None
```

- [ ] **Step 4: 运行测试验证通过**
- [ ] **Step 5: 提交**

```bash
git add apps/api-gateway/src/services/lifecycle_action_service.py apps/api-gateway/tests/test_lifecycle_action_service.py
git commit -m "feat: 会员等级升降自动推送行动服务"
```

---

### Task 3.3: 动态标签扩展 + 定时更新

**Files:**
- Modify: `packages/agents/private_domain/src/agent.py` (扩展 `_infer_dynamic_tags`)
- Create: `apps/api-gateway/src/services/dynamic_tag_service.py`
- Test: `apps/api-gateway/tests/test_dynamic_tag_service.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dynamic_tag_service.py
import pytest
from src.services.dynamic_tag_service import infer_tags

def test_family_dining_tag():
    customer = {"monetary": 3000, "frequency": 5, "recency_days": 3,
                "avg_party_size": 4.5, "avg_order_time": 18}
    tags = infer_tags(customer)
    assert "家庭聚餐" in tags

def test_rising_trend_tag():
    customer = {"monetary": 2000, "frequency": 8, "recency_days": 5,
                "monthly_amounts": [300, 400, 500, 600, 800]}
    tags = infer_tags(customer)
    assert "消费上升" in tags

def test_cross_store_tag():
    customer = {"monetary": 5000, "frequency": 15, "recency_days": 2,
                "store_count": 3}
    tags = infer_tags(customer)
    assert "跨店活跃" in tags

def test_basic_tags_still_work():
    customer = {"monetary": 10000, "frequency": 20, "recency_days": 1}
    tags = infer_tags(customer)
    assert "高消费" in tags
    assert "高频" in tags
    assert "近期活跃" in tags
```

- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 实现 dynamic_tag_service.py**

```python
# src/services/dynamic_tag_service.py
"""动态标签推断服务（纯函数，无DB依赖）"""
from typing import Dict, Any, List

def infer_tags(customer: Dict[str, Any]) -> List[str]:
    tags = []
    monetary = customer.get("monetary", 0)
    frequency = customer.get("frequency", 0)
    recency = customer.get("recency_days", 999)

    # 基础标签（兼容原有逻辑）
    if monetary >= 5000:
        tags.append("高消费")
    if frequency >= 4:
        tags.append("高频")
    if recency <= 7:
        tags.append("近期活跃")

    # 时段偏好
    avg_time = customer.get("avg_order_time")
    if avg_time is not None:
        if 11 <= avg_time < 14:
            tags.append("午餐偏好")
        elif 17 <= avg_time < 21:
            tags.append("晚餐偏好")

    # 消费类型
    avg_party = customer.get("avg_party_size", 0)
    if avg_party >= 4:
        tags.append("家庭聚餐")
    elif avg_party >= 6 and monetary >= 3000:
        tags.append("商务宴请")

    # 消费趋势
    amounts = customer.get("monthly_amounts", [])
    if len(amounts) >= 3:
        recent = amounts[-2:]
        earlier = amounts[:-2]
        if recent and earlier:
            avg_recent = sum(recent) / len(recent)
            avg_earlier = sum(earlier) / len(earlier)
            if avg_earlier > 0 and avg_recent / avg_earlier >= 1.3:
                tags.append("消费上升")
            elif avg_earlier > 0 and avg_recent / avg_earlier <= 0.5:
                tags.append("消费下降")

    # 跨店活跃
    if customer.get("store_count", 1) >= 2:
        tags.append("跨店活跃")

    return tags or ["普通用户"]
```

- [ ] **Step 4: 运行测试验证通过**
- [ ] **Step 5: 提交**

```bash
git add apps/api-gateway/src/services/dynamic_tag_service.py apps/api-gateway/tests/test_dynamic_tag_service.py
git commit -m "feat: 动态标签推断服务（家庭聚餐/消费趋势/跨店活跃）"
```

---

## Chunk 2: 任务4 — Stub 页面补全（19页）

### 总体策略

19个 Stub 页面按功能域分组开发，每组共享设计模式。每个页面包含：
- TypeScript 接口定义
- Mock 数据（BFF 端点就绪前的降级展示）
- Z组件集成（ZCard/ZKpi/ZTable/ZBadge/ZEmpty）
- CSS Modules 配套文件
- 数据拉取 + 30s 轮询 + 错误静默降级

**参考页面**：`PlatformAdminHome.tsx`（525行）和 `CommandCenterPage.tsx`（582行）

**apiClient 注意**：`apiClient.get<T>()` 直接返回 `T`（response.data 已解包），不要再访问 `.data`

---

### Task 4.1: OPS — 控制台首页 (OpsHomePage)

**Files:**
- Rewrite: `apps/web/src/pages/ops/OpsHomePage.tsx`
- Create: `apps/web/src/pages/ops/OpsHomePage.module.css`

- [ ] **Step 1: 实现 OpsHomePage**

运维控制台首页，展示：
- 4个核心 KPI（活跃门店数、POS连接率、数据同步成功率、今日告警数）
- 系统健康状态卡片（API Gateway / Redis / PostgreSQL / Qdrant）
- 最近同步事件时间线
- 待处理告警列表

使用 ZCard + ZKpi + ZBadge + ZTable 组件。数据先用 Mock 展示，API 端点路径预留 `/api/v1/bff/ops/dashboard`。

- [ ] **Step 2: 创建配套 CSS Module**
- [ ] **Step 3: 验证页面渲染** (`pnpm build` 无报错)
- [ ] **Step 4: 提交**

---

### Task 4.2: OPS — POS对接页 (DataPipelinePage)

**Files:**
- Rewrite: `apps/web/src/pages/ops/DataPipelinePage.tsx`
- Create: `apps/web/src/pages/ops/DataPipelinePage.module.css`

- [ ] **Step 1: 实现 DataPipelinePage**

POS 数据管道管理页面，展示：
- 各门店 POS 连接状态表格（门店名/POS类型/状态/最后同步/同步间隔/操作）
- 手动触发同步按钮
- 同步历史日志（时间/门店/类型/结果/耗时/订单数）
- 数据质量监控（字段缺失率、金额异常率）

- [ ] **Step 2: CSS Module**
- [ ] **Step 3: 验证构建**
- [ ] **Step 4: 提交**

---

### Task 4.3: OPS — 菜单导入 + BOM导入 (MenuImportPage, BomImportPage)

**Files:**
- Rewrite: `apps/web/src/pages/ops/MenuImportPage.tsx`, `BomImportPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 MenuImportPage**

菜单导入工具：
- 上传区域（支持 Excel/CSV）
- 字段映射配置（POS字段 → 屯象字段）
- 预览表格 + 冲突检测
- 导入进度条 + 结果摘要

- [ ] **Step 2: 实现 BomImportPage**（类似结构，字段为原料/用量/单位）
- [ ] **Step 3: CSS Modules**
- [ ] **Step 4: 验证构建**
- [ ] **Step 5: 提交**

---

### Task 4.4: OPS — 渠道数据 + 业务规则 (ChannelDataPage, BusinessRulesPage)

**Files:**
- Rewrite: `apps/web/src/pages/ops/ChannelDataPage.tsx`, `BusinessRulesPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 ChannelDataPage**

多渠道数据汇聚看板：
- 渠道卡片（美团/饿了么/抖音/大众点评 — 各显示今日订单/评分/同步状态）
- 渠道数据趋势对比图
- 数据异常告警列表

- [ ] **Step 2: 实现 BusinessRulesPage**

业务规则引擎配置：
- 规则列表表格（名称/触发条件/动作/状态/最后触发）
- 规则编辑抽屉（条件构造器 + 动作配置）
- 规则启停开关

- [ ] **Step 3: CSS Modules**
- [ ] **Step 4: 验证构建**
- [ ] **Step 5: 提交**

---

### Task 4.5: OPS — 门店模板 + 数据隔离 (StoreTemplatePage, DataIsolationPage)

**Files:**
- Rewrite: `apps/web/src/pages/ops/StoreTemplatePage.tsx`, `DataIsolationPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 StoreTemplatePage**

门店配置模板管理：
- 模板列表（名称/适用业态/包含模块/应用门店数/操作）
- 模板详情展开（菜单模板/排班模板/KPI目标/Agent配置）
- 一键下发 + 差异对比

- [ ] **Step 2: 实现 DataIsolationPage**

数据隔离策略：
- 品牌间隔离规则表格
- 门店数据权限矩阵
- 数据访问审计日志

- [ ] **Step 3-5: CSS + 构建 + 提交**

---

### Task 4.6: OPS — AI运维三件套 (AgentTrainingPage, LLMConfigPage, ModelMonitorPage)

**Files:**
- Rewrite: `AgentTrainingPage.tsx`, `LLMConfigPage.tsx`, `ModelMonitorPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 AgentTrainingPage**

Agent 训练数据管理：
- 训练任务列表（Agent名/数据源/样本数/准确率/状态/操作）
- 样本审核面板（标注对/错）
- 训练效果趋势图

- [ ] **Step 2: 实现 LLMConfigPage**

LLM 配置管理：
- Provider 切换（Claude/DeepSeek/OpenAI — 卡片式选择）
- 模型参数配置（temperature/max_tokens/top_p）
- API Key 管理（脱敏显示）
- 用量统计（今日 token 数/费用估算）

- [ ] **Step 3: 实现 ModelMonitorPage**

模型监控看板：
- 模型健康 KPI（准确率/响应时间P99/错误率/降级次数）
- 嵌入模型状态（本地/远程/零向量降级）
- Agent 调用链追踪表格
- 异常日志

- [ ] **Step 4-6: CSS + 构建 + 提交**

---

### Task 4.7: OPS — 推送策略 + IoT设备 (PushStrategyPage, IoTDevicesPage)

**Files:**
- Rewrite: `PushStrategyPage.tsx`, `IoTDevicesPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 PushStrategyPage**

推送策略管理：
- 策略列表（名称/渠道/触发条件/优先级/静默时段/状态）
- 推送频率控制（每日上限/静默期配置）
- 推送效果分析（送达率/打开率/点击率）

- [ ] **Step 2: 实现 IoTDevicesPage**

IoT 设备管理：
- 设备列表表格（设备ID/类型/门店/在线状态/最后心跳/固件版本）
- 设备类型分布饼图
- 离线告警列表
- 固件升级管理

- [ ] **Step 3-5: CSS + 构建 + 提交**

---

### Task 4.8: OPS — 数据导入/导出 (DataImportPage, DataExportPage)

**Files:**
- Rewrite: `DataImportPage.tsx`, `DataExportPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 DataImportPage**

通用数据导入：
- 数据类型选择（订单/库存/菜品/员工/会员）
- 文件上传区域
- 字段映射 + 数据预览
- 导入历史记录表

- [ ] **Step 2: 实现 DataExportPage**

数据导出中心：
- 导出模板选择（日报/周报/订单明细/库存快照/会员列表）
- 时间范围 + 门店筛选
- 格式选择（Excel/CSV/PDF）
- 导出任务队列 + 下载链接

- [ ] **Step 3-5: CSS + 构建 + 提交**

---

### Task 4.9: Platform — 7个 Stub 页面

**Files:**
- Rewrite: `CrossMerchantLearningPage.tsx`, `DeliveryTrackingPage.tsx`, `KeyManagementPage.tsx`, `ModelVersionPage.tsx`, `ModuleAuthPage.tsx`, `PromptWarehousePage.tsx`, `RenewalAlertPage.tsx`
- Create: 配套 CSS Modules

- [ ] **Step 1: 实现 CrossMerchantLearningPage**

跨商户学习看板：
- 联邦学习任务列表（任务ID/参与品牌数/模型类型/聚合轮次/精度提升）
- 数据贡献统计
- 隐私保护指标

- [ ] **Step 2: 实现 DeliveryTrackingPage**

交付跟踪：
- 商户交付流水线（接入 → 配置 → 测试 → 上线）
- 各阶段耗时统计
- 阻塞项告警

- [ ] **Step 3: 实现 KeyManagementPage**

密钥管理：
- API Key 列表（名称/类型/脱敏值/创建时间/过期时间/状态）
- Key 轮换操作
- 使用量统计

- [ ] **Step 4: 实现 ModelVersionPage**

模型版本管理：
- 模型注册表（名称/版本/大小/精度/部署状态）
- 版本对比
- 回滚操作

- [ ] **Step 5: 实现 ModuleAuthPage**

模块授权：
- 商户模块矩阵（商户 × 模块功能的开关网格）
- 批量授权操作
- 授权变更日志

- [ ] **Step 6: 实现 PromptWarehousePage**

提示词仓库：
- Prompt 列表（名称/Agent/版本/效果评分/使用次数）
- 版本对比 diff 视图
- A/B 测试配置

- [ ] **Step 7: 实现 RenewalAlertPage**

续费预警：
- 合同到期看板（30天内/60天内/90天内分组）
- 续费风险评估（使用频率/满意度/替代风险）
- 续费行动计划

- [ ] **Step 8: CSS Modules 全部创建**
- [ ] **Step 9: `pnpm build` 验证零错误**
- [ ] **Step 10: 提交**

```bash
git add apps/web/src/pages/ops/ apps/web/src/pages/platform/
git commit -m "feat: 补全19个Stub页面（12个OPS + 7个Platform）真实UI"
```

---

## Chunk 3: 任务5 — 知识OS层 API + Service

### Task 5.1: KnowledgeService 核心服务

**Files:**
- Create: `apps/api-gateway/src/services/knowledge_service.py`
- Test: `apps/api-gateway/tests/test_knowledge_service.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_knowledge_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.knowledge_service import KnowledgeService

@pytest.fixture
def svc():
    return KnowledgeService()

@pytest.mark.asyncio
async def test_create_skill_node(svc):
    db = AsyncMock()
    result = await svc.create_skill_node(db, {
        "skill_id": "SKILL_COOK_WOK_001",
        "name": "炒锅基础",
        "category": "cooking",
        "max_level": 5,
        "kpi_impact": {"waste_rate": -0.02, "speed_of_service": 0.1},
        "estimated_revenue_lift": 15000.00,
    })
    assert result["skill_id"] == "SKILL_COOK_WOK_001"
    db.add.assert_called_once()

@pytest.mark.asyncio
async def test_capture_knowledge(svc):
    db = AsyncMock()
    result = await svc.capture_knowledge(db, {
        "person_id": "P001",
        "trigger_type": "exit",
        "context": "离职交接",
        "action": "记录炒锅火候控制经验",
        "result": "已提炼为标准操作规范",
    })
    assert result["status"] == "draft"
    assert result["quality_score"] is None  # 待审核

@pytest.mark.asyncio
async def test_record_achievement(svc):
    db = AsyncMock()
    result = await svc.record_achievement(db, {
        "person_id": "P001",
        "skill_node_id": "SK001",
        "level": 3,
        "evidence": {"type": "exam", "score": 85},
    })
    assert result["level"] == 3

@pytest.mark.asyncio
async def test_get_person_skill_passport(svc):
    db = AsyncMock()
    # Mock 查询返回2个技能认证
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(skill_node_id="SK1", level=3, is_valid=True),
        MagicMock(skill_node_id="SK2", level=5, is_valid=True),
    ]
    db.execute = AsyncMock(return_value=mock_result)
    passport = await svc.get_person_skill_passport(db, "P001")
    assert len(passport["skills"]) == 2

@pytest.mark.asyncio
async def test_detect_behavior_pattern(svc):
    db = AsyncMock()
    result = await svc.detect_behavior_pattern(db, {
        "pattern_type": "churn_risk",
        "feature_vector": {"attendance_anomaly": 0.8, "performance_decline": 0.6},
        "outcome": "high_risk",
        "confidence": 0.85,
        "sample_size": 500,
    })
    assert result["confidence"] == 0.85
    assert result["is_active"] is True
```

- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 实现 KnowledgeService**

```python
# src/services/knowledge_service.py
"""知识OS层核心服务 — 技能图谱、知识采集、行为模式、成就认证"""
import logging
from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.skill_node import SkillNode
from src.models.knowledge_capture import KnowledgeCapture
from src.models.achievement import Achievement
from src.models.behavior_pattern import BehaviorPattern
from src.models.retention_signal import RetentionSignal

logger = logging.getLogger(__name__)

class KnowledgeService:
    # ── 技能图谱 ──
    async def create_skill_node(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        node = SkillNode(id=str(uuid4()), **data)
        db.add(node)
        await db.flush()
        return {"skill_id": node.skill_id, "id": node.id, "name": node.name}

    async def list_skill_nodes(self, db: AsyncSession, category: Optional[str] = None) -> List[Dict]:
        q = select(SkillNode)
        if category:
            q = q.where(SkillNode.category == category)
        result = await db.execute(q)
        return [{"id": str(n.id), "skill_id": n.skill_id, "name": n.name,
                 "category": n.category, "max_level": n.max_level}
                for n in result.scalars().all()]

    # ── 知识采集 ──
    async def capture_knowledge(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        cap = KnowledgeCapture(
            id=str(uuid4()),
            person_id=data["person_id"],
            trigger_type=data["trigger_type"],
            context=data.get("context", ""),
            action=data.get("action", ""),
            result=data.get("result", ""),
            status="draft",
            capture_method=data.get("capture_method", "form"),
            created_at=datetime.now(timezone.utc),
        )
        db.add(cap)
        await db.flush()
        return {"id": cap.id, "status": cap.status, "quality_score": None}

    async def review_knowledge(self, db: AsyncSession, capture_id: str,
                                quality_score: str, reviewer: str) -> Dict[str, Any]:
        result = await db.execute(select(KnowledgeCapture).where(KnowledgeCapture.id == capture_id))
        cap = result.scalar_one()
        cap.quality_score = quality_score
        cap.reviewed_by = reviewer
        cap.reviewed_at = datetime.now(timezone.utc)
        cap.status = "reviewed"
        await db.flush()
        return {"id": cap.id, "status": "reviewed", "quality_score": quality_score}

    # ── 成就认证 ──
    async def record_achievement(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        ach = Achievement(
            id=str(uuid4()),
            person_id=data["person_id"],
            skill_node_id=data["skill_node_id"],
            level=data["level"],
            evidence=data.get("evidence", {}),
            achieved_at=datetime.now(timezone.utc),
            is_valid=True,
        )
        db.add(ach)
        await db.flush()
        return {"id": ach.id, "level": ach.level, "person_id": ach.person_id}

    async def get_person_skill_passport(self, db: AsyncSession, person_id: str) -> Dict[str, Any]:
        result = await db.execute(
            select(Achievement).where(Achievement.person_id == person_id, Achievement.is_valid.is_(True))
        )
        skills = [{"skill_node_id": a.skill_node_id, "level": a.level, "achieved_at": str(a.achieved_at)}
                  for a in result.scalars().all()]
        return {"person_id": person_id, "skills": skills, "total": len(skills)}

    # ── 行为模式 ──
    async def detect_behavior_pattern(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        bp = BehaviorPattern(
            id=str(uuid4()),
            pattern_type=data["pattern_type"],
            feature_vector=data["feature_vector"],
            outcome=data["outcome"],
            confidence=data["confidence"],
            sample_size=data.get("sample_size", 0),
            is_active=True,
            version=1,
        )
        db.add(bp)
        await db.flush()
        return {"id": bp.id, "confidence": bp.confidence, "is_active": True}

    # ── 离职风险信号 ──
    async def create_retention_signal(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        sig = RetentionSignal(
            id=str(uuid4()),
            assignment_id=data["assignment_id"],
            risk_score=data["risk_score"],
            risk_level=data["risk_level"],
            risk_factors=data.get("risk_factors", {}),
            intervention_status="none",
            computed_at=datetime.now(timezone.utc),
        )
        db.add(sig)
        await db.flush()
        return {"id": sig.id, "risk_score": sig.risk_score, "risk_level": sig.risk_level}
```

- [ ] **Step 4: 运行测试验证通过**
- [ ] **Step 5: 提交**

---

### Task 5.2: Knowledge API 路由

**Files:**
- Create: `apps/api-gateway/src/api/knowledge.py`
- Modify: `apps/api-gateway/src/main.py` (注册 router)

- [ ] **Step 1: 实现 API 路由**

```python
# src/api/knowledge.py
"""知识OS层 API — /api/v1/knowledge"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
svc = KnowledgeService()

# ── 技能图谱 ──
@router.get("/skills")
async def list_skills(category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await svc.list_skill_nodes(db, category)

@router.post("/skills")
async def create_skill(data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await svc.create_skill_node(db, data)
    await db.commit()
    return result

# ── 知识采集 ──
@router.post("/captures")
async def capture_knowledge(data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await svc.capture_knowledge(db, data)
    await db.commit()
    return result

@router.put("/captures/{capture_id}/review")
async def review_capture(capture_id: str, data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await svc.review_knowledge(db, capture_id, data["quality_score"], user.id)
    await db.commit()
    return result

# ── 技能护照 ──
@router.get("/passport/{person_id}")
async def get_passport(person_id: str, db: AsyncSession = Depends(get_db)):
    return await svc.get_person_skill_passport(db, person_id)

@router.post("/achievements")
async def record_achievement(data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await svc.record_achievement(db, data)
    await db.commit()
    return result

# ── 行为模式 ──
@router.post("/behavior-patterns")
async def create_pattern(data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await svc.detect_behavior_pattern(db, data)
    await db.commit()
    return result

# ── 离职风险 ──
@router.post("/retention-signals")
async def create_signal(data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await svc.create_retention_signal(db, data)
    await db.commit()
    return result
```

- [ ] **Step 2: 在 main.py 注册 router**

```python
from src.api.knowledge import router as knowledge_router
app.include_router(knowledge_router)
```

- [ ] **Step 3: 验证**

```bash
cd apps/api-gateway && python -c "from src.api.knowledge import router; print(f'{len(router.routes)} routes registered')"
```

- [ ] **Step 4: 提交**

```bash
git add apps/api-gateway/src/api/knowledge.py apps/api-gateway/src/services/knowledge_service.py apps/api-gateway/src/main.py apps/api-gateway/tests/test_knowledge_service.py
git commit -m "feat: 知识OS层 — Service + API 路由（技能图谱/知识采集/成就认证/行为模式）"
```

---

## Chunk 4: 任务6-7 — Neo4j + BettaFish 迁移规划

### Task 6.1: Neo4j 本体图迁移规划文档

**Files:**
- Create: `docs/superpowers/plans/2026-03-17-neo4j-migration.md`

- [ ] **Step 1: 编写迁移规划**

核心内容：
- 迁移范围（哪些 PostgreSQL 表的关系适合图化）
- 本体模型设计（节点类型/关系类型/属性）
- 双写过渡策略（PG + Neo4j 并行，逐步切读）
- 回滚计划
- 性能基准测试方案

- [ ] **Step 2: 提交**

---

### Task 7.1: BettaFish 迁移规划文档

**Files:**
- Create: `docs/superpowers/plans/2026-03-17-bettafish-migration.md`

- [ ] **Step 1: 编写迁移规划**

核心内容：
- BettaFish 系统能力清单
- SentimentAnalysisModel 优先迁移方案
- API 兼容层设计
- 数据迁移脚本

- [ ] **Step 2: 提交**

---

## 执行顺序汇总

| 序号 | 任务 | 预计提交数 | 依赖 |
|------|------|-----------|------|
| 3.1 | Celery RFM 定时重算 | 1 | 无 |
| 3.2 | 会员升降自动推送 | 1 | 无 |
| 3.3 | 动态标签扩展 | 1 | 无 |
| 4.1-4.8 | OPS 12页 | 4-6 | 无 |
| 4.9 | Platform 7页 | 1 | 无 |
| 5.1 | KnowledgeService | 1 | 无 |
| 5.2 | Knowledge API | 1 | 5.1 |
| 6.1 | Neo4j 规划 | 1 | 无 |
| 7.1 | BettaFish 规划 | 1 | 无 |
