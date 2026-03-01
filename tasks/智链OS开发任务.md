# 智链OS 开发任务清单

> 依据《智链OS-Palantir本体论-兼容性扩展性与产品计划》与 `tasks/todo.md` 整理，便于排期与验收。  
> 更新日期：2026-02

---

## 一、本轮已完成（本节更新）

- [x] **PG Dish 与 BOM 版本对齐**（产品计划 7.6 对接清单）
  - `Dish` 模型增加可选字段 `bom_version`、`effective_date`
  - Alembic 迁移 `z02_dish_bom_version` 已添加
  - `ontology_sync_service.sync_dishes_to_graph` 同步时将 `bom_version`/`effective_date` 写入图谱 Dish 节点
  - 菜品 API `DishResponse` 增加可选 `bom_version`、`effective_date`

- [x] **Week 2 业务调度**（开发计划排期项）
  - 营收异常检测、日报生成、库存预警已由 `scheduler.py` + Celery 任务实现；修复 `scheduler` 缺失的 `datetime` 导入。

- [x] **BOM 双向同步**（后续可迭代方向）
  - `ontology_sync_service.sync_bom_version_to_pg(dish_id, version, effective_date)`：图谱 BOM 写入后回写 PG `Dish.bom_version`、`Dish.effective_date`
  - `POST /ontology/bom/upsert` 成功后自动调用，保证 PG 与图谱一致。

- [x] **Week 4 语音**（后续可排期项）
  - 语音提供商可配置：`VOICE_PROVIDER=azure|baidu|xunfei`（config + `voice_service` 全局实例按 env 选择）。
  - Shokz 边缘回调：`EDGE_SHOKZ_CALLBACK_URL` 配置后，`connect_device`/`disconnect_device`/`voice_output` 会 POST 通知边缘节点（树莓派5）执行实际蓝牙连接/断开/音频播放。

- [x] **Week 5–6 向量库**（后续可排期项）
  - 可替换嵌入模型：`EMBEDDING_PROVIDER=local|openai`；`local` 使用 sentence-transformers（默认 384 维），`openai` 使用 OpenAI Embeddings API（`OPENAI_EMBEDDING_MODEL`，1536 维）。
  - `vector_db_service` 与 `domain_vector_service` 均支持；集合维度随 provider 自动使用 384 或 1536。

---

## 二、计划内待补齐（产品计划 §7.6）

| 项 | 说明 | 状态 |
|----|------|------|
| 前端 inventoryData 等 | 逐步替换为 L1 真实数据（POS/Excel）；Excel 导入与 POS Webhook→图谱已打通 | 可选、低优先级 |

---

## 三、TODO 清理计划中的排期项（api-gateway）

| 阶段 | 内容 | 优先级 | 状态 |
|------|------|--------|------|
| Week 2 | 业务调度：营收异常检测、日报生成、库存预警（`scheduler.py`） | P0 | 已完成 |
| Week 4 | 语音：STT/TTS 可配置提供商、Shokz 边缘回调（`voice_service`、`shokz_device_service`） | P0 | 已完成 |
| Week 5–6 | 向量库：可替换嵌入模型 local/openai（`vector_db_service`、`domain_vector_service`） | P1 | 已完成 |

---

## 四、建议冻结/暂缓（产品计划 §3.4）

- 联邦学习、国际化、开放 API 平台、竞争分析页：仅维护不增强。

---

## 五、后续可迭代方向

- ~~**BOM 双向同步**~~：已实现；`POST /ontology/bom/upsert` 后自动回写 PG Dish。
- ~~**知识库增强**~~：已实现。损耗规则库、BOM 基准库、异常模式库的编辑（`PATCH/DELETE /ontology/knowledge/{id}`）与连锁下发（`POST /ontology/knowledge/{id}/distribute`，支持按门店或连锁级下发）。
- ~~**数据主权**~~：已实现。加密导出/断开权调用时写入审计日志（AuditAction.DATA_SOVEREIGNTY_*、ResourceType.DATA_SOVEREIGNTY）；`GET /ontology/data-sovereignty/config`（enabled、key_configured）、`GET /ontology/data-sovereignty/audit-logs`；前端「数据主权」页（系统管理菜单：配置状态、加密导出/断开权操作、审计日志列表）。

---

## 六、参考文档

- [智链OS-Palantir本体论-兼容性扩展性与产品计划](../docs/智链OS-Palantir本体论-兼容性扩展性与产品计划.md)
- [智链OS-Palantir本体论对标分析](../docs/智链OS-Palantir本体论对标分析.md)
- [任务清单（todo.md）](./todo.md)
- [TODO 清理计划](../apps/api-gateway/TODO_CLEANUP_PLAN.md)
