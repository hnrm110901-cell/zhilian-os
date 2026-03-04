# 智链OS：基于 Palantir 本体论战略的兼容性、扩展性与产品计划

> 依据《智链OS架构差距分析与优化方案》与《智链OS整体架构设计方案》，对现有产品架构及代码做兼容性、扩展性梳理，并按智链OS Palantir 本体论方向重新规划产品计划。  
> 版本 v1.0 · 2026年2月

**关联文档**：  
- [《智链OS-Palantir本体论对标分析》](./智链OS-Palantir本体论对标分析.md)：Gotham 五层架构解析、智链OS 对标、融合层/推理层/行动层实现要点、12 个月路线图与行动清单、本体与推理最佳实践。  
- [《智链OS 代码与 Palantir 本体论对齐梳理》](./智链OS代码与Palantir本体论对齐梳理.md)：原项目代码与 L1–L4 的映射、各模块对齐状态、本体相关 API 速查、与原业务模块的对接关系。

---

## 一、战略定位与 Palantir 本体论摘要

### 1.1 战略定位

**智链OS 不是软件工具，而是「餐厅运营的知识操作系统」。**

| 维度 | 传统餐饮 SaaS | 智链OS 知识 OS |
|------|----------------|----------------|
| 数据存储 | 关系型数据库表 | 本体图谱（Neo4j） |
| 系统输出 | 数字报表 | 可执行 Action 任务 |
| AI 能力 | 固定规则 | 图谱推理 + LLM 查询 |
| 竞争壁垒 | 功能堆砌 | 知识积累护城河 |
| 客户迁移 | 低成本 | 越用越难离开 |

核心承诺：

- **语义中间层**：不替换现有 POS，在其上建立语义中间层。
- **可执行任务**：不生产报表，只输出可执行行动任务。
- **数据主权**：客户数据本地私有存储，屯象无法接触客户数据。

### 1.2 Palantir 四层本体论架构

| 层级 | 英文名 | 定位 | 核心产出 |
|------|--------|------|----------|
| **L1 感知层** | Perception | 神经末梢：原始世界→语义世界的翻译器 | 标准化对象事件流 |
| **L2 本体层** | Ontology | 世界模型：餐厅运营的完整知识图谱 | 对象 + 关系 + 版本快照 |
| **L3 推理层** | Reasoning | 大脑：在图谱上运行，输出有溯源的结论 | 带推理链的决策建议 |
| **L4 行动层** | Action | 手脚：将推理结论转化为人能执行的任务 | 企微任务 + 闭环追踪 |

### 1.3 本体层 11 个核心对象类型（目标架构）

| 对象类型 | 核心属性 | 关键关系 |
|----------|----------|----------|
| 门店 Store | store_id, name, tier, capacity | → 拥有员工、菜单、设备 |
| 菜品 Dish | dish_id, name, category, bom_version | → 包含食材(BOM), → 属于菜单 |
| 食材 Ingredient | ing_id, unit, supplier_ids | → 关联 BOM 用量, → 来自供应商 |
| 订单 Order | order_id, table, timestamp, status | → 包含菜品, → 由员工服务 |
| 员工 Staff | staff_id, role, wechat_id, shift | → 执行 Action, → 属于门店 |
| 库存快照 InventorySnapshot | ing_id, qty, ts, source | → 关联食材, → 触发推理 |
| BOM 配方 BOM | dish_id, version, effective_date | → 定义标准用料量 |
| 损耗事件 WasteEvent | type, amount, root_cause | → 关联订单/员工/食材 |
| Action 任务 Action | type, assignee, status, deadline | → 分配给员工, → 溯源推理 |
| 供应商 Supplier | sup_id, name, lead_time | → 提供食材, → 关联采购单 |
| 设备 Equipment | equip_id, type, status, location | → 属于门店, → 触发维护 Action |

核心语义关系（Relation Schema）：

- `(Order)-[:CONTAINS]->(Dish)`
- `(Dish)-[:HAS_BOM]->(BOM)`
- `(BOM)-[:REQUIRES {qty}]->(Ingredient)`
- `(WasteEvent)-[:TRIGGERED_BY]->(Staff)`
- `(Action)-[:ASSIGNED_TO]->(Staff)`

---

## 二、现有产品架构与代码映射

### 2.1 现有代码结构概览

- **应用**：`api-gateway`（FastAPI）、`web`（React + TypeScript）
- **模型**：`apps/api-gateway/src/models/`（SQLAlchemy + PostgreSQL）
- **服务**：`apps/api-gateway/src/services/`、根目录 `src/services/`（部分）
- **Agent**：`packages/agents/` 下 7 个专域 Agent + `api-gateway/src/agents/`
- **外部适配**：奥琦韦、品智 POS、亿订、天财商龙、美团、企微（文档与接口定义）

### 2.2 11 个本体对象 ↔ 现有模型/表映射

| 目标对象类型 | 现有实现 | 存储 | 兼容性 | 说明 |
|--------------|----------|------|--------|------|
| Store | `Store` 模型 | PostgreSQL `stores` | 高 | 有 store_id/name 等，缺 tier/capacity 等可扩展字段 |
| Dish | `Dish` + `DishCategory` | `dishes`, `dish_categories` | 高 | 无 `bom_version`，BOM 通过 DishIngredient 关联 |
| Ingredient | `InventoryItem`（库存品项） | `inventory_items` | 中 | 食材与库存合一；无显式 supplier_ids，供应商在 supply_chain |
| Order | `Order` + `OrderItem` | `orders`, `order_items` | 高 | 有状态机与合法转换表，缺与 BOM 版本的关联 |
| Staff | `Employee` | `employees` | 高 | 有 role；wechat_id 在 user 或扩展字段，需统一 |
| InventorySnapshot | 无独立模型 | 无 | 缺失 | 有 `InventoryItem`/`InventoryTransaction`，无「快照」语义与时间点查询 |
| BOM | `DishIngredient`；根目录 `BOM`/`Material`/`WasteRecord` | `dish_ingredients`；根目录 `boms` 等 | 部分 | 两套：DishIngredient 无版本/生效日；bom_service 有版本，未与图谱统一 |
| WasteEvent | 无 | 无 | 缺失 | 无损耗事件实体与 root_cause 链路 |
| Action | 无 | 无 | 缺失 | 有 `Task`，无 P0–P3 分级、超时升级、溯源推理 |
| Supplier | `Supplier` + `PurchaseOrder` | `suppliers`, `purchase_orders` | 高 | 有 lead_time 等，可映射 |
| Equipment | 无独立模型 | 无 | 缺失 | 硬件/边缘节点有服务层，无设备本体 |

### 2.3 四层架构 ↔ 现有实现差距

| 层级 | 目标能力 | 现有实现 | 差距等级 |
|------|----------|----------|----------|
| **L1 感知层** | POS 适配器 + IoT 网关 + 语义标准化 | 前端模拟数据（如 inventoryData.ts）；无统一 POS 适配器与语义管道 | 根本性缺失 |
| **L2 本体层** | Neo4j 图谱、11 对象类型、关系与版本管理 | 仅 PostgreSQL 关系表，无本体建模、无图、无时间旅行 | 根本性 |
| **L3 推理层** | 规则引擎 + 时序预测 + LLM 自然语言查询 + 损耗五步推理 | decision_validator 仅「双规校验」、无图谱推理；无 LLM 图谱查询；无损耗推理链 | 部分实现 |
| **L4 行动层** | 企微原生集成 + Action 状态机 + 分级升级 | wechatWork.ts 调后端发消息，无企微应用/Webhook 签名/任务卡片/回执/升级 | 部分实现 |

---

## 三、兼容性与扩展性分析

### 3.1 可直接复用或小幅扩展的部分

- **Agent 体系**：7 个专域 Agent（排班/订单/库存/服务/培训/决策/预约）划分与无状态设计可保留；后续让 Agent 从「图谱+推理」读上下文而非仅从关系型表读。
- **RBAC / 权限**：现有 RBAC 与 13 种角色可保留，逐步对齐「本体级 ACL」细粒度（按对象类型/关系控制）。
- **订单状态机**：`OrderStatus` 与 `_VALID_TRANSITIONS` 可保留，扩展为「订单→图谱节点/边」的同步或双写。
- **门店/员工/菜品/供应商/订单/采购**：现有模型与 API 可保留为「事务与报表源」，通过 ETL 或双写同步到图谱，作为 L2 的权威数据源之一。
- **BOM 基础能力**：根目录 `bom_service.py` 与 `DishIngredient` 的配方与用量数据，作为 BOM 本体化的数据来源（需统一为一套并增加 version/effective_date）。
- **决策校验思路**：`decision_validator.py` 已扩展为「规则引擎 + 图谱事实」联合校验（`OntologyFactsRule`、`get_ontology_facts_for_decision` 注入 context）。

### 3.2 需改造才能对齐本体论的部分

- **数据层**：从「仅 PostgreSQL」改为「PostgreSQL（事务）+ Neo4j（本体）」双库；新增本体访问层（OntologyRepository），封装 Cypher。
- **BOM**：从「表记录」升级为「本体对象 + 版本」：BOM 节点带 version/effective_date/expiry_date；`(BOM)-[:REQUIRES {qty, unit}]->(Ingredient)`；历史版本不删，仅过期。
- **损耗与推理**：引入 WasteEvent 节点与损耗五步推理（库存差异→BOM 偏差→时间窗口→供应商批次→根因评分），推理基于图遍历而非仅 SQL。
- **企微**：从「发消息接口」升级为「企微应用 + Webhook 签名 + 任务卡片 + 回执 + 分级升级」的 L4 行动层。
- **Action**：新增 Action 对象与状态机（创建→推送→回执→超时升级→完成/关闭），与推理结论绑定（溯源）。

### 3.3 当前缺失且需新建的部分

- **L1 感知层**：POS 适配器（奥琦韦等）、IoT 网关（树莓派 5）、语义标准化管道（ID/时间戳/单位统一）。
- **L2 本体层**：Neo4j 图谱、11 种节点类型与关系类型、本体版本管理（时间旅行/快照）。
- **L3 推理层**：基于图谱的损耗五步推理引擎、时序预测备货（90 天历史+节假日+天气）、LLM 自然语言→Cypher→结构化答案+溯源。
- **L4 行动层**：Action 状态机、P0–P3 分级与 30min/2h/24h/3d 升级策略、企微 Webhook 与任务闭环。
- **数据主权**：本地 AES-256 加密、客户自持密钥、一键导出与断开权（当前仅为 Docker 部署，无加密与主权设计）。

### 3.4 建议冻结或暂缓的部分

- **联邦学习**：`federated_learning_service.py` / `federated_bom_service.py` 对当前 3–20 店规模过度超前；建议冻结维护，资源用于本体与推理。
- **国际化**：定位长沙本地连锁，暂缓国际化模块。
- **开放 API 平台**：生态扩展为更晚阶段，暂缓。
- **竞争分析页**：演示价值有，但工程优先聚焦本体与推理。

---

## 四、按 Palantir 本体论方向的产品计划

### 4.1 Phase 0：止血与定标（约 2 周）

- **冻结**：联邦学习、国际化、开放 API 平台、竞争分析页（仅维护不增强）。
- **关键决策**：图数据库选型（生产推荐 Neo4j Community）；企微接入方式（服务商或客户自建）；POS 优先级（如徐记所用 POS 与版本）。
- **产出**：决策记录、Phase 1 排期与负责人。

### 4.2 Phase 1：本体层建立（第 1–2 个月）

- **目标**：建立「世界模型」，为推理与行动提供图谱基础。
- **动作要点**：
  - 在 Docker Compose 中接入 Neo4j；定义 11 个节点标签与核心关系类型（HAS_BOM, CONTAINS, ASSIGNED_TO 等）。
  - 实现 OntologyRepository（Python + neo4j-driver），封装 Cypher 与基础 CRUD。
  - BOM 本体化：BOM 节点 + BOM_ITEM/REQUIRES 关系，支持 version/effective_date；从现有 DishIngredient 与 bom_service 迁移/双写。
  - PostgreSQL 保留订单、支付、凭证等事务数据；图谱存对象与关系，双库并行。
  - 感知层先「半自动」：Excel/CSV 导入 + 标准化模板映射到本体；预留树莓派/IoT 同一接口。
- **交付物**：Neo4j 图谱 schema、OntologyRepository、BOM 本体化、数据标准化 Pipeline（含导入模板）。

**Phase 1 已实现（代码库）**：

- [x] Docker Compose 接入 Neo4j 5.x（`docker-compose.yml`），配置项 `NEO4J_URI/USER/PASSWORD/ENABLED`（`core/config.py`）。
- [x] 本体 Schema：`src/ontology/schema.py`（11 节点标签 + 关系类型）、`cypher_schema.py`（约束与索引）。
- [x] OntologyRepository：`src/ontology/repository.py`（merge_node、merge_relation、upsert_bom、upsert_bom_requires、get_dish_bom_ingredients、health、init_schema）。
- [x] BOM 本体化 API：`POST /api/v1/ontology/bom/upsert`、`GET /api/v1/ontology/bom/dish/{dish_id}`。
- [x] 从 PG 同步到图谱：`src/services/ontology_sync_service.py`（Store/Dish/Ingredient），`POST /api/v1/ontology/sync-from-pg`。
- [x] 健康检查：`/api/v1/ontology/health`、就绪检查中可选 Neo4j 状态。
- [x] 感知层半自动：Excel/CSV 导入（`perception_import_service` + `POST/GET /ontology/perception/import`、`/perception/template/inventory_snapshot`）。

### 4.3 Phase 2：推理层与行动层激活（第 2–3 个月）

- **目标**：在图谱上跑通「损耗防控五步推理」与「企微任务闭环」。
- **动作要点**：
  - **损耗推理引擎**：库存差异检测 → BOM 偏差计算 → 时间窗口关联员工 → 供应商批次定位 → 根因评分（TOP3）；输出带溯源的根因报告。
  - **企微真实集成**：客户企微下创建「智链OS」应用；Webhook 签名验证；Action 状态机（创建→推送→回执→超时升级）；P0 30min@督导、P1 2h 升级等。
  - **LLM 自然语言查询**：企微/控制台自然语言 → 意图识别 → Cypher 生成 → 图谱查询 → 结构化答案 + 溯源链路（Claude API + 图谱 RAG）。
- **交付物**：五步推理 API、Action 状态机与升级策略、企微 Webhook 与任务推送、自然语言查询接口。

**Phase 2 已实现（代码库）**：

- [x] 损耗五步推理：`waste_reasoning_service.py`（库存差异→BOM 偏差→时间窗口员工→供应商批次→根因 TOP3），`POST /api/v1/ontology/reasoning/waste`。
- [x] Action 状态机：`OntologyAction` 模型与 `ontology_actions` 表，状态 CREATED→SENT→ACKED→IN_PROGRESS→DONE/CLOSED，P0–P3 时限；`POST/GET/PATCH /api/v1/ontology/actions`，`POST /api/v1/ontology/actions/{id}/send` 推送企微。
- [x] 企微 Webhook：`enterprise.py` 中 GET/POST `/enterprise/wechat/webhook` 已实现签名验证与解密；L4 Action 推送通过 `wechat_service.send_text_message` + `action_send` 标记 SENT。
- [x] LLM 自然语言查询：`ontology_nl_query_service`（意图识别→图谱/推理→答案+溯源），`POST /api/v1/ontology/query`。

### 4.4 Phase 3：数据主权与规模化（第 3–4 个月）

- **目标**：数据主权落地、多店扩展与知识沉淀。
- **动作要点**：
  - 本地/私有化：PostgreSQL 与 Neo4j 数据文件 AES-256 加密；客户自持密钥；一键导出、断开权与停服后本地保留。
  - 连锁扩展：跨店对比（如 A 店 vs B 店损耗率）、本体模板复制、连锁级 KPI 与知识库（损耗规则库、BOM 基准库、异常模式库）。
- **交付物**：加密与密钥方案、导出/断开权功能、跨店分析能力与知识库雏形。

**Phase 3 已实现（雏形）**：

- [x] 一键导出：`ontology_export_service.export_graph_snapshot`，`GET /api/v1/ontology/export?tenant_id=&store_id=`（图谱快照 JSON）。
- [x] 跨店损耗对比：`ontology_cross_store_service.cross_store_waste_comparison`，`GET /api/v1/ontology/cross-store/waste?tenant_id=&date_start=&date_end=&store_ids=`。
- [x] 加密与客户密钥、断开权：`data_sovereignty_service`（AES-256 加密导出、断开权删除图谱数据），`POST /ontology/data-sovereignty/export-encrypted`、`POST /ontology/data-sovereignty/disconnect`；配置 `DATA_SOVEREIGNTY_ENABLED`、`CUSTOMER_ENCRYPTION_KEY`。

### 4.5 徐记 POC 与最小可行本体（MVO）

- **徐记专项扩展**（可选）：LiveSeafood、SeafoodPool、PortionWeight、PurchaseInvoice 等节点与关系，用于海鲜池与损耗溯源。
- **90 天 POC 里程碑**：数据摸底(1–2 周) → 本体建立(3–4 周) → BOM 录入(5–6 周) → 推理验证(7–8 周) → 企微接入(9–10 周) → ROI 测算(11–12 周)。

**徐记扩展已实现（雏形）**：

- [x] 扩展节点标签：`ExtensionNodeLabel`（LiveSeafood、SeafoodPool、PortionWeight、PurchaseInvoice），约束与索引见 `cypher_schema.extension_constraints_cypher`。
- [x] 活海鲜/海鲜池写入：`repository.merge_live_seafood`、`merge_seafood_pool`，`POST /api/v1/ontology/xuji/live-seafood`、`/xuji/seafood-pool`。
- [x] 份量/采购凭证：`merge_portion_weight`、`merge_purchase_invoice`，`POST /api/v1/ontology/xuji/portion-weight`、`/xuji/purchase-invoice`。
- [x] 损耗推理写回图谱：`run_waste_reasoning` 结束后将 TOP3 根因写入 `WasteEvent` 节点并 `TRIGGERED_BY` 关联 Staff。

---

## 五、与现有代码的对接清单（便于落地）

| 现有模块/文件 | 建议动作 |
|---------------|----------|
| `apps/api-gateway/src/models/*` | 保留；增加 Neo4j 同步或 ETL 到图谱；Dish/Order/Employee/Store/Supplier 等作为本体数据源 |
| `apps/api-gateway/src/models/dish.py` (DishIngredient) | 作为 BOM 本体化的来源；增加 bom_version/effective_date 或通过 BOM 表映射 |
| `src/services/bom_service.py`、`src/models/bom.py` | 与 api-gateway 的 DishIngredient 统一为一套 BOM 模型；再升级为图谱 BOM 节点+关系 |
| `apps/api-gateway/src/services/decision_validator.py` | 保留双规校验；新增「从图谱取事实」的规则与损耗推理调用 |
| `apps/web/src/services/wechatWork.ts`、`wechat_*_service.py` | 在现有发消息能力上增加：企微应用、Webhook 验证、任务卡片、回执、升级策略 |
| `packages/agents/*` | 保持无状态；已提供「图谱上下文」`GET /api/v1/ontology/context` 与 Action 创建接口 |
| `inventoryData.ts` / 前端模拟数据 | 逐步替换为 L1 感知层真实数据（POS 适配器 / Excel 导入） |
| `federated_learning_service.py`、`federated_bom_service.py` | 冻结；不投入新功能 |

---

## 六、总结

- **战略**：智链OS 以「知识操作系统」为定位，以 Palantir 式本体论为架构方向，以语义中间层、可执行任务与数据主权为承诺。
- **现状**：现有产品与代码在 Agent、订单、权限、BOM 基础、决策校验等方面可复用或可扩展，但在「图谱本体、感知层、损耗推理、企微行动闭环、数据主权」上存在根本性或重要差距。
- **产品计划**：通过 Phase 0 止血与定标 → Phase 1 本体层建立 → Phase 2 推理与行动层激活 → Phase 3 数据主权与规模化，在保留现有工程优势的前提下，逐步将系统升级为「以图谱为中心、以推理与行动为输出」的知识 OS，并依托徐记 POC 验证最小可行本体与 ROI。

本文档可作为「智链OS Palantir 本体论方向」下，产品与研发对齐的基准文档；具体迭代可再拆为 sprint 级任务与验收标准。

---

## 七、计划内未开发/待补齐内容（检查清单）

以下为按计划文档与代码库对照后，**尚未实现或仅部分实现**的项，便于后续迭代优先排期。

### 7.1 L1 感知层

| 项 | 计划要求 | 当前状态 | 优先级建议 |
|----|----------|----------|------------|
| POS → 本体写入 | POS 适配器（奥琦韦/品智等）数据经语义标准化后写入图谱（InventorySnapshot/Order 等） | **已实现**：POS Webhook 归一化后双写 PG + 图谱（`push_normalized_order_to_graph`），Order 节点 + BELONGS_TO + CONTAINS | — |
| IoT 网关（树莓派 5） | 边缘数据采集 + 标准化输出到本体 | **已实现**：`POST /ontology/perception/edge-push` 接收标准化 inventory_snapshots/equipment，写入图谱 | — |

### 7.2 L2 本体层

| 项 | 计划要求 | 当前状态 | 优先级建议 |
|----|----------|----------|------------|
| Order / Staff 同步到图谱 | 从 PG 同步订单、员工到图谱，作为本体数据源 | **已实现**：`sync_staff_to_graph`、`sync_orders_to_graph`，`sync-from-pg` 返回 staff/orders 计数 | — |
| Equipment 节点 | 11 对象含设备；属于门店、可触发维护 Action | **已实现**：`merge_equipment`、`POST /ontology/equipment`，边缘/IoT 可调用 | — |
| 本体版本管理（时间旅行） | 按 as_of 时间查询历史快照 | **已实现**：`GET /ontology/bom/dish/{dish_id}?as_of=YYYY-MM-DD` 查询当时生效 BOM | — |

### 7.3 L3 推理层

| 项 | 计划要求 | 当前状态 | 优先级建议 |
|----|----------|----------|------------|
| 时序预测备货 | 90 天历史 + 节假日 + 天气 → 备货建议 | **已实现**：`ontology_replenish_service` + `GET /ontology/replenish`，Prophet 订单预测 + 图谱 BOM + 损耗缓冲 | — |

### 7.4 L4 行动层

| 项 | 计划要求 | 当前状态 | 优先级建议 |
|----|----------|----------|------------|
| Action 自动升级定时任务 | P0 30min 无回执 @督导、P1 2h 升级等自动执行 | **已实现**：Celery Beat `escalate_ontology_actions` 每 10 分钟；`process_escalations` 标记并推送企微；配置 `WECHAT_ESCALATION_TO` | — |
| 企微任务卡片 + 一键回执 | 任务推送卡片、用户点击回执后更新 Action 状态 | **已实现**：配置 `ACTION_ACK_BASE_URL` 后发 textcard，`GET /enterprise/action-ack` 校验签名并更新 ACKED | — |

### 7.5 Phase 3 规模化

| 项 | 计划要求 | 当前状态 | 优先级建议 |
|----|----------|----------|------------|
| 本体模板复制 | 连锁扩展时复制本体模板到新店 | **已实现**：`POST /ontology/clone-template`（source_store_id → target_store_id）复制 Dish+BOM+REQUIRES | — |
| 知识库（损耗规则库、BOM 基准库、异常模式库） | 沉淀为连锁级/行业资产 | **已实现（雏形）**：`POST/GET /ontology/knowledge`，type=waste_rule/bom_baseline/anomaly_pattern，文件存储 | — |

### 7.6 对接清单待办

| 项 | 计划建议 | 当前状态 |
|----|----------|----------|
| PG Dish 表 bom_version | 增加 bom_version/effective_date 或通过 BOM 表映射 | **已实现**：Dish 模型增加 `bom_version`、`effective_date`；迁移 `z02_dish_bom_version`；`sync_dishes_to_graph` 同步至图谱 Dish 节点；DishResponse API 暴露两字段 |
| 前端 inventoryData 等 | 逐步替换为 L1 真实数据（POS/Excel） | Excel 导入已有；POS Webhook→图谱 已打通；前端替换为可选低优先级 |

---

**说明**：已实现的 Phase 0–3 与徐记扩展见上文各节「已实现」勾选；本节仅列**未开发或待补齐**项，按优先级可纳入下一轮 sprint。
