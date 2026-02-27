# 智链OS 业财税资金一体化 — 完全闭环管理与操作检测报告

本文档从**完全闭环**角度检测 FCT 项目：各业务流是否能在系统内完成「从发生到结果」的全流程管理与操作，并给出结论与缺口清单。

---

## 一、「完全闭环」定义

**完全闭环**：在智链OS（或 FCT 独立部署）内，无需依赖外部系统手工补录或线下处理，即可完成：

1. **数据闭环**：业务发生 → 进入业财 → 生成凭证/总账/资金/税务数据 → 可查询、可追溯。
2. **操作闭环**：创建、审批、过账、勾对、结账、报表等动作均有对应 API 或界面，且前后衔接。
3. **管理闭环**：主数据、期间、权限、预算/审批等管控动作可在系统内配置与执行。

以下按**业务流维度**逐项检测。

---

## 二、分项闭环检测

### 2.1 业 → 财（业务事件 → 凭证）

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 事件接入 | POST /events（门店日结、采购入库等） | ✅ 闭环 | 幂等、规则引擎自动生成凭证 |
| 对账联动 | POS 对账完成后自动推送日结事件 | ✅ 闭环 | reconciliation 执行成功后若 FCT_ENABLED 则 push_store_daily_settlement_event |
| 凭证来源标识 | event_id、event_type、voucher_id 回写事件表 | ✅ 闭环 | 可追溯业务→凭证 |
| 其他事件类型 | 平台结算、储值、薪酬等 | 🔶 部分 | 仅日结/采购有规则，其余需扩展规则或手工凭证 |

**结论**：业→财主链路（日结/采购）**可完全闭环**；其他业务类型需补规则或用手工凭证补全。

---

### 2.2 凭证 → 总账（过账与余额/明细）

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 凭证状态 | draft / pending / approved / posted / rejected | ✅ 闭环 | 模型与 API 支持 |
| 过账 | PATCH /vouchers/{id}/status，draft→posted | ✅ 闭环 | 过账后进入总账 |
| 总账余额 | GET /ledger/balances（默认仅已过账） | ✅ 闭环 | 按科目汇总 |
| 总账明细 | GET /ledger/entries（按科目/主体/日期） | ✅ 闭环 | 可钻取到凭证 |
| 手工凭证 | POST /vouchers，来源 manual | ✅ 闭环 | 调账、计提可在系统内完成 |

**结论**：凭证→总账 **可完全闭环**。

---

### 2.3 资金（流水、录入、与凭证关联）

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 流水列表 | GET /cash/transactions | ✅ 闭环 | 分页、筛选 |
| 流水录入 | POST /cash/transactions（收/付，可选生成凭证） | ✅ 闭环 | ref_type=manual，可选 ref_id 指向凭证 |
| 流水→凭证 | generate_voucher=true 时自动生成凭证并写 ref_id | ✅ 闭环 | 款与账可关联 |
| 对账状态 | GET /cash/reconciliation（未匹配笔数/金额） | ✅ 闭环 | 统计 status=pending |
| **流水勾对** | 将某笔流水标记为已匹配（更新 status/match_id） | ✅ 闭环 | PATCH /cash/transactions/{id}/match；取消匹配传 match_id 空 |
| **流水导入** | 批量导入银行/业务流水 | ✅ 闭环 | POST /cash/transactions/import，按 ref_id 去重 |

**结论**：资金**录入、勾对、批量导入与凭证关联可闭环**。

---

### 2.4 票 → 账（发票与凭证）

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 发票与凭证关联 | POST /invoices/link，GET /invoices/by-voucher/{id} | ✅ 闭环 | 票-账关联可维护、可查 |
| 验真占位 | POST /invoices/{id}/verify，verify_status/verified_at | ✅ 闭环 | 状态占位，真实验真需对接税控/全电 |
| 发票列表 | GET /tax/invoices | ✅ 闭环 | 占位数据可维护 |

**结论**：票-账关联与验真状态 **可闭环**（真实开票/采集/勾选依赖外部对接）。

---

### 2.5 税务申报

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 申报列表占位 | GET /tax/declarations | ✅ 可查 | 占位 |
| 申报表取数 | 从总账/发票自动生成申报表 | ✅ 闭环 | GET /tax/declarations/draft?tax_type=vat&period=YYYYMM，从总账取销项/进项/应纳税额 |
| 税局对接 | 申报提交、回执 | ❌ 未闭环 | 待对接 |

**结论**：申报表取数**可闭环**；税局提交与回执依赖外部对接。

---

### 2.6 费控/备用金、预算、审批

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 备用金主档与流水 | PUT/GET /petty-cash，POST /petty-cash/records | ✅ 闭环 | 申请/冲销/还款、余额更新 |
| 预算编制与占用 | PUT /budgets，GET /budgets/check，POST /budgets/occupy | ✅ 闭环 | 超预算可校验、占用可记录 |
| 预算与凭证/付款联动 | 创建凭证或付款时强制校验/占用预算 | ✅ 闭环 | PUT /budgets/control 配置 enforce_check/auto_occupy；制单/过账/付款时按配置强制校验或自动占用 |
| 审批记录 | POST /approvals，GET /approvals/by-ref | ✅ 闭环 | 占位留痕，与 OA 可扩展 |

**结论**：费控/备用金、预算、审批及**预算强制联动**均可闭环。

---

### 2.7 报表与计划

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 期间汇总/四维/趋势/门店/区域/同比环比 | GET /reports/* | ✅ 闭环 | 基于凭证与总账 |
| 年度计划与达成 | PUT/GET /plans，plan_vs_actual | ✅ 闭环 | 目标与实绩对比 |
| 合并报表 | 多主体合并、内部抵销 | ✅ 闭环（简化） | GET /reports/consolidated?period=YYYYMM&group_by=entity|all，多主体总账汇总；内部抵销可后续扩展 |

**结论**：单主体报表与计划、多主体合并汇总**可闭环**；内部抵销规则可后续扩展。

---

### 2.8 会计期间与结账

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 期间定义 | 自然月/季/年 | ✅ 闭环 | 期间主数据 fct_periods，GET /periods，按 period_key 自动生成自然月 |
| 期间锁定/结账 | 结账后禁止该期间凭证新增/修改/过账/作废 | ✅ 闭环 | POST /periods/{period_key}/close、/reopen；结账前校验无草稿凭证 |
| 报表按期间 | 总账/报表支持 period=YYYYMM 取数 | ✅ 闭环 | GET /ledger/balances、GET /reports/* 支持 period 参数，与 start_date/end_date 二选一 |

**结论**：会计期间与结账**可闭环**。

---

### 2.9 主数据与权限

| 环节 | 能力 | 状态 | 说明 |
|------|------|------|------|
| 主数据 | PUT/GET /master（门店、客商、科目、银行账户） | ✅ 闭环 | 与业务/财务共用 |
| FCT 权限 | FCT_READ / FCT_WRITE，合并形态 JWT | ✅ 闭环 | 可控制读写 |
| 独立形态认证 | X-API-Key | ✅ 闭环 | 独立部署可用 |

**结论**：主数据与权限**可闭环**。

---

## 三、总体结论：能否完全闭环？

| 维度 | 是否完全闭环 | 说明 |
|------|--------------|------|
| **业→财（日结/采购）** | ✅ 是 | 事件→凭证→过账→总账，对账联动有 |
| **凭证→总账** | ✅ 是 | 手工凭证、过账、余额、明细齐全 |
| **资金（录入+凭证）** | ✅ 是 | 流水录入、可选生成凭证、关联清晰 |
| **资金（流水勾对/导入）** | ✅ 是 | 勾对 API、批量导入 API 已落地 |
| **票-账** | ✅ 是 | 发票与凭证关联、验真占位可维护 |
| **税务申报** | 🔶 部分 | 申报表取数（draft）已闭环；税局提交待对接 |
| **费控/预算/审批** | ✅ 是 | 预算控制配置（PUT/GET /budgets/control）支持强制校验与自动占用 |
| **报表与计划** | ✅ 是 | 多维度报表、计划 vs 实际、合并报表（简化汇总）已落地 |
| **期间与结账** | ✅ 是 | 期间主数据、结账/反结账、总账/报表按 period 取数已落地 |
| **主数据与权限** | ✅ 是 | 满足闭环 |

**综合结论**：

- **业财税资金在系统内**已支持**完全闭环**（业财、凭证总账、资金录入/勾对/导入、票账、申报取数、期间与结账、合并报表、主数据与权限）。**预算与凭证/付款强制联动**可通过预算控制配置开启；税局申报提交为外部对接。

---

## 四、缺口清单（影响完全闭环的项）

以下按**优先级**与**闭环影响**列出缺口，每项含：验收标准、接口/实现要点、依赖、涉及模型或代码位置。

### 4.1 汇总表

| 序号 | 缺口 | 优先级 | 影响闭环 |
|------|------|--------|----------|
| 1 | 资金流水勾对 API | P1 | 资金「录入→勾对」无法在系统内完成 | ✅ 已落地：PATCH /cash/transactions/{id}/match |
| 2 | 会计期间与结账 | P2 | 无法按期间锁账、报表无期间口径 | ✅ 已落地：GET /periods、POST /periods/{key}/close、/reopen |
| 3 | 预算与凭证/付款强制联动 | P2 | 超预算仍可制单/过账 | ✅ 已落地：凭证/资金 API 可选 budget_check、budget_occupy |
| 4 | 凭证红冲/作废 | P2 | 错证无法在系统内红冲或作废，仅能查 | ✅ 已落地：POST /vouchers/{id}/void、/red-flush |
| 5 | 税务申报取数 | P3 | 申报表不能从总账/发票自动产出 | ✅ 已落地：GET /tax/declarations/draft |
| 6 | 合并报表 | P3 | 多主体合并、内部抵销无法在系统内完成 | ✅ 已落地：GET /reports/consolidated（简化汇总） |
| 7 | 银企直连/流水导入 | P3 | 银行流水依赖外部写入 | ✅ 已落地：POST /cash/transactions/import |
| 8 | 发票登记 CRUD | P2 | 进项/销项发票仅能列表与关联，无法在系统内登记新票 | ✅ 已落地：POST/PATCH /tax/invoices |
| 9 | 业财事件规则扩展 | P3 | 平台结算、储值、薪酬等无自动凭证规则 | ✅ 已落地：platform_settlement、member_stored_value |

---

### 4.2 缺口 1：资金流水勾对 API

| 项 | 内容 |
|----|------|
| **验收标准** | 支持将指定资金流水标记为「已匹配」，并写入匹配标识；GET /cash/reconciliation 的未匹配数随之减少；支持取消匹配（改回 pending）。 |
| **接口建议** | `PATCH /cash/transactions/{transaction_id}/match`，body：`{ "match_id": "uuid?", "match_type": "bank_receipt" \| "business" \| "manual", "remark": "?" }`；取消匹配：`PATCH .../unmatch` 或同一接口 `match_id: null`。 |
| **实现要点** | 更新 `FctCashTransaction.status` 为 `matched`、`match_id` 为传入 UUID；可选扩展表记录匹配对（本方流水 id、对方流水/业务单 id、匹配时间）。仅允许对 `status=pending` 的流水执行匹配。 |
| **依赖** | 无；现有表已有 `status`、`match_id` 列（`fct_cash_transactions`）。 |
| **涉及代码** | `src/models/fct.py`（FctCashTransaction）；`src/services/fct_service.py`（新增 `match_cash_transaction`、`unmatch_cash_transaction`）；`src/api/fct.py`、`fct_public.py`。 |

---

### 4.3 缺口 2：会计期间与结账

| 项 | 内容 |
|----|------|
| **验收标准** | 支持按租户配置会计期间（自然月/季/年）；支持对某期间执行「结账」后，该期间凭证不允许新增/修改/删除，总账余额与报表按「已结账期间」取数；支持反结账（可选、需权限）。 |
| **接口建议** | `GET/PUT /fct/periods` 期间列表与配置；`POST /fct/periods/{period_key}/close` 结账；`POST /fct/periods/{period_key}/reopen` 反结账（可选）；`GET /ledger/balances`、`GET /reports/*` 增加参数 `period`（如 202502）。 |
| **实现要点** | 新增表 `fct_periods`（tenant_id、period_key、start_date、end_date、status=open/closed、closed_at）；结账时校验该期间内无 draft 凭证，然后 status=closed；报表与总账查询增加「按期间过滤」逻辑。 |
| **依赖** | 无；与现有凭证 biz_date、总账查询兼容。 |
| **涉及代码** | 新增模型与迁移；`fct_service` 结账/反结账、报表按期间；`fct.py`/`fct_public.py` 新路由。 |

---

### 4.4 缺口 3：预算与凭证/付款强制联动

| 项 | 内容 |
|----|------|
| **验收标准** | 可配置「某预算维度下制单/过账/付款前必须校验预算」；超预算时拒绝创建凭证或拒绝过账（或仅预警、由配置决定）；占用预算可在凭证过账或付款时自动调用 occupy_budget。 |
| **接口建议** | 配置可放在主数据或独立「预算控制配置」表；现有 `POST /vouchers`、`PATCH /vouchers/{id}/status`、`POST /cash/transactions` 在实现内可选调用 `check_budget`，超预算返回 400 及剩余额度；过账/付款成功时可选调用 `occupy_budget`。 |
| **实现要点** | 新增「预算控制配置」（如 tenant、entity、budget_type、category、action=block/warn、是否自动占用）；在 `create_manual_voucher`、`update_voucher_status`（过账）、`create_cash_transaction` 中按配置调用 `check_budget`/`occupy_budget`。 |
| **依赖** | 依赖现有 `check_budget`、`occupy_budget`、`FctBudget`。 |
| **涉及代码** | `src/services/fct_service.py`（凭证创建/过账、资金录入处增加预算校验与占用）；可选新表与 API 管理配置。 |

---

### 4.5 缺口 4：凭证红冲/作废

| 项 | 内容 |
|----|------|
| **验收标准** | 支持对已过账凭证做「红冲」（生成红字凭证，借贷相反、金额为负或红字标识）；或「作废」（凭证状态改为 voided，不再参与总账）；红冲凭证可追溯原凭证。 |
| **接口建议** | `POST /vouchers/{id}/red-flush` 红冲（生成新凭证，event_type=red_flush，attachments 含 original_voucher_id）；`PATCH /vouchers/{id}/status` 扩展 status=voided（作废），或新增 `POST /vouchers/{id}/void`。总账与报表排除 voided 或仅按红冲后净额汇总。 |
| **实现要点** | 红冲：复制原凭证分录、借贷互换或金额取反，新凭证与原凭证关联；作废：更新 status=voided，get_ledger_balances/get_ledger_entries 过滤掉 voided。需约定：已结账期间是否允许红冲/作废（通常不允许）。 |
| **依赖** | 与「会计期间与结账」配合更佳（结账后禁止红冲/作废）。 |
| **涉及代码** | `FctVoucherStatus` 增加 VOIDED（若作废）；`fct_service` 新增 `red_flush_voucher`、`void_voucher`；总账/报表查询过滤 voided；`fct.py`/`fct_public.py` 新路由。 |

---

### 4.6 缺口 5：税务申报取数 ✅ 已落地

| 项 | 内容 |
|----|------|
| **验收标准** | 支持按税种与所属期从总账/发票数据生成申报表草稿（如增值税申报表主表、附表）；结果可通过 API 返回或导出，供人工确认后提交税局。 |
| **接口** | `GET /tax/declarations/draft?tenant_id=&tax_type=vat&period=202502` 返回 output_tax、input_tax、net_tax、source=ledger。 |
| **实现** | `fct_service.get_tax_declaration_draft` 从已过账凭证 2221/2221_01 科目按期间汇总；`fct.py`、`fct_public.py` 已挂载。 |

---

### 4.7 缺口 6：合并报表 ✅ 已落地（简化汇总）

| 项 | 内容 |
|----|------|
| **验收标准** | 支持多主体（多法人/多门店）报表汇总；支持内部往来、内部交易抵销规则配置；支持按合并主体或组出表（如按区域、品牌）。 |
| **接口** | `GET /reports/consolidated?tenant_id=&period=202502&group_by=entity|all`；group_by=entity 按主体返回 by_entity，group_by=all 或不传返回全主体汇总 balances。 |
| **实现** | `fct_service.get_report_consolidated` 多主体总账汇总，当前不做内部抵销；抵销规则可后续扩展。 |

---

### 4.8 缺口 7：银企直连/流水导入 ✅ 已落地

| 项 | 内容 |
|----|------|
| **验收标准** | 支持从外部（文件或银企接口）批量导入银行流水到 `fct_cash_transactions`，或通过定时任务拉取银行流水并写入；导入/拉取后可配合「流水勾对」在系统内完成勾对。 |
| **接口** | `POST /cash/transactions/import`，body：tenant_id、entity_id、items=[{tx_date, amount, direction, ref_id?, description?}]、ref_type?=bank、skip_duplicate_ref_id?=true。 |
| **实现** | `fct_service.import_cash_transactions` 按 ref_id 去重（可选）；ref_type=bank；返回 imported、skipped、errors。 |

---

### 4.9 缺口 8：发票登记 CRUD

| 项 | 内容 |
|----|------|
| **验收标准** | 支持在系统内新增/编辑进项或销项发票（发票号、金额、税额、日期、类型等），而不仅依赖事件或外部同步；列表、关联、验真已有，补「创建/更新」即可形成发票主数据闭环。 |
| **接口建议** | `POST /tax/invoices` 登记发票（tenant_id、entity_id、invoice_type、invoice_no、amount、tax_amount、invoice_date 等）；`PATCH /tax/invoices/{id}` 更新；删除可为软删或仅允许未关联凭证的删除。 |
| **实现要点** | `FctTaxInvoice` 已存在，新增 `create_tax_invoice`、`update_tax_invoice`；校验发票号在同 tenant 下唯一（或同主体+类型+号码唯一）。 |
| **依赖** | 无；现有表与 list、link、verify 兼容。 |
| **涉及代码** | `src/services/fct_service.py` 新增发票创建/更新；`src/api/fct.py`、`fct_public.py` 新增 POST/PATCH /tax/invoices。 |

---

### 4.10 缺口 9：业财事件规则扩展 ✅ 已落地（部分）

| 项 | 内容 |
|----|------|
| **验收标准** | 平台结算、会员储值、薪酬等事件类型在推送至 POST /events 后，能按规则自动生成凭证（或明确返回「暂无规则」由调用方改用手工凭证）。 |
| **已实现** | `platform_settlement`（借银行存款/销售费用 贷应收账款）、`member_stored_value`（储值 charge/consume/refund）；`_rule_engine_dispatch` 已扩展；薪酬等可后续增加。 |

---

### 4.11 实施顺序建议

| 阶段 | 缺口项 | 说明 |
|------|--------|------|
| **第一阶段** | 1 资金流水勾对、8 发票登记 CRUD | 补全资金与发票在系统内的完整操作链，表结构已就绪，改动面小 |
| **第二阶段** | 2 会计期间与结账、3 预算强制联动、4 凭证红冲/作废 | 提升管控与合规，期间结账可与红冲/作废一起设计（结账后禁止红冲） |
| **第三阶段** | 5 税务申报取数、6 合并报表、7 银企/流水导入、9 业财规则扩展 | 按客户需求与资源排期，申报与合并可并行，银企与规则扩展可独立 |

---

## 五、与现有文档关系

| 文档 | 关系 |
|------|------|
| [FCT 财务部门可正常使用完整性评估](./fct-completeness-for-finance-department.md) | 从「可正常使用」角度评估；本报告从「完全闭环」角度检测，并明确勾对/期间/申报/合并等缺口。 |
| [业财税资金一体化技术方案](./chain-restaurant-finance-tax-treasury-technical-solution.md) | 技术方案与实施进度；本报告结论可同步到其实施进度或「闭环能力」小节。 |
| [FCT 最小工作台对接说明](./fct-workbench-integration.md) | 工作台对接以当前已闭环的凭证/总账/资金录入为基础。 |

---

*文档版本：v1.1 | 业财税资金一体化完全闭环管理与操作检测；缺口清单已完善为 9 项，含验收标准、接口建议、实现要点与实施顺序。*
