# 屯象OS AI模型调用位置清单

> 生成时间: 2026-03-27
> 目的: 统一迁移至 `ModelRouter`（`apps/api-gateway/src/core/model_router.py`）

---

## 统一层（已封装，迁移基座）

| 文件 | 用途 | 模型 | 备注 |
|------|------|------|------|
| `apps/api-gateway/src/core/llm.py` | LLM 工厂 + 全局单例（AnthropicClient / OpenAIClient） | 所有模型 | **ModelRouter 的下层，不需迁移，需与 ModelRouter 集成** |
| `apps/api-gateway/src/agents/llm_agent.py` | Agent 基类，通过 `get_llm_client()` 调用 | 配置决定 | 已走统一层，后续接入 ModelRouter 做任务路由 |
| `apps/api-gateway/src/utils/retry_helper.py` | 重试装饰器，捕获 anthropic/openai 异常 | - | 基础设施，不需迁移 |

## 优先级 P0 — 直接绕过统一层调用 Anthropic API

| 文件 | 行号 | 用途 | 当前模型 | 迁移方案 |
|------|------|------|---------|---------|
| `apps/api-gateway/src/services/onboarding_pipeline_service.py` | L297-324 | 品牌知识摘要生成 | `claude-haiku-4-5-20251001`（硬编码） | 改用 `get_llm_client()` + ModelRouter 路由 `knowledge_summary` 任务 |

## 优先级 P1 — 通过统一层但模型选择硬编码

| 文件 | 行号 | 用途 | 当前模型 | 迁移方案 |
|------|------|------|---------|---------|
| `apps/api-gateway/src/services/journey_narrator.py` | L155-163 | 旅程叙事消息生成 | `AnthropicClient(model=CLAUDE_HAIKU)` 硬编码 | 改用 ModelRouter.get_model("journey_message") |
| `apps/api-gateway/src/services/hr_ai_decision_service.py` | L436-468 | 单员工离职风险分析 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 `turnover_risk_analysis` |
| `apps/api-gateway/src/services/hr_ai_decision_service.py` | L470-500+ | 门店级风险扫描 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 `store_risk_scan` |
| `apps/api-gateway/src/services/hr_ai_decision_service.py` | L714+ | 薪资竞争力分析 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 `salary_competitiveness` |
| `apps/api-gateway/src/services/decision_flywheel_service.py` | L535 | 校准洞察生成 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 `calibration_insight` |
| `apps/api-gateway/src/services/hr_growth_agent_service.py` | L319+ | 个性化成长计划 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 `growth_plan_generation` |
| `apps/api-gateway/src/services/hr_report_engine.py` | L385+ | 人事工作总结 AI 生成 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 `hr_report_generation` |
| `apps/api-gateway/src/services/smart_schedule_service.py` | L921+ | 门店人力成本效率分析 | `get_llm_client()` 默认模型 | 添加 ModelRouter 路由 |
| `apps/api-gateway/src/services/llm_cypher_service.py` | L105-180 | 自然语言转 Cypher 查询 | OpenAI GPT-4（硬编码） | 改用 ModelRouter 路由 `cypher_generation` |

## 优先级 P2 — 独立 Agent 包内的调用

| 文件 | 行号 | 用途 | 当前模型 | 迁移方案 |
|------|------|------|---------|---------|
| `packages/agents/supplier/src/agent.py` | L38-58 | 供应商 AI 洞察 | `get_llm_client()` 默认模型 | 接入 ModelRouter 路由 `supplier_insight` |
| `packages/agents/people_agent/src/agent.py` | L37 | 人事 Agent LLM 调用 | `LLM_PROVIDER` 环境变量 | 接入 ModelRouter |
| `packages/agents/business_intel/src/agent.py` | L38 | 商业智能洞察生成 | `get_llm_client()` | 接入 ModelRouter |
| `packages/agents/ops_flow/src/agent.py` | L35 | 运营流程 Agent | `LLM_ENABLED` 环境变量 | 接入 ModelRouter |

## 优先级 P3 — Agent 基类下的批量受益

以下 Agent 继承 `LLMEnhancedAgent`，统一走 `llm_agent.py` → `get_llm_client()`。
一旦 `LLMEnhancedAgent` 接入 ModelRouter，这些 Agent 自动受益：

| Agent | 文件 |
|-------|------|
| PerformanceAgent | `apps/api-gateway/src/agents/performance_agent.py` |
| OpsAgent | `apps/api-gateway/src/agents/ops_agent.py` |
| InventoryAgent | `apps/api-gateway/src/agents/inventory_agent.py` |
| OrderAgent | `apps/api-gateway/src/agents/order_agent.py` |
| KPIAgent | `apps/api-gateway/src/agents/kpi_agent.py` |
| DecisionAgent | `apps/api-gateway/src/agents/decision_agent.py` |
| ScheduleAgent | `apps/api-gateway/src/agents/schedule_agent.py` |

## 辅助调用（嵌入/向量化，非 LLM 生成）

| 文件 | 用途 | 备注 |
|------|------|------|
| `apps/api-gateway/src/services/vector_db_service_enhanced.py` | OpenAI embedding API 降级 | 嵌入模型，不走 ModelRouter |

---

## 迁移策略

1. **Phase 1（当前）**: 创建 `ModelRouter` 基础设施，不修改现有代码
2. **Phase 2**: 迁移 P0（直接绕过统一层的调用）
3. **Phase 3**: 在 `LLMEnhancedAgent` 基类中集成 ModelRouter，P3 自动受益
4. **Phase 4**: 逐个迁移 P1 服务层调用
5. **Phase 5**: 迁移 P2 独立 Agent 包

## 配置兼容性

ModelRouter 与现有 `config.py` 中的 AI 配置完全兼容：

| 配置项 | 当前值 | ModelRouter 关系 |
|--------|--------|-----------------|
| `LLM_PROVIDER` | `deepseek` | ModelRouter 路由模型 ID，实际调用仍由 LLMFactory 决定 provider |
| `LLM_MODEL` | `deepseek-chat` | ModelRouter 建议模型，调用方可结合 LLM_MODEL 做降级 |
| `LLM_ENABLED` | `True` | ModelRouter 不检查此开关，由调用方（Agent/Service）自行检查 |
| `ANTHROPIC_API_KEY` | 环境变量 | 由 `core/llm.py` AnthropicClient 读取，ModelRouter 不涉及 |
