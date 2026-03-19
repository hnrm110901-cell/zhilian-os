# Neo4j 本体图迁移规划

> **版本**: v1.0 | **日期**: 2026-03-17 | **状态**: 规划中
>
> 将屯象OS中关系密集型数据从 PostgreSQL 迁移到 Neo4j 图数据库，释放图查询在多跳遍历、路径发现、相似度计算等场景下的性能优势。

---

## 1. 现状分析

### 1.1 已有基础设施

| 组件 | 状态 | 详情 |
|------|------|------|
| Neo4j 5.17 Community | **已部署** | docker-compose + k8s StatefulSet，APOC 插件已启用 |
| 连接配置 | **已完成** | `.env` 含 `NEO4J_URI/USER/PASSWORD`，`k8s/configmap.yaml` 含 Bolt 地址 |
| Schema Bootstrap | **已完成** | `src/ontology/bootstrap.py` — 11 个唯一约束 + 7 个性能索引，幂等执行 |
| 本体数据模型 | **已完成** | `src/ontology/models.py` — 11 个 dataclass 对象（Company/Store/Staff/Dish/BOM/Ingredient/Supplier/InventorySnapshot/Order/WasteEvent/Equipment） |
| Schema 枚举 | **已完成** | `src/ontology/schema.py` — 12 个 NodeLabel + 13 个 RelType + 4 个扩展节点（LiveSeafood/SeafoodPool/PortionWeight/PurchaseInvoice） |

### 1.2 已有代码模块

| 模块 | 文件 | 行数 | 职责 |
|------|------|------|------|
| OntologyAdapter | `src/agents/ontology_adapter.py` | 237 | Agent 基类：Cypher 查询 + BOM/损耗/门店知识摘要 |
| OntologyRepository | `src/ontology/repository.py` | 848 | 图 CRUD 封装：merge_node/merge_relation + BOM/库存/培训/设备/门店相似度/数据主权删除 |
| OntologyDataSync | `src/ontology/data_sync.py` | 766 | 融合层：POS/PG -> Neo4j 多源同步（Store/Dish/BOM/Ingredient/IngredientMapping/ExternalSource/ReasoningReport） |
| OntologySyncService | `src/services/ontology_sync_service.py` | 543 | PG -> Neo4j 批量同步：Store/Dish/Ingredient/Staff/Order/Supplier/BOM/WasteEvent + BOM 双向回写 PG |
| LLM Cypher Service | `src/services/llm_cypher_service.py` | ~200 | 自然语言 -> Cypher 只读查询（白名单校验） |
| Celery 定时任务 | `src/core/celery_tasks.py` | — | `daily_ontology_sync` 每日 02:00 执行全量 PG -> Neo4j 同步 |

### 1.3 当前问题（缺什么）

1. **同步方向单一**: 当前主要是 PG -> Neo4j 单向同步（仅 BOM 有双向回写），缺少实时事件驱动的增量同步
2. **Neo4j 仍是辅助角色**: 所有业务查询仍以 PG 为主，Neo4j 仅用于推理/知识图谱展示，降级策略是"返回空"
3. **缺少会员/消费图谱**: `PrivateDomain`（会员RFM/生命周期）、`Member`（会员画像）等数据尚未进入图谱
4. **无异步驱动**: 当前使用同步 `neo4j` Python driver（`GraphDatabase.driver`），无 async 支持
5. **缺乏性能监控**: 无 Cypher 查询性能 metrics，无图数据库容量监控
6. **扩展节点未纳入同步**: 徐记 POC 的 LiveSeafood/SeafoodPool/PortionWeight/PurchaseInvoice 节点无自动同步流程

---

## 2. 迁移范围

### 2.1 适合图化的 PG 关系（按优先级排序）

#### P0 — 已在 Neo4j 中，需强化

| PG 表 | Neo4j 节点 | 关系 | 现状 |
|--------|-----------|------|------|
| `stores` | `Store` | `(Company)-[:HAS_STORE]->(Store)` | 已同步，缺 Company 关联 |
| `dishes` | `Dish` | `(Store)-[:HAS_DISH]->(Dish)` | 已同步 |
| `bom_templates` + `bom_items` | `BOM` + `REQUIRES` | `(Dish)-[:HAS_BOM]->(BOM)-[:REQUIRES]->(Ingredient)` | 已同步，支持双向回写 |
| `inventory_items` | `Ingredient` | `(BOM)-[:REQUIRES]->(Ingredient)` | 已同步 |
| `employees` | `Staff` | `(Staff)-[:BELONGS_TO]->(Store)` | 已同步 |
| `orders` + `order_items` | `Order` | `(Order)-[:CONTAINS]->(Dish)`, `(Order)-[:BELONGS_TO]->(Store)` | 已同步 |
| `waste_events` | `WasteEvent` | `(WasteEvent)-[:TRIGGERED_BY]->(Staff)` | 已同步 |
| `suppliers` | `Supplier` | 节点已同步 | 缺 `SUPPLIES -> Ingredient` 关系 |

#### P1 — 适合迁入的关系密集型数据

| PG 表 | 建议 Neo4j 节点 | 核心关系 | 图化收益 |
|--------|----------------|---------|---------|
| `skill_nodes` + `training` | `Skill` + `TrainingModule` | `(Staff)-[:HAS_SKILL {level}]->(Skill)`, `(Skill)-[:TRAINED_BY]->(TrainingModule)` | 技能图谱：快速查询"会做某菜但缺某技能的员工"，多跳遍历 |
| `ingredient_masters` + `supply_chain.suppliers` | `Ingredient` + `Supplier` | `(Ingredient)-[:SUPPLIED_BY {lead_time, price}]->(Supplier)`, `(Supplier)-[:DELIVERS_TO]->(Store)` | 供应链图谱：断供影响分析（某供应商停供 -> 影响哪些菜品 -> 影响哪些门店） |
| `member_rfm` + `member_lifecycle` | `Member` | `(Member)-[:VISITED]->(Store)`, `(Member)-[:ORDERED]->(Dish)`, `(Member)-[:PREFERS {score}]->(DishCategory)` | 会员画像图：偏好推荐路径（相似会员喜欢什么菜） |
| `private_domain` | `MemberJourney` | `(Member)-[:JOURNEY_STAGE {stage, entered_at}]->(Store)` | 生命周期可视化 |
| `schedules` + `shifts` | `Shift` | `(Staff)-[:WORKS]->(Shift)`, `(Shift)-[:AT]->(Store)` | 排班关系：冲突检测、技能覆盖率计算 |

#### P2 — 长期迁入

| PG 表 | 建议 Neo4j 节点 | 核心关系 | 图化收益 |
|--------|----------------|---------|---------|
| `reservations` + `banquet_events` | `Reservation` + `BanquetEvent` | `(Reservation)-[:FOR]->(Store)`, `(BanquetEvent)-[:USES]->(BanquetHall)` | 宴会/预订资源图 |
| `competitor` | `Competitor` | `(Competitor)-[:NEAR]->(Store)` | 竞争态势图 |
| `marketing_campaigns` | `Campaign` | `(Campaign)-[:TARGETS]->(MemberSegment)`, `(Campaign)-[:PROMOTES]->(Dish)` | 营销效果归因图 |

### 2.2 不迁移的数据（留在 PG）

以下数据保留在 PostgreSQL，因为它们是事务性/审计性数据，关系简单，不受益于图查询：

- **财务类**: `payslips`、`bank_reconciliation`、`financial_closing`、`payment_reconciliation`
- **审计类**: `audit_logs`、`operation_audit_log`、`sensitive_audit_log`
- **配置类**: `agent_config`、`brand_im_config`、`channel_config`
- **流程类**: `approval_flows`、`workflow`、`backup_job`
- **认证类**: `users`、`health_certificates`

---

## 3. 本体模型设计

### 3.1 节点类型总览（目标状态）

```
已有 (12 + 4扩展 = 16 个):
  Store, Dish, BOM, Ingredient, Supplier, Staff, Order,
  WasteEvent, InventorySnapshot, Equipment, Company, TrainingModule
  + LiveSeafood, SeafoodPool, PortionWeight, PurchaseInvoice

新增 (P1, 6 个):
  Skill, Member, MemberSegment, Shift, DishCategory, SupplyRoute

新增 (P2, 3 个):
  Reservation, BanquetEvent, Campaign
```

### 3.2 P1 新增节点与关系（Cypher 示例）

#### 技能图谱

```cypher
-- 节点
CREATE CONSTRAINT unique_skill_id IF NOT EXISTS
  FOR (sk:Skill) REQUIRE sk.skill_id IS UNIQUE;

-- 员工技能关系
// (Staff)-[:HAS_SKILL {level, acquired_at, certified}]->(Skill)
MERGE (s:Staff {staff_id: $staff_id})
MERGE (sk:Skill {skill_id: $skill_id})
MERGE (s)-[r:HAS_SKILL]->(sk)
SET r.level = $level, r.acquired_at = $acquired_at, r.certified = $certified;

-- 技能->培训关联
// (Skill)-[:REQUIRES_TRAINING]->(TrainingModule)
MERGE (sk:Skill {skill_id: $skill_id})
MERGE (tm:TrainingModule {module_id: $module_id})
MERGE (sk)-[:REQUIRES_TRAINING]->(tm);

-- 查询：某菜品需要哪些技能，哪些员工具备
MATCH (d:Dish {dish_id: $dish_id})-[:HAS_BOM]->(b:BOM)-[:REQUIRES]->(i:Ingredient)
MATCH (sk:Skill)-[:RELATED_TO]->(i)
MATCH (s:Staff)-[r:HAS_SKILL]->(sk)
WHERE r.level >= 3
RETURN s.name, sk.name, r.level;
```

#### 供应链图谱

```cypher
-- 供应商->食材供应关系
// (Supplier)-[:SUPPLIES {price_fen, lead_time_days, min_order_qty}]->(Ingredient)
MERGE (sup:Supplier {sup_id: $sup_id})
MERGE (ing:Ingredient {ing_id: $ing_id})
MERGE (sup)-[r:SUPPLIES]->(ing)
SET r.price_fen = $price_fen,
    r.lead_time_days = $lead_time_days,
    r.min_order_qty = $min_order_qty,
    r.updated_at = timestamp();

-- 供应商->门店配送关系
// (Supplier)-[:DELIVERS_TO {frequency, route}]->(Store)
MERGE (sup:Supplier {sup_id: $sup_id})
MERGE (st:Store {store_id: $store_id})
MERGE (sup)-[r:DELIVERS_TO]->(st)
SET r.frequency = $frequency, r.route = $route;

-- 断供影响分析（3跳查询，PG 需要多次 JOIN）
MATCH (sup:Supplier {sup_id: $supplier_id})-[:SUPPLIES]->(ing:Ingredient)
      <-[:REQUIRES]-(b:BOM)<-[:HAS_BOM]-(d:Dish)<-[:HAS_DISH]-(s:Store)
RETURN s.name AS store_name, d.name AS dish_name, ing.name AS ingredient_name
ORDER BY s.name;
```

#### 会员画像图

```cypher
-- 会员节点
CREATE CONSTRAINT unique_member_id IF NOT EXISTS
  FOR (m:Member) REQUIRE m.member_id IS UNIQUE;

-- 消费关系
// (Member)-[:ORDERED {order_id, amount_fen, ordered_at}]->(Dish)
MERGE (m:Member {member_id: $member_id})
MERGE (d:Dish {dish_id: $dish_id})
CREATE (m)-[:ORDERED {
  order_id: $order_id,
  amount_fen: $amount_fen,
  ordered_at: $ordered_at
}]->(d);

-- 偏好关系（由推理层写入）
// (Member)-[:PREFERS {score, computed_at}]->(DishCategory)
MERGE (m:Member {member_id: $member_id})
MERGE (cat:DishCategory {name: $category})
MERGE (m)-[r:PREFERS]->(cat)
SET r.score = $score, r.computed_at = timestamp();

-- 推荐查询：与目标会员消费相似的会员还点了什么
MATCH (target:Member {member_id: $member_id})-[:ORDERED]->(d:Dish)
      <-[:ORDERED]-(similar:Member)-[:ORDERED]->(recommend:Dish)
WHERE NOT (target)-[:ORDERED]->(recommend)
RETURN recommend.name, count(similar) AS overlap
ORDER BY overlap DESC LIMIT 5;
```

### 3.3 关系类型完整清单（目标状态）

```
层级关系:
  (Company)-[:HAS_STORE]->(Store)
  (Store)-[:HAS_DISH]->(Dish)
  (Dish)-[:HAS_BOM]->(BOM)
  (BOM)-[:REQUIRES {qty, unit, waste_factor}]->(Ingredient)
  (BOM)-[:SUCCEEDED_BY]->(BOM)

运营关系:
  (Order)-[:CONTAINS {qty, unit_price}]->(Dish)
  (Order)-[:PLACED_AT]->(Store)
  (Staff)-[:BELONGS_TO]->(Store)
  (Staff)-[:WORKS]->(Shift)

供应链关系:
  (Supplier)-[:SUPPLIES {price_fen, lead_time}]->(Ingredient)
  (Supplier)-[:DELIVERS_TO]->(Store)
  (Equipment)-[:STORES]->(Ingredient)

技能关系:
  (Staff)-[:HAS_SKILL {level, certified}]->(Skill)
  (Skill)-[:REQUIRES_TRAINING]->(TrainingModule)
  (Staff)-[:COMPLETED_TRAINING {score}]->(TrainingModule)
  (Staff)-[:NEEDS_TRAINING {urgency}]->(TrainingModule)

会员关系:
  (Member)-[:ORDERED {amount_fen}]->(Dish)
  (Member)-[:VISITED]->(Store)
  (Member)-[:PREFERS {score}]->(DishCategory)

推理/损耗关系:
  (WasteEvent)-[:INVOLVES]->(Ingredient)
  (WasteEvent)-[:TRIGGERED_BY {confidence}]->(Staff)
  (WasteEvent)-[:OCCURRED_IN]->(Store)
  (WasteEvent)-[:ROOT_CAUSE {evidence}]->(Equipment|Staff|Ingredient)

跨店关系:
  (Store)-[:SIMILAR_TO {score, reason}]->(Store)
  (Store)-[:SHARES_RECIPE {variance_pct}]->(Store)
  (Store)-[:BENCHMARK_OF]->(BenchmarkSnapshot)
```

---

## 4. 迁移策略

### Phase 1: 双写（4 周）

**目标**: PG 保留为主库，Neo4j 作为辅助查询层，新写入同步到两个库。

**改造内容**:

1. **Service 层双写拦截器**
   - 在关键 Service（`bom_service`、`ontology_sync_service`、`waste_event_service`）的写入路径上，增加 Neo4j 写入调用
   - 写入 Neo4j 失败不阻塞 PG 事务（try-catch + 降级日志）
   - 利用现有 `OntologyRepository.merge_node` / `merge_relation` 作为统一写入入口

2. **增量事件驱动**
   - 在 PG 写入后发布 Redis 事件（`store:updated`、`dish:created`、`order:placed`）
   - 新增 Celery worker 消费事件，调用 `ontology_sync_service` 对应方法
   - 保留每日 02:00 全量同步作为兜底

3. **P1 新节点写入**
   - Supplier -> Ingredient 的 SUPPLIES 关系（从 `supply_chain.suppliers` 同步）
   - Skill 节点（从 `skill_nodes` 同步）
   - Member 节点（从 `member_rfm` 同步，仅写入活跃会员）

4. **异步驱动升级**
   - 引入 `neo4j` async driver（`AsyncGraphDatabase.driver`）替换同步调用
   - 改造 `OntologyRepository` 为 async 版本（`AsyncOntologyRepository`）

**验收标准**:
- PG 与 Neo4j 节点数差异 < 1%（每日对账脚本）
- Neo4j 写入失败率 < 0.1%
- 双写延迟 < 200ms（P99）

### Phase 2: 读切换（6 周）

**目标**: 关系密集型查询逐步迁移到 Neo4j，PG 降级为数据归档。

**改造内容**:

1. **查询路由层**
   - 新增 `GraphQueryRouter`：根据查询类型决定走 PG 还是 Neo4j
   - 规则：多跳关系查询（BOM 展开、断供影响、会员推荐） -> Neo4j
   - 规则：单表 CRUD、分页列表、聚合统计 -> PG
   - 支持 Feature Flag 按查询粒度切换

2. **迁移优先级**（按业务影响排序）
   - **第 1 批**: BOM 展开查询（`get_dish_bom`、`get_dish_bom_ingredients`） — 当前已在 Neo4j，切为主路径
   - **第 2 批**: 损耗推理链（`explain_reasoning`、`get_waste_events`） — 当前已在 Neo4j
   - **第 3 批**: 供应链影响分析（新增查询） — Neo4j 原生
   - **第 4 批**: 会员推荐/相似度查询 — Neo4j 原生
   - **第 5 批**: 技能图谱查询 — Neo4j 原生

3. **LLM Cypher Service 增强**
   - 更新 `ONTOLOGY_SCHEMA` 提示词，纳入新增节点/关系
   - 增加查询结果缓存（Redis 60s TTL）

4. **性能对比验证**
   - 每个批次切换前，对同一查询分别测量 PG（SQL）和 Neo4j（Cypher）的响应时间
   - Neo4j 必须在多跳查询上优于 PG 才切换，否则保留 PG

**验收标准**:
- 已迁移查询的 P95 延迟 < 100ms
- 业务功能零回归（AB 测试 1 周无告警）
- PG 相关表的读 QPS 下降 > 50%

### Phase 3: 完全迁移（8 周）

**目标**: 关系数据完全在 Neo4j，PG 仅存储事务性/审计性数据。

**改造内容**:

1. **PG 表归档**
   - `bom_templates` / `bom_items` -> 只保留最近 90 天热数据，历史归档到冷存储
   - `skill_nodes` / `training` -> 完全迁移到 Neo4j，PG 表标记 deprecated
   - `member_rfm` / `member_lifecycle` -> 图谱为主，PG 保留只读快照供报表

2. **同步方向反转**
   - 部分数据的主写入改为 Neo4j -> PG 反向同步（仅保留 PG 兼容性）
   - BOM 管理界面直接操作 Neo4j，通过 `sync_bom_version_to_pg` 回写

3. **废弃代码清理**
   - 删除不再需要的 PG -> Neo4j 全量同步（`daily_ontology_sync` 简化为对账任务）
   - `OntologyDataSync` 与 `OntologySyncService` 合并为单一 `GraphService`

4. **Neo4j 集群化**（如业务量增长需要）
   - 从 Community 升级到 Enterprise（或 Aura）
   - 读写分离：1 Primary + 2 Read Replicas

**验收标准**:
- 关系查询 100% 走 Neo4j
- PG 中关系密集型表可以安全清理
- Neo4j 集群 SLA > 99.9%

---

## 5. 数据迁移脚本设计

### 5.1 ETL 流程总览

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │────>│  ETL Worker  │────>│    Neo4j     │
│  (asyncpg)   │     │  (Python)    │     │  (Bolt)      │
└──────────────┘     └──────────────┘     └──────────────┘
      │                     │                     │
      │  SELECT + LIMIT     │  MERGE/CREATE       │
      │  + cursor 分页      │  + UNWIND 批量       │
      │                     │  + 事务管理           │
      └─────────────────────┴─────────────────────┘
```

### 5.2 现有同步入口（直接复用）

当前 `ontology_sync_service.sync_ontology_from_pg()` 已实现 8 类数据同步：

```python
# 已实现的同步函数（可直接作为初始迁移脚本）
sync_stores_to_graph()       # Store 节点 + SIMILAR_TO 关系
sync_dishes_to_graph()       # Dish 节点
sync_ingredients_to_graph()  # Ingredient 节点
sync_staff_to_graph()        # Staff 节点 + BELONGS_TO 关系
sync_orders_to_graph()       # Order 节点 + CONTAINS/BELONGS_TO 关系
sync_suppliers_to_graph()    # Supplier 节点
sync_boms_to_graph()         # BOM 节点 + HAS_BOM/REQUIRES 关系
sync_waste_events_to_graph() # WasteEvent 节点 + TRIGGERED_BY 关系
```

### 5.3 新增迁移脚本需求

| 脚本 | 源 PG 表 | 目标 Neo4j | 预估数据量 | 批次大小 |
|------|----------|-----------|-----------|---------|
| `migrate_supplier_ingredients.py` | `supply_chain.suppliers` + 关联表 | `(Supplier)-[:SUPPLIES]->(Ingredient)` | ~500 关系 | 100/批 |
| `migrate_skills.py` | `skill_nodes` + `training` | `(Staff)-[:HAS_SKILL]->(Skill)` | ~2000 节点 | 200/批 |
| `migrate_members.py` | `member_rfm` + `orders` | `(Member)-[:ORDERED]->(Dish)` | ~50000 关系 | 1000/批 |
| `migrate_shifts.py` | `schedules` + `shifts` | `(Staff)-[:WORKS]->(Shift)` | ~10000 关系 | 500/批 |

### 5.4 批量写入模式

```cypher
-- 使用 UNWIND 批量写入（比逐条 MERGE 快 10-50 倍）
UNWIND $batch AS row
MERGE (sup:Supplier {sup_id: row.sup_id})
MERGE (ing:Ingredient {ing_id: row.ing_id})
MERGE (sup)-[r:SUPPLIES]->(ing)
SET r.price_fen = row.price_fen,
    r.lead_time_days = row.lead_time_days,
    r.updated_at = timestamp()
```

### 5.5 对账脚本

```
每日 03:00（在全量同步之后）执行对账：
1. 分别查询 PG 和 Neo4j 各节点类型的 COUNT
2. 抽样 100 条记录做属性一致性校验
3. 差异 > 1% 发送企微告警
4. 将对账结果写入 Prometheus metric: ontology_sync_diff_ratio
```

---

## 6. 回滚计划

### 6.1 Phase 1 回滚（双写阶段）

- **触发条件**: Neo4j 写入失败率 > 5% 持续 10 分钟，或 Neo4j 服务完全不可用
- **回滚操作**: 关闭双写开关（Feature Flag `neo4j_dual_write_enabled=false`），所有写入仅走 PG
- **数据恢复**: 下次全量同步（每日 02:00）自动补齐 Neo4j 数据
- **影响范围**: 无，PG 仍为主库

### 6.2 Phase 2 回滚（读切换阶段）

- **触发条件**: Neo4j 查询 P99 > 500ms 持续 5 分钟，或查询结果与 PG 不一致
- **回滚操作**: `GraphQueryRouter` Feature Flag 按查询类型逐个回退到 PG
- **数据恢复**: 不需要，PG 数据仍然完整
- **影响范围**: 部分查询恢复为 PG SQL

### 6.3 Phase 3 回滚（完全迁移阶段）

- **触发条件**: Neo4j 集群故障且无法在 15 分钟内恢复
- **回滚操作**:
  1. 启用 PG 备份表（Phase 3 开始前创建的只读副本）
  2. 切换 `GraphQueryRouter` 全部回退到 PG
  3. 从 Neo4j 最新备份 + PG 归档还原
- **数据恢复**: 可能丢失最近一次对账间隔（最多 24 小时）的图谱写入
- **影响范围**: 多跳查询性能下降，但功能不丢失

### 6.4 Neo4j 备份策略

```
- 开发环境: docker volume 快照（每日）
- 生产环境: neo4j-admin database dump（每日 01:00，保留 7 天）
- K8s: VolumeSnapshot（每日，保留 14 天）
```

---

## 7. 性能基准

### 7.1 需要测量的关键指标

| 指标 | 测量方法 | PG 预期 | Neo4j 预期 | 改善倍数 |
|------|---------|---------|-----------|---------|
| **BOM 3 层展开**（菜品->BOM->食材->供应商） | 单次查询延迟 | ~50ms（3 次 JOIN） | ~5ms（1 次遍历） | 10x |
| **断供影响分析**（供应商->食材->BOM->菜品->门店，4 跳） | 单次查询延迟 | ~200ms（4 次 JOIN + 子查询） | ~10ms（路径遍历） | 20x |
| **会员推荐**（相似会员消费重叠，协同过滤） | 单次查询延迟 | ~500ms（多次 JOIN + GROUP BY） | ~30ms（图遍历 + COUNT） | 15x |
| **损耗根因链**（事件->食材->BOM->厨师->培训，5 跳） | 单次查询延迟 | ~300ms | ~15ms | 20x |
| **门店相似度 Top-K** | 单次查询延迟 | ~100ms（全表扫描 + 距离计算） | ~3ms（关系索引） | 30x |
| **技能覆盖率**（某门店所有菜品需要的技能 vs 当前员工技能） | 单次查询延迟 | ~400ms | ~20ms | 20x |

### 7.2 基准测试计划

1. **Phase 1 结束时**: 对上述 6 个查询建立 PG 基准线（production-like 数据量）
2. **Phase 2 每批切换前**: 同时执行 PG SQL 和 Neo4j Cypher，记录 P50/P95/P99
3. **Phase 3 结束时**: 确认所有关系查询的 P95 < 50ms

### 7.3 容量规划

| 指标 | 当前（POC） | 6 个月预期 | 12 个月预期 |
|------|------------|-----------|------------|
| 节点总数 | ~5,000 | ~100,000 | ~500,000 |
| 关系总数 | ~15,000 | ~500,000 | ~2,000,000 |
| 数据库大小 | ~50MB | ~2GB | ~10GB |
| Heap 内存 | 512MB | 2GB | 4GB |
| Page Cache | — | 1GB | 2GB |
| 查询 QPS | ~10 | ~200 | ~1000 |

---

## 8. 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **Neo4j Community 版功能限制**（无集群、无在线备份） | Phase 3 无法实现读写分离 | 中 | 评估 Neo4j Aura 或 Enterprise 许可证成本；备选方案：Memgraph（MIT 协议兼容 Cypher） |
| **双写一致性问题** | PG 写入成功但 Neo4j 失败导致数据不一致 | 中 | 异步双写 + 每日对账 + 补偿队列（失败的写入放入 Redis 重试队列） |
| **Cypher 查询性能不及预期** | 某些查询在小数据量下 Neo4j 不如 PG | 低 | Phase 2 逐个查询 AB 测试，不及预期的保留 PG |
| **APOC 插件兼容性** | Neo4j 版本升级后 APOC 不兼容 | 低 | 锁定 Neo4j 5.17 + APOC 版本；升级前在 staging 验证 |
| **开发团队 Cypher 学习曲线** | 新查询开发速度慢 | 中 | LLM Cypher Service 辅助生成查询；编写 Cypher 最佳实践文档；Repository 层封装常用查询 |
| **async driver 改造工作量** | 现有同步 driver 改异步影响面大 | 中 | 分步改造：Phase 1 仅新增代码用 async，旧代码 Phase 2 统一迁移 |
| **会员数据量爆炸** | 大量消费关系导致图数据库膨胀 | 中 | 会员消费关系设置 TTL（仅保留 180 天热数据），历史聚合为 PREFERS 关系 |
| **数据主权/GDPR** | 图数据库删除需要 DETACH DELETE | 低 | `OntologyRepository.delete_tenant_data()` 已实现，扩展至新增节点类型 |

---

## 附录 A: 现有 Neo4j 相关文件索引

```
apps/api-gateway/src/ontology/
  __init__.py               # 模块入口，导出 get_ontology_repository()
  bootstrap.py              # Schema 初始化（约束+索引）
  cypher_schema.py          # Cypher DDL 语句生成
  data_sync.py              # 数据融合层（POS/PG -> Neo4j）
  models.py                 # 本体 dataclass（11 个对象）
  reasoning.py              # 推理层图查询
  repository.py             # 图 CRUD 封装（848 行）
  schema.py                 # NodeLabel/RelType 枚举

apps/api-gateway/src/agents/
  ontology_adapter.py       # Agent 基类（Neo4j 查询能力）

apps/api-gateway/src/services/
  ontology_sync_service.py  # PG -> Neo4j 同步（8 类数据）
  ontology_sync_pipeline.py # 同步管线编排
  ontology_nl_query_service.py  # 自然语言图谱查询
  ontology_knowledge_service.py # 知识规则管理
  ontology_export_service.py    # 图谱导出
  ontology_cross_store_service.py # 跨店知识传播
  ontology_context_service.py   # 图谱上下文服务
  ontology_agent_service.py     # 本体 Agent 编排
  ontology_action_service.py    # 本体动作执行
  ontology_replenish_service.py # 本体补货服务
  llm_cypher_service.py         # LLM -> Cypher 转换
  store_ontology_replicator.py  # 门店本体复制
  causal_graph_service.py       # 因果图服务

docker-compose.yml          # Neo4j 5.17 容器配置
k8s/neo4j-statefulset.yaml  # K8s 部署（StatefulSet + Headless Service）
k8s/configmap.yaml          # NEO4J_URI/USER 配置
.env.example                # NEO4J_URI/USER/PASSWORD
```

## 附录 B: 里程碑时间线

| 里程碑 | 时间 | 交付物 |
|--------|------|--------|
| M0: 规划确认 | Week 0 | 本文档评审通过 |
| M1: Phase 1 双写上线 | Week 4 | 增量同步 + P1 新节点 + async driver + 对账脚本 |
| M2: Phase 2 第 1-2 批查询切换 | Week 7 | BOM/损耗查询走 Neo4j |
| M3: Phase 2 第 3-5 批查询切换 | Week 10 | 供应链/会员/技能查询走 Neo4j |
| M4: Phase 3 完全迁移 | Week 18 | PG 关系表归档，Neo4j 为主 |
| M5: 性能优化 & 稳定性 | Week 20 | 所有查询 P95 < 50ms，SLA > 99.9% |
