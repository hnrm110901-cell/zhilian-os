# /debug — 错误快速诊断与修复

当用户输入 `/debug <错误描述或堆栈>` 时，协调 Debugger + Tester + Architect 三个 Agent 完成诊断修复闭环。

用法：
- `/debug ImportError: cannot import name 'XxxAgent'`
- `/debug 品智接口 sign error`
- `/debug 前端白屏 /sm/home 页面`
- `/debug` — 自动读取最近日志中的错误

## 执行流程

### Phase 1: 错误收集（Debugger Agent 主导，30s）

1. **如有用户提供的错误信息**：直接解析
2. **如无**：自动收集
   ```bash
   # 后端错误
   docker logs api-gateway --tail 200 2>&1 | grep -B2 -A5 "Error\|Exception\|Traceback" | tail -50

   # 前端错误
   cat apps/web/src/**/*.log 2>/dev/null || echo "无前端日志"

   # 最近变更
   git log --oneline -5
   git diff --name-only HEAD~3
   ```

### Phase 2: 根因定位（Debugger Agent 主导，2min）

按 `.claude/agents/debugger.md` 的诊断流程：

1. 错误分类（数据库/POS/Agent/前端/...）
2. 定位关键文件和代码行
3. 读取相关代码（≤ 5 个文件）
4. 确定根因

输出：
```
根因：{一句话}
位置：{file}:{line}
证据：{代码片段或日志}
```

### Phase 3: 修复（Debugger Agent 执行）

1. 提出 3 个修复方案（A 保守 / B 推荐 / C 激进）
2. **默认执行 B 推荐方案**（除非用户指定）
3. 编辑代码修复
4. 检查是否需要同步修改（级联影响评估）

### Phase 4: 架构合规检查（Architect Agent）

按 `.claude/agents/architect.md` 验证修复：
- 修复是否破坏分层约束
- 修复是否引入新的多租户风险
- 修复是否需要 Alembic 迁移

### Phase 5: 测试验证（Tester Agent）

按 `.claude/agents/tester.md`：

1. 运行受影响的测试文件
   ```bash
   pytest tests/test_affected.py -v
   ```
2. 如无现有测试 → 为该 bug 新增回归测试
3. 确认无回归

### Phase 6: 输出诊断报告

```
# 错误诊断与修复报告

## 错误：{一句话标题}
## 严重程度：P0/P1/P2/P3
## 状态：已修复 ✅ / 需确认 ⚠️ / 无法修复 ❌

## 根因
{说明}

## 修复内容
| 文件 | 变更 | 说明 |
|------|------|------|
| xxx.py:42 | 修改 | 改用参数化查询 |

## 验证结果
- 单元测试：X passed, 0 failed
- 新增回归测试：test_xxx_regression
- 架构合规：通过

## 经验教训（已写入 tasks/lessons.md）
### LXXX — {标题}
**问题**：...
**规则**：...
```

**修复完成后自动将经验写入 `tasks/lessons.md`。**
