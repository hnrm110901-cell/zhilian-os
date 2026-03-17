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
  id              UUID PRIMARY KEY,
  name            VARCHAR(50) NOT NULL,
  id_number       VARCHAR(18),          -- 身份证号（加密存储）
  phone           VARCHAR(20),
  photo_url       VARCHAR(500),
  emergency_contact JSON,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
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

#### `knowledge_rules` — 行业经验库

```sql
knowledge_rules (
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
  prerequisite_skill_ids UUID[],        -- 前置技能
  related_training_ids   UUID[],        -- 关联培训
  kpi_impact            JSONB,          -- 影响哪些KPI
  estimated_revenue_lift DECIMAL(10,2), -- 预计¥收入提升（元/月）
  org_node_id           UUID REFERENCES org_nodes(id),  -- NULL = 行业通用
  created_at            TIMESTAMPTZ DEFAULT NOW()
)
```

**核心推理链**：`岗位 → 所需技能集 → 前置技能 → 关联培训 → KPI影响 → ¥提升`

#### `behavior_patterns` — 行为模式学习

```sql
behavior_patterns (
  id            UUID PRIMARY KEY,
  pattern_type  VARCHAR(50),    -- turnover_risk / high_performance / schedule_optimal
  feature_vector JSONB NOT NULL, -- 特征向量（行为指标组合）
  outcome       VARCHAR(100),   -- 结果标签
  confidence    FLOAT,
  sample_size   INTEGER,
  org_scope     VARCHAR(30),    -- brand / region / network
  org_node_id   UUID REFERENCES org_nodes(id),
  last_trained  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
)
```

**冷启动降级**：样本不足时自动降级为 KnowledgeRule（规则引擎）兜底。

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
```

#### `knowledge_captures` — 对话式知识采集记录

```sql
knowledge_captures (
  id                UUID PRIMARY KEY,
  person_id         UUID NOT NULL REFERENCES persons(id),
  trigger_type      VARCHAR(30),  -- exit / monthly_review / incident / onboarding
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
└── actions_taken: list            # 已执行动作（D级）

节点（Nodes）：
IntentRouter → [DiagnosisNode | PredictionNode | ActionNode]
                      ↓
              KnowledgeRetriever（共享）
              ├── RuleRetriever      → knowledge_rules
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
→ 质量评分 > 0.8 → 提升为 knowledge_rules 或 skill_nodes
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

### 3.1 迁移原则

**Expand → Migrate → Contract**：先建新表，新旧并存，验证后删旧表。全程不停服，种子客户数据完整保留。

### 3.2 四个里程碑

| 里程碑 | 周期 | Alembic | 关键交付 |
|--------|------|---------|---------|
| **M1** | Week 1-2 | z54, z55 | 新表建立 + 餐饮知识包冷启动 |
| **M2** | Week 3-5 | — | 数据迁移脚本 + 双写模式 + HRAgent v1（B级） |
| **M3** | Week 6-9 | z56 | 99模型外键更新 + HRAgent v2（C级）|
| **M4** | Week 10-12 | z57 | 旧表清理 + OrgHierarchy联通 + 前端全面接入 |

### 3.3 数据迁移映射

```
employees.id              → persons.id（保持UUID不变）
employees.name            → persons.name
employees.phone           → persons.phone
employees.store_id        → employment_assignments.org_node_id（通过stores.org_node_id关联）
employees.position        → employment_assignments.job_standard_id
employees.employment_type → employment_assignments.employment_type
employees.salary          → employment_contracts.pay_scheme.base_salary
employees.hire_date       → employment_assignments.start_date
employees.status          → employment_assignments.status
```

### 3.4 99个模型外键迁移策略

```
原来：schedule.employee_id → employees.id
迁移后：schedule.assignment_id → employment_assignments.id
```

**Assignment 是"在职关系"，与旧 employee 语义最接近**，所有现有关联表（排班/KPI/考勤/培训记录）的外键统一从 `employee_id` 更新为 `assignment_id`。

### 3.5 风险对策

| 风险 | 对策 |
|------|------|
| 迁移脚本数据丢失 | 双写模式保证安全窗口；迁移前全量备份；验证脚本逐行核对记录数 |
| 99个模型漏更新 | Grep扫描所有 employee_id 引用，生成迁移清单，逐项确认 |
| 种子客户数据中断 | M2双写期间新旧API并行；M3迁移选业务低峰期（凌晨2-4点）|
| BehaviorPattern冷启动 | 样本不足时自动降级为 RuleRetriever |

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
| OrgNode / OrgHierarchy | 强依赖 | Assignment.org_node_id 依赖 OrgNode |
| JobStandard | 依赖 | Assignment.job_standard_id 使用现有 job_standards 表 |
| Schedule / Shift | 外键更新 | employee_id → assignment_id |
| KPI | 外键更新 | employee_id → assignment_id |
| Attendance | 外键更新 | employee_id → assignment_id |
| POS适配器 | 不变 | 无需修改 |
| OrderAgent / InventoryAgent | 不变 | 无需修改 |

---

*文档由 Claude Code (superpowers:brainstorming) 生成，经用户逐节确认。实施前请 Review 完整计划文档。*
