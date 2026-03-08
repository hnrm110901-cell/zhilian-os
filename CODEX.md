# CODEX.md — Codex 协作接入说明

## 接入步骤
1. 阅读本文件与 `CLAUDE.md`，确认开发宪法与协作规则。
2. 阅读 `tasks/collab-sync.md`，优先处理 `P0`，再处理 `P1/P2`。
3. 执行 `git pull --ff-only origin main`，确保与 Claude 最新提交对齐。
4. 选取明确任务实现，提交后更新 `tasks/collab-sync.md` 的 `[Codex]` 状态块。

## 协作约定
- 不改动与当前任务无关的文件。
- 每次提交必须包含：变更范围、验证命令、结果。
- 优先前端任务，后端仅做配套接口或兼容修复。
- 与 Claude 通过 git commit message + `tasks/collab-sync.md` 保持异步握手。

## 提交模板
```
type(scope): summary

[Codex]
- scope:
- verify:
- next:
```
