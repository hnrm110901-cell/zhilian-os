# Claude Code × Codex 协作分工方案

> 日期：2026-03-12
> 项目：智链OS（zhilian-os）
> 测试现状：3348 passed / 401 failed / 38 errors / 33 skipped（通过率 88%）

---

## 一、项目现状摘要

### 已完成的核心模块
| 层级 | 模块 | 状态 |
|------|------|------|
| 感知层 | 天财商龙适配器 + 6个POS适配器 | ✅ |
| 本体层 | 62个Model + 96个Alembic迁移 | ✅ |
| 推理层 | 11个Agent + 决策引擎 + NarrativeEngine | ✅ |
| 行动层 | 企微推送(4时间点) + FSM + 审批 | ✅ |
| 前端 | 10个MVP页面 + 4角色Layout + 设计系统 | ✅ |
| 人力管理 | Phase 8全3个月完成 | ✅ |

### 测试失败分类（401 failed + 38 errors）

| 类别 | 数量 | 典型文件 | 根因 |
|------|------|----------|------|
| Qdrant向量DB | ~10 | test_qdrant_compatibility.py | 无Qdrant服务 |
| 报表导出CSV | ~6 | test_report_export_service.py | 方法签名变更 |
| 调度器 | ~3 | test_scheduler.py | AttributeError |
| 服务质量 | ~6 | test_service_service.py | 接口重构未同步 |
| 语音集成 | ~7 | test_voice_*.py | mock路径错误 |
| Shokz | ~3 | test_shokz_service.py | 方法签名变更 |
| 培训服务 | ~1 | test_training_service.py | 接口变更 |
| 损耗守卫 | ~1 | test_waste_guard_service.py | 未知root_cause |
| 导入错误(errors) | 38 | test_batch_indexing_api等 | main.py导入链 |
| Prometheus | ~15 | test_prometheus_metrics.py | app fixture问题 |
| 其他service测试 | ~350 | 分布在180+文件 | 待逐一分析 |

---

## 二、协作原则

```
┌─────────────────────────────────────────────┐
│   Claude Code (Opus) = 架构师 + 修复者      │
│   Codex = 批量执行者 + 测试补全者            │
│                                             │
│   原则：Claude Code 诊断 → Codex 批量修      │
│         Codex 写代码 → Claude Code 审查      │
└─────────────────────────────────────────────┘
```

---

## 三、具体分工

### 🔧 任务A：测试修复（目标：通过率 88% → 95%+）

#### Claude Code 负责（需要上下文理解的）：
1. **导入链错误修复（38 errors）** — 修复 `src/main.py` 导入链，使依赖外部服务（Qdrant/voice）的模块做 lazy import
2. **service_service.py 接口重构对齐** — 理解重构意图，修复6个失败测试
3. **waste_guard_service unknown root_cause** — 需要理解业务逻辑
4. **scheduler AttributeError** — 需要理解 Celery Beat 配置变更

#### Codex 负责（可批量执行的）：
1. **voice_*.py mock路径批量修复（~7个测试）** — 模式统一：mock路径从旧模块改为新模块
2. **report_export_service CSV测试修复（~6个）** — 方法签名对齐
3. **shokz_service 测试修复（~3个）** — 方法签名对齐
4. **training_service 测试修复（~1个）** — 接口变更同步
5. **prometheus_metrics 测试修复（~15个）** — app fixture统一使用TestClient
6. **qdrant_compatibility 测试跳过标记（~10个）** — 加 `@pytest.mark.skipif` 无Qdrant服务时跳过

**给 Codex 的指令模板：**
```
在 zhilian-os/apps/api-gateway/ 目录下：

任务1：修复 tests/test_voice_integration.py 和 tests/test_voice_service.py
- 运行 pytest tests/test_voice_integration.py tests/test_voice_service.py -v --tb=short
- 根据错误信息修复 mock 路径（通常是 patch 路径从旧模块名改为当前实际模块路径）
- 确保所有测试通过

任务2：修复 tests/test_report_export_service.py
- 先读 src/services/report_export_service.py 了解当前方法签名
- 更新测试使其匹配当前签名
- 运行验证

任务3：为 tests/test_qdrant_compatibility.py 添加跳过条件
- 在文件顶部添加：
  import pytest
  qdrant_available = pytest.importorskip("qdrant_client", reason="Qdrant not available")
- 或者用 @pytest.mark.skipif 标记需要 Qdrant 服务的测试

任务4：修复 tests/test_prometheus_metrics.py
- 测试需要使用 TestClient(app) 但 app 导入可能失败
- 确保使用环境变量：DATABASE_URL/REDIS_URL/SECRET_KEY/JWT_SECRET

任务5：修复 tests/test_shokz_service.py 和 tests/test_training_service.py
- 读取对应 service 文件了解当前接口
- 修复测试中的方法调用使其匹配

每个任务完成后运行 pytest 验证。
提交信息格式：fix(tests): 修复{模块名}测试 — {N}个测试恢复通过
```

---

### 🏗️ 任务B：未完成功能开发

#### Claude Code 负责：
1. **BFF聚合层实现** — `GET /api/v1/bff/{role}/{store_id}`（4个角色首屏数据聚合）
2. **前端角色路由落地** — `/sm/`, `/chef/`, `/floor/`, `/hq/` 四个角色入口
3. **Agent协作优化器** — `agent_collaboration_optimizer.py` 需要numpy，当前有import但功能未验证

#### Codex 负责：
1. **前端 TypeScript 测试补全** — 当前只有3个前端测试，补充核心组件测试
2. **API 端点 OpenAPI 文档** — 为28个MVP端点补充 response_model 和 description
3. **CSS Module 规范化** — 检查所有页面是否使用了 CSS Module（禁止内联样式）

---

### 📊 任务C：POC交付支持

#### Claude Code 负责：
1. **BOM数据导入脚本** — 从Excel导入徐记海鲜实际BOM数据到数据库
2. **天财商龙对接调试** — 真实POS接口联调
3. **企微推送模板微调** — 根据徐记海鲜实际需求调整卡片格式

#### Codex 负责：
1. **种子数据脚本** — 生成徐记海鲜5家门店的模拟运营数据（30天）
2. **健康检查脚本** — `scripts/health_check.py` 验证所有服务连通性
3. **部署脚本优化** — docker-compose 一键启动所有服务

---

## 四、协作工作流

```
时间线：
═══════════════════════════════════════════════
Week 1（3/12-3/16）：测试修复冲刺
  Claude Code：修复38个import errors + service重构对齐
  Codex：批量修复voice/report/prometheus/qdrant测试
  目标：通过率 → 95%

Week 2（3/17-3/21）：BFF + 角色路由
  Claude Code：BFF聚合层 + 角色路由架构
  Codex：前端测试补全 + OpenAPI文档
  目标：4个角色首屏可访问

Week 3（3/22-3/26）：POC数据准备
  Claude Code：BOM导入 + POS联调
  Codex：种子数据 + 部署脚本
  目标：徐记海鲜五一广场店可演示
═══════════════════════════════════════════════
```

---

## 五、代码同步规则

1. **分支策略**：
   - Claude Code → `claude/` 前缀分支
   - Codex → `codex/` 前缀分支
   - 都 PR 到 `develop`，互相 review

2. **避免冲突**：
   - Claude Code 不动 `tests/test_voice_*.py`、`tests/test_prometheus_*.py`
   - Codex 不动 `src/services/`、`src/api/`（业务逻辑层）
   - 共同区域（`tests/conftest.py`、`src/main.py`）由 Claude Code 统一管理

3. **验收标准**：
   - 每个 PR 必须附 pytest 运行结果
   - 新代码必须有测试（Rule：标记完成前问"一个高级工程师会批准这个吗？"）
   - 不引入新的 TODO/FIXME（宪法条款）

---

## 六、立即可给 Codex 的第一条指令

```
检查 zhilian-os 项目，在 apps/api-gateway/ 目录下执行以下测试修复任务：

环境准备：
- 设置环境变量：DATABASE_URL=sqlite+aiosqlite:///test.db REDIS_URL=redis://localhost:6379 SECRET_KEY=test JWT_SECRET=test
- 安装依赖：pip install -r requirements.txt

任务（按优先级）：

1. 修复 tests/test_voice_integration.py 和 tests/test_voice_service.py（~10个失败测试）
   - 先读源码：src/services/voice_service.py, src/services/voice_orchestrator.py
   - 修复mock路径和方法签名

2. 修复 tests/test_report_export_service.py（~6个失败测试）
   - 先读源码：src/services/report_export_service.py
   - 对齐方法签名和返回值结构

3. 修复 tests/test_service_service.py（~6个失败测试）
   - 先读源码：src/services/quality_service.py
   - 对齐接口变更

4. 为 tests/test_qdrant_compatibility.py 添加跳过条件（无Qdrant服务时skip）

5. 修复 tests/test_shokz_service.py（~3个失败测试）

每修复一组，运行 pytest 验证后提交。
分支：codex/fix-tests-batch1
提交信息格式：fix(tests): {描述}
```
