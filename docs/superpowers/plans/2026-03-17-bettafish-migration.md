# BettaFish 系统能力迁移规划

> **日期**: 2026-03-17 | **状态**: 规划中 | **优先级**: 架构欠债 P2

-----

## 现状分析

BettaFish 是一个独立的 AI 能力系统，原用于社交媒体舆情研究（微博/小红书），包含情感分析、关键词优化、流程状态管理、重试机制等核心能力。当前项目中 **已完成 4 个模块的迁移**，均位于 `apps/api-gateway/src/` 下：

### 已迁移模块（4/N）

| 模块 | 源文件 | BettaFish 原版 | 屯象OS 改造 | 状态 |
|------|--------|---------------|------------|------|
| **SentimentAnalysisModel** | `services/customer_sentiment_service.py` | `WeiboMultilingualSentiment`（PyTorch + Transformers 本地模型） | LLM 替代 PyTorch，零额外依赖；批量处理 8 条/次；输出 `SentimentResult` → `DishSentimentSummary` | **已完成，已集成** |
| **DecisionFlowState** | `services/decision_flow_state.py` | `State` 数据类（report_structure / researches / final_report） | 改造为决策推送流程状态快照（scenario → top3 → narrative → push），Redis 24h 持久化 | **已完成，已集成** |
| **QueryOptimizer** | `services/query_optimizer.py` | `keyword_optimizer`（社交媒体舆情关键词优化） | 改造为餐饮运营域 RAG 查询优化器，输出 2-3 个语义变体 | **已完成，已集成** |
| **RetryHelper** | `utils/retry_helper.py` | BettaFish 重试机制 | 适配 async/structlog/httpx 环境，提供 4 套预设配置（LLM/WeChat/HTTP/DB） | **已完成，已集成** |

### 已有集成点

`CustomerSentimentService` 已被以下模块引用：

- **`dish_health_service.py`** — `enrich_with_sentiment()` 作为菜品健康评分第 5 维度（0-25 分制）
- **`dining_journey_service.py`** — 用餐旅程中的评论情感分析
- **`banquet_agent` API** — 宴会评论情感趋势（`get_review_sentiment_trend` / `get_review_sentiment_breakdown`）
- **`growth_handlers.py`**（private_domain Agent） — 会员增长分析中的情感分布统计

-----

## 能力清单

基于已迁移代码的注释和 BettaFish 原版对标关系，推断 BettaFish 系统的完整能力清单如下：

| # | 能力 | BettaFish 原版用途 | 屯象OS 对应需求 | 迁移状态 |
|---|------|-------------------|----------------|---------|
| 1 | **SentimentAnalysisModel** | 微博多语言情感分析（PyTorch 本地模型） | 顾客评论情感分析（美团/大众点评/外卖/WeCom） | 已完成 |
| 2 | **State Management** | 舆情研究全流程状态（Search/Research/State 三层） | 决策推送流程状态追踪（DecisionFlowState） | 已完成 |
| 3 | **Keyword Optimizer** | 社交媒体舆情关键词优化 | RAG 查询语义变体生成 | 已完成 |
| 4 | **Retry Mechanism** | 外部 API 调用重试 | LLM/WeChat/HTTP/DB 统一重试策略 | 已完成 |
| 5 | **Search 数据类** | 单次搜索的 query/url/content/score 记录 | DecisionRecord（单条决策的 title/action/saving/approved） | 已完成（融入 DecisionFlowState） |
| 6 | **Research 数据类** | 多次搜索聚合为一次研究 | 尚无直接对标，可用于知识采集流程 | 待评估 |
| 7 | **Report Generation** | report_structure → final_report 生成 | 业务报告生成模块（ReportEngine）可能复用 | 待评估 |
| 8 | **Batch Processing** | 批量处理社交媒体数据 | 已在 SentimentService 中实现（8 条/批） | 已完成（模式已复用） |
| 9 | **to_dict / from_dict 序列化** | Python 数据类序列化/反序列化 | 已在 DecisionFlowState 中复用 | 已完成 |

-----

## 优先级排序

### 已完成（无需额外工作）

1. **SentimentAnalysisModel** — 核心能力，已完成迁移并深度集成到 dish_health、dining_journey、banquet、private_domain 四个业务线
2. **State Management** — 已改造为 DecisionFlowState，支持 Redis 持久化
3. **Keyword Optimizer** — 已改造为 QueryOptimizer，服务 RAG 检索
4. **Retry Mechanism** — 已成为全项目基础设施，4 套预设配置覆盖所有场景

### 待评估（低优先级）

5. **Research 聚合模式** — 如果未来知识OS层需要多轮采集聚合，可参考 BettaFish Research 数据类设计
6. **Report Generation 模式** — 当前 ReportEngine 已独立开发，需评估是否有 BettaFish 报告生成逻辑可复用

-----

## Phase 1: SentimentAnalysisModel 迁移（已完成）

### 目标

将 BettaFish 的 `WeiboMultilingualSentiment`（PyTorch + Transformers 本地推理模型）迁移为屯象OS 的 `CustomerSentimentService`（LLM 驱动，零额外依赖）。

### 已实现的接口设计

```
CustomerSentimentService
├── analyze_and_aggregate(reviews) → Dict[dish_name, DishSentimentSummary]  # 主入口
├── analyze_batch(reviews) → List[SentimentResult]                          # 批量分析
└── aggregate_by_dish(results, reviews) → Dict[dish_name, DishSentimentSummary]  # 按菜品聚合
```

核心数据类：
- `CustomerReview` — 输入（text, source, dish_name, platform_rating, review_id）
- `SentimentResult` — 单条分析结果（sentiment, confidence, key_points, dish_mentions）
- `DishSentimentSummary` — 按菜品聚合摘要（屯象OS 新增，BettaFish 无此概念）

### 已实现的数据流

```
美团/点评/外卖/WeCom 评论
       ↓
  CustomerReview 列表
       ↓
  analyze_batch() → LLM 批量调用（8条/次）→ List[SentimentResult]
       ↓
  aggregate_by_dish() → Dict[dish_name, DishSentimentSummary]
       ↓
  dish_health_service.enrich_with_sentiment()  → 第5维评分注入
       ↓
  厨师长Agent: "鱼香肉丝 差评率↑23%，主要吐槽：偏咸、份量少"
```

### 与 BettaFish 原版的关键差异

| 维度 | BettaFish 原版 | 屯象OS 实现 |
|------|---------------|------------|
| 推理引擎 | PyTorch + Transformers 本地模型 | LLM API 调用（零依赖） |
| 输入源 | 微博/小红书 | 美团/大众点评/外卖/企业微信 |
| 输出粒度 | 单条 SentimentResult | 单条 + 菜品聚合（DishSentimentSummary） |
| 降级策略 | 无 | `SENTIMENT_ENABLED=false` 功能开关 + LLM 失败降级为 neutral |
| 批处理 | 逐条处理 | 8 条/批，平衡延迟与 token 成本 |
| 业务集成 | 独立系统 | 深度嵌入菜品健康评分（第5维，0-25分制） |

### 测试策略（已有）

- `test_dining_journey_service.py` — 覆盖 `_analyze_sentiment` 函数的正/负/中性场景
- `test_banquet_agent_phase27.py` — 覆盖宴会评论情感趋势
- `test_banquet_agent_phase37.py` — 覆盖评论情感分布

### 待补充测试

- [ ] `CustomerSentimentService` 单元测试（mock LLM，验证批量解析、降级、聚合逻辑）
- [ ] `enrich_with_sentiment` 纯函数测试（多菜品、缺失菜品、空输入边界）
- [ ] 集成测试：从 CustomerReview 到 health_record 全链路

-----

## Phase 2: 其他能力迁移

### 2.1 Research 聚合模式（优先级: 低 | 依赖: 知识OS层上线）

**BettaFish 原版**: Research 数据类将多次 Search 聚合为一次完整研究，记录研究主题、多次搜索结果、综合结论。

**屯象OS 潜在用途**: 知识OS层（`KnowledgeService`）的知识采集流程可能需要类似的多轮聚合能力。例如：一次"菜品调研"可能包含多次数据查询（销量、成本、评价、竞品），需要聚合为一份完整的调研报告。

**评估依据**: 等 KnowledgeService API 上线后，评估是否需要引入 Research 聚合模式。如果 KnowledgeService 的采集流程足够简单（单次查询即可），则无需迁移。

### 2.2 Report Generation 模式（优先级: 低 | 依赖: ReportEngine 完善）

**BettaFish 原版**: `report_structure → final_report`，支持结构化报告模板 + LLM 填充。

**屯象OS 现状**: 业务报告生成模块（ReportEngine）已独立开发，属于当前最高优先级任务之一。

**评估依据**: 如果 ReportEngine 当前实现中缺少"结构化模板 + 分段填充"的能力，可参考 BettaFish 的 report_structure 设计。否则无需额外迁移。

-----

## API 兼容层设计

当前无需设计 API 兼容层，原因如下：

1. **BettaFish 是内部系统**，不存在外部消费者依赖其 API
2. **已迁移模块均已做了领域适配**，接口设计完全面向屯象OS 业务场景（CustomerReview 而非 WeiboPost，DishSentimentSummary 而非通用 SentimentResult）
3. **全局单例模式**已统一：`customer_sentiment_service`、`query_optimizer` 作为模块级单例导出，与项目中其他 service 风格一致

如果未来需要同时保留 BettaFish 原版 API（例如有其他项目仍在使用），建议方案：

- 在 `packages/` 下创建 `bettafish-compat` 包
- 提供 `BettaFishSentimentAdapter`，将 BettaFish 原版接口映射到 `CustomerSentimentService`
- 通过环境变量 `BETTAFISH_COMPAT=true` 启用

-----

## 数据迁移

### 模型权重

BettaFish 原版使用 PyTorch + Transformers 本地模型（`WeiboMultilingualSentiment`）。屯象OS 实现已完全替换为 LLM API 调用，**无需迁移模型权重**。

优势：
- 零额外依赖（无 PyTorch/Transformers）
- 部署简化（无 GPU 需求）
- 模型能力随 LLM 升级自动提升

劣势：
- 每次调用有 LLM API 成本（通过 8 条/批缓解）
- 依赖网络连接（通过 `SENTIMENT_ENABLED=false` 降级开关缓解）

### 训练数据

如果 BettaFish 有餐饮评论的标注数据集（正/负/中性标签 + 关键词），可用于：

1. **LLM Prompt 优化** — 作为 few-shot 示例嵌入 `_SYSTEM_PROMPT`
2. **评估基准** — 用标注数据集验证 LLM 分析的准确率（目标: positive/negative 分类准确率 >= 90%）
3. **未来微调** — 如果成本压力增大，可考虑用标注数据微调小模型替代 LLM

### 历史分析结果

BettaFish 已有的情感分析历史结果无需迁移到屯象OS 数据库。原因：
- 数据源不同（微博/小红书 vs 美团/大众点评）
- 分析维度不同（通用情感 vs 菜品维度聚合）

-----

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| BettaFish 还有未识别的能力模块 | 迁移不完整 | 中 | 获取 BettaFish 完整代码库进行全面审计；当前文档基于已迁移代码的注释推断 |
| LLM 情感分析成本随评论量增长 | 运营成本上升 | 中 | 当前 8 条/批已做成本优化；未来可引入缓存（相似评论不重复分析）或切换小模型 |
| LLM 情感分析准确率不如专用模型 | 分析质量下降 | 低 | `temperature=0.1` 已提高确定性；可用标注数据集做定期基准测试 |
| `SENTIMENT_ENABLED=false` 关闭后菜品健康评分缺失第5维 | 评分不完整 | 低 | `dish_health_service` 已处理 `None` 情况，显示"暂无数据"，不阻塞其他 4 维 |
| QueryOptimizer 改写后语义偏移 | RAG 召回质量下降 | 低 | 已有降级逻辑：解析失败返回原始查询；`QUERY_OPTIMIZER_ENABLED=false` 可关闭 |
| DecisionFlowState Redis 过期丢失 | 历史决策记录不可查 | 低 | 当前 TTL 24h 满足"今日推送记录"需求；如需更长保留，可同步写入 PostgreSQL |

-----

## 总结

BettaFish 系统的核心能力迁移 **已基本完成**。4 个主要模块（SentimentAnalysis、FlowState、QueryOptimizer、RetryHelper）均已成功适配屯象OS 的餐饮运营域，并深度集成到现有业务流程中。

**后续行动项**（按优先级）：

1. **补充 CustomerSentimentService 单元测试**（Phase 1 遗留，建议近期完成）
2. **获取 BettaFish 完整代码库进行审计**（确认无遗漏能力模块）
3. **知识OS层上线后评估 Research 聚合模式**（Phase 2.1，非紧急）
4. **ReportEngine 完善后评估报告生成模式**（Phase 2.2，非紧急）
