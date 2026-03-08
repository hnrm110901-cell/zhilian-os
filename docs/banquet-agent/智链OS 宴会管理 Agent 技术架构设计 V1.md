**《智链OS 宴会管理 Agent 技术架构设计 V1》**





版本：V1.0

产品名称：智链OS Banquet Agent

文档类型：技术架构设计

适用对象：CTO / 架构师 / 后端 / 前端 / 数据 / 测试 / 实施

设计目标：支撑连锁餐饮大、中、小型宴会的全流程数字化、协同化、智能化，并逐步演进为宴会经营操作系统



这份架构设计延续智链OS整体方向：现有系统已有财务、库存、KPI、Agent、RBAC 等基础，但整体仍偏工具层，核心缺口在行业本体层、决策智能层与闭环执行层。宴会管理 Agent 的技术架构必须避免再次做成“孤立功能模块”，而要补足本体、智能和闭环三层。 



------





# **一、技术目标**





宴会管理 Agent V1 的技术目标不是“做一个宴会表单系统”，而是支撑以下 5 个能力：



1. 线索到订单的全流程结构化
2. 厅房、时段、套餐、订单、任务的一体化协同
3. 宴会执行过程中的跨部门任务分发与追踪
4. 宴会收入、成本、利润、转化率的实时分析
5. Agent 对跟进、排期、执行、复盘的初步自动化支持





------





# **二、总体技术架构**





采用五层架构：

```
智链OS 宴会管理 Agent
│
├── L5 交互与驾驶舱层
├── L4 Agent 编排与任务闭环层
├── L3 宴会分析与决策层
├── L2 宴会业务本体层
└── L1 业务接入与数据事件层
```

对应技术落地：

```
┌──────────────────────────────┐
│ L5 前端应用层                 │
│ CEO台 / 销售台 / 店长台 / 财务台 │
├──────────────────────────────┤
│ L4 Agent与任务层              │
│ Orchestrator / Rule Engine    │
│ Task Center / Notification    │
├──────────────────────────────┤
│ L3 业务分析层                 │
│ Revenue / Profit / Funnel     │
│ Utilization / Forecast        │
├──────────────────────────────┤
│ L2 本体与领域服务层           │
│ CRM / Order / Hall / Menu     │
│ Execution / Payment / Cost    │
├──────────────────────────────┤
│ L1 数据接入层                 │
│ POS / Inventory / HR / Finance│
│ Message Bus / API Gateway     │
└──────────────────────────────┘
```



------





# **三、架构原则**







## **1. 领域优先**





以宴会业务领域拆服务，而不是按页面拆。





## **2. 事件驱动**





订单创建、厅房锁档、定金到账、菜单确认、任务逾期、宴会结束，都必须是事件。





## **3. 本体驱动**





Customer、Lead、BanquetOrder、BanquetHall、MenuPackage、Task、Payment 之间不是孤立表，而是有业务关系的语义对象。





## **4. 可追溯**





每一次线索流转、订单变更、任务生成、定金收取、异常处理都要有日志和事件链。





## **5. 渐进智能**





V1 先规则驱动，再逐步引入预测、推荐和更复杂 Agent。



------





# **四、微服务拆分设计**





建议采用中等粒度微服务，不建议一开始拆得过细。





## **核心服务列表**



```
banquet-crm-service
banquet-order-service
banquet-resource-service
banquet-menu-service
banquet-execution-service
banquet-finance-service
banquet-analytics-service
banquet-agent-service
task-center-service
notification-service
integration-service
auth-rbac-service
dashboard-service
```



------





## **4.1 banquet-crm-service**





负责：



- 客户档案
- 联系人
- 线索管理
- 跟进记录
- 销售漏斗状态





核心实体：



- Customer
- Contact
- Lead
- FollowUpRecord
- LeadStage





核心职责：



- 线索创建
- 线索分配
- 线索状态流转
- 客户合并去重
- 跟进时间线维护





------





## **4.2 banquet-order-service**





负责：



- 宴会订单
- 合同
- 定金/尾款状态
- 宴会变更
- 宴会生命周期状态机





核心实体：



- BanquetOrder
- Contract
- DepositRecord
- SettlementRecord
- OrderChangeLog





核心职责：



- 线索转订单
- 订单创建/变更/取消
- 状态机维护
- 收款节点管理





建议状态机：

```
Draft
→ Quoted
→ DepositPending
→ Confirmed
→ Preparing
→ InProgress
→ Completed
→ Settled
→ Closed
```



------





## **4.3 banquet-resource-service**





负责：



- 宴会厅/包间
- 档期
- 时段
- 容量
- 资源占用
- 档期冲突校验





核心实体：



- BanquetHall
- TimeSlot
- HallCalendar
- ResourceOccupation





核心职责：



- 厅房主数据管理
- 可售时段查询
- 冲突检测
- 厅房锁档
- 厅房解锁





------





## **4.4 banquet-menu-service**





负责：



- 套餐
- 菜单
- 菜品
- 套餐成本
- 推荐规则





核心实体：



- MenuPackage
- MenuPackageItem
- Dish
- PackagePricingRule
- PackageCostSnapshot





核心职责：



- 套餐配置
- 菜单替换规则
- 成本快照
- 毛利预估
- 基础推荐接口





------





## **4.5 banquet-execution-service**





负责：



- 执行任务模板
- 任务拆解
- 时间轴
- 异常事件
- 执行状态





核心实体：



- ExecutionTemplate
- ExecutionTask
- TaskAssignment
- TaskTimeline
- ExceptionEvent





核心职责：



- 基于订单自动生成任务
- 任务指派
- 逾期识别
- 异常上报与处理
- 宴会执行过程记录





------





## **4.6 banquet-finance-service**





负责：



- 定金
- 尾款
- 开票状态
- 成本归集
- 利润测算





核心实体：



- PaymentRecord
- InvoiceRecord
- CostSnapshot
- ProfitSnapshot





核心职责：



- 订单收款节点管理
- 收款状态同步
- 成本汇总
- 利润计算
- 财务状态查询





------





## **4.7 banquet-analytics-service**





负责：



- 收入分析
- 转化分析
- 档期利用率
- 客户来源分析
- 基础收入预测





核心实体：



- RevenueAgg
- FunnelAgg
- UtilizationAgg
- SourceAgg
- ForecastResult





核心职责：



- 指标聚合
- OLAP 查询
- 定时报表生成
- 预测结果存储





------





## **4.8 banquet-agent-service**





负责：



- Agent 规则
- Agent 触发
- Agent 建议输出
- Agent 行动日志





核心实体：



- AgentRule
- AgentTrigger
- AgentAction
- AgentSuggestion
- AgentExecutionLog





核心职责：



- 跟进提醒 Agent
- 自动报价 Agent
- 排期推荐 Agent
- 执行任务 Agent
- 复盘 Agent 基础版





------





## **4.9 task-center-service**





负责：



- 通用任务中心
- 风险任务
- 业务任务
- 状态追踪





核心职责：



- 多来源任务归一
- 任务状态机
- 指派/转派/催办
- 完成留痕





------





## **4.10 notification-service**





负责：



- 站内消息
- 企微/微信通知
- 短信
- 订阅提醒





------





## **4.11 integration-service**





负责：



- POS 集成
- 库存/供应链集成
- 人力系统集成
- 财务系统集成
- 第三方渠道导入





------





## **4.12 auth-rbac-service**





复用智链OS现有 RBAC 体系，支撑：



- 品牌级权限
- 区域级权限
- 门店级权限
- 页面权限
- 数据权限





这个部分是现有系统明确可复用的资产之一。 



------





# **五、服务之间的调用关系**







## **主链路一：线索转订单**



```
CRM Service
→ Order Service
→ Resource Service（锁档）
→ Finance Service（创建定金节点）
→ Execution Service（生成任务）
→ Agent Service（触发跟进/执行Agent）
→ Notification Service
```



## **主链路二：宴会订单执行**



```
Order Service
→ Execution Service（任务模板拆解）
→ Task Center
→ Notification Service
→ Inventory/HR via Integration Service
```



## **主链路三：宴会结束复盘**



```
POS / Finance / Feedback
→ Finance Service（收入/成本）
→ Analytics Service（利润/转化/来源）
→ Agent Service（复盘草稿）
```



------





# **六、事件总线设计**





宴会业务很适合事件驱动，建议引入消息总线。



技术建议：



- 初期可用 Redis Stream / RabbitMQ
- 成熟后可升级 Kafka







## **核心事件定义**



```
lead.created
lead.assigned
lead.followup_added
lead.stage_changed

banquet.order_created
banquet.order_updated
banquet.order_cancelled
banquet.order_confirmed

banquet.hall_locked
banquet.hall_conflict_detected

banquet.deposit_received
banquet.contract_signed
banquet.balance_due

banquet.task_generated
banquet.task_assigned
banquet.task_overdue
banquet.exception_reported
banquet.exception_closed

banquet.completed
banquet.settled
banquet.review_received

banquet.agent.triggered
banquet.agent.suggestion_generated
```



## **事件价值**





- 解耦服务
- 支撑任务自动生成
- 支撑通知自动发送
- 支撑分析异步聚合
- 支撑 Agent 触发





------





# **七、数据库与存储设计**





采用“事务库 + 分析库 + 图谱/关系本体”的组合。





## **7.1 事务库**





建议：PostgreSQL



用途：



- 客户
- 线索
- 订单
- 厅房
- 套餐
- 任务
- 收款
- 配置
- RBAC







## **7.2 缓存层**





建议：Redis



用途：



- 热数据缓存
- 会话
- 幂等控制
- 分布式锁
- 队列/延迟提醒







## **7.3 分析库**





建议：



- PostgreSQL 物化视图起步
- 后续可升级 ClickHouse





用途：



- 收入趋势
- 转化漏斗
- 档期利用率
- 多维统计







## **7.4 本体/图谱层**





V1 可以不单独上 Neo4j，但建议按图谱思维设计关系；V1.5/V2 再升级为宴会业务图谱。



原因：

当前智链OS最大的长期缺口之一就是缺少真正的行业本体层。宴会系统若后续要支持“高价值客户、最优厅型、套餐利润、复购关系”等多跳推理，图谱层是自然演进方向。 



------





# **八、核心数据模型设计**







## **8.1 CRM 相关表**







### **customer**





- id
- brand_id
- name
- customer_type
- phone
- source
- tags
- created_at







### **customer_contact**





- id
- customer_id
- name
- phone
- role_title
- relation







### **banquet_lead**





- id
- customer_id
- banquet_type
- expected_date
- expected_store_id
- expected_people_count
- expected_budget
- preferred_hall_type
- source_channel
- current_stage
- owner_user_id







### **lead_followup_record**





- id
- lead_id
- followup_type
- content
- next_followup_time
- created_by





------





## **8.2 资源相关表**







### **banquet_hall**





- id
- store_id
- name
- hall_type
- max_tables
- max_people
- min_spend
- status







### **banquet_time_slot**





- id
- store_id
- slot_date
- slot_name
- start_time
- end_time







### **banquet_hall_booking**





- id
- hall_id
- slot_id
- banquet_order_id
- status





------





## **8.3 菜单相关表**







### **menu_package**





- id
- store_id
- package_type
- name
- suggested_price
- target_people_min
- target_people_max
- status







### **menu_package_item**





- id
- package_id
- dish_id
- item_type
- quantity
- replace_group







### **dish_cost_snapshot**





- id
- dish_id
- snapshot_date
- estimated_cost





------





## **8.4 订单相关表**







### **banquet_order**





- id
- lead_id
- customer_id
- store_id
- hall_id
- slot_id
- banquet_type
- people_count
- table_count
- package_id
- order_status
- deposit_status
- total_amount
- remark







### **banquet_contract**





- id
- banquet_order_id
- contract_no
- file_url
- contract_status
- signed_at







### **banquet_payment_record**





- id
- banquet_order_id
- payment_type
- amount
- paid_at
- payment_method
- payment_status





------





## **8.5 执行相关表**







### **execution_template**





- id
- template_name
- banquet_type
- version
- status







### **execution_task**





- id
- banquet_order_id
- template_id
- task_type
- task_name
- owner_role
- owner_user_id
- due_time
- task_status







### **execution_exception**





- id
- banquet_order_id
- task_id
- exception_type
- description
- severity
- owner_user_id
- status





------





## **8.6 分析与 Agent 相关表**







### **banquet_profit_snapshot**





- id
- banquet_order_id
- revenue_amount
- ingredient_cost
- labor_cost
- material_cost
- other_cost
- gross_profit
- gross_margin







### **banquet_kpi_daily**





- id
- store_id
- stat_date
- lead_count
- order_count
- revenue_amount
- gross_profit
- hall_utilization







### **banquet_agent_rule**





- id
- agent_type
- trigger_event
- rule_expression
- status







### **banquet_agent_action_log**





- id
- agent_type
- related_object_type
- related_object_id
- action_type
- action_result
- created_at





------





# **九、状态机设计**







## **9.1 线索状态机**



```
New
→ Contacted
→ VisitScheduled
→ Quoted
→ WaitingDecision
→ DepositPending
→ Won
→ Lost
```



## **9.2 订单状态机**



```
Draft
→ Confirmed
→ Preparing
→ InProgress
→ Completed
→ Settled
→ Closed
→ Cancelled
```



## **9.3 任务状态机**



```
Pending
→ InProgress
→ Done
→ Verified
→ Closed
→ Overdue
```



------





# **十、Agent 技术设计**





V1 不做复杂自主 Agent，采用“规则 + 模板 + 任务”模式最稳。





## **10.1 Agent 架构**



```
Trigger Layer
→ Rule Matching
→ Suggestion Builder
→ Action Dispatcher
→ Log & Feedback
```



## **10.2 V1 Agent 清单**







### **1. 跟进提醒 Agent**





触发条件：



- 超过 N 天未跟进
- 看厅后未报价
- 报价后未继续跟进





动作：



- 生成待办
- 发送提醒







### **2. 自动报价 Agent**





输入：



- 人数
- 预算
- 宴会类型
- 厅房
- 套餐库





输出：



- 候选套餐
- 推荐价格区间







### **3. 排期推荐 Agent**





输入：



- 日期
- 时段
- 人数
- 宴会类型





输出：



- 合适厅房列表
- 冲突说明







### **4. 执行任务 Agent**





触发条件：



- 订单确认
- 距离宴会开始 T-7 / T-3 / T-1
- 任务逾期





动作：



- 生成任务
- 催办提醒







### **5. 复盘 Agent 基础版**





宴会结束后：



- 汇总收入
- 汇总成本
- 汇总异常
- 生成复盘草稿





------





# **十一、前端架构建议**





建议：



- React + Next.js
- Zustand / Redux Toolkit
- React Query
- Ant Design 或基于现有智链OS组件体系复用







## **模块划分**



```
/apps/banquet-console
  /pages
    /dashboard
    /crm
    /calendar
    /packages
    /orders
    /execution
    /finance
    /analytics
    /settings

  /modules
    /crm
    /hall-calendar
    /package-center
    /order-center
    /execution-center
    /analytics-center
    /agent-center
```



## **页面角色分层**





- CEO 驾驶舱
- 宴会销售工作台
- 店长执行工作台
- 财务工作台
- 配置中心





------





# **十二、接口设计建议**







## **外部接口**







### **POS**





- 获取宴会实际消费流水
- 获取结算明细







### **库存/供应链**





- 套餐映射物料
- 获取原料成本
- 发起采购预占







### **人力系统**





- 根据宴会规模给排班系统发需求







### **财务系统**





- 收款状态同步
- 开票状态同步







## **内部接口风格**





建议统一 REST + 事件流，后续分析/图谱可补 GraphQL 查询层。



------





# **十三、非功能要求**







## **性能**





- 档期查询 < 500ms
- 订单详情 < 800ms
- 驾驶舱核心卡片 < 1.5s







## **一致性**





- 厅房锁档必须强一致
- 定金状态必须幂等更新
- 任务生成不可重复







## **安全**





- 门店级权限隔离
- 敏感收款数据权限控制
- 审计日志不可篡改







## **可观测性**





- API tracing
- 事件日志
- Agent 触发日志
- 任务逾期监控





------





# **十四、开发阶段建议**







## **Phase 1：核心交易闭环**





范围：



- CRM
- 订单
- 厅房档期
- 套餐
- 定金
- 基础驾驶舱







## **Phase 2：执行协同闭环**





范围：



- 任务模板
- 自动任务拆解
- 异常处理
- 店长执行台







## **Phase 3：经营分析闭环**





范围：



- 收入
- 利润
- 转化
- 渠道
- 档期利用率







## **Phase 4：Agent 闭环**





范围：



- 跟进提醒
- 自动报价
- 排期推荐
- 复盘草稿





------





# **十五、与智链OS主系统的耦合策略**







## **直接复用**





- RBAC
- 用户中心
- 消息中心
- 基础组织架构
- 审计日志基建







## **适度耦合**





- 财务服务
- 供应链服务
- 排班服务
- 会员服务







## **相对独立**





- 宴会 CRM
- 宴会厅/档期
- 套餐/菜单
- 宴会执行中心
- 宴会 Agent





这样做的好处是：

既能快速上线，又不会把宴会系统做成主系统里的一个难维护“大页面”。



------





# **十六、CTO 级结论**





智链OS 宴会管理 Agent 的技术架构，不能按“预订页面 + 订单页面 + 报表页面”的思路做。

正确方式是：



> 以宴会业务对象为核心，

> 以事件驱动为骨架，

> 以任务协同为闭环，

> 以 Agent 规则为增强，

> 逐步演进为宴会经营操作系统。





