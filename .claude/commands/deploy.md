# /deploy — 部署就绪性全量检查

当用户输入 `/deploy` 时，协调 Security + DevOps + Tester + Performance 四个 Agent 完成部署前全量验证。

可选参数：
- `/deploy` — 完整检查（全部 4 个 Agent）
- `/deploy quick` — 快速检查（只跑 DevOps + Tester）
- `/deploy --env staging` — 指定目标环境

## 执行流程

### Phase 1: 变更盘点（2 min）

```bash
# 与 main 分支的差异
git diff main --stat
git log main..HEAD --oneline
```

输出：变更文件数、新增/删除行数、涉及模块摘要。

### Phase 2: 安全审计（Security Agent）

按 `.claude/agents/security.md` 执行：

1. 扫描 SQL 注入风险（所有 `text(` 调用）
2. 检查敏感数据泄露（日志/API 响应）
3. 验证环境变量配置（无硬编码 Token）
4. 运行 `pip audit`（Python 依赖漏洞）

**阻塞条件**：发现 🔴 严重级别问题则暂停部署。

### Phase 3: 测试验证（Tester Agent）

按 `.claude/agents/tester.md` 执行：

1. 运行后端测试：
   ```bash
   cd apps/api-gateway && pytest tests/ -q --tb=short
   ```
2. 运行变更涉及的 Agent 包测试（独立运行）
3. 检查测试覆盖率
4. 报告失败和覆盖盲区

**阻塞条件**：核心测试失败则暂停部署。

### Phase 4: 性能检查（Performance Agent）

按 `.claude/agents/performance.md` 执行：

1. N+1 查询扫描
2. 缓存策略检查
3. 前端 Bundle 大小检查（如有前端变更）

**非阻塞**：性能问题记录为 WARNING，不阻塞部署。

### Phase 5: 部署检查（DevOps Agent）

按 `.claude/agents/devops.md` 执行：

1. 数据库迁移状态（`alembic heads` / `alembic current`）
2. 依赖完整性（lock 文件一致）
3. Docker 构建验证
4. 环境变量完整性
5. 回滚方案确认

### Phase 6: 输出综合报告

```
# 部署就绪性报告

## 目标环境：[dev / staging / production]
## 检查时间：YYYY-MM-DD HH:mm
## 变更摘要：X 文件，+XX/-XX 行

## 检查结果

| Agent | 状态 | BLOCKER | WARNING | 详情 |
|-------|------|---------|---------|------|
| Security | ✅/❌ | 0 | 2 | 无 SQL 注入，2 处日志建议 |
| Tester | ✅/❌ | 0 | 1 | 45 passed, 0 failed |
| Performance | ✅/⚠️ | 0 | 3 | 3 处缓存建议 |
| DevOps | ✅/❌ | 0 | 0 | 迁移最新，Docker OK |

## 总评：[可以部署 ✅ / 修复后重检 ❌]

## 阻塞项（必须修复）
1. ...

## 建议项（非阻塞）
1. ...

## 回滚方案
- 当前版本：git rev xxx
- 回滚命令：...
```

**只有 BLOCKER = 0 时才建议部署。**
