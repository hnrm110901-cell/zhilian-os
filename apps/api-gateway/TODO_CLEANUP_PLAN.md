# TODO 清理计划（收敛结果）
## 屯象OS - API Gateway

**状态**: 已完成  
**更新日期**: 2026-03-08

---

## 一、清理结果

- 历史计划中的 API 侧遗留 TODO 已全部处理完成。
- `apps/api-gateway/src/api` 与 `apps/api-gateway/src/services` 当前已无 `TODO` 注释。
- 对于明确延期到 2027Q3 的厨房视觉能力，已统一改用 `Roadmap(2027Q3)` 标记，不再计入遗留 TODO。

---

## 二、已完成项对照

- Week 2 业务调度：已实现（营收异常检测、日报生成、库存预警）。
- Week 4 语音与 Shokz 边缘集成：已实现（多语音提供商 + 边缘回调）。
- Week 5-6 向量库可替换嵌入模型：已实现（local/openai）。
- 原“永远删除”类低优先级 TODO：已完成清理或已落地实现。

---

## 三、后续维护规则

- 新增延期功能请使用 `Roadmap(YYYYQX)` 标记，不使用 `TODO`。
- 保持 `src/api` 和 `src/services` 目录无未分级 TODO。
