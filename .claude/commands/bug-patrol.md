# /bug-patrol — 每日代码巡检与自动修复

每日美东时间 8:00（北京时间 21:00）自动执行，扫描昨日代码变更中的潜在 BUG 并修复。

用法：
- `/bug-patrol` — 执行完整巡检（昨日变更）
- `/bug-patrol 3` — 扫描最近 3 天的变更
- `/bug-patrol --file path/to/file.py` — 只扫描指定文件

## 执行流程

### Phase 1: 收集变更范围

```bash
# 获取昨日变更的所有文件
git log --since="yesterday 00:00" --until="today 00:00" --name-only --pretty=format: | sort -u | grep -v '^$'

# 如果昨日无变更，扫描最近一个工作日
git log -1 --format=%ci  # 最后一次提交时间
```

- 如果无变更：输出 "昨日无代码变更，巡检跳过" 并退出
- 变更文件 >30 个：使用子代理并行扫描

### Phase 2: 按优先级扫描（使用 Bug Patrol Agent 规范）

**P0 安全扫描**（必须全量扫描）：
1. SQL 注入 — grep 变更文件中的 `text(f"` / `.format(` / `+` 拼接
2. 硬编码密钥 — grep `password=` / `api_key=` / `secret=`（排除 env 引用）
3. INTERVAL 注入 — grep `INTERVAL` 在 f-string 中
4. XSS — grep `dangerouslySetInnerHTML` 在 tsx 文件中

**P1 正确性扫描**：
1. 未 await 异步 — 读变更的 py 文件，检查 async 调用
2. 金额单位 — 涉及金额的字段检查 分/元 转换
3. UUID 外键 — 新增 model 检查外键类型匹配
4. Import 错误 — 检查引用的模块/方法是否存在
5. 异常吞没 — grep `except.*pass` 无日志

**P2 质量扫描**：
1. 死代码 — 新增函数是否有调用者
2. TODO/FIXME — production 代码中残留
3. 离线降级缺失 — 新增查询功能无缓存

### Phase 3: 自动修复

**修复规则**：
- P0：立即修复，不等待确认
- P1：逐个修复，每个修复后跑相关测试
- P2：记录到 `tasks/todo.md`，不修复

**修复后验证**：
```bash
# 后端
cd apps/api-gateway && pytest tests/ -q --tb=short

# 如果涉及 agent 包
pytest packages/agents/{affected}/tests/ -v

# 前端（如果有 ts/tsx 变更）
cd apps/web && pnpm tsc --noEmit 2>&1 | head -20
```

### Phase 4: 生成报告 & 提交

1. 输出巡检报告到终端（格式见 Bug Patrol Agent 规范）
2. 追加记录到 `.claude/knowledge/bug-patrol-log.md`
3. 如有修复：
   ```
   git add <修复的文件>
   git commit -m "fix: 每日巡检修复 YYYY-MM-DD (XP0 + XP1)"
   ```
4. 如发现新 BUG 模式：追加到 `tasks/lessons.md`
5. P2 问题追加到 `tasks/todo.md`

### Phase 5: 趋势分析（每周一额外执行）

每周一的巡检额外输出：
- 本周 vs 上周：P0/P1/P2 数量对比
- 高频 BUG 模式 Top3
- 代码质量趋势（改善/持平/恶化）
- 建议重点关注的模块

## 与其他命令的协作

| 场景 | 触发 |
|------|------|
| 发现安全漏洞 | 自动调用 Security Agent 深度审计 |
| 发现性能问题 | 建议执行 `/review --perf` |
| 修复引入新测试失败 | 自动调用 Debugger Agent |
| 发现架构违规 | 记录并建议下次 `/review` 关注 |
