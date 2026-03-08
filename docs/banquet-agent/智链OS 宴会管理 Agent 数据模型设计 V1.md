# **《智链OS 宴会管理 Agent 数据模型设计 V1》**





版本：V1.0

产品名称：智链OS Banquet Agent

文档类型：数据模型设计

适用对象：CTO / 架构师 / 后端 / 数据工程 / 前端 / 测试 / BI

设计目标：建立支撑连锁餐饮大、中、小型宴会全流程管理的标准数据模型，并为后续 Agent、分析、预测、图谱化演进打基础



这份设计延续智链OS整体方向：不是只做页面和表单，而是建立“宴会业务对象 + 状态流 + 事件链 + 经营分析”的数据底座。结合你之前的差距诊断，当前智链OS整体缺口之一正是“只有业务表，没有行业语义本体和决策层”，宴会系统的数据模型必须从一开始就考虑对象关系与可推理性。 



------





# **一、数据模型设计目标**





宴会管理 Agent 的数据模型，必须同时满足五类需求：



1. 支撑宴会全业务流程

   线索 → 跟进 → 报价 → 订单 → 执行 → 收款 → 评价 → 复盘

2. 支撑多门店、多厅房、多套餐、多角色协同

   不能只适配单店单厅场景

3. 支撑经营分析

   收入、成本、利润、转化率、档期利用率、来源渠道分析

4. 支撑 Agent 编排

   跟进提醒、排期推荐、自动报价、执行催办、复盘生成

5. 支撑未来本体/图谱升级

   Customer、Lead、BanquetOrder、Hall、Package、Task、Payment 之间要有明确关系





------





# **二、模型分层设计**





建议将宴会管理数据模型拆成五层：

```
L1 组织与基础主数据层
L2 客户与线索层
L3 订单与资源层
L4 执行与收款层
L5 分析、快照与Agent层
```

对应关系：

```
主数据层        → 门店、厅房、宴会类型、渠道、角色
客户线索层      → 客户、联系人、线索、跟进、报价
订单资源层      → 宴会订单、档期、套餐、菜单、资源占用
执行收款层      → 任务、异常、定金、尾款、合同、开票
分析智能层      → 成本快照、利润快照、预测结果、Agent日志
```



------





# **三、核心实体总览**





建议 V1 至少定义以下实体：





## **3.1 组织与基础主数据**





- brand
- region
- store
- banquet_hall
- banquet_hall_type
- banquet_type
- source_channel
- user
- role







## **3.2 客户与线索**





- customer
- customer_contact
- banquet_lead
- lead_followup_record
- lead_visit_record
- banquet_quote







## **3.3 订单与资源**





- banquet_order
- banquet_order_change_log
- banquet_time_slot
- banquet_hall_booking
- menu_package
- menu_package_item
- dish
- banquet_order_package_snapshot







## **3.4 执行与收款**





- banquet_contract
- banquet_payment_record
- banquet_invoice_record
- execution_template
- execution_task
- execution_task_log
- execution_exception







## **3.5 分析与 Agent**





- banquet_cost_snapshot
- banquet_profit_snapshot
- banquet_kpi_daily
- banquet_funnel_daily
- banquet_agent_rule
- banquet_agent_trigger_log
- banquet_agent_action_log
- banquet_review
- banquet_replay_snapshot





------





# **四、主数据层设计**





主数据层是所有业务关系的锚点，必须稳定、统一。



------





## **4.1 brand 品牌表**





用途：支持多品牌管理。





### **字段建议**



| **字段**   | **类型**     | **说明** |
| ---------- | ------------ | -------- |
| id         | bigint       | 主键     |
| brand_code | varchar(64)  | 品牌编码 |
| brand_name | varchar(128) | 品牌名称 |
| status     | smallint     | 状态     |
| created_at | datetime     | 创建时间 |
| updated_at | datetime     | 更新时间 |



------





## **4.2 region 区域表**





用途：支撑区域维度分析。

| **字段**    | **类型**     | **说明** |
| ----------- | ------------ | -------- |
| id          | bigint       | 主键     |
| brand_id    | bigint       | 所属品牌 |
| region_code | varchar(64)  | 区域编码 |
| region_name | varchar(128) | 区域名称 |
| status      | smallint     | 状态     |



------





## **4.3 store 门店表**





用途：宴会业务主归属对象。

| **字段**   | **类型**     | **说明** |
| ---------- | ------------ | -------- |
| id         | bigint       | 主键     |
| brand_id   | bigint       | 品牌ID   |
| region_id  | bigint       | 区域ID   |
| store_code | varchar(64)  | 门店编码 |
| store_name | varchar(128) | 门店名称 |
| store_type | varchar(64)  | 门店类型 |
| city       | varchar(64)  | 城市     |
| address    | varchar(255) | 地址     |
| status     | smallint     | 状态     |



------





## **4.4 banquet_hall_type 厅型表**





用途：标准化厅房类型。

| **字段**    | **类型**     | **说明** |
| ----------- | ------------ | -------- |
| id          | bigint       | 主键     |
| type_code   | varchar(64)  | 类型编码 |
| type_name   | varchar(64)  | 类型名称 |
| description | varchar(255) | 描述     |

示例：



- small_room
- medium_hall
- large_hall
- vip_room
- wedding_hall





------





## **4.5 banquet_hall 宴会厅/包间表**





用途：宴会资源核心表。

| **字段**     | **类型**      | **说明** |
| ------------ | ------------- | -------- |
| id           | bigint        | 主键     |
| store_id     | bigint        | 门店ID   |
| hall_type_id | bigint        | 厅型ID   |
| hall_code    | varchar(64)   | 厅房编码 |
| hall_name    | varchar(128)  | 厅房名称 |
| floor_no     | varchar(32)   | 楼层     |
| max_tables   | int           | 最大桌数 |
| max_people   | int           | 最大人数 |
| min_spend    | decimal(12,2) | 最低消费 |
| status       | smallint      | 状态     |
| is_active    | bool          | 是否启用 |



------





## **4.6 banquet_type 宴会类型表**





用途：标准化宴会类型。

| **字段**    | **类型**     | **说明** |
| ----------- | ------------ | -------- |
| id          | bigint       | 主键     |
| type_code   | varchar(64)  | 类型编码 |
| type_name   | varchar(64)  | 类型名称 |
| category    | varchar(64)  | 类别     |
| description | varchar(255) | 描述     |

示例：



- wedding
- birthday
- business
- reunion
- full_moon
- school_banquet
- family_party





------





## **4.7 source_channel 来源渠道表**





用途：线索与成交来源分析。

| **字段**     | **类型**    | **说明** |
| ------------ | ----------- | -------- |
| id           | bigint      | 主键     |
| channel_code | varchar(64) | 渠道编码 |
| channel_name | varchar(64) | 渠道名称 |
| channel_type | varchar(64) | 渠道类型 |
| status       | smallint    | 状态     |

示例：



- phone
- wechat
- douyin
- meituan
- xiaohongshu
- referral
- walkin





------





# **五、客户与线索层设计**





这一层决定宴会业务是不是“CRM 驱动”。



------





## **5.1 customer 客户表**





用途：宴会业务客户主档。

| **字段**          | **类型**     | **说明**              |
| ----------------- | ------------ | --------------------- |
| id                | bigint       | 主键                  |
| brand_id          | bigint       | 品牌ID                |
| customer_code     | varchar(64)  | 客户编码              |
| customer_type     | varchar(32)  | personal / enterprise |
| customer_name     | varchar(128) | 客户名称              |
| phone             | varchar(32)  | 主电话                |
| wechat            | varchar(64)  | 微信                  |
| source_channel_id | bigint       | 初始来源              |
| birthday          | date         | 生日，可选            |
| tags              | json         | 标签                  |
| note              | text         | 备注                  |
| created_at        | datetime     | 创建时间              |
| updated_at        | datetime     | 更新时间              |



### **说明**





一个客户可能多次办宴会，因此 customer 不能和 banquet_lead 一对一。



------





## **5.2 customer_contact 客户联系人表**





用途：支持企业客户/家庭客户多联系人。

| **字段**       | **类型**     | **说明**     |
| -------------- | ------------ | ------------ |
| id             | bigint       | 主键         |
| customer_id    | bigint       | 客户ID       |
| contact_name   | varchar(64)  | 联系人姓名   |
| phone          | varchar(32)  | 电话         |
| relation_title | varchar(64)  | 关系/职位    |
| is_primary     | bool         | 是否主联系人 |
| note           | varchar(255) | 备注         |



------





## **5.3 banquet_lead 宴会线索表**





用途：宴会商机核心对象。

| **字段**               | **类型**      | **说明** |
| ---------------------- | ------------- | -------- |
| id                     | bigint        | 主键     |
| customer_id            | bigint        | 客户ID   |
| brand_id               | bigint        | 品牌ID   |
| store_id               | bigint        | 意向门店 |
| source_channel_id      | bigint        | 渠道ID   |
| banquet_type_id        | bigint        | 宴会类型 |
| expected_date          | date          | 预期日期 |
| expected_time_slot     | varchar(64)   | 预期时段 |
| expected_people_count  | int           | 预期人数 |
| expected_table_count   | int           | 预期桌数 |
| expected_budget        | decimal(12,2) | 预算     |
| preferred_hall_type_id | bigint        | 偏好厅型 |
| current_stage          | varchar(32)   | 当前阶段 |
| owner_user_id          | bigint        | 归属销售 |
| win_probability        | decimal(5,2)  | 成交概率 |
| lost_reason            | varchar(255)  | 流失原因 |
| note                   | text          | 备注     |
| created_at             | datetime      | 创建时间 |
| updated_at             | datetime      | 更新时间 |



### **建议状态值**



```
new
contacted
visit_scheduled
visited
quoted
waiting_decision
deposit_pending
won
lost
```



------





## **5.4 lead_followup_record 跟进记录表**





用途：沉淀销售过程时间线。

| **字段**           | **类型**     | **说明**            |
| ------------------ | ------------ | ------------------- |
| id                 | bigint       | 主键                |
| lead_id            | bigint       | 线索ID              |
| followup_type      | varchar(32)  | 电话/微信/到店/报价 |
| content            | text         | 跟进内容            |
| followup_result    | varchar(128) | 跟进结果            |
| next_followup_time | datetime     | 下次跟进时间        |
| created_by         | bigint       | 创建人              |
| created_at         | datetime     | 创建时间            |



------





## **5.5 lead_visit_record 看厅记录表**





用途：记录到店看厅过程。

| **字段**          | **类型** | **说明** |
| ----------------- | -------- | -------- |
| id                | bigint   | 主键     |
| lead_id           | bigint   | 线索ID   |
| visit_date        | datetime | 看厅时间 |
| visited_store_id  | bigint   | 看厅门店 |
| visited_hall_id   | bigint   | 看厅厅房 |
| reception_user_id | bigint   | 接待人   |
| feedback          | text     | 客户反馈 |
| created_at        | datetime | 创建时间 |



------





## **5.6 banquet_quote 报价单表**





用途：报价留痕，支持多轮报价。

| **字段**            | **类型**      | **说明** |
| ------------------- | ------------- | -------- |
| id                  | bigint        | 主键     |
| lead_id             | bigint        | 线索ID   |
| quote_no            | varchar(64)   | 报价单号 |
| hall_id             | bigint        | 厅房ID   |
| package_id          | bigint        | 套餐ID   |
| quoted_people_count | int           | 报价人数 |
| quoted_table_count  | int           | 报价桌数 |
| quoted_amount       | decimal(12,2) | 报价金额 |
| discount_amount     | decimal(12,2) | 优惠金额 |
| quote_status        | varchar(32)   | 状态     |
| valid_until         | datetime      | 有效期   |
| created_by          | bigint        | 创建人   |
| created_at          | datetime      | 创建时间 |



------





# **六、订单与资源层设计**





这一层决定宴会业务是不是“交易型系统”。



------





## **6.1 banquet_time_slot 时段表**





用途：统一门店宴会可售时段。

| **字段**   | **类型**    | **说明**             |
| ---------- | ----------- | -------------------- |
| id         | bigint      | 主键                 |
| store_id   | bigint      | 门店ID               |
| slot_code  | varchar(64) | 时段编码             |
| slot_name  | varchar(64) | 时段名称             |
| start_time | time        | 开始时间             |
| end_time   | time        | 结束时间             |
| slot_type  | varchar(32) | lunch/dinner/all_day |
| status     | smallint    | 状态                 |



------





## **6.2 banquet_order 宴会订单表**





用途：宴会核心交易对象。

| **字段**        | **类型**      | **说明**   |
| --------------- | ------------- | ---------- |
| id              | bigint        | 主键       |
| order_no        | varchar(64)   | 订单号     |
| lead_id         | bigint        | 来源线索ID |
| customer_id     | bigint        | 客户ID     |
| brand_id        | bigint        | 品牌ID     |
| store_id        | bigint        | 门店ID     |
| banquet_type_id | bigint        | 宴会类型   |
| hall_id         | bigint        | 厅房ID     |
| slot_id         | bigint        | 时段ID     |
| banquet_date    | date          | 宴会日期   |
| people_count    | int           | 人数       |
| table_count     | int           | 桌数       |
| package_id      | bigint        | 套餐ID     |
| order_status    | varchar(32)   | 订单状态   |
| deposit_status  | varchar(32)   | 定金状态   |
| total_amount    | decimal(12,2) | 订单金额   |
| discount_amount | decimal(12,2) | 优惠金额   |
| actual_amount   | decimal(12,2) | 应收金额   |
| remark          | text          | 备注       |
| created_by      | bigint        | 创建人     |
| created_at      | datetime      | 创建时间   |
| updated_at      | datetime      | 更新时间   |



### **建议状态值**



```
draft
confirmed
preparing
in_progress
completed
settled
closed
cancelled
```



------





## **6.3 banquet_hall_booking 厅房占用表**





用途：档期冲突校验关键表。

| **字段**         | **类型**    | **说明**       |
| ---------------- | ----------- | -------------- |
| id               | bigint      | 主键           |
| hall_id          | bigint      | 厅房ID         |
| slot_id          | bigint      | 时段ID         |
| booking_date     | date        | 占用日期       |
| banquet_order_id | bigint      | 宴会订单ID     |
| booking_status   | varchar(32) | 锁定/占用/释放 |
| created_at       | datetime    | 创建时间       |



### **唯一约束建议**





unique(hall_id, slot_id, booking_date, booking_status in active states)



------





## **6.4 banquet_order_change_log 订单变更日志表**





用途：订单变更可追溯。

| **字段**         | **类型**    | **说明** |
| ---------------- | ----------- | -------- |
| id               | bigint      | 主键     |
| banquet_order_id | bigint      | 订单ID   |
| change_type      | varchar(64) | 变更类型 |
| field_name       | varchar(64) | 变更字段 |
| old_value        | text        | 旧值     |
| new_value        | text        | 新值     |
| changed_by       | bigint      | 操作人   |
| changed_at       | datetime    | 变更时间 |



------





## **6.5 menu_package 套餐表**





用途：宴会套餐主表。

| **字段**            | **类型**      | **说明**                 |
| ------------------- | ------------- | ------------------------ |
| id                  | bigint        | 主键                     |
| store_id            | bigint        | 门店ID，可为空表示品牌级 |
| banquet_type_id     | bigint        | 宴会类型                 |
| package_code        | varchar(64)   | 套餐编码                 |
| package_name        | varchar(128)  | 套餐名称                 |
| price               | decimal(12,2) | 套餐售价                 |
| target_people_min   | int           | 最少人数                 |
| target_people_max   | int           | 最多人                   |
| gross_margin_target | decimal(5,2)  | 目标毛利率               |
| status              | smallint      | 状态                     |



------





## **6.6 menu_package_item 套餐菜品表**





用途：套餐与菜品映射。

| **字段**      | **类型**      | **说明**               |
| ------------- | ------------- | ---------------------- |
| id            | bigint        | 主键                   |
| package_id    | bigint        | 套餐ID                 |
| dish_id       | bigint        | 菜品ID                 |
| item_type     | varchar(32)   | 主菜/凉菜/汤/甜点/酒水 |
| quantity      | decimal(10,2) | 数量                   |
| unit          | varchar(32)   | 单位                   |
| replace_group | varchar(64)   | 替换组                 |
| sort_no       | int           | 排序                   |



------





## **6.7 dish 菜品表**





若主系统已有菜品表，可复用；否则宴会系统保留快照型映射。

| **字段**       | **类型**      | **说明** |
| -------------- | ------------- | -------- |
| id             | bigint        | 主键     |
| dish_code      | varchar(64)   | 菜品编码 |
| dish_name      | varchar(128)  | 菜名     |
| category       | varchar(64)   | 分类     |
| standard_price | decimal(12,2) | 标准售价 |
| estimated_cost | decimal(12,2) | 预估成本 |
| status         | smallint      | 状态     |



------





## **6.8 banquet_order_package_snapshot 订单套餐快照表**





用途：避免后续套餐修改影响历史订单。

| **字段**         | **类型**      | **说明** |
| ---------------- | ------------- | -------- |
| id               | bigint        | 主键     |
| banquet_order_id | bigint        | 订单ID   |
| package_id       | bigint        | 原套餐ID |
| snapshot_json    | json          | 套餐快照 |
| snapshot_amount  | decimal(12,2) | 快照金额 |
| created_at       | datetime      | 创建时间 |



------





# **七、执行与收款层设计**





这一层决定宴会系统是不是“协同型系统”。



------





## **7.1 banquet_contract 合同表**



| **字段**         | **类型**     | **说明** |
| ---------------- | ------------ | -------- |
| id               | bigint       | 主键     |
| banquet_order_id | bigint       | 订单ID   |
| contract_no      | varchar(64)  | 合同号   |
| contract_status  | varchar(32)  | 状态     |
| file_url         | varchar(255) | 文件地址 |
| signed_at        | datetime     | 签订时间 |
| created_at       | datetime     | 创建时间 |



------





## **7.2 banquet_payment_record 收款记录表**





用途：记录定金、尾款、其他款项。

| **字段**         | **类型**      | **说明**              |
| ---------------- | ------------- | --------------------- |
| id               | bigint        | 主键                  |
| banquet_order_id | bigint        | 订单ID                |
| payment_type     | varchar(32)   | deposit/balance/other |
| payment_method   | varchar(32)   | 现金/微信/支付宝/转账 |
| amount           | decimal(12,2) | 金额                  |
| payment_status   | varchar(32)   | 状态                  |
| paid_at          | datetime      | 支付时间              |
| operator_user_id | bigint        | 操作人                |
| note             | varchar(255)  | 备注                  |



------





## **7.3 banquet_invoice_record 开票记录表**



| **字段**         | **类型**      | **说明**  |
| ---------------- | ------------- | --------- |
| id               | bigint        | 主键      |
| banquet_order_id | bigint        | 订单ID    |
| invoice_type     | varchar(32)   | 普票/专票 |
| invoice_title    | varchar(128)  | 抬头      |
| invoice_amount   | decimal(12,2) | 金额      |
| invoice_status   | varchar(32)   | 状态      |
| issued_at        | datetime      | 开票时间  |



------





## **7.4 execution_template 执行模板表**





用途：定义不同宴会类型任务模板。

| **字段**        | **类型**     | **说明** |
| --------------- | ------------ | -------- |
| id              | bigint       | 主键     |
| template_name   | varchar(128) | 模板名称 |
| banquet_type_id | bigint       | 宴会类型 |
| version         | int          | 版本     |
| status          | smallint     | 状态     |
| created_at      | datetime     | 创建时间 |



------





## **7.5 execution_task 执行任务表**





用途：宴会执行核心任务表。

| **字段**           | **类型**     | **说明**                 |
| ------------------ | ------------ | ------------------------ |
| id                 | bigint       | 主键                     |
| banquet_order_id   | bigint       | 订单ID                   |
| template_id        | bigint       | 模板ID                   |
| parent_task_id     | bigint       | 父任务ID                 |
| task_type          | varchar(64)  | 采购/厨房/服务/布场/设备 |
| task_name          | varchar(128) | 任务名称                 |
| owner_role         | varchar(64)  | 负责人角色               |
| owner_user_id      | bigint       | 负责人                   |
| planned_start_time | datetime     | 计划开始                 |
| due_time           | datetime     | 截止时间                 |
| completed_at       | datetime     | 完成时间                 |
| task_status        | varchar(32)  | 状态                     |
| priority           | varchar(16)  | 优先级                   |
| note               | text         | 备注                     |



### **建议状态值**



```
pending
in_progress
done
verified
closed
overdue
```



------





## **7.6 execution_task_log 任务日志表**





用途：追踪任务过程。

| **字段**       | **类型**    | **说明**                 |
| -------------- | ----------- | ------------------------ |
| id             | bigint      | 主键                     |
| task_id        | bigint      | 任务ID                   |
| action_type    | varchar(64) | 创建/开始/完成/转派/催办 |
| action_content | text        | 操作内容                 |
| action_by      | bigint      | 操作人                   |
| action_at      | datetime    | 操作时间                 |



------





## **7.7 execution_exception 异常事件表**





用途：现场异常上报与处理。

| **字段**         | **类型**    | **说明**                 |
| ---------------- | ----------- | ------------------------ |
| id               | bigint      | 主键                     |
| banquet_order_id | bigint      | 订单ID                   |
| task_id          | bigint      | 关联任务，可为空         |
| exception_type   | varchar(64) | 类型                     |
| severity         | varchar(16) | low/medium/high/critical |
| description      | text        | 描述                     |
| owner_user_id    | bigint      | 责任人                   |
| status           | varchar(32) | 状态                     |
| resolved_at      | datetime    | 解决时间                 |
| created_by       | bigint      | 创建人                   |
| created_at       | datetime    | 创建时间                 |



------





# **八、成本、利润与分析层设计**





这一层决定宴会系统是不是“经营系统”。



------





## **8.1 banquet_cost_snapshot 成本快照表**





用途：沉淀单场宴会成本结构。

| **字段**         | **类型**      | **说明** |
| ---------------- | ------------- | -------- |
| id               | bigint        | 主键     |
| banquet_order_id | bigint        | 订单ID   |
| ingredient_cost  | decimal(12,2) | 食材成本 |
| beverage_cost    | decimal(12,2) | 酒水成本 |
| labor_cost       | decimal(12,2) | 人工成本 |
| decoration_cost  | decimal(12,2) | 布场成本 |
| gift_cost        | decimal(12,2) | 赠送成本 |
| other_cost       | decimal(12,2) | 其他成本 |
| total_cost       | decimal(12,2) | 总成本   |
| snapshot_time    | datetime      | 快照时间 |



------





## **8.2 banquet_profit_snapshot 利润快照表**





用途：单场宴会利润结果。

| **字段**         | **类型**      | **说明** |
| ---------------- | ------------- | -------- |
| id               | bigint        | 主键     |
| banquet_order_id | bigint        | 订单ID   |
| revenue_amount   | decimal(12,2) | 收入     |
| discount_amount  | decimal(12,2) | 优惠     |
| actual_income    | decimal(12,2) | 实收     |
| total_cost       | decimal(12,2) | 总成本   |
| gross_profit     | decimal(12,2) | 毛利     |
| gross_margin     | decimal(5,2)  | 毛利率   |
| snapshot_time    | datetime      | 快照时间 |



------





## **8.3 banquet_kpi_daily 日指标表**





用途：日报聚合。

| **字段**              | **类型**      | **说明**   |
| --------------------- | ------------- | ---------- |
| id                    | bigint        | 主键       |
| brand_id              | bigint        | 品牌ID     |
| store_id              | bigint        | 门店ID     |
| stat_date             | date          | 统计日期   |
| lead_count            | int           | 线索数     |
| quote_count           | int           | 报价数     |
| order_count           | int           | 订单数     |
| completed_order_count | int           | 完成单数   |
| revenue_amount        | decimal(12,2) | 收入       |
| gross_profit          | decimal(12,2) | 毛利       |
| hall_utilization      | decimal(5,2)  | 厅房利用率 |



------





## **8.4 banquet_funnel_daily 漏斗聚合表**





用途：销售漏斗分析。

| **字段**              | **类型** | **说明** |
| --------------------- | -------- | -------- |
| id                    | bigint   | 主键     |
| store_id              | bigint   | 门店ID   |
| stat_date             | date     | 日期     |
| new_count             | int      | 新线索   |
| contacted_count       | int      | 已联系   |
| visited_count         | int      | 已看厅   |
| quoted_count          | int      | 已报价   |
| deposit_pending_count | int      | 待定金   |
| won_count             | int      | 已成交   |
| lost_count            | int      | 已流失   |



------





## **8.5 banquet_review 评价表**





用途：宴会后评价/满意度。

| **字段**         | **类型** | **说明** |
| ---------------- | -------- | -------- |
| id               | bigint   | 主键     |
| banquet_order_id | bigint   | 订单ID   |
| customer_id      | bigint   | 客户ID   |
| rating           | int      | 评分     |
| review_content   | text     | 评价内容 |
| complaint_flag   | bool     | 是否投诉 |
| created_at       | datetime | 创建时间 |



------





## **8.6 banquet_replay_snapshot 复盘快照表**





用途：沉淀复盘结果。

| **字段**         | **类型**    | **说明**            |
| ---------------- | ----------- | ------------------- |
| id               | bigint      | 主键                |
| banquet_order_id | bigint      | 订单ID              |
| summary_json     | json        | 复盘摘要            |
| issues_json      | json        | 异常清单            |
| suggestions_json | json        | 优化建议            |
| generated_by     | varchar(32) | system/manual/agent |
| created_at       | datetime    | 创建时间            |



------





# **九、Agent 层数据模型设计**





V1 Agent 先以“规则 + 触发 + 日志”实现。



------





## **9.1 banquet_agent_rule Agent规则表**



| **字段**        | **类型**    | **说明**                 |
| --------------- | ----------- | ------------------------ |
| id              | bigint      | 主键                     |
| agent_type      | varchar(64) | 跟进/报价/排期/执行/复盘 |
| trigger_event   | varchar(64) | 触发事件                 |
| rule_expression | text        | 规则表达式               |
| action_template | text        | 动作模板                 |
| status          | smallint    | 状态                     |
| priority        | int         | 优先级                   |



------





## **9.2 banquet_agent_trigger_log 触发日志表**



| **字段**            | **类型**    | **说明**        |
| ------------------- | ----------- | --------------- |
| id                  | bigint      | 主键            |
| rule_id             | bigint      | 规则ID          |
| agent_type          | varchar(64) | Agent类型       |
| related_object_type | varchar(64) | lead/order/task |
| related_object_id   | bigint      | 对象ID          |
| trigger_time        | datetime    | 触发时间        |
| trigger_payload     | json        | 触发载荷        |
| result_status       | varchar(32) | 结果状态        |



------





## **9.3 banquet_agent_action_log 行动日志表**



| **字段**       | **类型**    | **说明**                    |
| -------------- | ----------- | --------------------------- |
| id             | bigint      | 主键                        |
| trigger_log_id | bigint      | 触发日志ID                  |
| action_type    | varchar(64) | 提醒/推荐/生成任务/生成草稿 |
| action_target  | varchar(64) | 用户/任务/订单              |
| action_result  | text        | 结果                        |
| created_at     | datetime    | 创建时间                    |



------





# **十、核心关系设计**





这一部分是未来“宴会知识图谱”的基础。



------





## **10.1 关键一对多关系**





- brand 1:N store
- store 1:N banquet_hall
- customer 1:N customer_contact
- customer 1:N banquet_lead
- banquet_lead 1:N lead_followup_record
- banquet_lead 1:N banquet_quote
- banquet_lead 1:0..1 banquet_order
- banquet_order 1:N banquet_payment_record
- banquet_order 1:N execution_task
- banquet_order 1:N execution_exception





------





## **10.2 关键多对一关系**





- banquet_order N:1 banquet_hall
- banquet_order N:1 banquet_time_slot
- banquet_order N:1 menu_package
- execution_task N:1 execution_template
- banquet_kpi_daily N:1 store





------





## **10.3 关键快照关系**





- banquet_order 1:1 banquet_order_package_snapshot
- banquet_order 1:N banquet_cost_snapshot
- banquet_order 1:N banquet_profit_snapshot
- banquet_order 1:N banquet_replay_snapshot





------





# **十一、状态流设计**





状态流是数据模型不可缺的一部分。



------





## **11.1 线索状态流**



```
new
→ contacted
→ visit_scheduled
→ visited
→ quoted
→ waiting_decision
→ deposit_pending
→ won
→ lost
```

规则：



- won 后可转订单
- lost 后必须记录 lost_reason





------





## **11.2 订单状态流**



```
draft
→ confirmed
→ preparing
→ in_progress
→ completed
→ settled
→ closed
→ cancelled
```

规则：



- confirmed 时必须成功锁档
- preparing 时必须有任务清单
- completed 后才能进入 settled





------





## **11.3 收款状态流**





定金状态：

```
unpaid
→ partial
→ paid
```

尾款状态：

```
pending
→ paid
→ overdue
```



------





## **11.4 任务状态流**



```
pending
→ in_progress
→ done
→ verified
→ closed
→ overdue
```



------





## **11.5 异常状态流**



```
open
→ processing
→ resolved
→ closed
```



------





# **十二、索引与约束建议**





为保证系统性能与一致性，建议添加以下约束。



------





## **12.1 唯一约束**





- customer.customer_code
- banquet_lead 唯一业务键可为 (customer_id, banquet_type_id, expected_date, store_id) 的弱唯一校验
- banquet_order.order_no
- banquet_contract.contract_no
- banquet_quote.quote_no





------





## **12.2 核心索引**







### **banquet_lead**





- idx_owner_stage(owner_user_id, current_stage)
- idx_expected_date(expected_date)
- idx_store_stage(store_id, current_stage)







### **banquet_order**





- idx_store_date(store_id, banquet_date)
- idx_status(order_status)
- idx_customer(customer_id)







### **banquet_hall_booking**





- idx_hall_slot_date(hall_id, slot_id, booking_date)







### **execution_task**





- idx_owner_status(owner_user_id, task_status)
- idx_order_status(banquet_order_id, task_status)
- idx_due_time(due_time)







### **banquet_payment_record**





- idx_order_type_status(banquet_order_id, payment_type, payment_status)





------





## **12.3 外键建议**





V1 若追求开发效率，可用“应用层保证 + 关键外键”；

核心外键建议保留在：



- store / hall
- customer / lead
- lead / order
- order / payment
- order / task





------





# **十三、面向 BI 与分析的派生模型建议**





为提高报表与驾驶舱性能，建议做以下派生表或物化视图：



- mv_banquet_revenue_by_store_day
- mv_banquet_profit_by_store_month
- mv_banquet_funnel_by_sales_day
- mv_banquet_hall_utilization_by_day
- mv_banquet_source_conversion_by_month
- mv_banquet_package_profit_rank





------





# **十四、面向图谱/本体演进的对象模型建议**





如果后续升级为“宴会经营图谱”，建议将以下对象显式建模：



节点：



- Customer
- Lead
- BanquetOrder
- BanquetHall
- TimeSlot
- Package
- Dish
- Task
- Payment
- Feedback
- Channel





关系：



- Customer HAS Lead
- Lead CONVERTS_TO Order
- Order USES Hall
- Order OCCURS_AT TimeSlot
- Order SELECTS Package
- Package CONTAINS Dish
- Order GENERATES Task
- Order HAS Payment
- Order RECEIVES Feedback
- Lead COMES_FROM Channel





这会支撑未来的多跳问题，例如：



- 哪类渠道来的婚宴客户更容易成交高毛利套餐
- 哪些厅房高峰时段被低利润宴会占用
- 哪类任务异常最容易导致客户投诉





------





# **十五、与其他系统的数据耦合点**





------





## **15.1 与供应链系统**





映射：



- 菜品成本
- 套餐食材消耗
- 采购占用





建议字段：



- dish_id
- ingredient_cost
- inventory_reservation_id





------





## **15.2 与人力系统**





映射：



- 任务负责人
- 服务人员安排
- 排班需求





建议字段：



- owner_user_id
- owner_role
- schedule_request_id





------





## **15.3 与财务系统**





映射：



- 收款状态
- 发票状态
- 利润核算





建议字段：



- payment_record_id
- invoice_record_id
- finance_voucher_id





------





## **15.4 与会员/私域系统**





映射：



- 老客识别
- 宴会客户沉淀
- 二次营销





建议字段：



- member_id
- campaign_id
- referral_customer_id





------





# **十六、V1 落地建议**





如果要快速进入开发，推荐优先落地以下表：





## **必须先建**





- customer
- customer_contact
- banquet_lead
- lead_followup_record
- banquet_hall
- banquet_time_slot
- banquet_order
- banquet_hall_booking
- menu_package
- menu_package_item
- banquet_payment_record
- execution_task
- execution_exception







## **第二批再建**





- banquet_quote
- banquet_contract
- banquet_cost_snapshot
- banquet_profit_snapshot
- banquet_kpi_daily
- banquet_agent_rule
- banquet_agent_action_log
- banquet_review







## **后续增强**





- banquet_funnel_daily
- banquet_replay_snapshot
- 图谱层节点表/关系表
- 预测结果表





------





# **十七、数据模型一句话总结**





**智链OS 宴会管理 Agent 数据模型 V1** 的核心不是多几张表，

而是建立这样一套业务结构：



> 客户可追踪、线索可流转、订单可锁档、套餐可快照、任务可协同、收款可核对、利润可分析、Agent 可触发。



再直白一点：



> 这套模型要让宴会业务从“靠人记”

> 升级成“系统可理解、可执行、可分析、可复盘”的经营数据系统。



