# 经验教训

> 每次用户纠正或发现问题后更新。目标：同类错误不再重犯。

---

## Python / 测试

### L001 — sys.path 污染（多 agent 同时运行）
**问题**：多个 agent 的 `src/agent.py` 都向 `sys.path` 插入自己的路径，pytest 同时收集时互相覆盖，导致 `ImportError: cannot import name 'XxxAgent' from 'src.agent'`。
**规则**：package agent 测试必须独立运行，不能合并到一个 pytest 命令。CI 中每个 agent 单独一个 job。

### L002 — pydantic_settings 在 import 时校验环境变量
**问题**：`apps/api-gateway` 的 agent 使用 pydantic_settings，import 时就触发校验，缺少 `DATABASE_URL` 等变量会直接报 `ValidationError`。
**规则**：api-gateway agent 测试文件顶部必须先 `os.environ` 设置默认值，再 import src 模块。

### L003 — 无状态 Agent 方法需调用方传入数据
**问题**：OrderAgent 重构为无状态设计后，`calculate_bill`、`get_order`、`cancel_order` 等方法都需要调用方从 DB 查询后传入 `order` 参数，旧测试直接调用不传参导致 TypeError 或返回失败。
**规则**：无状态 Agent 的测试必须构造并传入所需的数据对象，不能依赖 Agent 内部状态。

### L004 — 空数据时返回空结构而非抛异常
**问题**：`monitor_service_quality`、`analyze_reservations`、`evaluate_training_effectiveness` 等方法在无数据时抛 `ValueError`，导致调用链上层全部失败。
**规则**：Agent 方法在无数据时应返回带默认值的空结构（`total: 0`、`[]` 等），只在参数非法时才抛异常。

### L005 — mock 数据方法应有样本数据兜底
**问题**：`_generate_mock_feedbacks` 改为 DB 优先后，无 DB 环境返回 `[]`，导致所有依赖反馈数据的测试（`total_feedbacks > 0`）失败。
**规则**：DB 优先方法在无 DB 时应返回少量样本数据（5-10条），保证测试在无 DB 环境可用。

### L006 — 除零保护
**问题**：`_calculate_cost_kpis` 中 `previous_cost / revenue_data.get("previous_revenue", 1)` — 当 key 存在但值为 0 时，`get` 返回 0 而非默认值 1，导致 ZeroDivisionError。
**规则**：所有除法运算必须显式判断分母 `> 0`，不能依赖 `dict.get` 的默认值来防零。

### L007 — 逻辑条件覆盖（LOW 状态不可达）
**问题**：`_analyze_inventory_status` 的 LOW 条件 `current <= safe * low_ratio` 在 `min_stock > safe * low_ratio` 时永远不可达，测试数据也未覆盖该分支。
**规则**：写条件分支时验证每个分支在测试数据下都可达；修复逻辑后同步修复测试数据。

---

## Git / 工作流

### L008 — 多 agent 测试不能合并到单个 pytest 命令
**问题**：见 L001。
**规则**：`git push` 前在各 agent 目录单独运行 `python3 -m pytest tests/test_agent.py -q`，全部通过再提交。

### L009 — 提交前排除自动生成文件
**问题**：`apps/api-gateway/.coverage` 和 `coverage.xml` 是自动生成文件，不应提交到版本库。
**规则**：确认 `.gitignore` 包含 `*.coverage`、`coverage.xml`、`.coverage`；提交时用具体文件名而非 `git add .`。
