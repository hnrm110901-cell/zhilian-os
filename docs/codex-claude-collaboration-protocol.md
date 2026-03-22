# Codex × Claude 协同开发协议（屯象OS）

更新时间：2026-03-08

## 1. 分工边界
- Codex（我）
  - 负责后端核心可执行闭环：`apps/api-gateway/src/services/fct_service.py` 与对应测试。
  - 每次迭代必须包含：实现 + 回归测试 + commit + push。
  - 维护“已完成任务清单”和“下一优先任务”。
- Claude
  - 负责并行支持：接口文档对齐、前端/集成调用适配、联调脚本、异常用例补充。
  - 接收 Codex 的最新 commit，基于最新 `main` 做联调与补充 PR。

## 2. 实时同步节奏
- 同步频率：每完成一个闭环（功能+测试）立即同步一次。
- 同步载体：本文件 + git commit message。
- 同步格式（固定）：
  - `Scope`: 本次改动范围
  - `Files`: 关键文件
  - `Tests`: 执行命令与结果
  - `Commit`: 提交号
  - `Next`: 下一任务

## 3. 冲突与互助规则
- 规则1：二人禁止同时改同一函数块；按模块切片并行。
- 规则2：若发生冲突，优先保留“测试覆盖更完整”的版本。
- 规则3：所有行为变化必须落测试；没有测试的改动不进入主干。
- 规则4：遇到阻塞（模型缺失、迁移缺失、契约不清）立即写入同步记录并交由另一方补位。

## 4. 当前握手状态（已生效）
- Codex 已连续完成并推送 FCT 多轮闭环开发（预算/凭证/税务发票/07:00 调度配置等）。
- Claude 可基于最新 `origin/main` 直接开展：
  - API 文档示例更新（预算控制、发票关联、备用金主档与明细）
  - 前端工作台接口联调
  - 端到端回归脚本

## 5. 本轮实时同步记录
- Scope: 备用金主档与明细从占位切换为真实持久化实现。
- Files:
  - `apps/api-gateway/src/models/fct.py`
  - `apps/api-gateway/src/models/__init__.py`
  - `apps/api-gateway/src/services/fct_service.py`
  - `apps/api-gateway/tests/test_fct_service.py`
- Tests:
  - `python3 -m pytest -q tests/test_fct_service.py -k "PettyCashPlaceholders"` -> passed
  - `python3 -m pytest -q tests/test_fct_service.py` -> passed
- Commit: 待提交（本地已完成代码与测试）
- Next:
  1. 提交并推送本轮备用金持久化改造。
  2. 继续补齐 `fct_service` 剩余占位接口（审批记录持久化优先）。
