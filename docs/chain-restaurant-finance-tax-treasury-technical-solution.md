# 连锁餐饮业、财、税、资金一体化 — 技术方案（智链OS 扩展）

## 文档说明

本技术方案在《[连锁餐饮业财税资金一体化数字化解决方案](./chain-restaurant-finance-tax-treasury-solution.md)》业务方案基础上，给出**结合智链OS 的扩展实现**与**交付形态**设计，支持：

- **合并销售及应用**：业财税资金作为智链OS 的可选扩展模块，与现有 Agent、适配器、API 一起部署与销售。
- **独立销售和交付**：业财税资金作为独立产品部署，通过标准 API/事件与智链OS 或第三方业务系统对接，可单独签约与交付。

---

## 一、技术架构总览

### 1.1 两种部署形态

```
形态A：合并部署（智链OS + 业财税资金一体化）
┌─────────────────────────────────────────────────────────────────────────────┐
│                         智链OS API Gateway (单进程/单集群)                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 现有路由: /api/v1/agents/*, /api/v1/finance/*, /api/v1/enterprise/*  │   │
│  │ 扩展路由: /api/v1/fct/* (业财税资金) [可选挂载]                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ 排班/订单/   │  │ 绩效/运维/   │  │ 业财税资金    │  │ 适配器层     │    │
│  │ 库存/决策等  │  │ 私域等Agent  │  │ 扩展服务     │  │ (POS/ERP等)  │    │
│  │ Agent        │  │              │  │ (可选加载)   │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└───────────────────────────────────────────┬─────────────────────────────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │ 共享: PostgreSQL / Redis / 消息队列 / 向量库  │
                    └─────────────────────────────────────────────┘

形态B：独立部署（业财税资金独立产品）
┌─────────────────────────────┐     ┌─────────────────────────────────────────┐
│ 智链OS（或其它业务系统）      │     │ 业财税资金一体化服务 (独立进程/集群)      │
│ - Agent / 适配器 / 现有API   │     │ - 凭证规则引擎 / 总账 / 税务 / 资金 / 对账 │
│ - 推送事件或调用开放API      │────▶│ - REST API + Webhook 入参                 │
└─────────────────────────────┘     │ - 独立 DB / Redis / 可选消息队列          │
                                    └─────────────────────────────────────────┘
```

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **模块可插拔** | 业财税资金功能通过配置/开关启用，未启用时不影响智链OS 原有启动与路由。 |
| **接口契约统一** | 合并与独立形态对外暴露同一套「业财事件 / 主数据 / 查询」契约，便于前端与集成一致。 |
| **数据源可替换** | 业务数据可来自智链OS 适配器/Agent，也可来自独立部署时的外部系统（通过 API/文件/消息）。 |
| **独立可运行** | 独立部署时仅依赖 DB/Redis 与配置，不依赖智链OS 进程；与智链OS 的对接通过 HTTP/消息完成。 |

---

## 二、模块边界与在智链OS 中的位置

### 2.1 新增/扩展组件

| 组件 | 说明 | 合并形态 | 独立形态 |
|------|------|----------|----------|
| **fct-api** | 业财税资金 REST API（凭证、总账、税务、资金、对账、报表） | 挂载在 API Gateway 下 `/api/v1/fct/*` | 独立服务唯一入口 |
| **fct-core** | 凭证规则引擎、主数据服务、自动化凭证、成本分摊 | 与 Gateway 同进程或同集群内网调用 | 独立进程核心逻辑 |
| **fct-integration** | 接收业务事件、拉取智链OS 或外部数据、推送事件到 fct-core | 订阅智链OS 事件 / 调用智链OS 只读 API | 仅对接外部系统 API/消息 |
| **业财税资金 Agent（可选）** | 自然语言查询、报表解读、审批建议等 | 注册到 AgentService，与决策/绩效等并列 | 独立形态可无或通过独立服务提供 |

### 2.2 与智链OS 现有模块的关系

```
智链OS 现有                    业财税资金扩展                数据流
─────────────────────────────────────────────────────────────────────────
api/agents.py                  可选: finance_tax Agent        Agent 可读 fct 报表/凭证
api/finance.py                 保留；fct 可复用权限与部分 API  现有 /finance 与 /fct 并存
services/agent_service.py      可选注册 fct Agent             无强依赖
packages/api-adapters/*        数据源：日结/订单/库存等        适配器 → 事件/API → fct-integration
packages/agents/decision      决策 Agent 可消费 fct 报表      只读 fct API 或共享 DB 只读
packages/agents/performance   绩效与薪酬数据可入账到 fct      写入 fct 或事件
reconciliation (对账)          可扩展为资金对账或复用逻辑     按需合并或独立
```

- **合并形态**：fct-api、fct-core、fct-integration 以**可选包/命名空间**形式存在于智链OS 仓库（或子仓），通过 `settings.FCT_ENABLED` 或环境变量控制挂载与初始化。
- **独立形态**：fct-* 单独仓库/镜像，独立部署；与智链OS 的集成仅通过「事件推送 + 开放 API」完成，无代码级依赖。

---

## 三、接口契约（合并与独立统一）

### 3.1 业财事件（入参）

业务侧（智链OS 或外部）向业财税资金推送「业财事件」，用于驱动自动凭证与对账。统一采用 **REST 或 消息体** 一致结构。

**端点（合并形态）**：`POST /api/v1/fct/events`  
**端点（独立形态）**：`POST /api/v1/events` 或同一路径（由独立服务路由决定）

**请求体示例（门店日结）**：

```json
{
  "event_type": "store_daily_settlement",
  "event_id": "evt_uuid_xxx",
  "occurred_at": "2025-02-26T02:00:00Z",
  "source_system": "zhilian_os",
  "source_id": "pos_daily_001",
  "tenant_id": "T001",
  "entity_id": "STORE_001",
  "payload": {
    "store_id": "STORE_001",
    "biz_date": "2025-02-25",
    "total_sales": 50000,
    "total_sales_tax": 2500,
    "payment_breakdown": [
      { "method": "wechat", "amount": 30000 },
      { "method": "alipay", "amount": 15000 },
      { "method": "cash", "amount": 5000 }
    ],
    "discounts": 800,
    "refunds": 0
  }
}
```

- **四流合一追溯**：payload 可选携带 `invoice_no`、`source_doc_id`、`order_id`、`settlement_id`、`purchase_order_id` 等，将写入生成凭证的 `attachments`，便于票-账-业务单关联与审计。

**事件类型约定（部分）**：

| event_type | 说明 | 主要 payload 字段 |
|------------|------|-------------------|
| store_daily_settlement | 门店日结 | store_id, biz_date, total_sales, payment_breakdown |
| purchase_receipt | 采购入库 | store_id, supplier_id, lines[], total, tax |
| platform_settlement | 平台结算 | platform, settlement_no, amount, commission, period |
| member_stored_value | 储值/消费 | store_id, member_id, type(charge/consume/refund), amount |
| payroll_batch | 薪酬批次 | period, store_id, total_amount, lines[] |

### 3.2 主数据同步（可选）

独立形态下，客商、门店、科目、银行账户等可由外部系统同步到业财税资金。

- **同步方式**：`PUT /api/v1/fct/master/*` 或 `POST /api/v1/fct/master/sync`（批量）。
- **数据模型**：与合并形态使用同一 JSON Schema，保证行为一致。

### 3.3 查询与报表（出参）

合并与独立形态均提供同一套查询 API，便于前端/大屏统一对接。

| 能力 | 方法 | 路径示例 |
|------|------|----------|
| 凭证列表/详情 | GET | /api/v1/fct/vouchers |
| 总账余额/明细 | GET | /api/v1/fct/ledger/balances, /ledger/entries |
| 资金流水/对账状态 | GET | /api/v1/fct/cash/transactions, /cash/reconciliation |
| 税务开票/申报状态 | GET | /api/v1/fct/tax/invoices, /tax/declarations |
| 业财报表 | GET | /api/v1/fct/reports/* |

响应格式统一为 JSON，分页、时间范围、主体/门店维度由 query 参数控制。

### 3.4 认证与多租户

- **合并形态**：复用智链OS 的 JWT、RBAC 与 `tenant_id`，fct 路由使用相同 `get_current_active_user` 与权限键（如 `fct:read` / `fct:write`）。
- **独立形态**：独立服务自带 API Key 或 JWT 签发，请求头携带 `X-Tenant-Id` 或等价字段做租户隔离；与智链OS 对接时可为「系统级」密钥 + 租户标识。

---

## 四、智链OS 侧集成实现要点

### 4.1 事件来源：从适配器/Agent 到 fct

- **推荐方式**：智链OS 在「日结完成、入库完成、平台结算拉取完成」等节点，向**内部事件总线**或**直接 HTTP 调用**发送业财事件；fct-integration 订阅或接收后写入 fct-core 队列并驱动凭证规则引擎。
- **实现位置**：
  - 适配器层：在品智/天财/奥琦韦等适配器的「日结/订单汇总」接口成功回调中，组装 `store_daily_settlement` 等事件并推送。
  - 或由定时任务从现有 `orders` / `inventory` / `finance` 等表聚合后推送。
- **合并形态**：推送目标为 `http://localhost/api/v1/fct/events` 或内部 Redis/Rabbit 队列。  
- **独立形态**：推送目标为独立服务的 `POST /api/v1/events`（或消息队列），由客户配置 URL/队列。

### 4.2 配置与开关

在智链OS 中通过配置控制业财税资金扩展是否启用，例如：

```yaml
# config/zhilian.yaml 或 环境变量
fct:
  enabled: true
  mode: embedded   # embedded | remote
  base_url: null   # mode=remote 时填独立服务 base_url
  event_target: internal  # internal | http | queue
  event_http_url: null   # event_target=http 时填写
```

- `enabled: false`：不加载 fct 路由、不注册 fct Agent、不推送业财事件。
- `mode: embedded`：使用同进程/同集群的 fct-api（合并交付）。
- `mode: remote`：业财事件与查询请求发往 `base_url`（独立交付，智链OS 作为调用方）。

### 4.3 路由挂载（合并形态）

在 `main.py` 中条件挂载，例如：

```python
# 业财税资金扩展（可选）
if getattr(settings, "FCT_ENABLED", False):
    from src.api import fct
    app.include_router(fct.router, prefix="/api/v1/fct", tags=["fct"])
```

仅当 `FCT_ENABLED=true` 时挂载 `/api/v1/fct/*`，避免对未采购客户暴露或依赖。

### 4.4 业财税资金 Agent（可选）

- 与现有 `agents.py` 一致：`POST /api/v1/agents/fct`，body 为 `agent_type: "fct", input_data: { action, params }`。
- Agent 支持 action 示例：`nl_query`（自然语言问报表/凭证）、`get_report`、`explain_voucher`、`reconciliation_status` 等。
- 合并形态：在 `AgentService._initialize_agents()` 中条件注册 `FCTAgent`（当 `FCT_ENABLED` 时）；FCTAgent 内通过 HTTP 或直接调用 fct-core 完成查询。

---

## 五、独立部署形态技术要点

### 5.1 运行边界

- 独立服务仅包含：fct-api、fct-core、fct-integration（对接外部业务系统）、自身 DB/Redis。
- 不依赖智链OS 的 FastAPI 应用、Agent 实现、适配器实现；不依赖企业微信/飞书。

### 5.2 与智链OS 的对接方式（独立形态）

| 场景 | 方向 | 方式 |
|------|------|------|
| 业财事件入 fct | 智链OS → 业财税资金 | 智链OS 调用 `POST https://fct-service/api/v1/events`（或投递到客户指定的 MQ） |
| 主数据 | 智链OS → 业财税资金 或 业财税资金 → 智链OS | 按需：业财税资金提供 `PUT /master/*` 供智链OS 同步；或业财税资金拉取智链OS 开放 API |
| 报表/凭证查询 | 智链OS / 大屏 → 业财税资金 | 智链OS 或前端直连 `GET https://fct-service/api/v1/fct/reports/*`，带 API Key + 租户 |

### 5.3 与第三方业务系统对接（无智链OS）

- 业财事件：第三方 POS/ERP 通过 HTTP 或 MQ 向独立服务推送同一套 `event_type` + `payload` 契约。
- 主数据：第三方调用业财税资金的主数据 API 同步门店、客商、科目等。
- 凭证/报表：由业财税资金产品自身提供前端或 API 给客户使用。

这样同一套业财税资金产品可「带智链OS 卖」或「不带智链OS、对接客户已有系统」独立交付。

---

## 六、数据与存储

### 6.1 合并形态

- **推荐**：与智链OS 共用 PostgreSQL，使用独立 schema（如 `fct`）存放凭证、总账、税务、资金、对账表，便于同库事务与联合查询；Redis 可共用或使用独立 key 前缀（如 `fct:`）。
- **可选**：独立数据库实例（如 `fct_db`），通过连接串与智链OS 分离，适合对数据隔离有强要求的客户。

### 6.2 独立形态

- 独立服务自带 PostgreSQL（及可选 Redis/队列），不访问智链OS 库。
- 所有业务数据通过「事件 + 主数据 API」进入，不直连客户 POS/ERP 数据库（除非客户要求并单独开发连接器）。

### 6.3 数据模型要点（示意）

- **凭证**：voucher_no, tenant_id, entity_id, biz_date, event_id, lines[], status, created_at。
- **总账**：ledger_entries 按科目+主体+期间存储，与凭证关联。
- **资金**：cash_transactions（收付）、reconciliation_matches（对账匹配）。
- **税务**：invoices（销项/进项）、declarations（申报记录）。

具体表结构在开发阶段按《业财税资金一体化数字化解决方案》中的领域设计细化。

---

## 七、销售与交付指引

### 7.1 合并销售及应用

| 项目 | 说明 |
|------|------|
| **产品名称** | 智链OS · 业财税资金一体化扩展包 |
| **交付物** | 智链OS 部署包 + 启用 fct 的配置 + 可选 fct Agent；同一套部署文档与运维体系。 |
| **依赖** | 智链OS 已就绪（含至少一种收银/ERP 适配器或可提供日结/订单数据）。 |
| **配置** | `FCT_ENABLED=true`，`fct.mode=embedded`，主数据与凭证规则按客户初始化。 |
| **验收** | 日结/采购等事件推送后，能在智链OS 内看到 fct 凭证与报表；企业微信/飞书可选用 fct Agent 查询。 |

### 7.2 独立销售和交付

| 项目 | 说明 |
|------|------|
| **产品名称** | 业财税资金一体化平台（独立版） |
| **交付物** | 独立部署包（同仓换入口 `fct_standalone_main` 或镜像）+ [独立部署指南](./fct-standalone-deployment.md) + 与业务系统对接规范（事件/主数据/报表 API）。 |
| **依赖** | 客户提供业务系统（POS/ERP/智链OS 等）的推送能力（HTTP 或 MQ）或只读 API；客户提供主数据或接受从业务系统同步。 |
| **配置** | 独立服务 `base_url`、数据库、Redis、与业务系统对接的 URL/密钥；若客户使用智链OS，在智链OS 侧配置 `fct.mode=remote` 与 `fct.base_url`。 |
| **验收** | 客户业务系统推送业财事件后，独立服务生成凭证、总账、资金与税务数据；客户可通过独立服务前端或 API 查看报表与对账结果。 |

### 7.3 组合报价建议

- **仅智链OS**：不包含 fct 模块，不涉及业财税资金报价。
- **智链OS + 业财税资金（合并）**：按「智链OS 许可 + 业财税资金扩展许可」报价，实施时一次部署、统一升级。
- **业财税资金（独立）**：按「业财税资金平台许可 + 对接实施」报价，可与智链OS 并行销售（客户先上业财税或先上智链OS 均可）。

---

## 八、实施路线建议

1. **Phase 1**：在智链OS 仓库内新增 `fct-api`、`fct-core` 最小闭环（事件接入 → 凭证规则 → 凭证存储 + 查询 API），配置开关与路由条件挂载，实现**合并形态**可交付。
2. **Phase 2**：将 fct 抽离为可独立启动的服务（同一套代码或子仓），实现**独立形态**部署与文档；与智链OS 的对接仅通过「事件 + 查询 API」验证。
3. **Phase 3**：完善主数据同步、资金对账、税务开票/申报对接与报表；可选业财税资金 Agent 与智链OS 决策/绩效等 Agent 的联动。

### 实施进度（开发记录）

| 阶段 | 状态 | 说明 |
|------|------|------|
| **Phase 1** | ✅ 已完成 | 事件接入、凭证规则（门店日结、采购入库）、凭证存储、总账余额汇总、查询 API、配置开关与条件挂载。 |
| **Phase 1+** | ✅ 已完成 | 对账完成后自动推送日结事件；采购入库凭证规则；总账余额按科目汇总。 |
| **Phase 2** | ✅ 已完成 | 独立服务形态：独立入口、API Key 认证、公开路由、部署文档；与智链OS 通过 HTTP 对接。 |
| **Phase 3** | ✅ 已完成 | 主数据同步（门店/客商/科目/银行）、资金流水与对账状态 API、税务发票/申报占位 API、业财期间汇总报表、FCT Agent（get_report/explain_voucher/reconciliation_status）。 |
| **Phase 3+** | ✅ 已完成 | **业财税资金报表汇总及分析**：`GET /reports/aggregate` 四维汇总、`GET /reports/trend` 期间趋势；**按门店/区域拆分**：`GET /reports/by_entity`、`GET /reports/by_region`；**同比环比分析**：`GET /reports/comparison?compare_type=yoy|mom|qoq`；FCT Agent 支持 report_type=aggregate/trend/by_entity/by_region/comparison。 |
| **行业对标与四流合一** | ✅ 已做 | 学习合思/金蝶/四流合一等行业方案，见 [业财税行业对标与完善路线图](./fct-industry-benchmark-and-roadmap.md)；**四流合一追溯**：事件 payload 可传 `invoice_no`、`source_doc_id`、`order_id` 等，生成凭证时写入 `voucher.attachments`，便于票-账-业务单关联。 |
| **年度计划与达成分析** | ✅ 已完成 | **年度计划**：`PUT/GET /fct/plans` 维护业财税资金年度目标；**计划 vs 实际**：按日/周/月/季对比（含成本/资金）；每期及年度返回 **累计达成率**、**收入类剩余目标**（target_remaining / year_target_remaining：revenue、tax_amount、cash_in，正=未达成）、**成本/支出类剩余预算**（budget_remaining / year_budget_remaining：cost、cash_out，正=预算有余）；趋势含 cost，支持 quarter。 |
| **Phase 4** | ✅ 已完成 | **费控/备用金**：备用金主档与流水（申请/冲销/还款）；**预算占位**：预算 upsert、占用校验、占用接口；**发票闭环**：发票与凭证关联、按凭证查发票、验真占位；**审批流占位**：审批记录创建与按业务单查询。详见 [行业对标与路线图](./fct-industry-benchmark-and-roadmap.md) 3.2。 |

**Phase 1 代码位置（智链OS api-gateway）**：

- 配置：`src/core/config.py`（`FCT_ENABLED`, `FCT_MODE`, `FCT_BASE_URL`, `FCT_EVENT_TARGET`, `FCT_EVENT_HTTP_URL`）
- 权限：`src/core/permissions.py`（`FCT_READ`, `FCT_WRITE`）
- 模型：`src/models/fct.py`（`FctEvent`, `FctVoucher`, `FctVoucherLine`, `FctVoucherStatus`）
- 服务：`src/services/fct_service.py`（事件接入；凭证规则：`store_daily_settlement`、`purchase_receipt`；凭证/总账余额/报表查询）；凭证规则与金蝶/用友及企业会计准则对照见 [业财凭证规则与会计准则对照](./fct-voucher-rules-and-accounting-standards.md)
- 集成：`src/services/fct_integration.py`（`push_store_daily_settlement_event`、`push_purchase_receipt_event`，供对账/适配器等调用）
- 对账联动：`src/api/reconciliation.py`（执行对账成功后若 `FCT_ENABLED` 则推送日结事件，响应中可选返回 `fct_event`）
- API：`src/api/fct.py`（`POST /api/v1/fct/events`，`GET /api/v1/fct/vouchers`，`GET /api/v1/fct/vouchers/{id}`，`GET /api/v1/fct/ledger/balances`，`GET /api/v1/fct/reports/{type}`，**`PUT/GET /api/v1/fct/plans`**，`GET /api/v1/fct/status`）；报表 type 含 **plan_vs_actual**（年度计划 vs 日/周/月/季实际）。
- 挂载：`src/main.py`（当 `FCT_ENABLED=true` 时挂载 `/api/v1/fct`）
- 迁移：`alembic/versions/s01_fct_tables.py`（表 `fct_events`, `fct_vouchers`, `fct_voucher_lines`）、`alembic/versions/t01_fct_phase3_tables.py`（表 `fct_master`, `fct_cash_transactions`, `fct_tax_invoices`, `fct_tax_declarations`）

**Phase 3 新增（代码位置）**：

- 模型：`src/models/fct.py`（`FctMaster`/`FctMasterType`、`FctCashTransaction`、`FctTaxInvoice`、`FctTaxDeclaration`）
- 服务：`src/services/fct_service.py`（主数据 upsert/list、资金流水/对账状态、税务列表、`get_report_period_summary`、`get_report_aggregate`、`get_report_trend`（含 **quarter**）、`get_report_by_entity`、`get_report_by_region`、`get_report_comparison`、**`upsert_plan`/`get_plan`/`get_plan_vs_actual` 年度计划与达成分析**）
- API：`src/api/fct.py` 与 `src/api/fct_public.py`（`PUT/GET /master/*`、`GET /cash/transactions`、`GET /cash/reconciliation`、`GET /tax/invoices`、`GET /tax/declarations`；`GET /reports/period_summary`、`GET /reports/aggregate`、`GET /reports/trend`、**`GET /reports/by_entity`**、**`GET /reports/by_region`**、**`GET /reports/comparison?compare_type=yoy|mom|qoq`**）
- Agent：`src/agents/fct_agent.py`（get_report 支持 report_type=period_summary/aggregate/trend/by_entity/by_region/comparison、explain_voucher、reconciliation_status）；`src/api/agents.py`（`POST /api/v1/agents/fct`）；`src/services/agent_service.py`（FCT_ENABLED 时注册 FctAgent）

**启用方式**：在环境变量或 `.env` 中设置 `FCT_ENABLED=true`，执行 `alembic upgrade head` 后重启服务即可使用业财税资金 API。执行对账后会自动向 FCT 推送门店日结事件并生成凭证。

**代码检查与修复（完整性/稳定性）**：

- **凭证详情**：`get_voucher_by_id` 使用 `selectinload(FctVoucher.lines)` 预加载分录，避免异步下懒加载；无效 `voucher_id`（非 UUID）返回 `None`，API 返回 404。
- **Result 用法**：与 SQLAlchemy 2.0 一致，查询单条实体使用 `result.scalars().one_or_none()`，不再使用 `scalar_one_or_none()`。
- **主数据写入**：`upsert_master` 在更新/创建后执行 `await session.commit()`，确保在使用 `Depends(get_db)` 时写入被持久化。
- **空字符串参数**：`get_report_period_summary`、`list_cash_transactions` 中将 `entity_id == ""` 规范为 `None`，避免无效筛选。
- **FCT Agent**：`get_report` 的 `start_date`/`end_date` 做日期解析并捕获 `ValueError`/`TypeError`，返回明确错误信息。
- **报表**：移除未使用变量，linter 通过。

**Phase 4 新增（代码位置）**：

- 模型：`src/models/fct.py`（`FctPettyCash`/`FctPettyCashRecord`、`FctBudget`、`FctApprovalRecord`；`FctTaxInvoice` 增加 `verify_status`/`verified_at`）
- 迁移：`alembic/versions/v01_fct_phase4_tables.py`（表 `fct_petty_cash`、`fct_petty_cash_records`、`fct_budgets`、`fct_approval_records`；`fct_tax_invoices` 增列）
- 服务：`src/services/fct_service.py`（`upsert_petty_cash`、`list_petty_cash`、`add_petty_cash_record`、`list_petty_cash_records`；`upsert_budget`、`check_budget`、`occupy_budget`；`link_invoice_to_voucher`、`list_invoices_by_voucher`、`verify_invoice_stub`；`create_approval_record`、`get_approval_by_ref`）
- API（合并形态）：`src/api/fct.py`（`PUT/GET /petty-cash`、`POST /petty-cash/records`、`GET /petty-cash/{id}/records`；`PUT /budgets`、`GET /budgets/check`、`POST /budgets/occupy`；`POST /invoices/link`、`GET /invoices/by-voucher/{voucher_id}`、`POST /invoices/{id}/verify`；`POST /approvals`、`GET /approvals/by-ref`）
- API（独立形态）：`src/api/fct_public.py`（同上路径，请求体为 Dict，契约与 fct.py 一致）

**P0/P1 优先落地（手工凭证、过账、总账明细、资金录入、工作台对接）**：

- 服务：`src/services/fct_service.py`（`create_manual_voucher`、`update_voucher_status`、`get_ledger_entries`、`create_cash_transaction`；`get_ledger_balances` 增加 `posted_only` 参数，默认仅已过账）
- API（合并）：`src/api/fct.py`（`POST /vouchers` 手工凭证、`PATCH /vouchers/{id}/status` 过账、`GET /ledger/entries` 总账明细、`POST /cash/transactions` 资金录入；`GET /ledger/balances` 支持 `posted_only`）
- API（独立）：`src/api/fct_public.py`（同上路径，Dict 入参）
- 对接说明：[FCT 最小工作台对接说明](./fct-workbench-integration.md)

**缺口清单第一阶段 + 第二阶段（部分）落地**：

- **资金流水勾对**：`PATCH /cash/transactions/{id}/match`（body：match_id 有值则勾对，无则取消匹配）；服务 `match_cash_transaction`、`unmatch_cash_transaction`。
- **发票登记 CRUD**：`POST /tax/invoices` 登记、`PATCH /tax/invoices/{id}` 更新；服务 `create_tax_invoice`、`update_tax_invoice`；同租户下 invoice_type+invoice_no 唯一。
- **凭证作废/红冲**：`POST /vouchers/{id}/void` 作废（仅 draft/posted）、`POST /vouchers/{id}/red-flush` 红冲（仅 posted，生成借贷相反的新凭证）；模型 `FctVoucherStatus.VOIDED`；总账余额/明细已排除已作废凭证。迁移：`alembic/versions/w01_fct_voucher_voided.py`（枚举增加 voided）。
- **会计期间与结账**：模型 `FctPeriod`（tenant_id、period_key、start_date、end_date、status=open/closed）；`GET /periods` 期间列表、`POST /periods/{period_key}/close` 结账、`POST /periods/{period_key}/reopen` 反结账；结账时校验该期间无草稿凭证；凭证创建/过账/作废/红冲时校验所属期间未结账。迁移：`alembic/versions/x01_fct_periods.py`。
- **预算与凭证/付款强制联动**：`POST /vouchers`、`PATCH /vouchers/{id}/status`、`POST /cash/transactions` 请求体支持可选 `budget_check`、`budget_occupy`；**预算控制配置**：`PUT /budgets/control`、`GET /budgets/control`；配置 `enforce_check`/`auto_occupy` 后，制单/过账/付款时未传 budget_check 也按配置强制校验或自动占用（表 `fct_budget_control`，迁移 `y01_fct_budget_control`）。

- **总账/报表按期间**：`GET /ledger/balances`、`GET /ledger/entries`、`GET /reports/*` 支持 `period=YYYYMM` 参数，与 as_of_date/start_date/end_date 二选一，按会计期间取数。

**缺口清单第三阶段落地**：

- **资金流水导入**：`POST /cash/transactions/import`，body：tenant_id、entity_id、items=[{tx_date, amount, direction, ref_id?, description?}]、ref_type?=bank、skip_duplicate_ref_id?=true；服务 `import_cash_transactions`，按 ref_id 去重；合并/独立 API 均已挂载。
- **税务申报取数**：`GET /tax/declarations/draft?tenant_id=&tax_type=vat&period=YYYYMM`，从总账已过账凭证按 2221/2221_01 科目汇总销项/进项/应纳税额；服务 `get_tax_declaration_draft`。
- **合并报表**：`GET /reports/consolidated?tenant_id=&period=YYYYMM&group_by=entity|all`，多主体总账汇总；group_by=entity 返回 by_entity，不传或 all 返回全主体汇总 balances；服务 `get_report_consolidated`；当前不做内部抵销。
- **业财事件规则扩展**：`_rule_engine_dispatch` 增加 `platform_settlement`（借银行存款/销售费用 贷应收账款）、`member_stored_value`（储值 charge/consume/refund）；科目常量 DEFAULT_ACCOUNT_RECEIVABLE、DEFAULT_ACCOUNT_SALES_EXPENSE、DEFAULT_ACCOUNT_CONTRACT_LIABILITY。

**Phase 2 独立部署（代码与文档）**：

- 独立服务入口：`apps/api-gateway/fct_standalone_main.py`（`uvicorn fct_standalone_main:app --port 8001`）
- 公开 API（无智链OS 用户/权限依赖）：`src/api/fct_public.py`（API Key 认证 `X-API-Key`，契约与合并形态一致，含 Phase 4 备用金/预算/发票/审批路由）
- 配置：`FCT_API_KEY`（可选，独立服务请求校验）
- 部署与对接说明：[FCT 独立部署指南](./fct-standalone-deployment.md)
- 契约：`POST /api/v1/events` 或 `POST /api/v1/fct/events` 接收业财事件；`GET /api/v1/fct/vouchers`、`/ledger/balances` 等查询；Phase 4 见上

---

## 九、附录：与现有文档的对应关系

| 文档 | 关系 |
|------|------|
| [连锁餐饮业财税资金一体化数字化解决方案](./chain-restaurant-finance-tax-treasury-solution.md) | 业务方案：业/财/税/资金能力与实施建议；本技术方案在其基础上给出智链OS 扩展与双形态交付设计。 |
| [业财税行业对标与完善路线图](./fct-industry-benchmark-and-roadmap.md) | 行业方案（合思/金蝶/四流合一）对标、智链OS 差距与 Phase 4/长期路线图；取长补短参考。 |
| [FCT 财务部门可正常使用完整性评估](./fct-completeness-for-finance-department.md) | 从连锁餐饮财务部门日常使用角度评估 FCT 完整性与缺口，P0/P1 已落地，P2/P3 待排期。 |
| [FCT 完全闭环管理与操作检测报告](./fct-closed-loop-detection.md) | 按业务流检测业财税资金是否可完全闭环；结论与缺口清单（流水勾对、期间结账、申报取数、合并报表等）。 |
| [FCT 最小工作台对接说明](./fct-workbench-integration.md) | 凭证/总账/资金录入等 API 的对接说明，供前端或第三方实现最小工作台。 |
| [智链OS 系统架构](./architecture.md) | 本方案扩展其「应用层」与「数据/集成层」，增加 fct 模块与事件流。 |
| [API 适配器集成指南](../packages/api-adapters/INTEGRATION_GUIDE.md) | 适配器作为业财事件数据源，在日结/订单等回调中推送事件到 fct。 |

---

*文档版本：v1.0 | 适用于智链OS 业财税资金扩展的技术评审与实施规划。*
