# 屯象OS HR SaaS 全栈建设计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以餐饮行业员工成长周期管理为核心、AI智能体全程介入为差异化，自建完整HR底座，最终达到可平替乐才云人力系统的能力。

**Architecture:** 三横两纵架构——横向分为「合规底座/AI成长层/薪资底座」，纵向以「Agent驱动层」和「员工自助层」贯穿全程。每个HR动作均有对应的AI分析和¥影响预测，超越传统HR SaaS的流程合规定位。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + PostgreSQL（主库）、Celery（异步任务）、Redis（缓存/消息）、React 19 + CSS Modules（前端）、企微/飞书 Webhook（员工触达）、LangChain（Agent）

---

## 战略定位

```
乐才云做的是：员工数据 → 合规流程 → HR管理（被动工具）
屯象OS HR做的是：员工成长 → 经营价值 → AI决策（主动智能体）
覆盖范围：可完整替换乐才云的所有核心模块
```

### 差异化护城河（不可抄）

1. **行业数据本体**：岗位/技能/培训周期内置餐饮行业语义，不是空白字段
2. **¥优先**：每个HR动作附带经营影响预测（离职=¥损失，晋升=¥收益）
3. **主动智能体**：AI主动发现问题推送建议，而非等HR点击查询

### 不做的边界

- ❌ 社保/公积金/个税计算规则维护（接三方服务，最后阶段）
- ❌ 法律合规文书生成（接三方电子签平台）
- ❌ 通用HR SaaS功能（绩效360/培训学习平台/招聘ATS）

---

## 现状盘点（截至 2026-03-18）

### 已完成

| 组件 | 文件 | 状态 |
|------|------|------|
| Person三层模型 | `models/hr/person.py` + `employment_assignment.py` + `employment_contract.py` | ✅ |
| WF-1 留人风险预测 | `services/hr/retention_risk_service.py` | ✅ |
| WF-2 排班诊断 | `services/hr/staffing_service.py` | ✅ |
| WF-3/4 知识采集 | `services/hr/knowledge_capture_service.py` | ✅ |
| WF-5 新店人才梯队 | `services/hr/talent_pipeline_service.py` | ✅ |
| HQ HR大盘 | `pages/hq/HR.tsx` + `HRKnowledge.tsx` + `HRTalentPipeline.tsx` | ✅ |
| SM HR人员档案 | `pages/sm/HRTeam.tsx` + `HRPerson.tsx` + `HRQuick.tsx` | ✅ |
| 运营工作流引擎 | `services/workflow_engine.py`（排班/菜单/采购） | ✅（HR不可用） |

### 缺口（需要新建）

```
合规底座：
  入职流程       ← 无
  离职流程       ← 无
  转岗/晋升流程  ← 无
  HR审批工作流   ← 无（现有引擎是运营专用）
  考勤打卡接入   ← 无
  考勤计算引擎   ← 无
  假期管理       ← 无
  员工自助       ← 基础档案有，申请流程无
  工资单生成     ← 无（薪资最后做）

AI成长层（超越乐才）：
  WF-6 入职智能引导   ← 未实现
  WF-7 晋升路径推荐   ← 未实现
  WF-8 薪资公平分析   ← 未实现
  WF-9 人才健康大盘   ← 未实现
```

---

## 里程碑总览

| 里程碑 | 主题 | 目标 | 完成标准 |
|--------|------|------|---------|
| **M6** | 组织人事完整底座 | 入职/离职/转岗完整流程 | 新员工从录用→在职→离职全流程可走通 |
| **M7** | HR审批工作流引擎 | 独立于运营引擎的HR审批系统 | 任意HR表单可配置多级审批 |
| **M8** | 考勤底座 | 打卡→计算→报表全链路 | 月度考勤报表可导出，误差率<1% |
| **M9** | 员工自助服务 | 员工移动端自主操作 | 员工可自助查薪/请假/换班/看成长 |
| **M10** | AI成长智能层 WF-6~9 | 超越乐才的差异化 | 4个新WF全部上线，可演示给客户 |
| **M11** | 薪资底座（基础版） | 工资单生成，可替换乐才薪资模块 | 按月核算工资单，一键推送工资条 |

---

## Chunk A：M6 — 组织人事完整底座

### 数据模型

**新建模型**（放入 `apps/api-gateway/src/models/hr/`）：

```python
# onboarding_process.py
class OnboardingProcess(Base):
    """入职流程主记录"""
    __tablename__ = "onboarding_processes"
    id: UUID
    person_id: UUID → Person
    org_node_id: UUID → OrgNode
    status: Enum["draft","pending_review","approved","active","rejected"]
    offer_date: date
    planned_start_date: date
    actual_start_date: date | None
    created_by: str
    metadata: JSONB  # 存储自定义字段

# onboarding_checklist_item.py
class OnboardingChecklistItem(Base):
    """入职清单条目（资料收集/培训/签署）"""
    __tablename__ = "onboarding_checklist_items"
    id: UUID
    process_id: UUID → OnboardingProcess
    item_type: Enum["document","training","contract_sign","system_setup","equipment"]
    title: str
    required: bool
    completed_at: datetime | None
    completed_by: str | None
    file_url: str | None

# offboarding_process.py
class OffboardingProcess(Base):
    """离职流程主记录"""
    __tablename__ = "offboarding_processes"
    id: UUID
    assignment_id: UUID → EmploymentAssignment
    reason: Enum["resignation","termination","contract_end","retirement","mutual"]
    apply_date: date
    planned_last_day: date
    actual_last_day: date | None
    status: Enum["pending","approved","completed","cancelled"]
    knowledge_capture_triggered: bool = False  # WF-4联动
    settlement_amount_fen: int = 0  # 结算金额（分）

# transfer_process.py
class TransferProcess(Base):
    """转岗/晋升流程"""
    __tablename__ = "transfer_processes"
    id: UUID
    person_id: UUID → Person
    from_assignment_id: UUID → EmploymentAssignment
    to_org_node_id: UUID
    to_employment_type: str
    new_pay_scheme: JSONB  # 新薪资方案
    transfer_type: Enum["internal_transfer","promotion","demotion","secondment"]
    effective_date: date
    status: Enum["pending","approved","active","rejected"]
    reason: str
    revenue_impact_yuan: float  # AI预测¥影响
```

**修改现有模型**：
- `models/hr/employment_assignment.py`：增加 `onboarding_process_id`、`offboarding_process_id` 字段
- `models/hr/person.py`：增加 `career_stage` 字段（Enum: probation/regular/senior/lead/manager）

### 服务层

**新建**：`apps/api-gateway/src/services/hr/onboarding_service.py`

```python
class OnboardingService:
    """
    入职流程服务。
    AI差异化：入职时自动生成基于岗位的90天成长计划（含技能节点目标）
    """
    async def create_process(self, person_id, org_node_id, planned_start, session) -> OnboardingProcess
    async def generate_checklist(self, process_id, session) -> list[OnboardingChecklistItem]
    async def complete_item(self, item_id, completed_by, file_url, session)
    async def approve(self, process_id, approved_by, session) -> EmploymentAssignment
    async def _generate_ai_growth_plan(self, person_id, job_title, session) -> dict
    # 触发WF-6（入职智能引导Celery任务）
```

**新建**：`apps/api-gateway/src/services/hr/offboarding_service.py`

```python
class OffboardingService:
    """
    离职流程服务。
    AI差异化：离职时自动计算技能¥损失 + 触发WF-4知识采集
    """
    async def apply(self, assignment_id, reason, planned_last_day, session) -> OffboardingProcess
    async def approve(self, process_id, approved_by, session)
    async def complete(self, process_id, session) -> dict  # 返回¥影响报告
    async def _calculate_skill_loss_yuan(self, assignment_id, session) -> float
    async def _trigger_knowledge_capture(self, process_id, session)  # 联动WF-4
```

**新建**：`apps/api-gateway/src/services/hr/transfer_service.py`

```python
class TransferService:
    """转岗/晋升流程。AI预测收入影响。"""
    async def apply(self, person_id, to_org_node_id, transfer_type, effective_date, session)
    async def approve(self, process_id, approved_by, session)
    async def execute(self, process_id, session) -> EmploymentAssignment  # 创建新Assignment
    async def _predict_revenue_impact(self, person_id, to_org_node_id, session) -> float
```

### API端点

**修改**：`apps/api-gateway/src/api/hr.py`

```python
# 入职
POST /api/v1/hr/onboarding                      # 发起入职流程
GET  /api/v1/hr/onboarding/{process_id}         # 查询进度
PATCH /api/v1/hr/onboarding/{process_id}/items/{item_id}  # 完成清单项
POST /api/v1/hr/onboarding/{process_id}/approve # 审批通过

# 离职
POST /api/v1/hr/offboarding                     # 申请离职
POST /api/v1/hr/offboarding/{process_id}/approve
POST /api/v1/hr/offboarding/{process_id}/complete

# 转岗
POST /api/v1/hr/transfers                       # 申请转岗/晋升
POST /api/v1/hr/transfers/{process_id}/approve
POST /api/v1/hr/transfers/{process_id}/execute

# 花名册完整管理
GET  /api/v1/hr/persons                         # 已有，增加批量导出
POST /api/v1/hr/persons                         # 新建员工档案
PATCH /api/v1/hr/persons/{id}                   # 更新
GET  /api/v1/hr/persons/export                  # Excel导出
POST /api/v1/hr/persons/import                  # Excel批量导入
```

### Alembic迁移

```
migration: add_hr_lifecycle_tables
表：onboarding_processes, onboarding_checklist_items,
    offboarding_processes, transfer_processes
字段补丁：employment_assignments.onboarding_process_id,
          employment_assignments.offboarding_process_id,
          persons.career_stage
```

### 前端页面

**新建**：`apps/web/src/pages/hq/HRLifecycle.tsx`
- 花名册列表（搜索/过滤/导入/导出）
- 入职流程看板（按状态分列）
- 离职预警列表（显示¥技能损失）

**修改**：`apps/web/src/pages/sm/HRQuick.tsx`
- 新增"发起入职"/"申请离职"快捷按钮

### 测试计划

```bash
# 文件：apps/api-gateway/tests/test_hr_lifecycle_service.py
# 覆盖：
test_create_onboarding_generates_checklist_by_job_title
test_approve_onboarding_creates_assignment
test_offboarding_triggers_knowledge_capture
test_offboarding_calculates_skill_loss_yuan
test_transfer_creates_new_assignment_ends_old
test_transfer_predicts_revenue_impact
# 最少15个测试
```

### M6 完成标准

- [ ] 4张新表迁移通过 `make migrate-up`
- [ ] 3个服务各≥5个测试通过
- [ ] 入职流程可从API走通（create → checklist → approve → EmploymentAssignment生成）
- [ ] 离职时自动触发WF-4（knowledge_capture_triggered = True）
- [ ] `pnpm build` 零错误

---

## Chunk B：M7 — HR审批工作流引擎

### 设计原则

现有 `workflow_engine.py` 是运营专用（排班/菜单/采购），强耦合于时间窗口。HR审批需要独立引擎，支持：
- 多级线性审批（N级）
- 按条件路由（金额>X元 → 增加总部审批）
- 代理审批（审批人不在时找代理人）
- 企微/飞书消息触达

### 数据模型

**新建**：`apps/api-gateway/src/models/hr_workflow/`

```python
# approval_template.py — 审批模板定义
class ApprovalTemplate(Base):
    __tablename__ = "approval_templates"
    id: UUID
    name: str                    # "入职审批"/"离职审批"/"转岗审批"
    resource_type: str           # "onboarding"/"offboarding"/"transfer"
    org_node_id: UUID | None     # None=集团通用，有=门店专属
    steps: JSONB                 # [{level:1, approver_type:"position", role:"store_manager"}]
    is_active: bool

# approval_instance.py — 审批实例
class ApprovalInstance(Base):
    __tablename__ = "approval_instances"
    id: UUID
    template_id: UUID → ApprovalTemplate
    resource_type: str
    resource_id: UUID            # onboarding_process_id 等
    status: Enum["pending","approved","rejected","cancelled"]
    current_step: int
    created_by: str
    created_at: datetime
    completed_at: datetime | None
    metadata: JSONB              # 存储申请摘要供审批人快速判断

# approval_step_record.py — 每步审批记录
class ApprovalStepRecord(Base):
    __tablename__ = "approval_step_records"
    id: UUID
    instance_id: UUID → ApprovalInstance
    step: int
    approver_id: str
    approver_name: str
    action: Enum["pending","approved","rejected","delegated"]
    comment: str | None
    acted_at: datetime | None
    notified_at: datetime | None
```

### 服务层

**新建**：`apps/api-gateway/src/services/hr/approval_workflow_service.py`

```python
class HRApprovalWorkflowService:
    """
    HR专用审批工作流引擎。
    与运营workflow_engine完全独立，专注HR审批场景。
    """
    async def start(self, resource_type, resource_id, initiator, session) -> ApprovalInstance
    async def action(self, instance_id, approver_id, action, comment, session)
    async def get_pending_for(self, approver_id, session) -> list[ApprovalInstance]
    async def _resolve_approver(self, step_config, org_node_id, session) -> str
    async def _notify_approver(self, instance_id, step, session)  # 企微推送
    async def _on_approved(self, instance_id, session)   # 回调资源方法
    async def _on_rejected(self, instance_id, session)
```

### Celery任务

**修改**：`apps/api-gateway/src/core/celery_tasks.py`

```python
@app.task
def notify_pending_approvals():
    """每天09:00推送超过24h未处理的审批"""

@app.task
def check_approval_deadline(instance_id: str):
    """48h超时自动升级到上级审批"""
```

### API端点

```python
GET  /api/v1/hr/approvals/pending             # 当前用户待审批列表
POST /api/v1/hr/approvals/{id}/approve        # 审批通过
POST /api/v1/hr/approvals/{id}/reject         # 驳回（需填原因）
POST /api/v1/hr/approvals/{id}/delegate       # 委托他人
GET  /api/v1/hr/approvals/{id}                # 审批详情+步骤记录
GET  /api/v1/hr/approval-templates            # 模板列表
POST /api/v1/hr/approval-templates            # 创建模板
```

### 前端

**新建**：`apps/web/src/pages/hq/HRApprovals.tsx`
- 待我审批列表（ZTable + ZBadge状态）
- 审批详情抽屉（时间线展示步骤）
- 审批统计（平均耗时、积压数量）

### M7 完成标准

- [ ] 审批工作流与运营工作流完全解耦
- [ ] 入职/离职/转岗均自动发起审批
- [ ] 企微推送审批通知可达
- [ ] 审批超时自动升级Celery任务配置
- [ ] ≥10个测试覆盖主要审批路径

---

## Chunk C：M8 — 考勤底座

### 架构决策

**打卡接入**：优先企业微信（餐饮连锁已广泛使用）→ 企微考勤数据通过Webhook推入系统。不自建人脸识别/门禁，走官方API。

**考勤计算引擎**：独立服务，每日00:30自动计算前一日考勤结果（Celery定时任务）。

### 数据模型

```python
# models/hr/attendance/clock_record.py
class ClockRecord(Base):
    """打卡原始记录（来自企微/钉钉/手工）"""
    __tablename__ = "clock_records"
    id: UUID
    assignment_id: UUID → EmploymentAssignment
    clock_type: Enum["in","out","break_start","break_end"]
    clock_time: datetime
    source: Enum["wechat_work","dingtalk","manual","face_recognition"]
    location: JSONB | None        # {lat, lng, address}
    is_anomaly: bool = False      # 异常打卡标记

# models/hr/attendance/daily_attendance.py
class DailyAttendance(Base):
    """日考勤计算结果"""
    __tablename__ = "daily_attendances"
    id: UUID
    assignment_id: UUID
    date: date
    status: Enum["normal","late","early_leave","absent","leave","holiday","overtime"]
    work_minutes: int              # 实际工作分钟
    overtime_minutes: int
    late_minutes: int
    early_leave_minutes: int
    calculated_at: datetime
    locked: bool = False          # 月结后锁定

# models/hr/leave/leave_request.py
class LeaveRequest(Base):
    """请假申请"""
    __tablename__ = "leave_requests"
    id: UUID
    assignment_id: UUID
    leave_type: Enum["annual","sick","personal","marriage","maternity","paternity","bereavement"]
    start_datetime: datetime
    end_datetime: datetime
    days: float                   # 支持0.5天
    reason: str
    status: Enum["pending","approved","rejected","cancelled"]
    approved_by: str | None

# models/hr/leave/leave_balance.py
class LeaveBalance(Base):
    """假期余额账户"""
    __tablename__ = "leave_balances"
    id: UUID
    assignment_id: UUID
    leave_type: str
    year: int
    total_days: float
    used_days: float
    remaining_days: float
    accrual_rule: JSONB          # 按工龄/用工性质的配额规则
```

### 服务层

**新建**：`apps/api-gateway/src/services/hr/attendance_service.py`

```python
class AttendanceService:
    """
    考勤计算引擎。
    AI差异化：异常打卡模式识别（凌晨2-3点场景参考乐才V6.1逻辑）
    """
    async def record_clock(self, assignment_id, clock_type, clock_time, source, session)
    async def calculate_daily(self, assignment_id, date, session) -> DailyAttendance
    async def get_monthly_summary(self, assignment_id, year, month, session) -> dict
    async def detect_anomalies(self, assignment_id, date, session) -> list[str]
    # 特殊处理：顶岗时记录原岗位（参考乐才V6.1案例）
    async def get_original_position(self, assignment_id, date, session) -> str
```

**新建**：`apps/api-gateway/src/services/hr/leave_service.py`

```python
class LeaveService:
    async def apply(self, assignment_id, leave_type, start, end, reason, session) -> LeaveRequest
    async def approve(self, request_id, approved_by, session)
    async def get_balance(self, assignment_id, leave_type, year, session) -> LeaveBalance
    async def accrue_annual_leave(self, assignment_id, session)  # 按工龄自动发放
    async def simulate(self, assignment_id, leave_type, start, end, session) -> dict
    # 模拟计算器（参考乐才V6.1发假模拟器思路）
```

### 企微打卡Webhook接入

**新建**：`apps/api-gateway/src/api/webhooks/wechat_attendance.py`

```python
@router.post("/webhooks/wechat/attendance")
async def receive_attendance_webhook(payload: dict, session: AsyncSession):
    """
    接收企业微信考勤打卡回调。
    验证签名 → 解析clock_in/clock_out → 写ClockRecord → 触发daily_calculate
    """
```

### Celery定时任务

```python
# celery_tasks.py 新增：
@app.task
def calculate_yesterday_attendance():
    """每日00:30计算全部门店前日考勤（DailyAttendance）"""

@app.task
def lock_previous_month_attendance():
    """每月5日锁定上月考勤（locked=True）"""

@app.task
def accrue_monthly_leave():
    """每月1日自动发放月度假期配额"""
```

### M8 完成标准

- [ ] 企微考勤Webhook可接收并写入ClockRecord
- [ ] 每日自动计算考勤，支持迟到/早退/缺勤/加班判断
- [ ] 请假申请走M7审批工作流
- [ ] 月度考勤报表可导出（Excel）
- [ ] 凌晨02:00-03:00异常打卡场景单独处理（不漏算）
- [ ] 顶岗场景保留原岗位记录
- [ ] ≥12个考勤计算测试

---

## Chunk D：M9 — 员工自助服务（移动端）

### 设计原则

目标用户：餐饮门店一线员工（店员、厨师、服务员），设备：手机。
核心诉求：查工资/查排班/请假/换班/看自己的成长档案。
路由：扩展现有 `/sm/hr/` 路径。

### 功能模块

```
/sm/hr/self                   员工个人中心（已有基础）
  ├── 今日排班卡片
  ├── 本月出勤摘要
  ├── 快捷操作：申请换班/请假
  └── 成长积分

/sm/hr/my-attendance          我的考勤（月历视图）
  ├── 日历热力图（出勤/迟到/休假颜色区分）
  ├── 月度汇总（工作天/迟到次数/剩余年假）
  └── 申诉入口（打卡异常申诉）

/sm/hr/leave                  假期管理
  ├── 假期余额卡片（年假/调休/病假）
  ├── 申请请假（选类型/日期/原因）
  ├── 我的申请记录
  └── 发假模拟（输入参数预计算余额影响）

/sm/hr/growth                 我的成长档案（现有HRPerson升级版）
  ├── 技能图谱（已认证技能）
  ├── 成长时间线（入职→转正→晋升→...）
  ├── 下一步建议（AI推荐下一个技能/晋升目标）
  └── ¥贡献值（持有技能对应预期增收）
```

### 关键交互细节

- **换班申请**：选择目标班次 → 系统显示当前该班次人员 → 对方确认 → 自动更新排班
- **申诉流程**：选择异常打卡日 → 填写说明 → 直属上级审批 → 走M7引擎
- **发假模拟**（借鉴乐才V6.1）：先模拟再提交，避免提交后发现余额不足
- **AI成长建议**：基于当前技能图谱 + 岗位本体，给出具体推荐（"再掌握拉面技术，预期增收¥300/月"）

### M9 完成标准

- [ ] 员工可通过手机完整走完"请假申请→审批→余额扣减"流程
- [ ] 考勤月历视图展示正确数据
- [ ] 发假模拟器在提交前可预计算结果
- [ ] 成长档案显示AI生成的下一步建议
- [ ] 所有页面响应式，375px手机屏正常显示

---

## Chunk E：M10 — AI成长智能层（WF-6 至 WF-9）

这是屯象OS HR超越乐才云的核心差异化层。

### WF-6：入职智能引导

**触发时机**：OnboardingProcess状态变为 `approved`，自动触发Celery任务

**能力**：
- 根据岗位本体，自动生成个性化90天成长计划
- 每周推送本周技能学习目标（企微）
- 第30/60/90天自动检查目标达成率
- AI预测：该员工按当前进度，预期转正时能创造¥X收益

```python
# services/hr/growth_guidance_service.py
class GrowthGuidanceService:
    async def generate_plan(self, assignment_id, session) -> dict
    # 返回: {week_1_goals, week_4_goals, ..., expected_revenue_by_day90_yuan}

    async def weekly_checkin(self, assignment_id, week_num, session)
    # 检查进度，低于预期时推送激励 + 调整计划

    async def milestone_review(self, assignment_id, day, session) -> dict
    # 30/60/90天里程碑评估报告
```

### WF-7：晋升路径推荐

**触发时机**：员工满足任一条件：在职≥6个月 / 技能认证数量增加 / 直属上级发起评估

**能力**：
- 基于技能图谱和餐饮行业岗位本体，计算最优晋升路径
- 对比同岗位同期员工的技能差距
- 给出具体行动计划（需要掌握X技能 → 预计N周 → 晋升后增薪¥Y）

```python
# services/hr/career_path_service.py
class CareerPathService:
    async def recommend_next_role(self, assignment_id, session) -> dict
    async def analyze_skill_gap_to_target(self, assignment_id, target_role, session) -> dict
    async def compare_with_peers(self, assignment_id, session) -> dict
    # 返回: {percentile, skill_delta, salary_delta_yuan}
```

### WF-8：薪资公平性分析

**触发时机**：每季度定时运行 / 新员工入职时做市场对标

**能力**：
- 计算同岗位/同技能/同工龄员工的薪资分布
- 识别薪资异常（低于P25或高于P90）
- 给店长/总部推送建议（"张三薪资低于同岗位中位数23%，离职风险↑"）

```python
# services/hr/compensation_fairness_service.py
class CompensationFairnessService:
    async def analyze_store(self, org_node_id, session) -> dict
    async def flag_anomalies(self, session) -> list[dict]
    async def market_benchmark(self, job_title, city, session) -> dict
```

### WF-9：门店人才健康度大盘

**触发时机**：HQ HR大盘页面加载 / 每周生成报告推送

**能力**：
- 各门店人才健康度综合评分（技能覆盖率 × 人员稳定性 × 成长速度）
- 识别人才风险最高的门店（需要优先干预）
- 集团人才流动图谱（谁在往哪儿流动）
- 新店开业人才就绪度（与WF-5联动）

```python
# services/hr/talent_health_service.py
class TalentHealthService:
    async def score_store(self, org_node_id, session) -> dict
    # 返回: {health_score, skill_coverage, stability_index, growth_rate}

    async def hq_dashboard(self, session) -> dict
    # HQ大盘BFF数据，30s Redis缓存

    async def talent_flow_matrix(self, session) -> dict
    # 人才流向矩阵（从哪个门店→流向哪个门店）
```

### 前端增强

**修改**：`apps/web/src/pages/hq/HR.tsx`
- 新增WF-7/WF-8/WF-9对应的展示组件
- 人才流向桑基图（ECharts）
- 门店健康度排名升级（加健康评分维度）

### M10 完成标准

- [ ] WF-6：新员工入职后24h内自动生成成长计划并推送企微
- [ ] WF-7：可查看当前员工的推荐晋升路径和技能差距
- [ ] WF-8：薪资异常检测，每季度推送给店长
- [ ] WF-9：HQ大盘展示门店健康度评分和人才流向
- [ ] 4个WF均有≥5个测试
- [ ] 所有AI建议均包含¥影响数字

---

## Chunk F：M11 — 薪资底座（基础版）

> 这是平替乐才薪资模块的最后一步。社保/个税接三方，不自研规则计算。

### 设计原则

- **工资单生成**：按月，以AssignmentContract的pay_scheme为基础，叠加考勤数据（出勤天数/加班时数/缺勤扣款）
- **薪税计算**：不自研。提供接口，接三方服务（薪人家 / 智联薪酬）。MVP阶段可以先导出Excel让HR手工处理
- **工资条推送**：企微推送，支持"阅后即焚"模式（参考乐才V6.1）
- **多门店分摊**：支持同一员工工资按比例分摊到多个门店（参考乐才V6.1 Item 2）

### 数据模型

```python
# models/hr/payroll/payroll_batch.py
class PayrollBatch(Base):
    """薪资核算批次"""
    __tablename__ = "payroll_batches"
    id: UUID
    org_node_id: UUID
    period_year: int
    period_month: int
    status: Enum["draft","calculating","review","approved","paid","locked"]
    total_gross_fen: int         # 税前总额（分）
    total_net_fen: int           # 税后总额（分）
    created_by: str
    approved_by: str | None
    paid_at: datetime | None

# models/hr/payroll/payroll_item.py
class PayrollItem(Base):
    """个人薪资条目"""
    __tablename__ = "payroll_items"
    id: UUID
    batch_id: UUID → PayrollBatch
    assignment_id: UUID → EmploymentAssignment
    base_salary_fen: int         # 基本工资
    performance_fen: int         # 绩效奖金
    overtime_fen: int            # 加班费
    deduction_absent_fen: int    # 缺勤扣款
    deduction_late_fen: int      # 迟到扣款
    allowances: JSONB            # 其他津贴
    gross_fen: int               # 税前合计
    social_insurance_fen: int    # 社保个人部分（三方计算填入）
    tax_fen: int                 # 个税（三方计算填入）
    net_fen: int                 # 实发工资
    viewed_at: datetime | None   # 阅后即焚：查看时间戳
    view_expires_at: datetime | None  # 查看有效期

# models/hr/payroll/cost_allocation.py
class CostAllocation(Base):
    """工资多门店分摊配置"""
    __tablename__ = "cost_allocations"
    id: UUID
    assignment_id: UUID
    org_node_id: UUID
    ratio: float                 # 分摊比例（0.0-1.0，同一assignment多行之和=1）
```

### 服务层

```python
# services/hr/payroll_service.py
class PayrollService:
    async def create_batch(self, org_node_id, year, month, session) -> PayrollBatch
    async def calculate(self, batch_id, session)
    # 从AssignmentContract取pay_scheme
    # 从DailyAttendance取出勤数据
    # 计算gross，留social_insurance/tax为0（等三方填）

    async def approve(self, batch_id, approved_by, session)
    async def send_payslips(self, batch_id, session)
    # 企微推送工资条 + 设置view_expires_at（阅后即焚）

    async def get_payslip(self, item_id, viewer_id, session) -> dict
    # 验证viewer_id是本人 + 未过期，记录viewed_at

    async def export_for_tax(self, batch_id, session) -> bytes
    # 导出给三方薪税服务的标准Excel模板

    async def allocate_cost(self, batch_id, session) -> dict
    # 按CostAllocation比例拆分到各门店成本中心
```

### M11 完成标准

- [ ] 按月可生成PayrollBatch，自动从考勤数据计算出勤天数
- [ ] 工资单可通过企微推送，支持阅后即焚
- [ ] 多门店分摊配置生效，HQ成本报表可按门店展示
- [ ] 导出三方薪税标准模板（Excel）
- [ ] ≥8个薪资计算测试

---

## AI Agent 贯穿层架构

以上每个模块均集成到AI Agent系统，形成"主动智能体"模式：

```
信号观察层（Celery定时 + Webhook触发）
    ↓
HRAgent判断层（LangChain，每日分析）
    ↓ 若发现需干预信号
推送建议层（企微，包含：动作建议 + ¥影响 + 置信度 + 一键操作链接）
    ↓ 管理者点击确认
执行层（调用相应Service方法）
    ↓
学习层（记录DecisionLog，更新StoreMemory）
```

**HRAgent每日执行的分析**：

| 时间 | 任务 | 推送接收者 |
|------|------|----------|
| 每日 07:30 | 今日异常出勤预警（昨日迟到/缺勤） | 店长 |
| 每日 09:00 | 待处理审批提醒（积压>24h） | 各级审批人 |
| 每周一 08:00 | 本周人才健康度简报（WF-9） | 总部HR |
| 每月5日 10:00 | 上月考勤锁定 + 薪资核算提醒 | HR专员 |
| 实时触发 | 留人风险达到阈值（WF-1）→建议谈话 | 店长 |
| 实时触发 | 离职流程完成 → 技能¥损失报告 | 总部 |

---

## 技术债务防范

### 排班分页记忆（借鉴乐才V6.1）
所有ZTable分页偏好存入localStorage，键值：`{table_id}_page_size`。
影响文件：`apps/web/src/design-system/components/ZTable.tsx`

### 顶岗原岗位记录
`ClockRecord` 新增 `original_position` 字段，在抢班场景写入被顶员工的原岗位。
这解决了乐才V6.1中提到的薪资核算问题。

### 借调精确日期范围判断
`LeaveService` 和 `AttendanceService` 的锁定判断，使用精确区间（[start, end] inclusive），
而非 `>= start_date`。参考乐才V6.1 假勤模块第4点的血泪教训。

---

## 里程碑时间估算

| 里程碑 | 主要工作量 | 参考周期 |
|--------|-----------|---------|
| M6 组织人事 | 4个模型 + 3个服务 + 6个端点 + 1个前端页面 | 5天 |
| M7 工作流引擎 | 3个模型 + 1个引擎服务 + Celery任务 + 前端 | 4天 |
| M8 考勤底座 | 4个模型 + 2个服务 + 企微Webhook + Celery | 6天 |
| M9 员工自助 | 4个前端页面 + 轻量后端 | 4天 |
| M10 AI成长层 | 4个服务 + Agent集成 + 前端增强 | 5天 |
| M11 薪资底座 | 3个模型 + 1个服务 + 企微推送 | 4天 |
| **合计** | | **约28个工作日** |

---

## 验证计划

```bash
# 每个里程碑完成后运行：
cd apps/api-gateway
pytest tests/test_hr_lifecycle_service.py -v     # M6
pytest tests/test_hr_approval_workflow.py -v     # M7
pytest tests/test_attendance_service.py -v       # M8
pytest tests/test_payroll_service.py -v          # M11

# 前端构建验证：
cd apps/web && pnpm build

# 集成验证（每个里程碑）：
# 问："一个高级工程师会批准这个吗？"
# 检查：所有涉及¥的字段是否都包含金额
# 检查：所有HR动作是否都有AI分析和建议推送
# 检查：SQL是否均使用参数化查询（无字符串拼接）
```
