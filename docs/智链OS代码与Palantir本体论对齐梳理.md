# 智链OS 代码与 Palantir 本体论对齐梳理

> 基于《智链OS-Palantir本体论-兼容性扩展性与产品计划》与当前代码库，梳理原智链OS 项目代码与四层本体论架构的对应关系及对齐状态。  
> 版本 v1.0 · 2026年2月

---

## 一、项目结构概览

```
zhilian-os/
├── apps/
│   ├── api-gateway/          # FastAPI 主应用（本体论相关逻辑集中在此）
│   │   ├── src/
│   │   │   ├── api/          # 路由层（含 ontology_api、enterprise、pos_webhook 等）
│   │   │   ├── core/         # 配置、Celery、数据库
│   │   │   ├── models/       # SQLAlchemy 模型（含 ontology_action）
│   │   │   ├── ontology/     # L2 本体层：Schema + Repository + Cypher
│   │   │   └── services/     # 业务服务（ontology_*、waste_reasoning、perception_import 等）
│   │   └── alembic/          # 迁移（含 ontology_actions 表）
│   └── web/                  # React 前端
├── packages/
│   ├── agents/               # 7 专域 Agent（排班/订单/库存/服务/培训/决策/预约 + private_domain）
│   └── api-adapters/         # 奥琦韦、品智、亿订、天财、美团等适配器
├── src/                      # 根目录共享（部分 services/models 与 api-gateway 重复或历史）
└── docs/                     # 产品计划、对标分析、本对齐梳理
```

**本体论相关代码入口**：`apps/api-gateway` 内 `src/ontology/`、`src/services/ontology_*`、`src/api/ontology_api.py`，以及 `enterprise.py`（企微）、`pos_webhook.py`（POS→图谱）、`decision_validator.py`（推理+图谱事实）。

---

## 二、四层架构 ↔ 代码映射与对齐状态

### 2.1 L1 感知层（Perception）

| 目标能力 | 代码位置 | 对齐状态 | 说明 |
|----------|----------|----------|------|
| 语义标准化、多源入图 | `src/services/perception_import_service.py` | ✅ 已对齐 | Excel/CSV 库存快照导入，列映射到本体 |
| POS → 本体写入 | `src/api/pos_webhook.py` + `ontology_sync_service.push_normalized_order_to_graph` | ✅ 已对齐 | Webhook 归一化后双写 PG + 图谱（Order + BELONGS_TO + CONTAINS） |
| IoT/边缘 → 本体 | `src/api/ontology_api.py`（`POST /ontology/perception/edge-push`） | ✅ 已对齐 | 标准化 JSON 写入 InventorySnapshot、Equipment |
| 导入模板 | `GET /ontology/perception/template/inventory_snapshot` | ✅ 已对齐 | 下载 CSV 模板 |
| 外部 POS/会员 | `packages/api-adapters/`、`src/services/pinzhi_service.py`、`members.py`（奥琦韦） | 🔶 部分对齐 | 业务 API 与健康检查已有；与图谱的「融合写入」仅 Webhook 路径打通，拉取式 POS 仍可走 sync-from-pg |

**L1 小结**：感知层「标准化 + 写图谱」已具备：Webhook 订单、边缘 edge-push、Excel 导入。拉取式 POS 数据需先落 PG 再通过 `sync-from-pg` 入图。

---

### 2.2 L2 本体层（Ontology）

| 目标能力 | 代码位置 | 对齐状态 | 说明 |
|----------|----------|----------|------|
| 图库与配置 | `docker-compose.yml`（Neo4j）、`src/core/config.py`（NEO4J_*） | ✅ 已对齐 | Neo4j 5.x，ENABLED 可关 |
| 11 对象 + 关系 Schema | `src/ontology/schema.py`、`cypher_schema.py` | ✅ 已对齐 | NodeLabel 11 类 + RelType + 约束与索引 |
| 图谱 CRUD | `src/ontology/repository.py` | ✅ 已对齐 | merge_node、merge_relation、upsert_bom、merge_*（含 Equipment、WasteEvent、徐记扩展） |
| BOM 本体化与时间旅行 | `repository.py`（upsert_bom、get_dish_bom_ingredients、get_dish_bom_ingredients_as_of） | ✅ 已对齐 | 版本/生效日/过期日；`GET /ontology/bom/dish/{id}?as_of=YYYY-MM-DD` |
| PG → 图谱同步 | `src/services/ontology_sync_service.py` | ✅ 已对齐 | Store、Dish、Ingredient、Staff、Order + 关系；`POST /ontology/sync-from-pg` |
| 设备节点 | `repository.merge_equipment`、`POST /ontology/equipment` | ✅ 已对齐 | Equipment + BELONGS_TO Store |
| 库存快照 | `repository.merge_inventory_snapshot` | ✅ 已对齐 | 感知层/边缘写入用 |
| 徐记扩展节点 | `repository.merge_live_seafood` 等、`/ontology/xuji/*` | ✅ 已对齐 | LiveSeafood、SeafoodPool、PortionWeight、PurchaseInvoice |
| 初始化 | `POST /ontology/init-schema` | ✅ 已对齐 | 创建约束与索引 |

**L2 小结**：本体层已按 11 对象 + 关系 + 版本管理落地，PG 双写与同步、设备与徐记扩展均具备。

---

### 2.3 L3 推理层（Reasoning）

| 目标能力 | 代码位置 | 对齐状态 | 说明 |
|----------|----------|----------|------|
| 损耗五步推理 | `src/services/waste_reasoning_service.py`、`POST /ontology/reasoning/waste` | ✅ 已对齐 | 库存差异→BOM 偏差→时间窗口员工→供应商批次→根因 TOP3；写回 WasteEvent + TRIGGERED_BY |
| 决策校验 + 图谱事实 | `src/services/decision_validator.py`（OntologyFactsRule）、`get_ontology_facts_for_decision` | ✅ 已对齐 | 校验前注入图谱事实，与规则引擎联合 |
| LLM 自然语言查询 | `src/services/ontology_nl_query_service.py`、`POST /ontology/query` | ✅ 已对齐 | 意图→图谱/推理→答案+溯源 |
| 时序预测备货 | `src/services/ontology_replenish_service.py`、`GET /ontology/replenish` | ✅ 已对齐 | Prophet 订单预测 + 图谱 BOM + 损耗缓冲 |
| Agent 图谱上下文 | `src/services/ontology_context_service.py`、`GET /ontology/context` | ✅ 已对齐 | BOM/库存快照/损耗摘要供 Agent 拉取 |
| 规则引擎（非图谱） | `decision_validator` 双规校验等 | ✅ 保留 | 与图谱事实并行 |

**L3 小结**：推理层已覆盖损耗推理、决策校验、NL 查询、备货建议、Agent 上下文，均与图谱或 PG 联动。

---

### 2.4 L4 行动层（Action）

| 目标能力 | 代码位置 | 对齐状态 | 说明 |
|----------|----------|----------|------|
| Action 模型与状态机 | `src/models/ontology_action.py`、`ontology_action_service.py` | ✅ 已对齐 | CREATED→SENT→ACKED→IN_PROGRESS→DONE/CLOSED，P0–P3 时限 |
| 创建/列表/状态/推送 | `POST/GET/PATCH /ontology/actions`、`POST /ontology/actions/{id}/send` | ✅ 已对齐 | 推送企微（文本或任务卡片） |
| 任务卡片 + 一键回执 | `wechat_service.send_card_message`、`GET /enterprise/action-ack` | ✅ 已对齐 | ACTION_ACK_BASE_URL 配置后发卡片，回执验签更新 ACKED |
| 超时自动升级 | `ontology_action_service.process_escalations`、Celery `escalate_ontology_actions` | ✅ 已对齐 | 每 10 分钟扫描，标记并推送 WECHAT_ESCALATION_TO |
| 企微 Webhook | `src/api/enterprise.py`（GET/POST /wechat/webhook） | ✅ 已对齐 | 签名验证、解密、文本/私域 Agent 回复 |

**L4 小结**：行动层已具备完整任务生命周期与企微集成（含卡片与回执、自动升级）。

---

## 三、数据主权与规模化（Phase 3）

| 能力 | 代码位置 | 对齐状态 |
|------|----------|----------|
| 图谱导出 | `ontology_export_service`、`GET /ontology/export` | ✅ 已对齐 |
| 加密导出与断开权 | `data_sovereignty_service`、`/ontology/data-sovereignty/*` | ✅ 已对齐 |
| 跨店损耗对比 | `ontology_cross_store_service`、`GET /ontology/cross-store/waste` | ✅ 已对齐 |
| 本体模板复制 | `repository.clone_template_to_store`、`POST /ontology/clone-template` | ✅ 已对齐 |
| 知识库雏形 | `ontology_knowledge_service`、`POST/GET /ontology/knowledge` | ✅ 已对齐（文件存储） |

---

## 四、本体相关 API 速查（按层级）

| 层级 | 方法 | 路径 | 说明 |
|------|------|------|------|
| L2 | POST | `/api/v1/ontology/init-schema` | 初始化约束与索引 |
| L2 | POST | `/api/v1/ontology/bom/upsert` | BOM 本体化 |
| L2 | GET | `/api/v1/ontology/bom/dish/{dish_id}` | 查 BOM（可选 `?as_of=YYYY-MM-DD`） |
| L2 | POST | `/api/v1/ontology/sync-from-pg` | PG → 图谱同步 |
| L2 | POST | `/api/v1/ontology/equipment` | 写入设备节点 |
| L2 | POST | `/api/v1/ontology/clone-template` | 本体模板复制到新店 |
| L1 | GET | `/api/v1/ontology/perception/template/inventory_snapshot` | 库存快照 CSV 模板 |
| L1 | POST | `/api/v1/ontology/perception/import` | Excel/CSV 导入 |
| L1 | POST | `/api/v1/ontology/perception/edge-push` | 边缘/IoT 标准化上报 |
| L3 | POST | `/api/v1/ontology/reasoning/waste` | 损耗五步推理 |
| L3 | POST | `/api/v1/ontology/query` | 自然语言查询 |
| L3 | GET | `/api/v1/ontology/replenish` | 时序预测备货建议 |
| L3 | GET | `/api/v1/ontology/context` | Agent 图谱上下文 |
| L4 | POST/GET/PATCH | `/api/v1/ontology/actions` | Action CRUD 与状态 |
| L4 | POST | `/api/v1/ontology/actions/{id}/send` | 推送企微 |
| - | GET | `/api/v1/enterprise/action-ack` | 一键回执（任务卡片点击） |
| Phase3 | GET | `/api/v1/ontology/export` | 图谱快照导出 |
| Phase3 | GET | `/api/v1/ontology/cross-store/waste` | 跨店损耗对比 |
| Phase3 | POST | `/api/v1/ontology/data-sovereignty/*` | 加密导出、断开权 |
| Phase3 | POST/GET | `/api/v1/ontology/knowledge` | 知识库（损耗规则/BOM 基准/异常模式） |
| - | GET | `/api/v1/ontology/health` | Neo4j 健康检查 |

---

## 五、与原业务模块的对接关系

| 原模块 | 与本体论对齐方式 |
|--------|------------------|
| **Agent**（`packages/agents/*`、`agent_service.py`） | 通过 `GET /ontology/context` 拉取 BOM/库存/损耗摘要；可创建 Action（`POST /ontology/actions`） |
| **决策校验**（`decision_validator.py`） | 校验前注入 `ontology_facts`（`get_ontology_facts_for_decision`），规则中可引用图谱事实 |
| **企微**（`wechat_service`、`enterprise.py`） | 发任务文本/卡片、Webhook 接收、action-ack 回执、升级推送 |
| **POS**（`pos_webhook`、`pinzhi_service` 等） | Webhook 路径：订单归一化后 `push_normalized_order_to_graph`；其他 POS 数据经 PG 再 `sync-from-pg` |
| **订单/门店/员工/菜品**（`orders`、`stores`、`employees`、`dishes`） | 仍为 PG 权威数据；图谱通过 sync-from-pg 同步，双库并行 |
| **BOM/配方**（`DishIngredient`、根目录 `bom_service`） | 图谱 BOM 为本体化结果；可从 PG 同步后通过 `/ontology/bom/upsert` 维护版本 |
| **库存**（`inventory`、`InventoryItem`） | 库存事务在 PG；快照语义写入图谱（perception 导入、edge-push） |
| **定时任务**（Celery） | `escalate_ontology_actions` 每 10 分钟执行 Action 超时升级；其他任务不变 |

---

## 六、建议的后续对齐动作（可选）

1. **融合层（对标分析中的 L2 Fusion）**  
   当前为「多源写同一套本体 ID」；若需显式多源融合（如 POS id / 供应商 id / 企微 id 映射与置信度），可增加 `DataFusionEngine` 或图谱节点上的 `external_ids` / `fusion_confidence` 字段。

2. **PG Dish 表**  
   若希望报表与前端直接显示「当前生效 BOM 版本」，可在 Dish 表增加 `bom_version` 或与图谱 BOM version 的映射字段。

3. **前端**  
   将仍使用模拟数据（如 `inventoryData.ts`）的页面逐步改为调用 L1 真实数据（`/ontology/perception/*`、`/ontology/context` 等）。

4. **知识库持久化**  
   当前知识库为文件存储；若需多实例或审计，可迁至 PostgreSQL 表或图谱节点。

---

## 七、总结

| 维度 | 状态 |
|------|------|
| **L1 感知层** | 已对齐：Webhook 订单→图谱、edge-push、Excel/CSV 导入、模板 |
| **L2 本体层** | 已对齐：Neo4j Schema、11 对象+关系、BOM 与时间旅行、PG 同步、Equipment、徐记扩展 |
| **L3 推理层** | 已对齐：损耗五步推理、决策+图谱事实、NL 查询、备货建议、Agent 上下文 |
| **L4 行动层** | 已对齐：Action 状态机、企微推送与任务卡片、一键回执、自动升级 |
| **Phase 3** | 已对齐：导出、加密与断开权、跨店对比、模板复制、知识库雏形 |

原智链OS 项目代码已按 Palantir 本体论四层架构完成对齐与实现；业务模块（Agent、决策、企微、POS、订单/门店/员工/菜品）通过图谱同步、上下文 API 与 Action API 与本体层衔接，双库（PostgreSQL + Neo4j）并行、可执行任务与数据主权能力均已就绪。
