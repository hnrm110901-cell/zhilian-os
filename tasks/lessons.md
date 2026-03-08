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

---

## SQL 安全

### L010 — INTERVAL 字符串内不能嵌入 SQLAlchemy 参数
**问题**：`INTERVAL ':weeks weeks'` 中的 `:weeks` 是 SQL 字符串字面量的一部分，SQLAlchemy **不会**将其替换为绑定参数，查询执行时会报 `invalid input syntax for type interval`，或静默忽略导致回溯范围逻辑失效。
**相同问题已在两处出现**：`private_domain/agent.py`（:days）、`schedule/agent.py`（:weeks）。
**规则**：INTERVAL 乘法必须写成 `(:n * INTERVAL '1 day')` 或 `(:n * INTERVAL '1 week')`，将数值作为独立参数绑定，而不是嵌入字符串内。

### L011 — 动态 SQL 的 f-string 与字符串拼接的界定
**问题**：用 `text(f"SELECT ... WHERE {where} ...")` 构建查询，即使 `where` 仅由代码常量（非用户输入）组成，也违反"绝不在 text() 中用 f-string"的宪法规则，且难以被代码审查者快速验证安全性。
**规则**：
- **条件数量固定（≤4种组合）**：写多个独立 `text()` 分支，用 `if/else` 选择，无 f-string。
- **条件数量可变（如 WHERE IN）**：用 `bindparam("ids", expanding=True)` + `IN :ids`，无需 f-string。
- **表名/列名必须动态（如全表备份）**：用正则 `^[a-z][a-z0-9_]*$` 白名单校验后再拼入，并在注释中写明"表名无法参数化，已通过白名单验证"。

### L012 — 方法重命名后测试文件必须同步更新
**问题**：将 `_generate_mock_feedbacks` 重命名为 `_fetch_feedbacks_from_db` 后，`service/tests/test_agent.py` 中仍调用旧名称，导致测试运行时报 `AttributeError`。
**规则**：重命名方法时，用 `grep -r "old_method_name" packages/ apps/` 找到所有调用点（包括测试），一并更新。

### L013 — JSON 消息体禁止字符串拼接
**问题**：`'{"text":"' + content + '"}'` 或 `f'{{"text":"{content}"}}'` 在 `content` 含双引号、反斜杠或换行时会生成非法 JSON，导致消息发送失败（飞书/企微返回 400）。
**规则**：所有 JSON 消息体必须用 `json.dumps({"key": value})` 构造，禁止字符串拼接或 f-string 格式化。

### L014 — `except Exception: pass` 等同于删除错误记录
**问题**：`except Exception: pass` 让异常彻底无声失败，线上无法追踪（如企微通知、Neo4j 同步失败时完全无日志）。
**规则**：即使是"不阻断主流程"的次要操作，也必须用 `logger.warning(...)` 或 `logger.debug(...)` 记录异常，只有 JSON 解码等语义上"尝试性"操作才允许静默 pass。

### L015 — 列表端点的 `total` 必须是真实总量
**问题**：`return {"items": rows, "total": len(rows)}` 在分页时 `total` 返回的是当前页行数，而非数据库总行数，前端无法计算总页数。
**规则**：分页接口必须单独执行 `SELECT COUNT(*) ...`（去掉 LIMIT/OFFSET），用其结果作为 `total`。

### L017 — _upgrade_priority 方向 bug（WeChatActionFSM）
**问题**：`_upgrade_priority` 用 `order[max(0, idx - 1)]` 向左移动，但 `order = [P3, P2, P1, P0]` 中 P0 在右侧（最高优先级）。导致 P2→P3（降级！）而非 P2→P1（升级）。
**规则**："优先级升级"应向列表中更高优先级的方向移动。`_upgrade_priority` 正确写法：`order[min(len(order)-1, idx+1)]`（向 P0 方向移动）。


**问题**：`os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/zhilian")` 在未配置环境变量时会静默使用弱默认密码，若意外部署至生产环境将造成数据泄露。
**规则**：必须配置的环境变量用 `os.environ["DATABASE_URL"]`（无默认值），启动时即刻崩溃并提示缺失配置，优于运行时出现意外行为。

### L018 — 后端 risk_level 与 api-contracts.md 不一致
**问题**：api-contracts.md 定义4级风险（low/medium/high/critical），前端 WorkforcePage.tsx 也实现了4级，但后端 `_risk_level()` 函数只返回3级（low/medium/high），≥0.7 应为 critical 却被标为 high。
导致前端 critical 分支永远不触发，高危员工被低报。
**规则**：修改前端类型定义或添加新枚举值时，必须同步检查并修复后端对应的分类函数（`_risk_level` / `classify_health` 等）。合约变更 → 前后端同步修改。
**正确分类**（对应 api-contracts.md）：
```python
def _risk_level(score: float) -> str:
    if score >= 0.7: return "critical"
    if score >= 0.5: return "high"
    if score >= 0.3: return "medium"
    return "low"
```
