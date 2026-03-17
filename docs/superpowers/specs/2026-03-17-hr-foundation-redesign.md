# 屯象OS 人力底层重构设计文档

**版本**: v1.0
**日期**: 2026-03-17
**作者**: 微了一 + Claude
**状态**: 待实施

---

## 0. 背景与目标

### 为什么重构

屯象OS现有人力模块存在四个根本性问题：

1. **Employee 模型过于扁平**：无法表达「一人多店多角色」「合伙人店长」「小时工跨店调配」等连锁餐饮真实用工场景
2. **知识孤岛**：老师傅离职带走所有经验，门店标准靠口口相传，新店复制失败率高
3. **被动响应**：现有系统只能报警，无法在问题发生前预测并主动干预
4. **组织结构缺失**：Employee 不感知集团→品牌→区域→城市→门店的组织层级

### 设计目标

构建屯象OS的**人力知识操作系统**（HR Knowledge OS），以真正的 AGI 服务餐饮行业：

- 覆盖连锁餐饮全5大痛点：人员流失、知识传承、排班效率、标准执行、用工复杂性
- AGI 能力路径：B级（诊断建议）→ C级（预测干预）→ D级（自主执行，架构预留）
- 三位一体知识OS：行业经验库 + 知识图谱 + 行为模式学习

### 迁移策略

**方案C — 完整底层重构**：Person/Assignment/Contract 三分离模型全面替换现有 Employee 模型，Expand → Migrate → Contract 安全换血，全程不停服。

---

## 1. 数据架构

### 1.1 核心领域模型（替换现有 Employee）

#### `persons` — 全局人员档案

```sql
persons (
  id                  UUID PRIMARY KEY,
  legacy_employee_id  VARCHAR(50),       -- 迁移桥接：原 employees.id（如 "EMP001"）
  name                VARCHAR(50) NOT NULL,
  id_number           VARCHAR(18),       -- 身份证号（加密存储）
  phone               VARCHAR(20),
  email               VARCHAR(200),
  photo_url           VARCHAR(500),
  preferences         JSONB,             -- 原 employees.preferences 迁移
  emergency_contact   JSONB,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
)
```

**设计要点**：跨门店全局唯一，代表自然人身份。不含任何用工关系字段。

#### `employment_assignments` — 在岗关系

```sql
employment_assignments (
  id                UUID PRIMARY KEY,
  person_id         UUID NOT NULL REFERENCES persons(id),
  org_node_id       UUID NOT NULL REFERENCES org_nodes(id),
  job_standard_id   UUID REFERENCES job_standards(id),
  employment_type   VARCHAR(30) NOT NULL,  -- full_time / hourly / outsourced / dispatched / partner
  start_date        DATE NOT NULL,
  end_date          DATE,                  -- NULL = 仍在职
  status            VARCHAR(20) DEFAULT 'active',  -- active / ended / suspended
  created_at        TIMESTAMPTZ DEFAULT NOW()
)
```

**设计要点**：
- 一个 Person 可有多个 Assignment（跨店兼职、历史记录）
- 与 OrgNode 直接关联，天然支持集团→门店全链路人力视图
- `employment_type` 支持5种用工形态，取代旧版 Employee 的类型枚举

#### `employment_contracts` — 用工合同

```sql
employment_contracts (
  id                  UUID PRIMARY KEY,
  assignment_id       UUID NOT NULL REFERENCES employment_assignments(id),
  contract_type       VARCHAR(30) NOT NULL,   -- labor / hourly / outsource / dispatch / partnership
  pay_scheme          JSONB NOT NULL,          -- 薪酬方案（月薪/时薪/提成比例）
  attendance_rule_id  UUID REFERENCES attendance_rules(id),
  kpi_template_id     UUID REFERENCES kpi_templates(id),
  valid_from          DATE NOT NULL,
  valid_to            DATE,
  signed_at           TIMESTAMPTZ,
  file_url            VARCHAR(500),
  created_at          TIMESTAMPTZ DEFAULT NOW()
)
```

**设计要点**：
- 同一 Assignment 可有多份合同（续签、合同变更）
- `pay_scheme` 用 JSONB 支持任意薪酬结构（全职月薪、小时工时薪、合伙人分成等）
- 考勤规则、KPI模板通过外键关联，不在合同里硬编码

### 1.2 三位一体知识OS层

#### `hr_knowledge_rules` — HR专属行业经验库

> ⚠️ **注意**：现有 `knowledge_rules` 表（`apps/api-gateway/src/models/knowledge_rule.py`）已存在，且 schema 不兼容（使用 `RuleCategory` Enum、`rule_code`、`conclusion` 等不同字段）。HR 知识库**单独建表** `hr_knowledge_rules`，避免破坏现有规则引擎。

```sql
hr_knowledge_rules (
  id            UUID PRIMARY KEY,
  rule_type     VARCHAR(30) NOT NULL,  -- sop / kpi_baseline / alert / best_practice
  category      VARCHAR(50),           -- turnover / scheduling / standards / training
  condition     JSONB NOT NULL,        -- 触发条件（结构化）
  action        JSONB NOT NULL,        -- 推荐动作
  expected_impact JSONB,               -- 预期¥影响
  confidence    FLOAT DEFAULT 0.8,
  industry_source VARCHAR(100),        -- 来源（16年行业经验/客户案例）
  org_node_id   UUID REFERENCES org_nodes(id),  -- NULL = 全行业通用
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
)
```

**冷启动**：上线时导入500+条餐饮行业基础规则（屯象16年积累）。

#### `skill_nodes` — 知识图谱骨架

```sql
skill_nodes (
  id                    UUID PRIMARY KEY,
  skill_name            VARCHAR(100) NOT NULL,
  category              VARCHAR(50),    -- service / kitchen / management / compliance
  description           TEXT,
  prerequisite_skill_ids UUID[],        -- 前置技能（PostgreSQL数组，无FK约束）
  related_training_ids   UUID[],        -- 关联培训ID数组
  kpi_impact            JSONB,          -- 影响哪些KPI
  estimated_revenue_lift DECIMAL(10,2), -- 预计¥收入提升（元/月）
  org_node_id           UUID REFERENCES org_nodes(id),  -- NULL = 行业通用
  created_at            TIMESTAMPTZ DEFAULT NOW()
)
```

**核心推理链**：`岗位 → 所需技能集 → 前置技能 → 关联培训 → KPI影响 → ¥提升`

**关于 Neo4j**：`prerequisite_skill_ids UUID[]` 为 PostgreSQL 原生数组，无 FK 约束，适合 POC 阶段快速开发。现有 `ARCHITECTURE.md` 规划 Neo4j 用于本体图，当 skill_nodes 数量超过 1000 条或需要复杂多跳推理时，可将此表迁移为 Neo4j 节点——`skill_nodes.id` 作为桥接键，届时 `prerequisite_skill_ids` 改为 Neo4j 边关系。本阶段 **skill_nodes 是 PostgreSQL 的临时实现**，不与 Neo4j 双写。

#### `behavior_patterns` — 行为模式学习

```sql
behavior_patterns (
  id            UUID PRIMARY KEY,
  pattern_type  VARCHAR(50),    -- turnover_risk / high_performance / schedule_optimal
  feature_vector JSONB NOT NULL, -- 特征元数据（字段名 + 权重，非向量值）
  qdrant_vector_id VARCHAR(100), -- 对应 Qdrant collection hr_behavior_patterns 的向量ID
  outcome       VARCHAR(100),   -- 结果标签
  confidence    FLOAT,
  sample_size   INTEGER,
  org_scope     VARCHAR(30),    -- brand / region / network
  org_node_id   UUID REFERENCES org_nodes(id),
  last_trained  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
)
```

**向量存储说明**：`feature_vector` 存储特征元数据（可读），实际384维嵌入向量存入 Qdrant collection `hr_behavior_patterns`（与现有架构一致）。`qdrant_vector_id` 为桥接字段。未来若迁移到 Neo4j 本体图，行为模式节点通过 `qdrant_vector_id` 与向量检索层解耦。

**冷启动降级**：样本不足时自动降级为 `hr_knowledge_rules` 规则引擎兜底。

### 1.3 职业发展 + 留人层

#### `person_achievements` — 技能认证记录

```sql
person_achievements (
  id              UUID PRIMARY KEY,
  person_id       UUID NOT NULL REFERENCES persons(id),
  skill_node_id   UUID NOT NULL REFERENCES skill_nodes(id),
  achieved_at     DATE NOT NULL,
  evidence        TEXT,           -- 认证依据（考试/实操/导师评估）
  verified_by     UUID REFERENCES persons(id),
  created_at      TIMESTAMPTZ DEFAULT NOW()
)
```

#### `retention_signals` — 离职风险预测

```sql
retention_signals (
  id                  UUID PRIMARY KEY,
  assignment_id       UUID NOT NULL REFERENCES employment_assignments(id),
  risk_score          FLOAT NOT NULL,    -- 0.0-1.0
  risk_factors        JSONB NOT NULL,    -- 风险因子明细
  intervention_status VARCHAR(30) DEFAULT 'pending',  -- pending / in_progress / resolved
  intervention_at     TIMESTAMPTZ,
  computed_at         TIMESTAMPTZ DEFAULT NOW()
)

-- WF-1 每日扫描索引（必须）
CREATE INDEX idx_retention_signals_scan
  ON retention_signals (risk_score DESC, computed_at DESC);
CREATE INDEX idx_retention_signals_assignment
  ON retention_signals (assignment_id, computed_at DESC);
```

#### `knowledge_captures` — 对话式知识采集记录

```sql
knowledge_captures (
  id                UUID PRIMARY KEY,
  person_id         UUID NOT NULL REFERENCES persons(id),
  trigger_type      VARCHAR(30),
  -- exit / monthly_review / incident / onboarding /
  -- growth_review（WF-3技能催化后触发）/
  -- talent_assessment（WF-5新店梯队评估触发）/
  -- legacy_import（Employee迁移历史数据导入）
  raw_dialogue      TEXT,         -- 原始对话记录
  context           TEXT,         -- 情境（Context）
  action            TEXT,         -- 处理动作（Action）
  result            TEXT,         -- 结果影响（Result）
  structured_output JSONB,        -- LLM结构化解析结果
  knowledge_node_id UUID REFERENCES skill_nodes(id),
  quality_score     FLOAT,        -- 知识质量评分
  created_at        TIMESTAMPTZ DEFAULT NOW()
)
```

---

## 2. HRAgent 架构

### 2.1 LangGraph 状态机

```
HRAgentState
├── intent: str                    # 意图分类
├── context: dict                  # 当前门店/人员上下文
├── knowledge_results: list        # 知识检索结果
├── prediction_results: dict       # 预测模型输出
├── recommendations: list          # 最终建议列表
└── actions_taken: list[ActionRecord]  # 已执行动作（D级）

ActionRecord（D级自主执行动作记录）：
{
  "action_type": str,        # publish_schedule / send_training / send_wechat
  "target_id": str,          # 操作对象ID
  "payload": dict,           # 操作内容
  "requires_approval": bool, # 是否需要人工审批
  "dry_run": bool,           # True = 预演模式，不真实执行
  "executed_at": datetime,
  "approved_by": str | None
}
# D级 ActionNode 在 requires_approval=True 时写入待审批队列，
# 不直接执行；只有 requires_approval=False 且 dry_run=False 时才真实执行。

节点（Nodes）：
IntentRouter → [DiagnosisNode | PredictionNode | ActionNode]
                      ↓
              KnowledgeRetriever（共享）
              ├── RuleRetriever      → hr_knowledge_rules
              ├── GraphTraversal     → skill_nodes 关系链
              └── PatternMatcher     → behavior_patterns ML
                      ↓
              OutputFormatter → [WeChat推送 | BFF响应 | DecisionLog]
```

### 2.2 三轨道能力

| 轨道 | 节点 | AGI级别 | 当前状态 |
|------|------|---------|---------|
| 诊断建议 | DiagnosisNode | B级 | M2上线 |
| 预测干预 | PredictionNode | C级 | M3上线 |
| 自主执行 | ActionNode | D级 | 架构预留，需信任积累后启用 |

### 2.3 五大核心工作流

#### WF-1 离职风险拦截流（每日自动触发）
```
扫描 retention_signals
→ score > 0.70：推送店长企业微信（建议1对1 + 历史干预成功率）
→ score > 0.85：升级区域经理
→ 员工提交离职申请：立即触发 WF-4（知识采集）
→ 记录干预结果 → 更新 behavior_patterns
```

#### WF-2 智能排班优化流（每周一自动触发）
```
读取 employment_assignments（active状态）+ 历史客流数据
→ 生成最优排班草案（最小化人力成本，保障服务质量）
→ 计算¥节省金额
→ 推送店长审批（M2）→ 自动发布（D级，M4预留）
```

#### WF-3 技能成长催化流（每周触发）
```
扫描每个 Person.achievements vs 目标岗位 skill_nodes 要求
→ 识别「距晋升最近的一个技能缺口」
→ 匹配关联培训 + 预估¥收入提升
→ 推送精准培训建议
→ 培训完成 → 更新 person_achievements
```

#### WF-4 知识采集触发流（事件驱动）
```
触发条件：离职申请 / 月度复盘时间点 / 异常事件处理后
→ AI通过企业微信发送结构化问题（情境/动作/结果三段式）
→ LLM解析回答 → 存入 knowledge_captures
→ 质量评分 > 0.8 → 提升为 hr_knowledge_rules 或 skill_nodes
```

#### WF-5 新店人才梯队复制流（手动触发）
```
输入：新店 OrgNode + 预计开业日期
→ 分析岗位需求矩阵
→ 扫描集团内 employment_assignments 识别内部储备人员
→ 识别技能缺口 → 生成培训时间线
→ 输出「人才就绪率」+ 补招建议（含¥预算）
```

---

## 3. 迁移策略

### 3.0 前置条件（⚠️ 硬性阻断门）

**M1 开始前必须完成：**

| 前置工作 | Alembic | 状态 |
|---------|---------|------|
| OrgHierarchy（OrgNode/OrgConfig 模型） | z52 | 计划已写，待实施 |
| OrgScope 传播（权限中间件）| z53 | 计划已写，待实施 |

`employment_assignments.org_node_id REFERENCES org_nodes(id)` 依赖 `org_nodes` 表存在。z52/z53 未合并则 M1 的 Alembic migration 会失败。预留 Week 0（2周）完成 OrgHierarchy 实施，HR 重构从 Week 3 启动，总工期调整为 14 周。

### 3.1 迁移原则

**Expand → Migrate → Contract**：先建新表，新旧并存，验证后删旧表。全程不停服，种子客户数据完整保留。

### 3.2 五个里程碑（含前置）

| 里程碑 | 周期 | Alembic | 关键交付 |
|--------|------|---------|---------|
| **M0（前置）** | Week 1-2 | z52, z53 | OrgHierarchy + OrgScope 实施完成 |
| **M1** | Week 3-4 | z54, z55 | 新表建立 + 餐饮知识包冷启动 |
| **M2** | Week 5-7 | — | 数据迁移脚本 + 双写模式 + HRAgent v1（B级） |
| **M3** | Week 8-11 | z56 | 外键更新 + HRAgent v2（C级）|
| **M4** | Week 12-14 | z57 | 旧表清理 + 前端全面接入 |

### 3.3 数据迁移映射（完整12字段）

Employee PK 现为 `String(50)`（如 "EMP001"），**不是 UUID**。迁移策略：为每个 Employee 生成新 UUID，保留 `legacy_employee_id` 作为查找桥接。

```
employees.id              → persons.legacy_employee_id（保留原值）
                            persons.id 生成新 UUID
employees.name            → persons.name
employees.phone           → persons.phone
employees.email           → persons.email（新增字段）
employees.store_id        → employment_assignments.org_node_id
                            （通过 stores.org_node_id 关联，需 z52 完成后才有此列）
employees.position        → employment_assignments.job_standard_id
employees.employment_type → employment_assignments.employment_type
employees.salary          → employment_contracts.pay_scheme.base_salary
employees.hire_date       → employment_assignments.start_date
employees.is_active       → employment_assignments.status
                            （True → 'active', False → 'ended'）
employees.preferences     → persons.preferences（新增 JSONB 字段）
employees.performance_score → 丢弃：新系统由 KPI 模块重新计算
employees.skills          → 转换：每个技能字符串查找 skill_nodes.skill_name
                            → 在 person_achievements 创建记录
                            （无匹配则跳过，人工后续补录）
employees.training_completed → 转换：同上，查找 skill_nodes 匹配后写 achievements
                              （trigger_type='legacy_import'）
```

**外键桥接表**（临时，M4删除）：
```sql
employee_id_map (
  legacy_employee_id  VARCHAR(50) PRIMARY KEY,  -- 原 "EMP001" 风格 ID
  person_id           UUID NOT NULL,
  assignment_id       UUID NOT NULL
)

CREATE INDEX idx_employee_id_map_person     ON employee_id_map (person_id);
CREATE INDEX idx_employee_id_map_assignment ON employee_id_map (assignment_id);
```
所有旧 `employee_id` FK 字段在过渡期通过此表查找对应的 `assignment_id`。

### 3.4 外键迁移范围（实际清单）

通过 `grep -r "employee_id" apps/ packages/ --include="*.py"` 确认的迁移目标：

**硬外键（4个，必须更新）：**
```
compliance.holder_employee_id        → assignment_id
customer_ownership.owner_employee_id → assignment_id
schedule.employee_id                 → assignment_id
employee_metric.employee_id          → assignment_id
```

**软引用字符串（~10个，逐项验证后更新）：**
```
attendance / people_agent / edge_hub / banquet_sales /
employee_growth_trace / health_certificate 等
```

实施前执行 grep 脚本生成完整清单，逐项标记「迁移/保留/删除」后才进入 M3。

### 3.5 风险对策

| 风险 | 对策 |
|------|------|
| OrgNode 未完成导致 M1 失败 | M0 完成并验证后才开始 M1（硬性阻断门） |
| Employee PK String→UUID 类型冲突 | `employee_id_map` 桥接表 + legacy_employee_id 保留 |
| `attendance_rules`/`kpi_templates` 不存在 | z54 同时创建这两张基础配置表（或外键设 NULLABLE，表存在后再补约束）|
| 数据迁移丢失 | 双写模式；迁移前全量备份；验证脚本核对每张表记录数 |
| 软引用字段漏更新 | grep 清单逐项确认，M3 分批提交，每批跑回归测试 |
| BehaviorPattern 冷启动 | 样本不足时自动降级为 RuleRetriever |

---

## 4. API 设计

### 4.1 BFF 端点

```
GET /api/v1/bff/sm/{store_id}/hr
返回：retention_risks[] + staffing_today + skill_gaps[] + pending_actions[]
缓存：30s Redis，?refresh=true 强刷

GET /api/v1/bff/hq/{org_node_id}/hr
返回：org_headcount + turnover_heatmap + talent_pipeline + knowledge_health
支持：org_node_id 按OrgNode层级下钻
```

### 4.2 核心资源 REST API

```
# 人员
POST   /api/v1/hr/persons
GET    /api/v1/hr/persons/{id}
PATCH  /api/v1/hr/persons/{id}

# 在岗关系
POST   /api/v1/hr/assignments
PATCH  /api/v1/hr/assignments/{id}/end     # 离职/调岗

# 合同
POST   /api/v1/hr/contracts
GET    /api/v1/hr/contracts/{assignment_id}

# 技能 & 成就
GET    /api/v1/hr/skill-nodes              # 技能图谱
POST   /api/v1/hr/achievements             # 记录技能认证

# 风险 & 知识
GET    /api/v1/hr/retention-signals        # 查询离职风险
POST   /api/v1/hr/knowledge-captures       # 提交知识采集
```

---

## 5. 前端页面

### 5.1 新增页面清单

| 路由 | 角色 | 设备 | 功能 |
|------|------|------|------|
| `/sm/hr` | 店长 | 手机 | HR首页：留人预警 + 今日在岗 + 技能提醒 + 待审批 |
| `/sm/hr/team` | 店长 | 手机 | 我的团队技能地图 |
| `/sm/hr/person/{id}` | 店长 | 手机 | 员工成长档案（技能树 + 成就 + 风险轨迹）|
| `/hq/hr` | 总部 | 桌面 | HR大盘：全集团人力总览 + 离职风险热力图 |
| `/hq/hr/talent-pipeline` | 总部 | 桌面 | 人才梯队：各岗位储备深度 + 新店就绪率 |
| `/hq/hr/knowledge` | 总部 | 桌面 | 知识库管理：规则 + 技能图谱 + 采集记录 |

### 5.2 关键组件

- **RetentionRiskCard** — 离职风险展示（风险分 + 主要因子 + 一键干预）
- **SkillTreeView** — 技能图谱可视化（已获得/待解锁/推荐下一步）
- **TalentPipelineTable** — 人才梯队表格（岗位→在职人数→储备人数→技能达标率）
- **KnowledgeHealthWidget** — 知识库健康度小卡片（条目数/覆盖率/本月新增）

---

## 6. 知识三位一体实施细节

### 第一层：行业经验库（启动即可用）

上线 M1 时导入屯象餐饮行业知识包，包含：
- 500+ 条离职预警规则（连续迟到/绩效下滑/特定行为组合）
- 200+ 条排班优化规则（客流峰值/岗位最低配置/跨店调配条件）
- 300+ 条技能-KPI映射关系（哪个技能影响哪个指标，预期¥提升）

### 第二层：知识图谱（M1建骨架，运营期持续丰富）

初始图谱包含餐饮行业标准岗位技能树：
```
服务员岗 → [点菜技能, 酒水知识, 投诉处理, 卫生规范]
           ↓ 掌握4项
领班岗   → [排班基础, 新员工培训, 成本意识]
           ↓ 掌握3项
主管岗   → [数据分析基础, 供应商沟通, 绩效面谈]
```

### 第三层：行为模式学习（数据积累后 M4 启动）

首批训练目标：
- **离职风险模型**：从历史员工行为数据中学习高风险特征组合
- **高绩效店长模型**：识别高绩效店长的早期行为特征（用于人才识别）
- **排班优化模型**：从历史排班结果中学习成本最优模式

---

## 7. 成功指标

| 指标 | 当前基线 | M2目标 | M4目标 |
|------|---------|--------|--------|
| 离职预警准确率 | — | ≥65% | ≥80% |
| 知识采集条目 | 0 | 200+ | 1000+ |
| 人均月人力成本节省 | — | — | ¥800+ |
| 新店人才就绪率 | 手动评估 | — | 系统自动计算 |
| 店长HR操作时间/周 | ~3小时 | ~2小时 | ~30分钟 |

---

## 8. 与现有系统的关系

| 现有模块 | 关系 | 变更 |
|---------|------|------|
| OrgNode / OrgHierarchy（z52） | **强依赖·硬性前置** | M0 完成后 M1 才能启动；Assignment.org_node_id 依赖 org_nodes 表 |
| JobStandard | 依赖 | Assignment.job_standard_id 使用现有 job_standards 表 |
| knowledge_rules（现有） | 共存·不修改 | HR 专属规则存入新表 hr_knowledge_rules，不触碰现有规则引擎 |
| Schedule / Shift | 外键更新 | employee_id → assignment_id |
| KPI | 外键更新 | employee_id → assignment_id |
| Attendance | 外键更新 | employee_id → assignment_id |
| Neo4j 本体图 | 暂不集成 | skill_nodes 本阶段在 PostgreSQL 实现；数据量大或需多跳推理后再迁移 Neo4j，skill_nodes.id 作为桥接键 |
| Qdrant 向量库 | 集成 | behavior_patterns 的实际向量存入 Qdrant collection hr_behavior_patterns |
| POS适配器 | 不变 | 无需修改 |
| OrderAgent / InventoryAgent | 不变 | 无需修改 |

---

*文档由 Claude Code (superpowers:brainstorming) 生成，经用户逐节确认。实施前请 Review 完整计划文档。*
